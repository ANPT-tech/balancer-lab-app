import asyncio
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

STARTED_MONOTONIC = time.monotonic()
STARTED_AT = datetime.now(timezone.utc)

HOSTNAME = socket.gethostname()
INSTANCE_ID = os.getenv("INSTANCE_ID", HOSTNAME)

app = FastAPI(
    title="Balancer Lab App",
    description="Stateless backend for load-balancing laboratory work.",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def backend_info(request_id: str | None = None) -> dict:
    return {
        "instance_id": INSTANCE_ID,
        "hostname": HOSTNAME,
        "pid": os.getpid(),
        "request_id": request_id,
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": round(time.monotonic() - STARTED_MONOTONIC, 3),
        "server_time": utc_now(),
    }


@app.middleware("http")
async def diagnostics_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Backend-Node"] = INSTANCE_ID
    response.headers["X-Backend-Hostname"] = HOSTNAME
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/backend-info")
async def get_backend_info(request: Request):
    """
    Returns information that uniquely identifies the backend instance
    that handled this request.
    """
    return backend_info(request.state.request_id)


@app.get("/api/async-work")
async def async_work(
    request: Request,
    delay_ms: int = Query(default=500, ge=0, le=5000),
):
    """
    Demonstrates non-blocking asynchronous request handling.
    asyncio.sleep() does not block the event loop.
    """
    started = time.monotonic()
    await asyncio.sleep(delay_ms / 1000)
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)

    return {
        "message": "Async work completed",
        "requested_delay_ms": delay_ms,
        "elapsed_ms": elapsed_ms,
        **backend_info(request.state.request_id),
    }


@app.get("/health/live")
async def liveness():
    return {
        "status": "ok",
        "instance_id": INSTANCE_ID,
        "hostname": HOSTNAME,
    }


@app.get("/health/ready")
async def readiness():
    # The app is stateless and has no external storage dependency,
    # so readiness only depends on the process being able to answer.
    return {
        "status": "ready",
        "instance_id": INSTANCE_ID,
        "hostname": HOSTNAME,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Keep diagnostic node identity even for unexpected errors.
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "instance_id": INSTANCE_ID,
            "request_id": getattr(request.state, "request_id", None),
        },
        headers={"X-Backend-Node": INSTANCE_ID},
    )
