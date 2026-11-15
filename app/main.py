"""FastAPI app factory and router registration.

Owner: M4. Run with: uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from app.api import routes_audit, routes_drafts
from app.core.container import Container, build_container
from app.core.errors import register_error_handlers
from app.core.logging import CorrelationIdMiddleware, configure_logging
from app.schemas.api import HealthResponse
from config.settings import get_settings


def create_app(container: Container | None = None) -> FastAPI:
    """Build the app. Tests pass a pre-built container (in-memory DB, fakes)."""
    configure_logging()
    container = container or build_container(get_settings())

    app = FastAPI(
        title="Customer Engagement Assistant",
        version="0.1.0",
        description=(
            "Explainable segmentation, policy-controlled drafts, human review, mock delivery."
        ),
    )
    app.state.container = container
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    def health(request: Request) -> HealthResponse:
        c: Container = request.app.state.container
        s = c.settings
        db = c.db_status()
        return HealthResponse(
            status="ok" if db == "ok" else "degraded",
            db=db,
            llm_mode=s.llm_provider,
            model_id=s.llm_model_id or s.llm_provider,
            ruleset_version=c.ruleset_version,
            pipeline_stubs=s.pipeline_stubs,
            as_of_date=s.as_of_date,
        )

    app.include_router(routes_drafts.router)
    app.include_router(routes_audit.router)
    # Owned by M1/M2; include once implemented:
    # from app.api import routes_customers, routes_policy
    # app.include_router(routes_customers.router); app.include_router(routes_policy.router)
    return app


def __getattr__(name: str):  # noqa: ANN202
    """Lazily create `app` so importing this module (e.g. in tests) has no side effects."""
    if name == "app":
        value = create_app()
        globals()["app"] = value
        return value
    raise AttributeError(name)
