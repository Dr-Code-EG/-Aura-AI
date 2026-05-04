"""High-level activation flow used by the desktop app.

States (kept on disk in ``~/.drcode/activation.json``):

  ``unactivated`` — first launch, no code entered yet
  ``activated``   — a valid code is bound to this device fingerprint
  ``blocked``     — too many wrong-code attempts; admin must unblock

Firestore documents this module reads / writes:

  /codes/{CODE}
      status        : "unused" | "active" | "revoked"
      device        : <fingerprint>          (set on activation)
      device_label  : <human-readable>       (set on activation)
      activated_at  : ISO timestamp
      last_seen_at  : ISO timestamp          (heartbeat)
      created_at    : ISO timestamp          (admin sets)
      created_by    : <admin uid>            (admin sets)

  /devices/{FINGERPRINT}
      code          : <CODE>
      label         : <human-readable>
      last_seen_at  : ISO timestamp
      bad_attempts  : integer
      blocked       : boolean
      blocked_at    : ISO timestamp          (set when blocked)
      blocked_reason: string                 (set when blocked)

The desktop client never has the privilege to *unblock* itself; the
admin must clear ``blocked`` from the Firestore console / admin app.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import (
    BLOCKED_COLLECTION,
    CODES_COLLECTION,
    DEVICES_COLLECTION,
    MAX_BAD_ATTEMPTS,
)
from .device_id import device_fingerprint, device_label
from .rest_client import (
    AuthSession,
    FirebaseError,
    get_document,
    patch_document,
    sign_in_anonymously,
)


def _now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def _state_path() -> Path:
    base = Path(os.path.expanduser("~/.drcode"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "activation.json"


@dataclass
class ActivationState:
    """Everything the app remembers locally about its activation."""

    status: str = "unactivated"   # unactivated | activated | blocked
    code: str = ""
    fingerprint: str = field(default_factory=device_fingerprint)
    bad_attempts: int = 0
    last_online_check: float = 0.0  # epoch seconds
    blocked_reason: str = ""

    @classmethod
    def load(cls) -> "ActivationState":
        path = _state_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            status=str(data.get("status", "unactivated")),
            code=str(data.get("code", "")),
            fingerprint=str(data.get("fingerprint", "") or device_fingerprint()),
            bad_attempts=int(data.get("bad_attempts", 0)),
            last_online_check=float(data.get("last_online_check", 0.0)),
            blocked_reason=str(data.get("blocked_reason", "")),
        )

    def save(self) -> None:
        _state_path().write_text(
            json.dumps(
                {
                    "status": self.status,
                    "code": self.code,
                    "fingerprint": self.fingerprint,
                    "bad_attempts": self.bad_attempts,
                    "last_online_check": self.last_online_check,
                    "blocked_reason": self.blocked_reason,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class ActivationResult:
    """Return value of :meth:`ActivationService.try_activate`."""

    OK = "ok"
    INVALID_CODE = "invalid_code"
    REVOKED = "revoked"
    USED_BY_OTHER_DEVICE = "used_by_other_device"
    DEVICE_BLOCKED = "device_blocked"
    NETWORK = "network"


class ActivationService:
    """Talks to Firebase to verify / claim an activation code."""

    def __init__(self) -> None:
        self.state = ActivationState.load()
        self._session: Optional[AuthSession] = None

    # ------------------------------------------------------------ helpers
    def _ensure_session(self) -> AuthSession:
        if self._session is None:
            self._session = sign_in_anonymously()
        return self._session

    def _normalize_code(self, raw: str) -> str:
        return "".join(ch for ch in raw.upper() if ch.isalnum())

    # ------------------------------------------------------------ public
    def is_activated(self) -> bool:
        return self.state.status == "activated"

    def is_blocked(self) -> bool:
        return self.state.status == "blocked"

    def try_activate(self, raw_code: str) -> str:
        """Attempt to claim ``raw_code`` for this device.

        Returns one of the ``ActivationResult.*`` values.
        """
        if self.is_blocked():
            return ActivationResult.DEVICE_BLOCKED

        code = self._normalize_code(raw_code)
        if len(code) < 8:
            return self._record_bad_attempt(ActivationResult.INVALID_CODE)

        try:
            session = self._ensure_session()
            doc = get_document(
                f"{CODES_COLLECTION}/{code}", id_token=session.id_token
            )
        except FirebaseError:
            return ActivationResult.NETWORK

        if doc is None:
            return self._record_bad_attempt(ActivationResult.INVALID_CODE)

        status = str(doc.get("status", "")) or "unused"
        bound_device = str(doc.get("device", ""))

        if status == "revoked":
            return self._record_bad_attempt(ActivationResult.REVOKED)
        if (
            status == "active"
            and bound_device
            and bound_device != self.state.fingerprint
        ):
            return self._record_bad_attempt(
                ActivationResult.USED_BY_OTHER_DEVICE
            )

        # Either unused, or already bound to *this* device. Claim/refresh.
        try:
            patch_document(
                f"{CODES_COLLECTION}/{code}",
                {
                    "status": "active",
                    "device": self.state.fingerprint,
                    "device_label": device_label(),
                    "activated_at": doc.get("activated_at") or _now(),
                    "last_seen_at": _now(),
                },
                id_token=session.id_token,
                update_mask=[
                    "status",
                    "device",
                    "device_label",
                    "activated_at",
                    "last_seen_at",
                ],
            )
            patch_document(
                f"{DEVICES_COLLECTION}/{self.state.fingerprint}",
                {
                    "code": code,
                    "label": device_label(),
                    "last_seen_at": _now(),
                    "bad_attempts": 0,
                    "blocked": False,
                },
                id_token=session.id_token,
                update_mask=[
                    "code",
                    "label",
                    "last_seen_at",
                    "bad_attempts",
                    "blocked",
                ],
            )
        except FirebaseError:
            return ActivationResult.NETWORK

        self.state.status = "activated"
        self.state.code = code
        self.state.bad_attempts = 0
        self.state.last_online_check = _dt.datetime.now().timestamp()
        self.state.save()
        return ActivationResult.OK

    def heartbeat(self) -> str:
        """Re-check that this device is still authorised.

        Returns one of ``ActivationResult.*``. ``OK`` means the code is
        still bound to this device and no admin revocation has fired.
        """
        if not self.is_activated():
            return ActivationResult.INVALID_CODE
        try:
            session = self._ensure_session()
            blocked = get_document(
                f"{BLOCKED_COLLECTION}/{self.state.fingerprint}",
                id_token=session.id_token,
            )
        except FirebaseError:
            return ActivationResult.NETWORK
        if blocked and blocked.get("blocked"):
            self.state.status = "blocked"
            self.state.blocked_reason = str(
                blocked.get("reason", "Blocked by administrator.")
            )
            self.state.save()
            return ActivationResult.DEVICE_BLOCKED

        try:
            doc = get_document(
                f"{CODES_COLLECTION}/{self.state.code}",
                id_token=session.id_token,
            )
        except FirebaseError:
            return ActivationResult.NETWORK
        if doc is None:
            self.state.status = "unactivated"
            self.state.code = ""
            self.state.save()
            return ActivationResult.INVALID_CODE
        status = str(doc.get("status", ""))
        bound_device = str(doc.get("device", ""))
        if status == "revoked":
            self.state.status = "unactivated"
            self.state.save()
            return ActivationResult.REVOKED
        if bound_device and bound_device != self.state.fingerprint:
            # Someone else stole our code somehow.
            self.state.status = "unactivated"
            self.state.save()
            return ActivationResult.USED_BY_OTHER_DEVICE

        try:
            patch_document(
                f"{CODES_COLLECTION}/{self.state.code}",
                {"last_seen_at": _now()},
                id_token=session.id_token,
                update_mask=["last_seen_at"],
            )
        except FirebaseError:
            # Heartbeat write failure shouldn't kick the user out, but
            # we DO want to return NETWORK so the caller can fall back
            # on the grace-period logic.
            return ActivationResult.NETWORK
        self.state.last_online_check = _dt.datetime.now().timestamp()
        self.state.save()
        return ActivationResult.OK

    # ----------------------------------------------------------- internals
    def _record_bad_attempt(self, result: str) -> str:
        self.state.bad_attempts += 1
        if self.state.bad_attempts >= MAX_BAD_ATTEMPTS:
            self.state.status = "blocked"
            self.state.blocked_reason = (
                "Too many invalid activation attempts on this device."
            )
            self._mark_blocked_remotely(self.state.blocked_reason)
        self.state.save()
        return (
            ActivationResult.DEVICE_BLOCKED
            if self.state.status == "blocked"
            else result
        )

    def _mark_blocked_remotely(self, reason: str) -> None:
        try:
            session = self._ensure_session()
            patch_document(
                f"{BLOCKED_COLLECTION}/{self.state.fingerprint}",
                {
                    "blocked": True,
                    "reason": reason,
                    "label": device_label(),
                    "blocked_at": _now(),
                    "bad_attempts": self.state.bad_attempts,
                },
                id_token=session.id_token,
                update_mask=[
                    "blocked",
                    "reason",
                    "label",
                    "blocked_at",
                    "bad_attempts",
                ],
            )
        except FirebaseError:
            # Network failure here doesn't change the local block — the
            # device stays locally locked until the admin clears it.
            pass
