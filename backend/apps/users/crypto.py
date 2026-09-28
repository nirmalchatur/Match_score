"""
Symmetric encryption for user-supplied third-party credentials.

Why this exists
---------------
Users paste their own Google AI Studio key into the UI so tailoring works.
A key like that is a long-lived bearer token: anyone holding it spends the
owner's quota, and Gemini's console only shows it once. Storing it in plain
text would also put it in database backups, in a `SELECT *` dump, and in any
admin view that lists rows.

The key material is derived from ``SECRET_KEY`` rather than being a separate
secret, so there is one thing to provision. The consequence is worth stating
plainly: **rotating SECRET_KEY makes existing stored keys undecryptable**, and
users must re-paste theirs. The failure is loud and safe (an explicit error,
not a silent plaintext fallback), and the settings note says so.

What this does *not* claim
--------------------------
Encryption at rest protects a database dump or a stolen backup. It does not
defend against code execution on the web host, where the running process can
decrypt any user's key. That is inherent to persisting a credential on the
server, not something this module can fix; the user's own decision to store
the key is what creates the exposure, and they can remove it at any time.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialCryptoError(RuntimeError):
    """Raised when a stored credential cannot be decrypted.

    Callers should surface this as "re-enter your key" rather than as a
    server error, because the overwhelmingly common cause is a rotated
    SECRET_KEY, not a bug.
    """


def _fernet() -> Fernet:
    """Derive a Fernet instance from SECRET_KEY.

    Fernet needs 32 url-safe base64-encoded bytes. SECRET_KEY is a 50-char
    string, so it is hashed to get exactly the width required. The purpose
    string is mixed in so this derived key cannot be accidentally reused for
    an unrelated purpose elsewhere in the project.
    """
    digest = hashlib.sha256(
        b"tailorup-ai-credential-v1:" + settings.SECRET_KEY.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    """Encrypt a credential for storage. Returns a url-safe ASCII token."""
    if plaintext is None:
        raise ValueError("plaintext is required")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a stored credential.

    Raises CredentialCryptoError on a wrong key or tampered ciphertext, so the
    caller never has to distinguish "corrupt" from "not ours" -- both mean the
    user needs to re-enter the key.
    """
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialCryptoError(
            "Stored credential could not be decrypted. The server's "
            "SECRET_KEY may have changed; the key must be re-entered."
        ) from exc


def mask(plaintext: str) -> str:
    """A hint for the UI that reveals the key without disclosing it.

    Google AI Studio keys share the ``AIza`` prefix and a roughly constant
    length, so the UI can show "AIza…4f2b" to confirm which key is stored
    without ever returning the full value. The tail is included deliberately:
    it is what lets a user with two keys tell them apart.
    """
    if not plaintext:
        return ""
    if len(plaintext) <= 4:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}...{plaintext[-4:]}"
