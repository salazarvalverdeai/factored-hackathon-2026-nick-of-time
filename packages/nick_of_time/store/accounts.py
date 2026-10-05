"""Rows and rules of `sessions`, `policy_denials`, `customer_channels`, `idempotency` and `llm_calls`, shared by every
backend (spec 01 §6.5, T9).

- `sessions`: the api or the eval seed inserts a row under a store-made id and every tool reads it (spec 03 AC-02).
  The store has no update, so `mode` and `run_id` stay as created (AC-07, §6.8) [assumption]: OTP verification and
  preferences change the row through spec 05's accessor.
- `policy_denials` (AO): one row per DENY (spec 03 AC-12) with the actor's closed list (no `system`); a missing
  guardrail id becomes G-POL-01; a denial of a session carries that session's `run_id` (D-023).
- `customer_channels` (AO): the latest row of each channel (the one inserted last) wins. A Telegram `/start` writes
  `linked` with `telegram_linked` on the case (spec 13 AC-02); a typed e-mail writes `linked`, its confirmation link
  `confirmed` with `email_confirmed`. The store returns raw addresses; tools mask them (spec 03 AC-11).
- `llm_calls` (AO): one row per billed LLM call under a store-made `LC-` id, written from a run's usage; `run_id` has no
  default, so a caller passes `None` for production on purpose (D-023); `cost_usd` is a finite decimal in
  [0, 10^6] `[assumption]` with a scale Postgres `numeric` holds, and is never null (spec 01 §6.5, §10).
- `idempotency` (spec 03 AC-03, §6.3 Idempotency, §6.5): `once` runs a W or N tool's write at most once per key and returns
  the stored result afterwards; the row's key is `[run_id:]<scope>:<key>` with `<scope>` = `c=<customer_id>` or `-` (the api's
  analyst actions) [assumption: §6.5 names only the run prefix; the scope keeps one customer from replaying another's
  result]. The row keeps a hash of the call's arguments and a key replayed with other arguments or another action is
  refused [assumption], so a reused key never skips a different write. A refused write is not remembered.
The accessors take plain arguments and refuse bad ones with StoreError before any write, never with a pydantic error.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import hashlib
import json
import re
import secrets
from typing import Any, Literal, Optional, TypeVar, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

from nick_of_time import ids
from nick_of_time.contracts import Language, Mode

# [assumption] §6.7 fixes no shape for these three ids; they take ids.py's 12 upper-case hex characters.
DENIAL_ID, CHANNEL_ID, LLM_CALL_ID = r"^PD-[0-9A-F]{12}$", r"^CH-[0-9A-F]{12}$", r"^LC-[0-9A-F]{12}$"
DENIAL_ACTOR = r"^(agent|customer|analyst:.*\S.*)$"                  # §6.5: a closed list, no `system`
POLICY_ID, GUARDRAIL_ID = r"^POL-[A-Z0-9-]+$", r"^G-[A-Z]+-[0-9]{2}$"   # the policies.yaml shapes
RULE_ONLY_GUARDRAIL = "G-POL-01"
LinkedChannel = Literal["telegram", "email"]
ChannelEvent = Literal["linked", "confirmed", "revoked"]
# The case event written with a channel row (§6.5): a Telegram link, an e-mail confirmation; no other row writes one.
CHANNEL_CASE_EVENT: dict[tuple[str, str], str] = {("telegram", "linked"): "telegram_linked",
                                                  ("email", "confirmed"): "email_confirmed"}


def new_row_id(pattern: str) -> str:
    """A fresh id for DENIAL_ID, CHANNEL_ID or LLM_CALL_ID: the prefix and 48 random bits."""
    return pattern[1:pattern.index("[")] + secrets.token_hex(6).upper()


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


M = TypeVar("M", bound=_Row)


class NewSession(_Row):
    """A session as the api or the eval seed creates it; `customer_id` None is the seed's `none` session (§6.8)."""
    customer_id: Optional[str] = None
    otp_hash: str = Field(min_length=1)
    verified_at: Optional[AwareDatetime] = None
    expires_at: AwareDatetime                               # in the past for the seed's `expired` session
    language: Language
    mode: Mode                                              # fixed at creation (AC-07)
    display_currency: Optional[str] = None
    tool_faults: tuple[str, ...] = ()                       # set only by the eval seed (spec 03 AC-05)
    run_id: Optional[str] = None
    arm: Optional[str] = None
    display_name: Optional[str] = Field(None, min_length=1, max_length=40)   # a demo visitor's typed name (ADR 0026)


class SessionRecord(NewSession):
    session_id: str = Field(pattern=ids.PATTERN["session"])
    created_at: AwareDatetime


class NewDenial(_Row):
    """A DENY as its writer reports it; `session_id` is None for an api or analyst denial (D-023)."""
    trace_id: str = Field(min_length=1)
    session_id: Optional[str] = Field(None, pattern=ids.PATTERN["session"])
    actor: str
    policy_id: str = Field(pattern=POLICY_ID)
    guardrail_id: str = Field(RULE_ONLY_GUARDRAIL, pattern=GUARDRAIL_ID)
    detail: dict[str, Any] = Field(default_factory=dict)    # JSON only, as in jsonb
    run_id: Optional[str] = None                            # the session's, when there is one

    @field_validator("guardrail_id", mode="before")
    @classmethod
    def _a_rule_only_denial_cites_g_pol_01(cls, value: Optional[str]) -> str:
        return RULE_ONLY_GUARDRAIL if value is None else value

    @field_validator("actor")
    @classmethod
    def _a_closed_actor_list(cls, value: str) -> str:
        # Python's re, as the store's ACTOR: its \S is str.isspace()'s, which the schema CHECK spells out; pydantic's
        # `pattern` engine has another \S (it lets \x1c through) and would differ from Postgres.
        if re.fullmatch(DENIAL_ACTOR, value) is None:
            raise ValueError("not a denial actor (agent, customer or analyst:<sub>)")
        return value


class NewLLMCall(_Row):
    """One billed LLM call as the api writes it from a run's usage (spec 04 AC-14, spec 18 AC-10); `run_id` is the
    session's, so a run's tokens and cost sum alone (D-023). Counts are non-negative and `cost_usd` a finite decimal."""
    trace_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tokens_in: int = Field(ge=0, strict=True, le=2**31 - 1)               # Postgres integer
    tokens_out: int = Field(ge=0, strict=True, le=2**31 - 1)
    latency_ms: int = Field(ge=0, strict=True, le=2**31 - 1)
    cost_usd: Decimal = Field(ge=0, le=Decimal(10) ** 6, allow_inf_nan=False)   # per-call cap [assumption]
    run_id: Optional[str]                                   # no default: None (production) must be passed on purpose

    @field_validator("cost_usd")
    @classmethod
    def _cost_fits_numeric(cls, value: Decimal) -> Decimal:
        # Postgres `numeric` keeps at most 16383 digits after the point; memory must refuse what the column refuses.
        if value.as_tuple().exponent < -16383:
            raise ValueError("more decimal places than a Postgres numeric holds")
        return abs(value) if value.is_zero() else value       # -0 reads back as 0 from Postgres


class LLMCall(NewLLMCall):
    call_id: str = Field(pattern=LLM_CALL_ID)
    created_at: AwareDatetime


class Once(_Row):
    """What `once` returns: the write's JSON result, and whether it is the stored one from an earlier call."""
    result: dict[str, Any]
    replayed: bool


class PolicyDenial(NewDenial):
    denial_id: str = Field(pattern=DENIAL_ID)
    created_at: AwareDatetime


class CustomerChannel(_Row):
    channel_id: str = Field(pattern=CHANNEL_ID)
    customer_id: str
    channel: LinkedChannel
    address: str                                            # chat id or e-mail, never shown unmasked
    event: ChannelEvent
    created_at: AwareDatetime

    @property
    def confirmed(self) -> bool:
        """Spec 03 AC-21 [assumption]: a channel takes a summary while its latest row is a Telegram link (the
        customer sent `/start`; Telegram is never `confirmed`) or a confirmed e-mail; a typed e-mail not yet confirmed
        or a revoked channel does not."""
        return self.event == "confirmed" or (self.channel, self.event) == ("telegram", "linked")


# The checks below run before any write and raise the package's StoreError, imported when called because the package
# imports this module first.
def parse(model: type[M], fields: dict[str, Any]) -> M:
    """The row model of an accessor's arguments, else StoreError naming the bad fields (never their values); its text
    holds no NUL or lone surrogate. A `detail` goes through the store's `_json` as well."""
    from nick_of_time.store import StoreError, check_text
    try:
        row = model(**fields)
    except ValidationError as error:
        bad = sorted({".".join(map(str, e["loc"])) or model.__name__ for e in error.errors()})
        raise StoreError(f"not a valid {model.__name__}: {', '.join(bad)}") from None
    values = list(row.model_dump().values())
    check_text(*values, *(item for value in values if isinstance(value, tuple) for item in value))
    return row


def check_channel_event(current: list[CustomerChannel], channel: Any, address: Any, event: Any) -> None:
    """A row may follow the channel's latest (in `current`, the customer's `channels()`) this way only: `linked`
    always (a new address replaces the old one); `confirmed` only for an e-mail, on its `linked` address (a Telegram
    link needs no confirmation); `revoked` only on the address not yet revoked."""
    from nick_of_time.store import StoreError, check_text
    if (not isinstance(channel, str) or channel not in get_args(LinkedChannel) or not isinstance(event, str)
            or event not in get_args(ChannelEvent) or (channel, event) == ("telegram", "confirmed")):
        raise StoreError(f"not a customer channel event: {channel!r} {event!r}")
    latest = next((row for row in current if row.channel == channel), None)
    if not isinstance(address, str) or not address.strip():
        raise StoreError("a channel needs its address")
    check_text(address)
    if event == "confirmed" and (latest is None or latest.event != "linked" or latest.address != address):
        raise StoreError("only the linked address of the channel can be confirmed")
    if event == "revoked" and (latest is None or latest.event == "revoked" or latest.address != address):
        raise StoreError("only the channel's current address can be revoked")


def check_denial_session(denial: NewDenial, session: Optional[SessionRecord]) -> None:
    """A denial of a session names a known session and carries that session's run_id (D-023)."""
    from nick_of_time.store import StoreError
    if denial.session_id is not None and session is None:
        raise StoreError(f"unknown session {denial.session_id}")
    if session is not None and session.run_id != denial.run_id:
        raise StoreError(f"a denial of session {session.session_id} carries its run_id {session.run_id!r}")


def window_start(session: Optional[SessionRecord], session_id: str, since: Any) -> dt.datetime:
    """The start of a session's send window: the later of `since` and the session's start."""
    from nick_of_time.store import StoreError
    if session is None:
        raise StoreError(f"unknown session {session_id}")
    if not isinstance(since, dt.datetime) or since.tzinfo is None:
        raise StoreError(f"not an aware datetime: {since!r}")
    return max(since, session.created_at)


def check_key(value: Any) -> Any:
    """A lookup key that is a string holding no NUL or lone surrogate, else StoreError (Postgres cannot take it)."""
    from nick_of_time.store import StoreError, check_text
    if value is not None and not isinstance(value, str):
        raise StoreError(f"not a key: {value!r}")
    check_text(value)
    return value


def idempotency_key(key: Any, action: Any, customer_id: Any, run_id: Any) -> str:
    """The stored `idempotency.key` of a tool call (see the module docstring), else StoreError."""
    from nick_of_time.store import StoreError
    for name, value in (("key", key), ("action", action)):
        if not isinstance(value, str) or not value.strip():
            raise StoreError(f"an idempotent call needs its {name}")
    check_key(key), check_key(action), check_key(customer_id), check_key(run_id)
    if customer_id is not None and (not customer_id.strip() or ":" in customer_id):
        raise StoreError("not a customer id")
    if run_id is not None and not run_id:
        raise StoreError("not a run id")
    scope = "-" if customer_id is None else f"c={customer_id}"
    return (f"{run_id}:" if run_id is not None else "") + f"{scope}:{key}"


def arguments_hash(arguments: Any) -> str:
    """A hash of a call's arguments as canonical JSON (the store's `_json` rules), kept with the key."""
    from nick_of_time.store import _json
    return hashlib.sha256(json.dumps(_json(arguments), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_replay(stored: tuple[str, Optional[str], Optional[str]], action: str, run_id: Optional[str],
                 arguments: str) -> None:
    """A key that names another action, run or set of arguments is a bug in the caller: refused, not replayed."""
    from nick_of_time.store import StoreError
    if stored != (action, run_id, arguments):
        raise StoreError("this idempotency key was used for another action or with other arguments")


def json_object(value: Any) -> dict[str, Any]:
    """A tool's result as `jsonb` keeps it: a JSON object, else StoreError."""
    from nick_of_time.store import StoreError, _json
    copy = _json(value)
    if not isinstance(copy, dict):
        raise StoreError("an idempotent result is a JSON object")
    return copy
