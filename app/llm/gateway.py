import json
import time
from typing import Literal
import httpx
from app.config import settings


class ModelGateway:
    """
    Unified Model Gateway with:
    - Tiered routing: fast 8B model for classification -> 70B/Gemini for structured extraction
    - Automatic provider fallback (Groq -> Gemini OpenAI-compatible endpoint)
    - Latency & simulated production cost tracking
    """

    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def __init__(self) -> None:
        self.call_count = 0
        self.total_latency_ms = 0.0
        self.total_estimated_cost_usd = 0.0

    def _post_chat(self, url: str, api_key: str, model: str, messages: list[dict]) -> dict:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        tier: Literal["fast", "strong"] = "strong",
    ) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        groq_model = "openai/gpt-oss-20b" if tier == "fast" else "openai/gpt-oss-120b"
        gemini_model = "gemini-2.5-flash"

        t0 = time.perf_counter()
        raw_response = None
        cost_per_1k = 0.0001 if tier == "fast" else 0.0007

        if settings.groq_api_key:
            try:
                raw_response = self._post_chat(self.GROQ_URL, settings.groq_api_key, groq_model, messages)
            except Exception:
                raw_response = None

        if raw_response is None and settings.gemini_api_key:
            raw_response = self._post_chat(self.GEMINI_URL, settings.gemini_api_key, gemini_model, messages)

        if raw_response is None:
            raise RuntimeError("No working LLM provider configured. Set GROQ_API_KEY or GEMINI_API_KEY in .env.")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        usage = raw_response.get("usage", {})
        tokens = usage.get("total_tokens", 500)

        self.call_count += 1
        self.total_latency_ms += elapsed_ms
        self.total_estimated_cost_usd += (tokens / 1000.0) * cost_per_1k

        content = raw_response["choices"][0]["message"]["content"]
        return json.loads(content)
