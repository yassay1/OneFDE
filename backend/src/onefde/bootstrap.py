from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from onefde.core import schemas
from onefde.core.config import Settings
from onefde.infrastructure.db.session import make_engine
from onefde.infrastructure.web.errors import install_handlers
from onefde.modules.auth import router as auth
from onefde.modules.business import router as business
from onefde.modules.dialogue import router as dialogue
from onefde.modules.engagements import router as engagements
from onefde.modules.fde import router as fde
from onefde.modules.knowledge import router as knowledge
from onefde.modules.office import router as office
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
        description="持久控制包含 Task、输入/采用、版本、Run 和评审。Business 支持客户会话、工作台待办、复试与候选门店。C2 Worker 按配置消费作业，202 表示持久接单。",
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.business_customer_origin],
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(auth.router)
    app.include_router(engagements.router)
    app.include_router(tasks.business_router)
    app.include_router(tasks.router)
    app.include_router(fde.router)
    app.include_router(knowledge.router)
    app.include_router(office.router)
    app.include_router(business.public)
    app.include_router(business.router)
    app.include_router(dialogue.router)
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=dist, html=True),
            name="workbench",
        )
    return app
