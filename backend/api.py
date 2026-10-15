from contextlib import asynccontextmanager
from hashlib import sha256
from datetime import date
from typing import Literal
import threading

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings, today_ist
from .data import CSV_COLUMNS, ProjectError, Store, demo_frame, parse_csv
from .feed import refresh_feed
from .models import ModelService
from .security import guard_request

Mode = Literal["demo", "real"]


class TrainRequest(BaseModel):
    mode: Mode = "demo"
    series_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)


class MarketCost(BaseModel):
    series_id: str = Field(min_length=1, max_length=40)
    transport_cost: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    market_fees: float = Field(ge=0, le=1e9, allow_inf_nan=False)


class ComparisonRequest(BaseModel):
    mode: Mode = "demo"
    replay_date: date | None = None
    quantity_quintals: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    markets: list[MarketCost] = Field(min_length=2, max_length=20)


class FeedRequest(BaseModel):
    state: str = Field(min_length=1, max_length=150)
    commodity: str = Field(min_length=1, max_length=150)
    market: str = Field(default="", max_length=150)
    max_pages: int = Field(default=3, ge=1, le=10)


def create_app(settings=None):
    settings = settings or Settings.default()
    store = Store(settings)
    models = ModelService(store)
    feed_lock = threading.Lock()
    app = FastAPI(title="HarvestShield API", version="1.1.0",
        description="Classical-ML crop price forecasts. Demo and real observations remain separate.",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
        openapi_url=None if settings.environment == "production" else "/openapi.json")
    app.state.store = store
    app.state.models = models
    app.state.settings = settings

    @app.middleware("http")
    async def security_guard(request, call_next):
        return await guard_request(request, call_next, settings)

    if settings.environment == "production":
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.exception_handler(ProjectError)
    async def project_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        import os
        return {"status": "ok", "service": "harvestshield", "version": "1.1.0",
            "today_ist": str(today_ist()), "feed_key_configured": bool(os.getenv("DATA_GOV_API_KEY", "").strip()),
            "read_only": settings.read_only, "admin_auth_required": bool(settings.admin_token)}

    @app.get("/ready")
    def ready():
        try:
            with store.connection() as conn:
                conn.execute("SELECT 1 FROM observations LIMIT 1").fetchall()
        except Exception:
            return JSONResponse({"status": "not_ready", "detail": "Storage unavailable."}, status_code=503)
        return {"status": "ready", "service": "harvestshield"}

    @app.get("/api/audit")
    def audit(mode: Mode = "demo"):
        return store.audit(mode)

    @app.get("/api/history")
    def history(mode: Mode = "demo", series_id: str = Query(default="", max_length=40), limit: int = Query(default=2000, ge=1, le=10000)):
        frame = store.frame(mode)
        if series_id:
            frame = frame[frame.series_id == series_id]
        return {"mode": mode, "synthetic": mode == "demo", "records": frame.sort_values("date").tail(limit).to_dict("records")}

    @app.post("/api/demo")
    def bootstrap_demo():
        # Reusing an existing demo never creates conflicts by regenerating rolling dates.
        frame = store.frame("demo")
        if not frame.empty:
            return {"mode": "demo", "inserted": 0, "rows": len(frame), "note": "Existing synthetic demo retained."}
        return store.ingest(demo_frame(), "demo", "SYNTHETIC: deterministic fictional demonstration; seed 42")

    @app.get("/api/template")
    def template():
        content = ",".join(CSV_COLUMNS) + "\n"
        return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=harvestshield_template.csv"})

    @app.post("/api/import")
    async def import_csv(file: UploadFile = File(...), source: str = Form(..., min_length=1, max_length=500)):
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise ProjectError("Upload a CSV file.")
        content = await file.read(20 * 1024 * 1024 + 1)
        frame = parse_csv(content)
        name = sha256(content).hexdigest() + ".csv"
        result = store.ingest(frame, "real", source, name)
        (settings.data_dir / "imports" / name).write_bytes(content)
        return result

    @app.post("/api/train")
    def train(request: TrainRequest):
        return models.train(request.mode, series_ids=request.series_ids)

    @app.get("/api/report")
    def report(mode: Mode = "demo"):
        return models.report(mode)

    @app.post("/api/backtest")
    def backtest(request: TrainRequest):
        return models.backtest(request.mode, series_ids=request.series_ids)

    @app.get("/api/backtest")
    def backtest_report(mode: Mode = "demo"):
        import json
        path = settings.artifacts_dir / "backtests" / mode / "summary.json"
        if not path.exists():
            raise ProjectError("No rolling backtest report yet. Run backtests first.", 409)
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/forecasts")
    def forecasts(mode: Mode = "demo", replay_date: date | None = None):
        return models.forecasts(mode, as_of=replay_date, historical=True) if replay_date else models.forecasts(mode)

    @app.post("/api/compare")
    def compare(request: ComparisonRequest):
        return models.compare(request.mode, request.quantity_quintals, [m.model_dump() for m in request.markets], replay_date=request.replay_date)

    @app.post("/api/feed/refresh")
    def refresh(request: FeedRequest):
        if not feed_lock.acquire(blocking=False):
            raise ProjectError("A feed refresh is already running. Wait for it to finish.", 409)
        try:
            return refresh_feed(store, **request.model_dump())
        finally:
            feed_lock.release()

    return app


app = create_app()
