"""
Internal AI API client.

Sends OpenAI-compatible chat-completion requests to the company's internal
AI gateway, authenticating with an API key + API secret pair.

Expected request shape:
  POST  {endpoint}/chat/completions
  Headers:
    Content-Type : application/json
    X-API-Key    : <api_key>
    X-API-Secret : <api_secret>
  Body (JSON):
    { "model": "gpt-5", "messages": [...], "temperature": 0.2, "max_tokens": 4096 }

Expected response shape (OpenAI-compatible):
  { "choices": [ { "message": { "content": "..." } } ] }
"""

import requests
from typing import List, Dict


class InternalAIClient:
    def __init__(self, endpoint: str, api_key: str, api_secret: str):
        if not endpoint:
            raise ValueError("INTERNAL_AI_ENDPOINT is not configured.")
        if not api_key:
            raise ValueError("INTERNAL_AI_KEY is not configured.")
        if not api_secret:
            raise ValueError("INTERNAL_AI_SECRET is not configured.")

        self._url = endpoint.rstrip("/") + "/chat/completions"
        self._headers = {
            "Content-Type": "application/json",
            "X-API-Key":    api_key,
            "X-API-Secret": api_secret,
        }

    def chat(
        self,
        model: str,
        messages: List[Dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """
        Call the internal AI API and return the assistant reply as a string.
        Raises requests.HTTPError on non-2xx responses.
        Raises KeyError / IndexError if the response shape is unexpected.
        """
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        resp = requests.post(
            self._url,
            headers=self._headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""
