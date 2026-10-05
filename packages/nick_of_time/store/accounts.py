"""Rows and rules of `sessions`, `policy_denials` and `customer_channels`, shared by every backend (spec 01 §6.5, T9).

- `sessions`: the api or the eval seed inserts a row under a store-made id and every tool reads it (spec 03 AC-02).
  The store has no update, so `mode` and `run_id` stay as created (AC-07, §6.8) [assumption]: OTP verification and
  preferences change the row through spec 05's accessor.
- `policy_denials` (AO): one row per DENY (spec 03 AC-12) with the actor's closed list (no `system`); a missing
  guardrail id becomes G-POL-01; a denial of a session carries that session's `run_id` (D-023).
- `customer_channels` (AO): the latest row of each channel (the one inserted last) wins. A Telegram `/start` writes
  `linked` with `telegram_linked` on the case (spec 13 AC-02); a typed e-mail writes `linked`, its confirmation link
  `confirmed` with `email_confirmed`. The store returns raw addresses; tools mask them (spec 03 AC-11).
The accessors take plain arguments and refuse bad ones with StoreError before any write, never with a pydantic error.
"""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Any, Literal, Optional, TypeVar, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

from nick_of_time import ids
from nick_of_time.contracts import Language, Mode

# [assumption] §6.7 fixes no shape for these two ids; they take ids.py's 12 upper-case hex characters.
DENIAL_ID, CHANNEL_ID = r"^PD-[0-9A-F]{12}$", r"^CH-[0-9A-F]{12}$"
DENIAL_ACTOR = r"^(agent|customer|analyst:.*\S.*)$"                  # §6.5: a closed list, no `system`
POLICY_ID, GUARDRAIL_ID = r"^POL-[A-Z0-9-]+$", r"^G-[A-Z]+-[0-9]{2}$"   # the policies.yaml shapes
RULE_ONLY_GUARDRAIL = "G-POL-01"
LinkedChannel = Literal["telegram", "email"]
ChannelEvent = Literal["linked", "confirmed", "revoked"]
# The case event written with a channel row (§6.5): a Telegram link, an e-mail confirmation; no other row writes one.
CHANNEL_CASE_EVENT: dict[tuple[str, str], str] = {("telegram", "linked"): "telegram_linked",
                                                  ("email", "confirmed"): "email_confirmed"}


def new_row_id(pattern: str) -> str:
    """A fresh id for DENIAL_ID or CHANNEL_ID: the prefix and 48 random bits."""
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


class SessionRecord(NewSession):
    session_id: str = Field(pattern=ids.PATTERN["session"])
    created_at: AwareDatetime


class NewDenial(_Row):
    """A DENY as its writer reports it; `session_id` is None for an api or analyst denial (D-023)."""
    trace_id: str = Field(min_length=1)
    session_id: Optional[str] = Field(None, pattern=ids.PATTERN["session"])
    actor: str = Field(pattern=DENIAL_ACTOR)
    policy_id: str = Field(pattern=POLICY_ID)
    guardrail_id: str = Field(RULE_ONLY_GUARDRAIL, pattern=GUARDRAIL_ID)
    detail: dict[str, Any] = Field(default_factory=dict)    # JSON only, as in jsonb
    run_id: Optional[str] = None                            # the session's, when there is one

    @field_validator("guardrail_id", mode="before")
    @classmethod
    def _a_rule_only_denial_cites_g_pol_01(cls, value: Optional[str]) -> str:
        return RULE_ONLY_GUARDRAIL if value is None else value


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
        customer sent `/start`) or a confirmed e-mail; a typed e-mail not yet confirmed or a revoked channel does not."""
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


def check_channel_event(latest: Optional[CustomerChannel], channel: Any, address: Any, event: Any) -> None:
    """A row may follow the channel's latest this way only: `linked` always (a new address replaces the old one);
    `confirmed` only on the `linked` address; `revoked` only on the address not yet revoked."""
    from nick_of_time.store import StoreError, check_text
    if channel not in get_args(LinkedChannel) or event not in get_args(ChannelEvent):
        raise StoreError(f"not a customer channel event: {channel!r} {event!r}")
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
