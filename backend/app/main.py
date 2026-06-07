from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.api.analyze import router as analyze_router
from app.api.history import router as history_router
from app.api.deep_analyze import router as deep_analyze_router
from app.api.system import router as system_router
from app.api.search import router as search_router
from app.api.analysis_packet import router as analysis_packet_router
from app.api.snapshot import router as snapshot_router
from app.api.facts import router as facts_router
from app.api.portfolio import router as portfolio_router
from app.core.config import settings

APP_VERSION = "v3.6I.5"

app = FastAPI(
    title="Stock Copilot API",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(deep_analyze_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(analysis_packet_router, prefix="/api")
app.include_router(snapshot_router, prefix="/api")
app.include_router(facts_router, prefix="/api")
app.include_router(portfolio_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """Run the background cold-data refresh check on startup."""
    from app.core.data_updater import check_and_update
    asyncio.create_task(check_and_update())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "stock-copilot-backend",
        "version": APP_VERSION,
    }
