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
import time
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

    # Re-auth this many seconds before the cached idToken expires so
    # we never hand a stale token to a Firestore call.
    _TOKEN_REFRESH_SLACK_SECONDS = 5 * 60

    def __init__(self) -> None:
        self.state = ActivationState.load()
        self._session: Optional[AuthSession] = None
        # Epoch second the cached _session.id_token stops being valid.
        self._session_expires_at: float = 0.0

    # ------------------------------------------------------------ helpers
    def _ensure_session(self, *, force: bool = False) -> AuthSession:
        """Return a non-expired anonymous session, refreshing as needed.

        Anonymous Firebase idTokens last ~3600 s. Without proactive
        refresh the heartbeat would silently start hitting 401 after
        roughly an hour and stop enforcing activation.
        """
        now = time.time()
        if (
            force
            or self._session is None
            or now >= self._session_expires_at
        ):
            self._session = sign_in_anonymously()
            # Apply the slack *inside* the max() so an unusually short
            # ``expires_in`` (anything <= slack) doesn't push the
            # expiry into the past, which would force every Firestore
            # call to re-sign-in and spawn a fresh anonymous user.
            self._session_expires_at = now + max(
                60,
                self._session.expires_in - self._TOKEN_REFRESH_SLACK_SECONDS,
            )
        return self._session

    def _is_unauthorized(self, exc: FirebaseError) -> bool:
        # FirebaseError messages start with the HTTP status code, see
        # rest_client._post_json / _get_json.
        msg = str(exc)
        return msg.startswith("401") or msg.startswith("403")

    def _get_doc(self, path: str) -> Optional[dict]:
        """Get a Firestore doc, transparently re-authing on 401/403."""
        session = self._ensure_session()
        try:
            return get_document(path, id_token=session.id_token)
        except FirebaseError as e:
            if not self._is_unauthorized(e):
                raise
            session = self._ensure_session(force=True)
            return get_document(path, id_token=session.id_token)

    def _patch_doc(self, path: str, fields: dict, mask: list[str]) -> None:
        session = self._ensure_session()
        try:
            patch_document(
                path, fields, id_token=session.id_token, update_mask=mask
            )
            return
        except FirebaseError as e:
            if not self._is_unauthorized(e):
                raise
        session = self._ensure_session(force=True)
        patch_document(
            path, fields, id_token=session.id_token, update_mask=mask
        )

    def _normalize_code(self, raw: str) -> str:
        """Canonicalise a user-typed code to ``DRCD-XXXX-XXXX-XXXX``.

        Codes are stored in Firestore with the dashes embedded in the
        document id, so we must preserve them here. Strip whitespace,
        upper-case, and re-insert dashes between every 4 alphanumerics
        if the user typed the code without them.
        """
        cleaned = "".join(ch for ch in raw.upper() if ch.isalnum())
        if not cleaned:
            return ""
        # If they already typed DRCDXXXXXXXXXXXX (16 chars), re-insert
        # the dashes in the canonical positions.
        if cleaned.startswith("DRCD") and len(cleaned) >= 16:
            body = cleaned[4:16]
            return f"DRCD-{body[0:4]}-{body[4:8]}-{body[8:12]}"
        # Fallback: at least re-insert dashes every 4 chars so the
        # caller can match a longer/shorter format if you ever change
        # the code shape later.
        chunks = [cleaned[i : i + 4] for i in range(0, len(cleaned), 4)]
        return "-".join(chunks)

    # ------------------------------------------------------------ public
    def is_activated(self) -> bool:
        return self.state.status == "activated"

    def is_blocked(self) -> bool:
        return self.state.status == "blocked"

    def recheck_block(self) -> bool:
        """Re-query Firestore to see if the admin has cleared the block.

        Returns ``True`` if the device is *still* blocked, ``False`` if
        the admin has lifted the block (in which case the local state
        is reset to ``unactivated`` so the user can enter a new code).
        Network failures keep the local block in place so a
        disconnected device cannot bypass the lock.
        """
        try:
            doc = self._get_doc(
                f"{BLOCKED_COLLECTION}/{self.state.fingerprint}"
            )
        except FirebaseError:
            return True
        if doc is None or not doc.get("blocked"):
            self.state.status = "unactivated"
            self.state.code = ""
            self.state.bad_attempts = 0
            self.state.blocked_reason = ""
            self.state.save()
            return False
        return True

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
            doc = self._get_doc(f"{CODES_COLLECTION}/{code}")
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
            self._patch_doc(
                f"{CODES_COLLECTION}/{code}",
                {
                    "status": "active",
                    "device": self.state.fingerprint,
                    "device_label": device_label(),
                    "activated_at": doc.get("activated_at") or _now(),
                    "last_seen_at": _now(),
                },
                [
                    "status",
                    "device",
                    "device_label",
                    "activated_at",
                    "last_seen_at",
                ],
            )
            self._patch_doc(
                f"{DEVICES_COLLECTION}/{self.state.fingerprint}",
                {
                    "code": code,
                    "label": device_label(),
                    "last_seen_at": _now(),
                    "bad_attempts": 0,
                    "blocked": False,
                },
                [
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
            blocked = self._get_doc(
                f"{BLOCKED_COLLECTION}/{self.state.fingerprint}"
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
            doc = self._get_doc(f"{CODES_COLLECTION}/{self.state.code}")
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
        if status != "active":
            # Admin reset the code (status flipped back to "unused").
            # Treat the same as revoked from the client's perspective:
            # log out locally and force a fresh activation.
            self.state.status = "unactivated"
            self.state.code = ""
            self.state.save()
            return ActivationResult.INVALID_CODE
        if bound_device and bound_device != self.state.fingerprint:
            # Someone else stole our code somehow.
            self.state.status = "unactivated"
            self.state.save()
            return ActivationResult.USED_BY_OTHER_DEVICE

        try:
            self._patch_doc(
                f"{CODES_COLLECTION}/{self.state.code}",
                {"last_seen_at": _now()},
                ["last_seen_at"],
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
            self._patch_doc(
                f"{BLOCKED_COLLECTION}/{self.state.fingerprint}",
                {
                    "blocked": True,
                    "reason": reason,
                    "label": device_label(),
                    "blocked_at": _now(),
                    "bad_attempts": self.state.bad_attempts,
                },
                [
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
