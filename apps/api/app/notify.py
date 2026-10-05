"""Customer notification channels beyond the in-app log (spec 05, spec 13 AC-01..AC-04, AC-07, AC-08).

`Notifier` sends one message and raises `ChannelFailed` when it cannot; the api keeps the in-app log row either way
(AC-07). `HttpNotifier` talks to the Telegram Bot API and Resend over httpx with tokens from the environment
(`TELEGRAM_BOT_TOKEN`, `RESEND_API_KEY`, SSM in production, constitution #10); a channel without its token fails.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Protocol

import httpx


class ChannelFailed(Exception):
    """The provider refused or could not be reached."""


class Notifier(Protocol):
    def telegram(self, chat_id: str, text: str) -> Optional[str]:
        """Send to a Telegram chat; the provider's message id."""

    def email(self, to: str, subject: str, text: str) -> Optional[str]:
        """Send an e-mail; the provider's message id."""


class HttpNotifier:
    def __init__(self, *, telegram_token: Optional[str] = None, resend_key: Optional[str] = None,
                 sender: str = "Nick of Time <no-reply@nickoftime.example>",
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._tg, self._resend, self._from = telegram_token, resend_key, sender
        self._client = httpx.Client(timeout=10.0, transport=transport)

    @classmethod
    def from_env(cls) -> "HttpNotifier":
        return cls(telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"), resend_key=os.getenv("RESEND_API_KEY"),
                   sender=os.getenv("EMAIL_FROM", "Nick of Time <no-reply@nickoftime.example>"))

    def _post(self, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.post(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ChannelFailed(type(error).__name__) from None

    def telegram(self, chat_id: str, text: str) -> Optional[str]:
        if not self._tg:
            raise ChannelFailed("no Telegram token")
        body = self._post(f"https://api.telegram.org/bot{self._tg}/sendMessage", json={"chat_id": chat_id, "text": text})
        return str((body.get("result") or {}).get("message_id", "")) or None

    def email(self, to: str, subject: str, text: str) -> Optional[str]:
        if not self._resend:
            raise ChannelFailed("no Resend key")
        body = self._post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {self._resend}"},
                          json={"from": self._from, "to": [to], "subject": subject, "text": text})
        return body.get("id")


def mask_email(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain[:1]}***.{domain.rpartition('.')[2] or 'com'}"


def mask_chat(chat_id: str) -> str:
    return "•••" + str(chat_id)[-3:]
