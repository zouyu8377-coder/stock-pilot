from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os

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
from app.agent_demo.api import router as collaboration_demo_router
from app.investment_agents.api import router as investment_agents_router
from app.core.config import settings

APP_VERSION = "v4.5.0"

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
app.include_router(collaboration_demo_router)
app.include_router(investment_agents_router)


async def _disclosure_verification_loop() -> None:
    from app.disclosure_verification import refresh_portfolio_disclosure_verifications

    while True:
        try:
            await asyncio.to_thread(refresh_portfolio_disclosure_verifications)
        except Exception as exc:
            print(f"[DisclosureVerification] Retry next cycle: {str(exc)[:500]}")
        await asyncio.sleep(max(60, settings.DISCLOSURE_INDEX_CHECK_MINUTES * 60))


async def _agent_automation_loop() -> None:
    from app.agent_review.workflow import start_pending_account_analysis
    from app.agent_review.automation import (
        mark_premarket_cycle_completed,
        mark_scheduled_cycle_completed,
        run_premarket_cycle,
        run_automatic_cycle,
        should_run_premarket_cycle,
        should_run_scheduled_cycle,
    )

    while True:
        try:
            from app.agent_review.plan_engine import tick, settings as plan_settings
            await asyncio.to_thread(tick)
            if plan_settings()["external_only"]:
                await asyncio.sleep(60)
                continue
            await asyncio.to_thread(start_pending_account_analysis)
            if should_run_premarket_cycle():
                await asyncio.to_thread(run_premarket_cycle)
                mark_premarket_cycle_completed()
            if should_run_scheduled_cycle():
                await asyncio.to_thread(run_automatic_cycle, trigger="scheduled")
                mark_scheduled_cycle_completed()
        except Exception as exc:
            print(f"[AgentAutomation] Retry next cycle: {str(exc)[:500]}")
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """Run the background cold-data refresh check on startup."""
    from app.core.data_updater import check_and_update
    from app.rotation.service import refresh_rotation_if_needed

    if os.environ.get("STOCK_PILOT_AUTO_DATA_SYNC", "1") != "0":
        from app.data_sync.startup import launch
        try:
            launch()
        except OSError as exc:
            print(f"[ObjectiveDataSync] Startup launch failed: {exc}")

    # The model-free Windows sync owns collection. Agent2 is explicitly user-triggered.
    # Legacy automation is opt-in to avoid two workflows racing or calling an expired provider.
    if os.environ.get("STOCK_PILOT_ENABLE_LEGACY_AUTOMATION") == "1":
        asyncio.create_task(check_and_update())
        asyncio.create_task(asyncio.to_thread(refresh_rotation_if_needed))
        asyncio.create_task(_agent_automation_loop())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "stock-copilot-backend",
        "version": APP_VERSION,
    }
