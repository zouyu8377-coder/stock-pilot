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
from app.api.rotation import router as rotation_router
from app.api.agent_context import router as agent_context_router
from app.api.agent_review import router as agent_review_router
from app.core.config import settings

APP_VERSION = "v4.0.0"

app = FastAPI(
    title="Stock Copilot API",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
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
app.include_router(rotation_router, prefix="/api")
app.include_router(agent_context_router, prefix="/api")
app.include_router(agent_review_router, prefix="/api")


async def _disclosure_verification_loop() -> None:
    from app.disclosure_verification import refresh_portfolio_disclosure_verifications

    while True:
        await asyncio.to_thread(refresh_portfolio_disclosure_verifications)
        await asyncio.sleep(max(60, settings.DISCLOSURE_INDEX_CHECK_MINUTES * 60))


async def _agent_automation_loop() -> None:
    from app.agent_review.automation import (
        mark_premarket_cycle_completed,
        mark_scheduled_cycle_completed,
        run_premarket_cycle,
        run_automatic_cycle,
        should_run_premarket_cycle,
        should_run_scheduled_cycle,
    )

    while True:
        if should_run_premarket_cycle():
            try:
                await asyncio.to_thread(run_premarket_cycle)
                mark_premarket_cycle_completed()
            except Exception as exc:
                print(f"[AgentAutomation] Premarket cycle failed: {str(exc)[:500]}")
        if should_run_scheduled_cycle():
            try:
                await asyncio.to_thread(run_automatic_cycle, trigger="scheduled")
                mark_scheduled_cycle_completed()
            except Exception as exc:
                print(f"[AgentAutomation] Scheduled cycle failed: {str(exc)[:500]}")
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """Run the background cold-data refresh check on startup."""
    from app.core.data_updater import check_and_update
    from app.rotation.service import refresh_rotation_if_needed

    asyncio.create_task(check_and_update())
    asyncio.create_task(asyncio.to_thread(refresh_rotation_if_needed))
    asyncio.create_task(_disclosure_verification_loop())
    asyncio.create_task(_agent_automation_loop())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "stock-copilot-backend",
        "version": APP_VERSION,
    }
