"""
FastAPI entry point for Scrutiny.

Serves a static SPA from web/ and exposes audit + rubric endpoints.
Designed for Hugging Face Spaces deployment.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fdcpa_audit.evaluator import evaluate_audit_request
from fdcpa_audit.llm import get_llm_client
from fdcpa_audit.models import AuditRequest, ComplianceReport

WEB_DIR = Path(__file__).parent / "web"
TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

_DEMO_DIR = Path(__file__).parent
_DEMO_CACHE: dict[str, dict] = {}


def _load_demo_cache() -> None:
    """Pre-load cached demo responses from real OpenAI runs (response_oi_*.json)."""
    for path in _DEMO_DIR.glob("response_oi_*.json"):
        # Filename format: response_oi_tx_001.json → key: tx_001
        key = path.stem.replace("response_oi_", "")
        with path.open("r", encoding="utf-8") as f:
            _DEMO_CACHE[key] = json.load(f)
    print(f"[Scrutiny] Loaded {len(_DEMO_CACHE)} demo responses from OpenAI runs.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_demo_cache()
    provider = os.environ.get("LLM_PROVIDER", "huggingface").lower().strip()
    key_map = {
        "huggingface": "HF_TOKEN",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    missing_key = key_map.get(provider)

    if missing_key and not os.environ.get(missing_key):
        app.state.server_key_configured = False
        print("=" * 60)
        print("SCRUTINY: No server-side LLM key configured.")
        print("  Demo mode is available for preset transcripts.")
        print("  Visitors can provide their own API key for custom transcripts.")
        print("=" * 60)
    else:
        try:
            get_llm_client()
            app.state.server_key_configured = True
            print("[Scrutiny] Server-side LLM client initialized successfully.")
        except Exception as exc:
            app.state.server_key_configured = False
            print("=" * 60)
            print("SCRUTINY: Server-side LLM client initialization FAILED.")
            print(f"  Reason: {exc}")
            print("=" * 60)
    yield


app = FastAPI(
    title="Scrutiny",
    description="What your QA misses in 60 minutes, Scrutiny finds in 60 seconds.",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit", response_model=ComplianceReport)
def api_audit(request: AuditRequest) -> ComplianceReport:
    """Evaluate a transcript + metadata against the FDCPA rubric.

    Demo mode: if request.demo=True and the transcript_id matches a preset,
    returns a cached response instantly with no LLM call.

    Custom evaluation: requires a server-side key or a visitor-provided
    provider_api_key.
    """
    # 1. Demo mode — serve cached response for known presets
    if request.demo:
        cached = _DEMO_CACHE.get(request.transcript.transcript_id)
        if cached:
            report = ComplianceReport(**cached)
            report.demo = True
            return report
        raise HTTPException(
            status_code=404,
            detail=f"Demo response not found for '{request.transcript.transcript_id}'. "
            "Available demos: " + ", ".join(_DEMO_CACHE.keys()),
        )

    # 2. Real evaluation — need a key somewhere
    has_server_key = getattr(app.state, "server_key_configured", False)
    has_visitor_key = bool(request.provider_api_key)

    if not has_server_key and not has_visitor_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM API key available.\n\n"
                "Options:\n"
                "1. Select a preset transcript and enable Demo Mode (instant, no key needed).\n"
                "2. Provide your own API key in the settings panel.\n"
                "3. Ask the space owner to configure a server-side key."
            ),
        )

    try:
        report = evaluate_audit_request(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}")
    return report


@app.get("/api/rubric")
def api_rubric() -> dict:
    """Return the FDCPA rubric for display in the frontend."""
    rubric_path = Path(__file__).parent / "fdcpa_rubric.json"
    with rubric_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# Static files
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if TRANSCRIPTS_DIR.exists():
    app.mount("/transcripts", StaticFiles(directory=TRANSCRIPTS_DIR), name="transcripts")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="index.html not found")
