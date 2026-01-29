from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.exc import OperationalError as SAOperationalError

from api.router import api_router
from core.config import settings
from core.db import DatabaseUnavailableError, ENGINE, is_transient_db_connectivity_error


def create_app() -> FastAPI:
    app = FastAPI(title="Timetable Generator API", version="0.1.0")

    @app.exception_handler(DatabaseUnavailableError)
    def _db_unavailable(_request, _exc: DatabaseUnavailableError):
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Database temporarily unavailable. Please retry.",
            },
        )

    @app.exception_handler(SAOperationalError)
    def _sqlalchemy_operational_error(_request, exc: SAOperationalError):
        if is_transient_db_connectivity_error(exc):
            return JSONResponse(
                status_code=503,
                content={
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database temporarily unavailable. Please retry.",
                },
            )
        return JSONResponse(
            status_code=500,
            content={
                "code": "DATABASE_ERROR",
                "message": "Database operation failed.",
            },
        )

    # Optional driver-specific exceptions (best-effort, no hard dependency).
    try:
        import psycopg2  # type: ignore

        @app.exception_handler(psycopg2.OperationalError)  # type: ignore[attr-defined]
        def _psycopg2_operational_error(_request, exc: Exception):
            if is_transient_db_connectivity_error(exc):
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "DATABASE_UNAVAILABLE",
                        "message": "Database temporarily unavailable. Please retry.",
                    },
                )
            return JSONResponse(
                status_code=500,
                content={
                    "code": "DATABASE_ERROR",
                    "message": "Database operation failed.",
                },
            )
    except Exception:
        pass

    try:
        import asyncpg  # type: ignore

        @app.exception_handler(asyncpg.PostgresError)  # type: ignore[attr-defined]
        def _asyncpg_error(_request, exc: Exception):
            if is_transient_db_connectivity_error(exc):
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "DATABASE_UNAVAILABLE",
                        "message": "Database temporarily unavailable. Please retry.",
                    },
                )
            return JSONResponse(
                status_code=500,
                content={
                    "code": "DATABASE_ERROR",
                    "message": "Database operation failed.",
                },
            )
    except Exception:
        pass

    app.add_middleware(
        CORSMiddleware,
        # Dev-friendly: allow the configured origin and any localhost port.
        allow_origins=[settings.frontend_origin],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        # Always respond; reflect DB availability without crashing.
        db_status = "ok"
        try:
            with ENGINE.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_status = "down"

        return {"app": "ok", "database": db_status}

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
