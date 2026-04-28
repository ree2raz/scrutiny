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

_CONFIG_MSG = (
    "LLM provider not configured. "
    "Set LLM_PROVIDER (huggingface, anthropic, openai, or openrouter) and the corresponding "
    "API key (HF_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY) in your .env file."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = os.environ.get("LLM_PROVIDER", "huggingface").lower().strip()
    key_map = {
        "huggingface": "HF_TOKEN",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    missing_key = key_map.get(provider)

    if missing_key and not os.environ.get(missing_key):
        app.state.llm_configured = False
        app.state.config_error = _CONFIG_MSG
        print("=" * 60)
        print("SCRUTINY: LLM provider is NOT configured.")
        print(f"  Expected environment variable: {missing_key}")
        print("  Please set it in your .env file or Hugging Face Space secrets.")
        print("=" * 60)
    else:
        try:
            get_llm_client()
            app.state.llm_configured = True
            app.state.config_error = None
            print("[Scrutiny] LLM client initialized successfully.")
        except Exception as exc:
            app.state.llm_configured = False
            app.state.config_error = _CONFIG_MSG
            print("=" * 60)
            print("SCRUTINY: LLM client initialization FAILED.")
            print(f"  Reason: {exc}")
            print("  Please check your API key and LLM_PROVIDER settings.")
            print("=" * 60)
    yield


app = FastAPI(
    title="Scrutiny",
    description="What your QA misses in 60 minutes, Scrutiny finds in 60 seconds.",
    version="0.2.0",
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

    Returns a ComplianceReport with per-rule results, aggregate scores,
    and a narrative summary.
    """
    if not getattr(app.state, "llm_configured", False):
        raise HTTPException(
            status_code=503,
            detail=getattr(app.state, "config_error", None) or _CONFIG_MSG,
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
