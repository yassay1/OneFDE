import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select, text

from onefde.core.clock import now
from onefde.core.errors import ApiException
from onefde.core.security import digest
from onefde.modules.auth import schemas
from onefde.modules.auth.models import AuthSession, LoginAttempt


def credential_fingerprint(settings):
    return digest(
        settings.owner_username + ":" + settings.owner_password_hash.get_secret_value()
    )


def authenticate(db, settings, token):
    if not token or len(token) > 256:
        raise ApiException(401, "UNAUTHENTICATED", "请登录或重新登录")
    row = db.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == digest(token))
        .with_for_update()
    )
    if (
        row is None
        or row.expires_at <= now()
        or row.credential_hash != credential_fingerprint(settings)
    ):
        raise ApiException(401, "UNAUTHENTICATED", "请登录或重新登录")
    return row


def login(data, db, settings, previous):
    # Short persistent rate-limit transaction. No proxy/client-IP trust assumptions.
    db.execute(text("SELECT pg_advisory_xact_lock(624013, 1)"))
    attempt = db.get(LoginAttempt, "owner")
    timestamp = now()
    if attempt is None:
        attempt = LoginAttempt(bucket="owner", window_start=timestamp, attempts=0)
        db.add(attempt)
    elif attempt.window_start + timedelta(minutes=5) <= timestamp:
        attempt.window_start, attempt.attempts = timestamp, 0
    if attempt.attempts >= settings.login_limit:
        raise ApiException(429, "LOGIN_RATE_LIMITED", "登录过于频繁，请稍后重试")
    attempt.attempts += 1
    db.commit()
    try:
        valid_password = PasswordHasher().verify(
            settings.owner_password_hash.get_secret_value(),
            data.password.get_secret_value(),
        )
    except VerificationError:
        valid_password = False
    if not (
        valid_password
        and secrets.compare_digest(
            data.username.encode(), settings.owner_username.encode()
        )
    ):
        raise ApiException(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    # A successful re-login rotates this browser's prior session.
    if previous:
        old = db.get(AuthSession, digest(previous))
        if old:
            db.delete(old)
    row = AuthSession(
        token_hash=digest(token),
        username=settings.owner_username,
        credential_hash=credential_fingerprint(settings),
        csrf_token=csrf,
        expires_at=now() + timedelta(hours=settings.session_hours),
    )
    db.add(row)
    result = schemas.OwnerSession.model_validate(row, from_attributes=True)
    db.commit()
    return result, token


def logout(db, current):
    db.delete(current)
    db.commit()
