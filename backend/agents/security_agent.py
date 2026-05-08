from __future__ import annotations

import logging

from backend.models.schemas import SecurityFinding, SecurityReport
from backend.utils.llm_client import call_llm_json
from backend.utils.severity_scorer import score_from_findings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior application security engineer with OSCP and CISSP certifications.
You analyze code with the same rigour as an OWASP Top 10 security audit.

Your job: identify ALL security vulnerabilities in the provided code.

For each finding return EXACTLY this JSON structure (no other text):
{
  "findings": [
    {
      "line_number": <integer or null>,
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFO>",
      "title": "<short title>",
      "description": "<detailed description of the vulnerability>",
      "fix_recommendation": "<concrete, actionable fix with example code where possible>",
      "owasp_category": "<e.g. A03:2021 - Injection>",
      "owasp_reference": "<URL like https://owasp.org/Top10/A03_2021-Injection/>"
    }
  ],
  "summary": "<1-2 sentence overall security assessment>"
}

Check for ALL of the following:
- SQL injection, NoSQL injection, command injection, LDAP injection
- XSS (reflected, stored, DOM-based)
- Hardcoded secrets, API keys, passwords, tokens
- Insecure deserialization
- Broken authentication / missing auth checks
- Sensitive data exposure (PII in logs, unencrypted storage)
- Security misconfiguration (debug mode, permissive CORS, open redirects)
- Broken access control (IDOR, privilege escalation)
- Path traversal / directory traversal
- SSRF (Server-Side Request Forgery)
- Insecure cryptography (MD5, SHA1, weak keys, ECB mode)
- Race conditions / TOCTOU issues
- Prototype pollution (JavaScript)
- XML external entity (XXE)
- Unvalidated redirects

If no issues found, return an empty findings array with a positive summary.
Return ONLY valid JSON. No markdown. No prose outside the JSON."""


async def analyze(code: str, language: str) -> SecurityReport:
    user_prompt = f"Language: {language}\n\nCode to audit:\n```\n{code}\n```"
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
        findings = [SecurityFinding(**f) for f in data.get("findings", [])]
        severities = [f.severity for f in findings]
        return SecurityReport(
            findings=findings,
            summary=data.get("summary", ""),
            score=score_from_findings(severities),
        )
    except Exception as exc:
        logger.error("Security agent failed: %s", exc)
        return SecurityReport(
            findings=[],
            summary="Security analysis could not be completed.",
            score=50.0,
            error=str(exc),
        )
