"""User accounts + session tokens for the bearer-token login flow.

The HTTP shape lives in ``server/api.py``. This module is the data layer:

- **Users** (``data/users.json``): email → password hash (PBKDF2-SHA256).
  Seeded on first start with the three accounts the operator named; later
  a password-change / password-set endpoint can mutate these in place
  without re-plumbing.
- **Sessions** (``data/sessions.json``): sha256(raw_token) → row with
  email, created_at, expires_at. We store the *hash* of the token so a
  leaked file alone can't be replayed against the API; the raw token
  only ever exists in the response body to the login call. Default TTL
  is 30 days; expired rows are dropped lazily on read.

The existing shared ``BSH_RESEARCH_API_TOKEN`` env var continues to work
independently for the served-HTML meta-tag flow — ``require_api_token``
in ``api.py`` accepts either kind.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"

SESSION_TTL = timedelta(days=30)
PBKDF2_ITERATIONS = 200_000
PBKDF2_ALGO = "sha256"

# Seeded on first start. The named accounts share the same initial
# password per the operator; a future password-change endpoint will
# mutate the store. `guest`/`guest` is a shared low-trust login — the
# login field accepts any string (no email-format validation), so a
# bare "guest" username works.
SEED_USERS: list[tuple[str, str]] = [
    ("robert@bshventures.com", "redapple"),
    ("elina.sun@bshventures.com", "redapple"),
    ("serena@bshfoundation.org", "redapple"),
    ("liupengsen50@gmail.com", "redapple"),
    ("guest", "guest"),
]

_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


# ---- Password hashing ---------------------------------------------------

def _hash_password(password: str, *, salt: bytes | None = None) -> dict:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return {
        "scheme": f"pbkdf2_{PBKDF2_ALGO}",
        "iterations": PBKDF2_ITERATIONS,
        "salt": salt.hex(),
        "hash": digest.hex(),
    }


def _verify_password(password: str, record: dict) -> bool:
    if not record or record.get("scheme") != f"pbkdf2_{PBKDF2_ALGO}":
        return False
    try:
        salt = bytes.fromhex(record["salt"])
        expected = bytes.fromhex(record["hash"])
        iterations = int(record.get("iterations", PBKDF2_ITERATIONS))
    except (KeyError, ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, password.encode("utf-8"), salt, iterations
    )
    return secrets.compare_digest(candidate, expected)


# ---- JSON store I/O -----------------------------------------------------

def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        return data
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def _load_users() -> dict:
    return _read_json(USERS_FILE, {"version": 1, "users": {}})


def _save_users(payload: dict) -> None:
    _write_json(USERS_FILE, payload)


def _load_sessions() -> dict:
    return _read_json(SESSIONS_FILE, {"version": 1, "sessions": {}})


def _save_sessions(payload: dict) -> None:
    _write_json(SESSIONS_FILE, payload)


# ---- Users --------------------------------------------------------------

def bootstrap_seed_users() -> None:
    """Create the seed user records on first start. Idempotent: existing
    rows are preserved; only missing emails are added.
    """
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        changed = False
        for email, password in SEED_USERS:
            key = _normalize_email(email)
            if key in users:
                continue
            users[key] = {
                "email": key,
                "password": _hash_password(password),
                "created_at": _iso(_now()),
            }
            changed = True
        if changed:
            payload["version"] = payload.get("version", 1)
            _save_users(payload)


def verify_credentials(email: str, password: str) -> str | None:
    """Return the canonical (normalized) email if credentials match, else
    None. Both branches do equivalent work to mitigate timing-based user
    enumeration.
    """
    key = _normalize_email(email)
    with _LOCK:
        users = _load_users().get("users", {})
        record = users.get(key)
    # Run the KDF either way so timing doesn't reveal whether the email
    # exists. The dummy hash is generated once per call from a throwaway
    # salt; matches will return False.
    if record is None:
        _verify_password(password, _hash_password("\x00", salt=b"\x00" * 16))
        return None
    if not _verify_password(password, record.get("password") or {}):
        return None
    return key


def set_password(email: str, new_password: str) -> bool:
    """Replace the password for an existing user. Returns True on success,
    False if the user doesn't exist. Wire into a future change-password
    endpoint.
    """
    key = _normalize_email(email)
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        if key not in users:
            return False
        users[key]["password"] = _hash_password(new_password)
        users[key]["password_changed_at"] = _iso(_now())
        _save_users(payload)
    return True


def create_user(email: str, password: str) -> bool:
    """Add a new user. Returns False if the email is already taken."""
    key = _normalize_email(email)
    if not key:
        return False
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        if key in users:
            return False
        users[key] = {
            "email": key,
            "password": _hash_password(password),
            "created_at": _iso(_now()),
        }
        _save_users(payload)
    return True


def list_user_emails() -> list[str]:
    with _LOCK:
        return sorted(_load_users().get("users", {}).keys())


# ---- Sessions -----------------------------------------------------------

def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _purge_expired(sessions: dict) -> bool:
    """Drop expired rows in place. Returns True if anything was removed."""
    now = _now()
    expired = []
    for h, row in sessions.items():
        exp = row.get("expires_at")
        if not exp:
            continue
        try:
            exp_dt = datetime.fromisoformat(exp)
        except ValueError:
            expired.append(h)
            continue
        if exp_dt <= now:
            expired.append(h)
    for h in expired:
        sessions.pop(h, None)
    return bool(expired)


def issue_session(email: str, *, ttl: timedelta = SESSION_TTL) -> dict:
    """Mint a fresh per-session token for ``email``. Returns
    ``{token, email, created_at, expires_at}`` — the raw token is only
    ever returned here (the on-disk store keeps just its sha256)."""
    key = _normalize_email(email)
    raw_token = secrets.token_urlsafe(32)
    h = _token_hash(raw_token)
    now = _now()
    expires = now + ttl
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        _purge_expired(sessions)
        sessions[h] = {
            "email": key,
            "created_at": _iso(now),
            "expires_at": _iso(expires),
        }
        _save_sessions(payload)
    return {
        "token": raw_token,
        "email": key,
        "created_at": _iso(now),
        "expires_at": _iso(expires),
    }


def validate_token(raw_token: str | None) -> dict | None:
    """Return the session row (with email) if ``raw_token`` is a valid,
    non-expired session token; else None. Expired rows are GC'd lazily
    here.
    """
    if not raw_token:
        return None
    h = _token_hash(raw_token)
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        if _purge_expired(sessions):
            _save_sessions(payload)
        row = sessions.get(h)
        if row is None:
            return None
        # Already-purged covers expiry; defensive double-check below.
        try:
            exp_dt = datetime.fromisoformat(row.get("expires_at") or "")
        except ValueError:
            return None
        if exp_dt <= _now():
            sessions.pop(h, None)
            _save_sessions(payload)
            return None
        return {"email": row.get("email"), **row}


def revoke_token(raw_token: str | None) -> bool:
    """Delete one session row. Returns True if the row existed."""
    if not raw_token:
        return False
    h = _token_hash(raw_token)
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        if h not in sessions:
            return False
        sessions.pop(h, None)
        _save_sessions(payload)
    return True


def revoke_email(email: str) -> int:
    """Delete all sessions for one email. Returns the count removed.
    Useful for a future "log out everywhere" or password-change flow."""
    key = _normalize_email(email)
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        targets = [h for h, row in sessions.items() if row.get("email") == key]
        for h in targets:
            sessions.pop(h, None)
        if targets:
            _save_sessions(payload)
    return len(targets)
