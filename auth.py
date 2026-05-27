import asyncio
import time

import bcrypt
from fastapi import Request

import db

_SIGNUP_COUNT: dict[str, tuple[int, float]] = {}
_MAX_SIGNUPS = 3
_SIGNUP_WINDOW = 86400  # 24 hours

_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 900

def check_signup_rate_limit(ip: str) -> bool:
    now = time.time()
    entry = _SIGNUP_COUNT.get(ip)
    if entry is None:
        return True
    count, first = entry
    if now - first > _SIGNUP_WINDOW:
        _SIGNUP_COUNT.pop(ip, None)
        return True
    return count < _MAX_SIGNUPS

def record_signup(ip: str):
    now = time.time()
    entry = _SIGNUP_COUNT.get(ip)
    if entry is None or now - entry[1] > _SIGNUP_WINDOW:
        _SIGNUP_COUNT[ip] = (1, now)
    else:
        _SIGNUP_COUNT[ip] = (entry[0] + 1, entry[1])


def check_login_rate_limit(ip: str) -> bool:
    now = time.time()
    entry = _LOGIN_ATTEMPTS.get(ip)
    if entry is None:
        return True
    count, first = entry
    if now - first > _LOCKOUT_SECONDS:
        _LOGIN_ATTEMPTS.pop(ip, None)
        return True
    return count < _MAX_ATTEMPTS


def record_login_failure(ip: str):
    now = time.time()
    entry = _LOGIN_ATTEMPTS.get(ip)
    if entry is None or now - entry[1] > _LOCKOUT_SECONDS:
        _LOGIN_ATTEMPTS[ip] = (1, now)
    else:
        _LOGIN_ATTEMPTS[ip] = (entry[0] + 1, entry[1])


def record_login_success(ip: str):
    _LOGIN_ATTEMPTS.pop(ip, None)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await asyncio.to_thread(db.db_get_user_by_id, user_id)


def create_user(email: str, password: str) -> dict:
    existing = db.db_get_user_by_email(email)
    if existing:
        raise ValueError("Email already registered")
    return db.db_create_user(email, hash_password(password))
