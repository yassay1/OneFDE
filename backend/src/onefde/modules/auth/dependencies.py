import secrets
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyCookie

from onefde.core.errors import ApiException
from onefde.infrastructure.web.dependencies import DB as DB
from onefde.modules.auth import service
from onefde.modules.auth.models import AuthSession

cookie_scheme = APIKeyCookie(name="__Host-onefde_session", auto_error=False)


def check_write(request: Request):
    settings = request.app.state.settings
    if request.headers.get("origin") != settings.trusted_origin:
        raise ApiException(403, "ORIGIN_FORBIDDEN", "请求 Origin 不受信任")
    if (
        request.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/json"
    ):
        raise ApiException(400, "JSON_REQUIRED", "写请求要求 application/json")


def current_session(request: Request, db: DB, _cookie=Depends(cookie_scheme)):
    settings = request.app.state.settings
    return service.authenticate(db, settings, request.cookies.get(settings.cookie_name))


Current = Annotated[AuthSession, Depends(current_session)]


def csrf_session(
    request: Request,
    current: Current,
    x_csrf_token: Annotated[
        str, Header(min_length=1, description="必填；缺失或错误返回403")
    ],
):
    check_write(request)
    if not x_csrf_token or not secrets.compare_digest(
        x_csrf_token.encode(), current.csrf_token.encode()
    ):
        raise ApiException(403, "CSRF_INVALID", "CSRF 校验失败")
    return current


WriteSession = Annotated[AuthSession, Depends(csrf_session)]
