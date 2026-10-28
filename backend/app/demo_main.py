"""Shareable demo server: no private account routers, background jobs, or LLM imports."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.agent_demo.api import router


def create_app():
    app = FastAPI(title="Stock-Pilot Collaboration Demo", version="4.4.0")
    origins = [v.strip() for v in os.environ.get("STOCK_PILOT_DEMO_CORS", "").split(",") if v.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "isolated-collaboration-demo", "version": "4.4.0", "model_calls": 0}

    @app.get("/")
    def home():
        return RedirectResponse("/demo.html")

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    @app.get("/demo.html")
    def page():
        target = dist / "demo.html"
        if not target.exists():
            raise HTTPException(503, "请先在 frontend 执行 npm run build，或使用 Vite 的 /demo.html")
        return FileResponse(target)

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="demo-assets")
    return app


app = create_app()
