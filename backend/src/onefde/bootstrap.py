from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from onefde.core import schemas
from onefde.core.config import Settings
from onefde.infrastructure.db.session import make_engine
from onefde.infrastructure.web.errors import install_handlers
from onefde.modules.auth import router as auth
from onefde.modules.engagements import router as engagements
from onefde.modules.tasks import router as tasks


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title="OneFDE MVP control API",
        version="0.2.0",
        lifespan=lifespan,
        description="已实现持久控制：输入/采用、版本、Run/待派发、轻量评审与事件。C2独立Worker按配置消费作业；202仅表示持久接单，不保证执行或交付。真实模型/隔离环境须另行验证，无前端。",
        responses={
            str(code): {"model": schemas.ApiError}
            for code in [400, 401, 403, 404, 409, 422, 429, 500, 503]
        },
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url.get_secret_value())
    install_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health", response_model=schemas.Health, operation_id="health")
    def health():
        return schemas.Health()

    app.include_router(auth.router)
    app.include_router(engagements.router)
    app.include_router(tasks.business_router)
    app.include_router(tasks.router)
    return app
