"""User accounts + session tokens for the bearer-token login flow.

The HTTP shape lives in ``server/api.py``. This module is the data layer:

- **Users** (``data/users.json``): email → password hash (PBKDF2-SHA256).
  Seeded on first start with the accounts the operator named; later
  a password-change / password-set endpoint can mutate these in place
  without re-plumbing.
- **Sessions** (``data/sessions.json``): sha256(raw_token) → row with
  email, created_at, expires_at. We store the *hash* of the token so a
  leaked file alone can't be replayed against the API; the raw token
  only ever exists in the response body to the login call. Default TTL
  is 30 days; expired rows are dropped lazily on read.

The shared ``BSH_RESEARCH_API_TOKEN`` env var also authenticates (service
role, header-only) — ``require_api_token`` in ``api.py`` accepts either.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
RESETS_FILE = DATA_DIR / "password_resets.json"

SESSION_TTL = timedelta(days=30)
# A reset link is carried to the person by hand (an admin copies it), so it
# has to outlive a working day rather than the few minutes an emailed link
# would get.
RESET_TTL = timedelta(hours=24)

# An account exists before it may be used. Registration opens one as
# ``pending``: it can hold a password and be signed into nothing. An admin
# moves it to ``active`` and assigns the role at the same moment, because
# a role inferred from the email domain is exactly what open registration
# would let a stranger choose for themselves.
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
STATUSES = (STATUS_PENDING, STATUS_ACTIVE, STATUS_DISABLED)

# Long enough to be worth the 200k-iteration KDF behind it. The ceiling is
# not a policy: it stops a 10MB "password" from becoming a KDF-priced request.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
# RFC 5321's path limit; the shape check is deliberately loose (one "@",
# something either side, a dot in the domain) because strict address
# grammars reject real addresses, and approval is a human step anyway.
MAX_EMAIL_LENGTH = 254
_EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# An account keeps at most this many live sessions; a sign-in past it
# retires the oldest. Bounds the store against a client that signs in on a
# loop, and bounds the damage of a stolen credential that keeps minting.
MAX_SESSIONS_PER_ACCOUNT = 25


def valid_email(email: str | None) -> bool:
    key = _normalize_email(email)
    return bool(key) and len(key) <= MAX_EMAIL_LENGTH and bool(_EMAIL_SHAPE_RE.match(key))
PBKDF2_ITERATIONS = 200_000
PBKDF2_ALGO = "sha256"

# Accounts created on first start. NO passwords are baked into source
# (an earlier version seeded a shared plaintext password, now burned).
# Each seeded account gets an unusable random password and ``must_reset``
# unless ``BSH_BOOTSTRAP_PASSWORD`` is set, in which case that password is
# applied (still ``must_reset`` so the operator rotates it). Set a real
# password per account with:  python -m server.auth_store set-password <email>
SEED_EMAILS: list[str] = [
    "robert@bshventures.com",
    "elina.sun@bshventures.com",
    "aurora.pan@bshventures.com",
    "serena@bshfoundation.org",
    "seline.sun@bshfoundation.org",
    "liupengsen50@gmail.com",
    "elbereth.wang@gmail.com",
    "viola.zhao@gmail.com",
    "846248966@qq.com",
]

_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_email(email: str | None) -> str:
    """The canonical form of an address, as the store keys it."""
    return _normalize_email(email)


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

class StoreUnreadableError(RuntimeError):
    """A store file exists but cannot be read as the JSON object it should
    be. Raised rather than swallowed: returning an empty default here would
    let the next write replace every account with a fresh seed set."""


_OWNER_ONLY = stat.S_IRUSR | stat.S_IWUSR


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreUnreadableError(f"{path} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise StoreUnreadableError(f"{path} does not hold a JSON object")
    return data


def _write_json(path: Path, payload: dict) -> None:
    """Atomic replace, owner-only. The tmp file is created 0600 before a
    byte of hash material lands in it, and the final file is re-asserted
    to 0600 in case it predates this rule (the default umask left the
    old ones world-readable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _OWNER_ONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)
    try:
        os.chmod(path, _OWNER_ONLY)
    except OSError:
        pass


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

    No plaintext password ships in source. Each new account is created
    with ``BSH_BOOTSTRAP_PASSWORD`` if set, else an unusable random one,
    and always flagged ``must_reset`` so the operator sets a real password
    via ``python -m server.auth_store set-password <email>``.
    """
    bootstrap_pw = os.environ.get("BSH_BOOTSTRAP_PASSWORD") or None
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        changed = False
        for email in SEED_EMAILS:
            key = _normalize_email(email)
            if key in users:
                continue
            password = bootstrap_pw or secrets.token_urlsafe(32)
            users[key] = {
                "email": key,
                "password": _hash_password(password),
                "created_at": _iso(_now()),
                "must_reset": True,
                "status": STATUS_ACTIVE,
            }
            changed = True
        if changed:
            payload["version"] = payload.get("version", 1)
            _save_users(payload)


def _migrate_users(users: dict) -> bool:
    """Give pre-status records a status. They predate registration, so they
    are the accounts an operator seeded deliberately: active, and with no
    stored role, which leaves them on the email-domain mapping they were
    built around. Returns True if anything changed."""
    changed = False
    for record in users.values():
        if isinstance(record, dict) and not record.get("status"):
            record["status"] = STATUS_ACTIVE
            changed = True
    return changed


def password_policy_error(password: str, email: str | None = None) -> str | None:
    """Why this password is unacceptable, or None. Deliberately short: a
    length floor and the two substitutions people actually reach for."""
    candidate = password or ""
    if len(candidate) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(candidate) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    if len(set(candidate)) < 4:
        return "Password must use more than a few distinct characters."
    local = _normalize_email(email).split("@")[0]
    if local and len(local) >= 3 and local in candidate.lower():
        return "Password must not contain your email address."
    return None


def account(email: str | None) -> dict | None:
    """The account's public view — never the password material."""
    key = _normalize_email(email)
    if not key:
        return None
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        if _migrate_users(users):
            _save_users(payload)
        record = users.get(key)
        if record is None:
            return None
        return _public_account(record)


def _public_account(record: dict) -> dict:
    return {
        "email": record.get("email"),
        "status": record.get("status") or STATUS_ACTIVE,
        "role": record.get("role"),
        "created_at": record.get("created_at"),
        "approved_at": record.get("approved_at"),
        "approved_by": record.get("approved_by"),
        "must_reset": bool(record.get("must_reset")),
        "reset_requested_at": record.get("reset_requested_at"),
        "last_login_at": record.get("last_login_at"),
    }


def list_accounts() -> list[dict]:
    """Every account, pending first, then by email."""
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        if _migrate_users(users):
            _save_users(payload)
        rows = [_public_account(r) for r in users.values() if isinstance(r, dict)]
    order = {STATUS_PENDING: 0, STATUS_ACTIVE: 1, STATUS_DISABLED: 2}
    return sorted(rows, key=lambda r: (order.get(r["status"], 3), r["email"] or ""))


def stored_role(email: str | None) -> str | None:
    """The role recorded on the account, or None when it has none and the
    caller should fall back to the email mapping."""
    record = account(email)
    return (record or {}).get("role") or None


def register(email: str, password: str) -> str:
    """Open a pending account. Returns "created", "exists", or "invalid".

    The caller must answer identically for "created" and "exists": telling
    a stranger which addresses are already registered is the one thing an
    open registration form must not do.
    """
    key = _normalize_email(email)
    if not valid_email(key):
        return "invalid"
    if password_policy_error(password, key):
        return "invalid"
    # The KDF runs before the address is looked up, so a taken address and a
    # free one take the same time to answer. Looking first would have made
    # "exists" a fast path — a stopwatch could tell them apart.
    hashed = _hash_password(password)
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        _migrate_users(users)
        if key in users:
            return "exists"
        users[key] = {
            "email": key,
            "password": hashed,
            "created_at": _iso(_now()),
            "status": STATUS_PENDING,
        }
        _save_users(payload)
    return "created"


def set_account_status(
    email: str,
    status: str,
    *,
    role: str | None = None,
    by: str | None = None,
) -> bool:
    """Move an account between pending/active/disabled, assigning its role
    on the way in. Disabling also drops the account's sessions, so access
    ends at the click rather than whenever the token expires."""
    key = _normalize_email(email)
    if status not in STATUSES:
        return False
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        _migrate_users(users)
        record = users.get(key)
        if record is None:
            return False
        record["status"] = status
        if role:
            record["role"] = role
        if status == STATUS_ACTIVE:
            record["approved_at"] = _iso(_now())
            if by:
                record["approved_by"] = _normalize_email(by)
        _save_users(payload)
    if status != STATUS_ACTIVE:
        revoke_sessions_for(key)
    return True


def note_login(email: str) -> None:
    key = _normalize_email(email)
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        record = users.get(key)
        if record is None:
            return
        record["last_login_at"] = _iso(_now())
        _save_users(payload)


def must_reset(email: str | None) -> bool:
    """True if ``email`` is flagged to change its password before use."""
    key = _normalize_email(email)
    if not key:
        return False
    with _LOCK:
        record = _load_users().get("users", {}).get(key)
    return bool(record and record.get("must_reset"))


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


def set_password(
    email: str, new_password: str, *, keep_token: str | None = None
) -> bool:
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
        users[key].pop("must_reset", None)
        users[key].pop("reset_requested_at", None)
        _save_users(payload)
    # A password change is how someone responds to a session they don't
    # recognise, so it has to end the others.
    revoke_sessions_for(key, keep_token=keep_token)
    _drop_resets_for(key)
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
        mine = sorted(
            (hh for hh, row in sessions.items() if row.get("email") == key),
            key=lambda hh: sessions[hh].get("created_at") or "",
        )
        for stale in mine[: max(0, len(mine) - (MAX_SESSIONS_PER_ACCOUNT - 1))]:
            sessions.pop(stale, None)
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
    Useful for a "log out everywhere" or password-change flow."""
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


def revoke_all_sessions() -> int:
    """Delete every session (e.g. after a credential compromise). Returns
    the count removed."""
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        count = len(sessions)
        if count:
            payload["sessions"] = {}
            _save_sessions(payload)
    return count


# ---- Operator CLI -------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        prog="python -m server.auth_store",
        description="Manage research-center accounts and sessions.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set-password", help="Set a user's password.")
    p_set.add_argument("email")
    p_set.add_argument(
        "password",
        nargs="?",
        help="New password. Omit to be prompted (not echoed).",
    )

    p_create = sub.add_parser("create-user", help="Create a new account.")
    p_create.add_argument("email")
    p_create.add_argument("password", nargs="?")

    sub.add_parser("list", help="List account emails.")

    p_revoke = sub.add_parser("revoke", help="Revoke a user's sessions.")
    p_revoke.add_argument("email")

    sub.add_parser("revoke-all", help="Revoke ALL sessions (compromise).")

    args = parser.parse_args(argv)

    if args.cmd == "set-password":
        pw = args.password or getpass.getpass("New password: ")
        if not pw:
            print("Password cannot be empty.")
            return 2
        ok = set_password(args.email, pw)
        print("Password updated." if ok else f"No such user: {args.email}")
        return 0 if ok else 1

    if args.cmd == "create-user":
        pw = args.password or getpass.getpass("Password: ")
        if not pw:
            print("Password cannot be empty.")
            return 2
        ok = create_user(args.email, pw)
        print("User created." if ok else f"User already exists: {args.email}")
        return 0 if ok else 1

    if args.cmd == "list":
        for email in list_user_emails():
            flag = " (must reset)" if must_reset(email) else ""
            print(f"{email}{flag}")
        return 0

    if args.cmd == "revoke":
        n = revoke_email(args.email)
        print(f"Revoked {n} session(s) for {args.email}.")
        return 0

    if args.cmd == "revoke-all":
        n = revoke_all_sessions()
        print(f"Revoked {n} session(s).")
        return 0

    return 2


if __name__ == "__main__":
    import sys

    sys.exit(_main())


def sessions_for(email: str | None, *, current_token: str | None = None) -> list[dict]:
    """Every live session for one account, newest first, each marked if it
    is the one asking. Tokens never leave the store, so a row is identified
    by the hash the store already keeps."""
    key = _normalize_email(email)
    current_hash = _token_hash(current_token) if current_token else None
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        if _purge_expired(sessions):
            _save_sessions(payload)
        rows = [
            {
                "id": h[:16],
                "created_at": row.get("created_at"),
                "expires_at": row.get("expires_at"),
                "current": h == current_hash,
            }
            for h, row in sessions.items()
            if row.get("email") == key
        ]
    return sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)


def revoke_sessions_for(
    email: str | None,
    *,
    keep_token: str | None = None,
    session_id: str | None = None,
) -> int:
    """Drop this account's sessions and return how many went. ``keep_token``
    spares the caller's own; ``session_id`` narrows it to one row."""
    key = _normalize_email(email)
    keep_hash = _token_hash(keep_token) if keep_token else None
    with _LOCK:
        payload = _load_sessions()
        sessions = payload.setdefault("sessions", {})
        doomed = [
            h
            for h, row in sessions.items()
            if row.get("email") == key
            and h != keep_hash
            and (session_id is None or h[:16] == session_id)
        ]
        for h in doomed:
            sessions.pop(h, None)
        if doomed:
            _save_sessions(payload)
    return len(doomed)


# ---- Password resets ----------------------------------------------------
#
# There is no mail path in this deployment, so a reset is a two-step the
# operator drives: the person asks from the sign-in page, which only flags
# the account, and an admin mints a single-use link and carries it over.
# Only the hash of the link's token is stored, exactly as for sessions.


def _load_resets() -> dict:
    return _read_json(RESETS_FILE, {"version": 1, "resets": {}})


def _save_resets(payload: dict) -> None:
    _write_json(RESETS_FILE, payload)


def _purge_expired_resets(resets: dict) -> bool:
    now = _now()
    dead = []
    for h, row in resets.items():
        try:
            if datetime.fromisoformat(row.get("expires_at") or "") <= now:
                dead.append(h)
        except ValueError:
            dead.append(h)
    for h in dead:
        resets.pop(h, None)
    return bool(dead)


def _drop_resets_for(email: str) -> None:
    key = _normalize_email(email)
    with _LOCK:
        payload = _load_resets()
        resets = payload.setdefault("resets", {})
        dead = [h for h, row in resets.items() if row.get("email") == key]
        for h in dead:
            resets.pop(h, None)
        if dead:
            _save_resets(payload)


def request_password_reset(email: str | None) -> bool:
    """Flag the account so an admin sees the request. Returns whether a
    record was flagged — which the HTTP layer must NOT pass on, or the
    form becomes a way to test which addresses exist."""
    key = _normalize_email(email)
    if not key:
        return False
    with _LOCK:
        payload = _load_users()
        users = payload.setdefault("users", {})
        record = users.get(key)
        if record is not None:
            record["reset_requested_at"] = _iso(_now())
        # Saved either way: the write is the measurable part of this call,
        # and an unknown address must cost the same as a known one.
        _save_users(payload)
    return record is not None


def mint_reset_token(email: str, *, ttl: timedelta = RESET_TTL) -> str | None:
    """A single-use reset token for ``email``. Returned once, in the clear,
    to the admin who will carry it; the store keeps only its hash. Any
    earlier token for the account stops working."""
    key = _normalize_email(email)
    if account(key) is None:
        return None
    _drop_resets_for(key)
    raw_token = secrets.token_urlsafe(32)
    with _LOCK:
        payload = _load_resets()
        resets = payload.setdefault("resets", {})
        _purge_expired_resets(resets)
        resets[_token_hash(raw_token)] = {
            "email": key,
            "created_at": _iso(_now()),
            "expires_at": _iso(_now() + ttl),
        }
        _save_resets(payload)
    return raw_token


def peek_reset_token(raw_token: str | None) -> str | None:
    """The email a live reset token belongs to, without spending it."""
    if not raw_token:
        return None
    with _LOCK:
        payload = _load_resets()
        resets = payload.setdefault("resets", {})
        if _purge_expired_resets(resets):
            _save_resets(payload)
        row = resets.get(_token_hash(raw_token))
    return row.get("email") if row else None


def consume_reset_token(raw_token: str, new_password: str) -> str | None:
    """Spend the token and set the password. Returns the email on success.

    Every session for the account ends here: a reset is what someone does
    when they believe another person has the old password.
    """
    if not raw_token:
        return None
    with _LOCK:
        payload = _load_resets()
        resets = payload.setdefault("resets", {})
        _purge_expired_resets(resets)
        row = resets.get(_token_hash(raw_token))
        email = row.get("email") if row else None
        if email is None or password_policy_error(new_password, email):
            if row is None:
                _save_resets(payload)
            return None
        # Spent here, atomically: a second submission racing this one finds
        # nothing, whichever of the two reached the lock first.
        resets.pop(_token_hash(raw_token), None)
        _save_resets(payload)
    if not set_password(email, new_password):
        return None
    _drop_resets_for(email)
    return email
