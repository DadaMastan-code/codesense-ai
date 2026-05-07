from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)

_GROQ_BASE = "https://api.groq.com/openai/v1"
_OPENAI_BASE = "https://api.openai.com/v1"


async def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Call the preferred LLM provider; fall back to OpenAI if Groq fails."""
    settings = get_settings()
    temp = temperature if temperature is not None else settings.temperature
    tokens = max_tokens if max_tokens is not None else settings.max_tokens

    if settings.groq_api_key:
        try:
            return await _call_openai_compatible(
                _GROQ_BASE,
                settings.groq_api_key,
                settings.groq_model,
                system_prompt,
                user_prompt,
                temp,
                tokens,
                settings.request_timeout,
            )
        except Exception as exc:
            logger.warning("Groq call failed: %s — falling back to OpenAI", exc)

    if settings.openai_api_key:
        return await _call_openai_compatible(
            _OPENAI_BASE,
            settings.openai_api_key,
            settings.openai_model,
            system_prompt,
            user_prompt,
            temp,
            tokens,
            settings.request_timeout,
        )

    raise RuntimeError("No LLM API key configured. Set GROQ_API_KEY or OPENAI_API_KEY.")


def extract_json(raw: str) -> Any:
    """Strip markdown fences and parse JSON from an LLM response."""
    cleaned = raw.strip()
    # Remove ```json ... ``` wrappers
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # drop first and last fence lines
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()
    return json.loads(cleaned)


async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    retry: bool = True,
) -> Any:
    """Call LLM and parse the result as JSON, with one retry on parse failure."""
    raw = await call_llm(system_prompt, user_prompt, temperature, max_tokens)
    try:
        return extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        if not retry:
            raise
        logger.warning("JSON parse failed (%s) — retrying with stricter prompt", exc)
        strict_system = system_prompt + (
            "\n\nCRITICAL: Your entire response MUST be valid JSON only. "
            "No prose, no markdown, no explanation. Start with { or [."
        )
        raw2 = await call_llm(strict_system, user_prompt, temperature, max_tokens)
        return extract_json(raw2)
