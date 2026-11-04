import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from onefde.core.errors import ApiException

logger = logging.getLogger("onefde")


def error_response(request, status, code, message, details=None):
    body = dict(
        code=code,
        message=message,
        request_id=getattr(request.state, "request_id", str(uuid4())),
    )
    if details is not None:
        body["details"] = details
    return JSONResponse(
        body,
        status_code=status,
        headers={
            "Cache-Control": "no-store",
            "X-Request-ID": body["request_id"],
            "X-Content-Type-Options": "nosniff",
        },
    )


def install_handlers(app):
    @app.exception_handler(ApiException)
    async def api_error(request: Request, exc: ApiException):
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if any(e["loc"] == ("header", "x-csrf-token") for e in exc.errors()):
            return error_response(request, 403, "CSRF_INVALID", "CSRF 校验失败")
        # Never include input values, password contents or validator context.
        fields = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return error_response(
            request, 422, "VALIDATION_ERROR", "字段校验失败", {"fields": fields}
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return error_response(request, 409, "RESOURCE_CONFLICT", "资源唯一性或归属冲突")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error(
            "database failure request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return error_response(request, 503, "DATABASE_UNAVAILABLE", "数据库暂不可用")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            request, exc.status_code, "HTTP_ERROR", "请求路径或方法不可用"
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error(
            "internal failure request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return error_response(request, 500, "INTERNAL_ERROR", "服务内部错误")
