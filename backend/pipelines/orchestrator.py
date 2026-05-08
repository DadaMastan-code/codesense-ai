from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents import (
    architecture_agent,
    doc_agent,
    fix_agent,
    performance_agent,
    security_agent,
    test_agent,
)
from backend.models.schemas import (
    ArchitectureReport,
    CodeSenseScore,
    DocReport,
    FixReport,
    FullAnalysisResponse,
    PerformanceReport,
    SecurityReport,
    TestReport,
)
from backend.utils.language_detector import detect_language
from backend.utils.tracing import traceable

logger = logging.getLogger(__name__)


# ── LangGraph state ───────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    code: str
    language: str
    context: str
    security: SecurityReport | None
    performance: PerformanceReport | None
    architecture: ArchitectureReport | None
    tests: TestReport | None
    documentation: DocReport | None
    fix: FixReport | None
    score: CodeSenseScore | None
    started_at: float


# ── Agent nodes ───────────────────────────────────────────────────────────────

@traceable(name="security-agent")
async def _security_node(state: AnalysisState) -> dict[str, Any]:
    try:
        result = await security_agent.analyze(state["code"], state["language"])
    except Exception as exc:
        logger.error("Security agent failed: %s", exc)
        result = SecurityReport(score=50.0, error=str(exc))
    return {"security": result}


@traceable(name="performance-agent")
async def _performance_node(state: AnalysisState) -> dict[str, Any]:
    try:
        result = await performance_agent.analyze(state["code"], state["language"])
    except Exception as exc:
        logger.error("Performance agent failed: %s", exc)
        result = PerformanceReport(score=50.0, error=str(exc))
    return {"performance": result}


@traceable(name="architecture-agent")
async def _architecture_node(state: AnalysisState) -> dict[str, Any]:
    try:
        result = await architecture_agent.analyze(state["code"], state["language"])
    except Exception as exc:
        logger.error("Architecture agent failed: %s", exc)
        result = ArchitectureReport(score=50.0, error=str(exc))
    return {"architecture": result}


@traceable(name="test-agent")
async def _tests_node(state: AnalysisState) -> dict[str, Any]:
    try:
        result = await test_agent.suggest(state["code"], state["language"])
    except Exception as exc:
        logger.error("Test agent failed: %s", exc)
        result = TestReport(error=str(exc))
    return {"tests": result}


@traceable(name="documentation-agent")
async def _documentation_node(state: AnalysisState) -> dict[str, Any]:
    try:
        result = await doc_agent.analyze(state["code"], state["language"])
    except Exception as exc:
        logger.error("Documentation agent failed: %s", exc)
        result = DocReport(score=50.0, error=str(exc))
    return {"documentation": result}


@traceable(name="fix-agent")
async def _fix_node(state: AnalysisState) -> dict[str, Any]:
    all_issues: list[str] = []
    sec = state.get("security")
    perf = state.get("performance")
    arch = state.get("architecture")

    if isinstance(sec, SecurityReport):
        for f in sec.findings:
            all_issues.append(f"[SECURITY {f.severity}] {f.title}: {f.description}")
    if isinstance(perf, PerformanceReport):
        for i in perf.issues:
            all_issues.append(f"[PERFORMANCE {i.severity}] {i.title}: {i.description}")
    if isinstance(arch, ArchitectureReport):
        for s in arch.suggestions:
            all_issues.append(f"[ARCHITECTURE {s.severity}] {s.title}: {s.description}")

    try:
        fix = await fix_agent.apply_fixes(state["code"], state["language"], all_issues[:20])
    except Exception as exc:
        logger.error("Fix agent failed: %s", exc)
        fix = FixReport(fixed_code=state["code"], error=str(exc))

    sec_score = sec.score if isinstance(sec, SecurityReport) else 50.0
    perf_score = perf.score if isinstance(perf, PerformanceReport) else 50.0
    arch_score = arch.score if isinstance(arch, ArchitectureReport) else 50.0
    docs = state.get("documentation")
    doc_score = docs.score if isinstance(docs, DocReport) else 50.0

    score = CodeSenseScore.compute(
        security=sec_score,
        performance=perf_score,
        architecture=arch_score,
        documentation=doc_score,
    )

    return {"fix": fix, "score": score}


# ── Graph definition ──────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(AnalysisState)

    graph.add_node("security", _security_node)
    graph.add_node("performance", _performance_node)
    graph.add_node("architecture", _architecture_node)
    graph.add_node("tests", _tests_node)
    graph.add_node("documentation", _documentation_node)
    graph.add_node("fix", _fix_node)

    # Fan-out: all 5 analysis agents start in parallel from START
    for node in ("security", "performance", "architecture", "tests", "documentation"):
        graph.add_edge(START, node)
        # Fan-in: each analysis agent feeds into fix (fix waits for ALL 5)
        graph.add_edge(node, "fix")

    graph.add_edge("fix", END)

    return graph.compile()


_graph = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

async def run_full_analysis(
    code: str,
    language: str | None = None,
    context: str | None = None,
) -> FullAnalysisResponse:
    start = time.monotonic()
    lang = language or detect_language(code)
    logger.info("Starting LangGraph analysis | language=%s | code_length=%d", lang, len(code))

    initial: AnalysisState = {
        "code": code,
        "language": lang,
        "context": context or "",
        "security": None,
        "performance": None,
        "architecture": None,
        "tests": None,
        "documentation": None,
        "fix": None,
        "score": None,
        "started_at": start,
    }

    final = await _graph.ainvoke(initial)

    elapsed = round(time.monotonic() - start, 2)
    logger.info("LangGraph analysis complete | score=%.1f | elapsed=%.2fs",
                final["score"].total if final.get("score") else 0, elapsed)

    return FullAnalysisResponse(
        language=lang,
        score=final["score"] or CodeSenseScore.compute(50, 50, 50, 50),
        security=final["security"] or SecurityReport(score=50.0, error="Agent failed"),
        performance=final["performance"] or PerformanceReport(score=50.0, error="Agent failed"),
        architecture=final["architecture"] or ArchitectureReport(score=50.0, error="Agent failed"),
        tests=final["tests"] or TestReport(error="Agent failed"),
        documentation=final["documentation"] or DocReport(score=50.0, error="Agent failed"),
        fix=final["fix"] or FixReport(fixed_code=code, error="Fix agent failed"),
        analysis_time_seconds=elapsed,
        metadata={"context": context or "", "orchestrator": "langgraph"},
    )


async def stream_analysis(
    code: str,
    language: str | None = None,
    context: str | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yield (agent_name, result) as each node in the graph completes."""
    lang = language or detect_language(code)
    yield ("language_detected", {"language": lang})

    initial: AnalysisState = {
        "code": code,
        "language": lang,
        "context": context or "",
        "security": None,
        "performance": None,
        "architecture": None,
        "tests": None,
        "documentation": None,
        "fix": None,
        "score": None,
        "started_at": time.monotonic(),
    }

    # astream yields a dict of {node_name: node_output} after each node completes
    agent_map = {
        "security": "security",
        "performance": "performance",
        "architecture": "architecture",
        "tests": "tests",
        "documentation": "documentation",
        "fix": "fix",
    }

    async for chunk in _graph.astream(initial):
        for node_name, node_output in chunk.items():
            if node_name in agent_map:
                # node_output is the dict returned by the node; extract the value
                for key, value in node_output.items():
                    yield (key, value)
