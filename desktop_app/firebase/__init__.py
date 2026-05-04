"""Firebase REST integration for Dr Code desktop client.

The desktop never bundles the official Firebase SDK (it is heavy and
hard to package with PyInstaller). Instead we talk to Firebase Auth
and Firestore directly via their REST APIs using the API key from the
Firebase project's Web/Android client config.
"""
