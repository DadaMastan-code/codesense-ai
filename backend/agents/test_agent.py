from __future__ import annotations

import logging

from backend.models.schemas import TestCase, TestReport
from backend.utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior SDET (Software Development Engineer in Test) who writes
production-grade test suites. You think about testing the way Google's test engineering team does:
every meaningful behaviour must be covered, edge cases must be explicit, and tests must be
self-documenting.

Analyze the code and return ONLY this JSON (no other text):
{
  "test_cases": [
    {
      "name": "<test function name in snake_case>",
      "category": "<happy_path|edge_case|error_case|boundary>",
      "description": "<what this test verifies>"
    }
  ],
  "generated_code": "<complete, runnable test file as a string — escape newlines as \\n>",
  "untested_branches": ["<description of logic paths not covered by any test>"],
  "framework": "<pytest|jest|mocha|junit>"
}

Rules for generated_code:
- Write COMPLETE, immediately runnable test code
- Use the requested framework syntax correctly
- Include all necessary imports at the top
- Use descriptive test names that explain what they test
- Cover: happy path, boundary values, error cases, null/empty inputs, type edge cases
- Mock external dependencies (databases, HTTP calls, file I/O)
- Each test must have exactly one clear assertion
- Do NOT add placeholder comments like "# TODO: implement"
- The generated_code field must be a single JSON string (use \\n for newlines, \\" for quotes)

Think carefully about what can go wrong in this code and write tests that would catch those bugs.
Return ONLY valid JSON. No markdown. No prose outside the JSON."""


async def suggest(code: str, language: str, framework: str = "pytest") -> TestReport:
    user_prompt = (
        f"Language: {language}\n"
        f"Test framework: {framework}\n\n"
        f"Code to test:\n```\n{code}\n```"
    )
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt, max_tokens=6144)
        test_cases = [TestCase(**tc) for tc in data.get("test_cases", [])]
        return TestReport(
            test_cases=test_cases,
            generated_code=data.get("generated_code", ""),
            untested_branches=data.get("untested_branches", []),
            framework=data.get("framework", framework),
        )
    except Exception as exc:
        logger.error("Test agent failed: %s", exc)
        return TestReport(
            test_cases=[],
            generated_code="",
            untested_branches=[],
            framework=framework,
            error=str(exc),
        )
