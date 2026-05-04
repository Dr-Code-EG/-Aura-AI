"""Thin REST wrapper around Firebase Auth + Firestore.

Why REST instead of the Firebase Admin / Web SDK?
* The Web SDK is JavaScript-only.
* The Admin SDK requires a service-account JSON, which we cannot
  ship with the desktop client (would let any user write anything).
* The Identity Toolkit + Firestore REST APIs only need the project's
  public API key, and access control is enforced by Firestore
  security rules (see firestore.rules in the repo root).

The client signs in anonymously on first launch — that gives us an
``idToken`` that Firestore rules can check for ``request.auth != null``
without us having to manage user accounts on the desktop.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .config import FIREBASE_API_KEY, FIRESTORE_BASE, IDENTITY_BASE


class FirebaseError(RuntimeError):
    """Any non-success response from a Firebase REST call."""


@dataclass
class AuthSession:
    id_token: str
    refresh_token: str
    local_id: str
    expires_in: int  # seconds


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 10.0,
               headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        raise FirebaseError(f"{e.code} {err_body}") from e
    except urllib.error.URLError as e:
        raise FirebaseError(f"Network error: {e.reason}") from e


def _get_json(url: str, *, timeout: float = 10.0,
              headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        raise FirebaseError(f"{e.code} {err_body}") from e
    except urllib.error.URLError as e:
        raise FirebaseError(f"Network error: {e.reason}") from e


# --------------------------------------------------------------------- Auth

def sign_in_anonymously() -> AuthSession:
    """Issue a one-shot anonymous Firebase Auth idToken."""
    url = f"{IDENTITY_BASE}/accounts:signUp?key={FIREBASE_API_KEY}"
    data = _post_json(url, {"returnSecureToken": True})
    return AuthSession(
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        local_id=data["localId"],
        expires_in=int(data.get("expiresIn", 3600)),
    )


# --------------------------------------------------------- Firestore helpers

# Firestore stores values as typed wrappers ({"stringValue": "x"}, etc).
# The helpers below convert between Python values and that wire format.


def _to_value(v: Any) -> dict[str, Any]:
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_to_value(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _to_value(x) for k, x in v.items()}}}
    raise TypeError(f"Unsupported Firestore value type: {type(v)!r}")


def _from_value(v: dict[str, Any]) -> Any:
    if "nullValue" in v:
        return None
    if "booleanValue" in v:
        return v["booleanValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "stringValue" in v:
        return v["stringValue"]
    if "timestampValue" in v:
        return v["timestampValue"]
    if "arrayValue" in v:
        return [_from_value(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {
            k: _from_value(x)
            for k, x in v["mapValue"].get("fields", {}).items()
        }
    return None


def _document_to_dict(doc: dict[str, Any]) -> dict[str, Any]:
    fields = doc.get("fields", {}) or {}
    return {k: _from_value(v) for k, v in fields.items()}


# ---------------------------------------------------------------- Firestore

def get_document(path: str, *, id_token: str) -> Optional[dict[str, Any]]:
    """Read a Firestore document. Returns ``None`` when it does not exist."""
    url = f"{FIRESTORE_BASE}/{path}"
    try:
        raw = _get_json(url, headers={"Authorization": f"Bearer {id_token}"})
    except FirebaseError as e:
        if "404" in str(e):
            return None
        raise
    return _document_to_dict(raw)


def patch_document(path: str, fields: dict[str, Any], *, id_token: str,
                   update_mask: Optional[list[str]] = None) -> dict[str, Any]:
    """Create-or-update a Firestore document.

    If ``update_mask`` is given, only those field names are touched —
    anything else stays as it was on the server. Otherwise every field
    in ``fields`` is overwritten and any existing field not present is
    deleted.
    """
    url = f"{FIRESTORE_BASE}/{path}"
    if update_mask:
        params = "&".join(f"updateMask.fieldPaths={n}" for n in update_mask)
        url = f"{url}?{params}"
    payload = {
        "fields": {k: _to_value(v) for k, v in fields.items()},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {id_token}")
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return _document_to_dict(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = str(e)
        raise FirebaseError(f"{e.code} {err_body}") from e
    except urllib.error.URLError as e:
        raise FirebaseError(f"Network error: {e.reason}") from e
