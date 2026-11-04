from fastapi import APIRouter, Depends, Request, Response

from onefde.infrastructure.web.dependencies import DB
from onefde.modules.auth import schemas, service
from onefde.modules.auth.dependencies import Current, WriteSession, check_write

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=schemas.OwnerSession,
    operation_id="login",
    dependencies=[Depends(check_write)],
)
def login(data: schemas.Login, request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    result, token = service.login(
        data, db, settings, request.cookies.get(settings.cookie_name)
    )
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_hours * 3600,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/session", response_model=schemas.OwnerSession, operation_id="getSession")
def get_session(current: Current, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return schemas.OwnerSession.model_validate(current, from_attributes=True)


@router.post("/logout", status_code=204, operation_id="logout")
def logout(request: Request, current: WriteSession, db: DB):
    service.logout(db, current)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        request.app.state.settings.cookie_name,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
