"""Analyst authentication (spec 05 AC-07, ADR 0017): a Cognito JWT checked against the user pool's JWKS.

The api trusts only the signed token: signature (RS256), issuer, expiry and audience/client. The analyst's identity
(`sub`) is read from the token and nowhere else, so an action's `actor_id` cannot be forged by the request body.
Keys come from a JWKS the caller provides (tests, offline) or from the pool's `.well-known/jwks.json` (httpx, cached).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

import jwt


class AuthError(Exception):
    """The token is missing, malformed, unsigned by the pool, expired or for another app."""


class CognitoVerifier:
    def __init__(self, *, issuer: str, client_id: str, jwks: Optional[dict[str, Any]] = None,
                 fetch_jwks: Optional[Callable[[str], dict[str, Any]]] = None, jwks_ttl: float = 3600.0) -> None:
        self.issuer, self.client_id = issuer.rstrip("/"), client_id
        self._jwks, self._fetch, self._ttl, self._loaded = jwks, fetch_jwks, jwks_ttl, time.monotonic()

    @classmethod
    def from_env(cls) -> Optional["CognitoVerifier"]:
        """`COGNITO_USER_POOL_ID` and `COGNITO_CLIENT_ID` (spec 01 §6.9); the issuer is derived from the pool id and
        `AWS_REGION` (default us-east-2). None when unset, so analyst routes answer 401 to everyone."""
        pool, client_id = os.getenv("COGNITO_USER_POOL_ID"), os.getenv("COGNITO_CLIENT_ID")
        if not pool or not client_id:
            return None
        region = os.getenv("AWS_REGION", "us-east-2")
        return cls(issuer=f"https://cognito-idp.{region}.amazonaws.com/{pool}", client_id=client_id,
                   fetch_jwks=_http_jwks)

    def _keys(self, refresh: bool = False) -> dict[str, Any]:
        stale = self._fetch is not None and time.monotonic() - self._loaded > self._ttl
        if self._jwks is None or stale or refresh:
            if self._fetch is None:
                raise AuthError("no signing keys")
            self._jwks, self._loaded = self._fetch(f"{self.issuer}/.well-known/jwks.json"), time.monotonic()
        return self._jwks

    def _key_for(self, kid: Any) -> Optional[dict[str, Any]]:
        """The JWKS key of `kid`; an unknown kid refetches the set once (key rotation), then gives up."""
        find = lambda jwks: next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)   # noqa: E731
        found = find(self._keys())
        if found is None and self._fetch is not None and time.monotonic() - self._loaded > 10:
            found = find(self._keys(refresh=True))              # at most one refetch per 10 s: no fetch storm
        return found

    def verify(self, token: str) -> str:
        """The analyst's `sub` from a valid token, else AuthError (never a pydantic or jwt error to the caller)."""
        try:
            header = jwt.get_unverified_header(token)
            key = self._key_for(header.get("kid"))
            if key is None or header.get("alg") != "RS256":
                raise AuthError("unknown signing key")
            claims = jwt.decode(token, jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key)), algorithms=["RS256"],
                                issuer=self.issuer, options={"require": ["exp", "iss", "sub"], "verify_aud": False})
        except AuthError:
            raise
        except Exception as error:                                   # jwt.InvalidTokenError, bad key, network
            raise AuthError(type(error).__name__) from None
        # An id token carries `aud`, an access token `client_id`; either must be this app's.
        if self.client_id not in (claims.get("aud"), claims.get("client_id")):
            raise AuthError("another app's token")
        if claims.get("token_use") not in ("id", "access"):
            raise AuthError("not a Cognito token")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise AuthError("no subject")
        return sub


def _http_jwks(url: str) -> dict[str, Any]:
    import httpx
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    return response.json()
