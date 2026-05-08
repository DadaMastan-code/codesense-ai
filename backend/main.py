from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from backend.agents import fix_agent, test_agent
from backend.api.evolution_route import router as evolution_router
from backend.api.github_webhook import router as webhook_router
from backend.config import get_settings
from backend.models.schemas import (
    AnalyzeRequest,
    FixReport,
    FixRequest,
    FullAnalysisResponse,
    GenerateTestsRequest,
    HealthResponse,
    SupportedLanguagesResponse,
    TestReport,
)
from backend.pipelines.orchestrator import run_full_analysis, stream_analysis
from backend.utils.language_detector import SUPPORTED_LANGUAGES, detect_language

# ── Logging ───────────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CodeSense AI",
    description="Multi-agent AI platform for production-grade code analysis",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(evolution_router)

# ── In-memory rate limiter ────────────────────────────────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)

_RATE_LIMITED_PATHS = {"/analyze", "/analyze/stream", "/fix", "/generate-tests"}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in _RATE_LIMITED_PATHS:
        ip = request.client.host if request.client else "unknown"
        settings = get_settings()
        limit = settings.rate_limit_per_minute
        now = time.time()
        window = 60.0
        _rate_store[ip] = [t for t in _rate_store[ip] if now - t < window]
        if len(_rate_store[ip]) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {limit} requests/minute"},
            )
        _rate_store[ip].append(now)
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = round((time.monotonic() - start) * 1000, 1)
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=elapsed,
    )
    return response


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        provider=settings.primary_llm_provider,
        model=settings.groq_model if settings.groq_api_key else settings.openai_model,
    )


@app.get("/supported-languages", response_model=SupportedLanguagesResponse)
async def supported_languages():
    return SupportedLanguagesResponse(languages=SUPPORTED_LANGUAGES)


@app.post("/analyze", response_model=FullAnalysisResponse)
async def analyze(body: AnalyzeRequest):
    settings = get_settings()
    if not settings.has_any_llm_key:
        raise HTTPException(
            status_code=503,
            detail="No LLM API key configured. Set GROQ_API_KEY or OPENAI_API_KEY.",
        )
    log.info("analyze_request", code_length=len(body.code), language=body.language)
    return await run_full_analysis(body.code, body.language, body.context)


@app.post("/analyze/stream")
async def analyze_stream(body: AnalyzeRequest):
    """Server-Sent Events endpoint — streams results agent by agent."""
    settings = get_settings()
    if not settings.has_any_llm_key:
        raise HTTPException(status_code=503, detail="No LLM API key configured.")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for agent_name, result in stream_analysis(body.code, body.language, body.context):
                if hasattr(result, "model_dump"):
                    payload = result.model_dump()
                elif isinstance(result, dict):
                    payload = result
                else:
                    payload = {"data": str(result)}
                data = json.dumps({"agent": agent_name, "result": payload})
                yield f"data: {data}\n\n"
        except Exception as exc:
            log.error("stream_error", error=str(exc))
            yield f"data: {json.dumps({'agent': 'error', 'result': {'error': str(exc)}})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/fix", response_model=FixReport)
async def fix(body: FixRequest):
    settings = get_settings()
    if not settings.has_any_llm_key:
        raise HTTPException(status_code=503, detail="No LLM API key configured.")
    language = detect_language(body.code)
    return await fix_agent.apply_fixes(body.code, language, body.issues)


@app.post("/generate-tests", response_model=TestReport)
async def generate_tests(body: GenerateTestsRequest):
    settings = get_settings()
    if not settings.has_any_llm_key:
        raise HTTPException(status_code=503, detail="No LLM API key configured.")
    language = detect_language(body.code)
    return await test_agent.suggest(body.code, language, body.framework.value)
