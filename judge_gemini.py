"""Gemini backend for HingeAuto judging.

Uses Google's Gemini models via their OpenAI-compatible endpoint, so the
same OpenAI-style tool envelope as the Ollama backend applies. Gemini is
vision-capable and supports function calling, which is all this needs.

Why you might pick this over Anthropic/Ollama:
  - Google AI Studio has a free tier (rate-limited) — $0 per profile.
  - gemini-2.5-flash is far stronger at structured multi-image output
    than the open Ollama vision models, while staying cheap/free.

Set in config.py:
  JUDGE_BACKEND = "gemini"
  GEMINI_MODEL  = "gemini-2.5-flash"   # or "gemini-2.5-pro" for quality

Set in your .env (or shell):
  GEMINI_API_KEY=...    # from https://aistudio.google.com/apikey

Requires the `openai` package:  pip install openai
"""

import base64
import json
import os

import config
from judge_common import (
    DECIDE_INPUT_SCHEMA,
    Decision,
    build_system_prompt,
    enforce_premade_verbatim,
)


# Gemini's OpenAI-compatible base URL.
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _client():
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "The `openai` package isn't installed (used to talk to Gemini's "
            "OpenAI-compatible endpoint). Run `pip install openai`."
        ) from e

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
        "GOOGLE_API_KEY"
    )
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a key at "
            "https://aistudio.google.com/apikey and put it in your .env as "
            "GEMINI_API_KEY=..."
        )
    base_url = getattr(config, "GEMINI_BASE_URL", None) or _GEMINI_BASE_URL
    return OpenAI(api_key=api_key, base_url=base_url)


def _tool_spec() -> dict:
    """OpenAI-compatible tool envelope wrapping the shared schema."""
    return {
        "type": "function",
        "function": {
            "name": "submit_decision",
            "description": "Submit a like/skip decision for this Hinge profile.",
            "parameters": DECIDE_INPUT_SCHEMA,
        },
    }


def _image_parts(frames: list[bytes]) -> list[dict]:
    """Each PNG frame as an OpenAI-style image_url data URI part."""
    parts = []
    for f in frames:
        b64 = base64.standard_b64encode(f).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )
    return parts


def _decision_from_args(args: dict, usage: dict) -> Decision:
    """Build Decision from a tool-call argument dict, tolerating mild
    schema drift."""
    defaults = {
        "name": "unknown",
        "decision": "skip",
        "confidence": "low",
        "reasoning": "",
        "message": "",
        "skip_reason": "other",
        "message_archetype": "empty",
        "premade_id": "",
        "prompt_referenced": "",
    }
    merged = {**defaults, **{k: v for k, v in args.items() if k in defaults}}
    if merged["decision"] not in ("like", "skip"):
        merged["decision"] = "skip"
    if merged["confidence"] not in ("low", "medium", "high"):
        merged["confidence"] = "low"
    return Decision(**merged, usage=usage)


def _try_model(client, model: str, frames: list[bytes]) -> Decision | None:
    """One judging attempt against a specific model. Returns a Decision or
    None if the model didn't emit a usable submit_decision call."""
    user_text = (
        f"Above are {len(frames)} screenshots of one Hinge profile, in order "
        "from top to bottom. Decide whether to like or skip, and call the "
        "submit_decision tool with the structured result."
    )
    user_content = [{"type": "text", "text": user_text}] + _image_parts(frames)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": user_content},
        ],
        tools=[_tool_spec()],
        tool_choice={
            "type": "function",
            "function": {"name": "submit_decision"},
        },
        temperature=0.2,
    )

    u = getattr(response, "usage", None)
    usage = {
        "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(u, "completion_tokens", 0) or 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

    choice = response.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None) or []
    for call in tool_calls:
        if call.function.name != "submit_decision":
            continue
        args = call.function.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        decision = _decision_from_args(args, usage)
        enforce_premade_verbatim(decision)
        return decision

    # Fallback: model returned JSON in content instead of a tool call.
    content = getattr(choice.message, "content", "") or ""
    if content:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start : end + 1])
                decision = _decision_from_args(data, usage)
                enforce_premade_verbatim(decision)
                return decision
            except json.JSONDecodeError:
                pass
    return None


def judge(frames: list[bytes]) -> Decision:
    """Given an ordered list of PNG frames of one profile, return a Decision.

    Tries the configured model first; if it flakes (no usable tool call,
    which gemini-2.5-flash does occasionally), falls back once to the
    stronger gemini-2.5-pro before giving up."""
    client = _client()
    primary = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    fallback = getattr(config, "GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")

    models = [primary]
    if fallback and fallback != primary:
        models.append(fallback)

    for model in models:
        try:
            decision = _try_model(client, model, frames)
        except Exception as e:
            # Network / transient API errors: let the next model (or the
            # caller's retry loop) handle it.
            if model == models[-1]:
                raise
            print(f"[gemini] {model} errored ({e!r}); trying {models[-1]}")
            continue
        if decision is not None:
            return decision
        if model != models[-1]:
            print(f"[gemini] {model} returned no decision; retrying with "
                  f"{models[-1]}")

    raise RuntimeError(
        f"Gemini ({' then '.join(models)}) did not return a usable "
        f"submit_decision call for this profile."
    )
