"""Firebase project config — values copied from android/app/google-services.json.

These values identify the Firebase project itself; they are not
secrets (the same values ship inside any Android APK that uses the
project). Access control is enforced server-side by Firestore
security rules, not by hiding these constants.
"""

from __future__ import annotations

# Project: drcode-ai
FIREBASE_PROJECT_ID = "drcode-ai"
FIREBASE_API_KEY = "AIzaSyBzPKcYz4Y02JO51Bu1aQwg7--VdJfSr6M"

# REST endpoints
IDENTITY_BASE = "https://identitytoolkit.googleapis.com/v1"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    f"/databases/(default)/documents"
)

# Collections
CODES_COLLECTION = "codes"
DEVICES_COLLECTION = "devices"
BLOCKED_COLLECTION = "blocked_devices"

# How many bad-code attempts a single device may submit before it is
# permanently blocked. Tracked locally on the device and mirrored to
# Firestore on every failed attempt so the admin can see the trail.
MAX_BAD_ATTEMPTS = 5

# How long the desktop client may operate without an online check
# before forcing the user back to the activation screen. The user
# explicitly asked for "always online" so we use a tiny grace window
# (a few minutes) to absorb transient network blips, not anything
# that would let a determined user run the app offline.
ONLINE_GRACE_SECONDS = 60

# Heartbeat interval — every 60 seconds the running app re-verifies
# that its activation is still valid (code not revoked, device not
# blocked).
HEARTBEAT_SECONDS = 60
