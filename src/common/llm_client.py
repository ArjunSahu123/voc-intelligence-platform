"""Provider-agnostic structured-output LLM call.

Every module that needs the LLM to return structured data (classification,
root-cause findings, recommendations, experiment narrative, report
narrative) calls `call_structured()` here instead of instantiating a
provider SDK directly. Switching providers is one env var
(`LLM_PROVIDER=anthropic|gemini` + the matching *_API_KEY) — no call site
elsewhere in the pipeline changes.

The two providers get structured JSON out of the model differently:
- Anthropic: forced tool-use (`tool_choice`) against the exact JSON Schema —
  the most reliable structured-output mechanism Claude offers.
- Gemini: `response_mime_type="application/json"` (native JSON mode) with
  the JSON Schema embedded in the prompt as an instruction rather than
  passed as a strict `response_schema` — Gemini's schema dialect is an
  OpenAPI subset that doesn't support the same constructs our schemas use
  (e.g. nullable enums as `["string", null]`), so translating schemas
  per-provider would be extra surface area for a demo-scale project. Native
  JSON mode plus an embedded schema is reliable enough in practice; if this
  were scaling to production Gemini usage, the next step would be writing a
  proper JSON-Schema -> Gemini-Schema converter.
"""
import json

from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import (
    ACTIVE_LLM_API_KEY,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
)


def _call_anthropic(system_prompt: str | None, user_message: str, json_schema: dict, tool_name: str, max_tokens: int) -> dict:
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to .env, or set LLM_PROVIDER=gemini instead.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tool = {"name": tool_name, "description": f"Return structured output for {tool_name}.", "input_schema": json_schema}
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt or anthropic.NOT_GIVEN,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_message}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"Claude did not return a {tool_name} tool call.")


def _call_gemini(system_prompt: str | None, user_message: str, json_schema: dict, max_tokens: int) -> dict:
    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env, or set LLM_PROVIDER=anthropic instead.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        f"{user_message}\n\n"
        "Respond with ONLY a single JSON object (no markdown code fences, no commentary before or after) "
        f"matching exactly this JSON Schema:\n{json.dumps(json_schema)}"
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            # Newer Gemini models spend part of the token budget on internal
            # "thinking" before the visible answer, so max_output_tokens is
            # generously padded above the caller's requested size rather
            # than passed straight through (this pinned SDK version doesn't
            # expose a thinking_budget config to disable that behavior).
            max_output_tokens=max_tokens * 4,
            temperature=0,
        ),
    )
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def call_structured(
    user_message: str,
    json_schema: dict,
    tool_name: str,
    system_prompt: str | None = None,
    max_tokens: int = 2048,
) -> dict:
    if not ACTIVE_LLM_API_KEY:
        raise RuntimeError(
            f"No API key set for LLM_PROVIDER={LLM_PROVIDER!r}. "
            "Set ANTHROPIC_API_KEY (provider=anthropic) or GEMINI_API_KEY (provider=gemini) in .env."
        )
    if LLM_PROVIDER == "gemini":
        return _call_gemini(system_prompt, user_message, json_schema, max_tokens)
    return _call_anthropic(system_prompt, user_message, json_schema, tool_name, max_tokens)
