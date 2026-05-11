from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.api.analyze import router as analyze_router
from app.api.history import router as history_router
from app.api.deep_analyze import router as deep_analyze_router

app = FastAPI(
    title="Stock Copilot API",
    version="0.1.0",
)

# 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册接口
app.include_router(analyze_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(deep_analyze_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """应用启动时自动检查并后台更新冷数据"""
    from app.core.data_updater import check_and_update
    asyncio.create_task(check_and_update())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "stock-copilot-backend"
    }