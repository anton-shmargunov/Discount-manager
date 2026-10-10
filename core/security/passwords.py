"""
Password hashing, verification and login throttling (stdlib only, no Streamlit).

Hash format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from typing import Callable, Optional

HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
MIN_ITERATIONS = 100_000
SALT_BYTES = 16

# Verified against when the username is unknown, so response time does not
# reveal which usernames exist.
_DUMMY_HASH = (
    f"{HASH_ALGORITHM}${DEFAULT_ITERATIONS}$"
    "00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    if iterations < MIN_ITERATIONS:
        raise ValueError(f"Use at least {MIN_ITERATIONS} iterations.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{HASH_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time check of *password* against a stored hash. Never raises."""
    try:
        algorithm, iterations_text, salt_hex, digest_hex = str(stored_hash).split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    if algorithm != HASH_ALGORITHM or iterations < MIN_ITERATIONS or not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(digest, expected)


def normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def authenticate(
    username: str,
    password: str,
    password_hashes: dict[str, str],
) -> Optional[str]:
    """Return the normalized username when the credentials match, else None."""
    user = normalize_username(username)
    hashes = {normalize_username(name): value for name, value in password_hashes.items()}
    stored = hashes.get(user)
    if stored is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, stored) else None


class LoginThrottle:
    """Per-username lockout after repeated failures. Shared across sessions of one process."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 15 * 60,
        lockout_seconds: float = 5 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def seconds_locked(self, username: str) -> float:
        user = normalize_username(username)
        with self._lock:
            remaining = self._locked_until.get(user, 0.0) - self._clock()
            return max(0.0, remaining)

    def record_failure(self, username: str) -> None:
        user = normalize_username(username)
        now = self._clock()
        with self._lock:
            recent = [t for t in self._failures.get(user, []) if now - t < self.window_seconds]
            recent.append(now)
            if len(recent) >= self.max_failures:
                self._locked_until[user] = now + self.lockout_seconds
                recent = []
            self._failures[user] = recent

    def record_success(self, username: str) -> None:
        user = normalize_username(username)
        with self._lock:
            self._failures.pop(user, None)
            self._locked_until.pop(user, None)
