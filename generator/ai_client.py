"""
Internal AI API client using the FiservAI library.

Usage:
    client = FiservAI.FiservAI(API_KEY, API_SECRET, API_URL, temperature=0.0)
    resp = await client.chat_completion_async(question)
"""

import asyncio
from fiservai import FiservAI
from typing import List, Dict


class InternalAIClient:
    def __init__(self, endpoint: str, api_key: str, api_secret: str):
        if not endpoint:
            raise ValueError("INTERNAL_AI_ENDPOINT is not configured.")
        if not api_key:
            raise ValueError("INTERNAL_AI_KEY is not configured.")
        if not api_secret:
            raise ValueError("INTERNAL_AI_SECRET is not configured.")

        self._endpoint = endpoint
        self._api_key = api_key
        self._api_secret = api_secret

    def chat(
        self,
        model: str,
        messages: List[Dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """
        Call the FiservAI API and return the assistant reply as a string.
        Combines system + user messages into a single question string.
        """
        # Build a single question string from the messages list
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                parts.append(content)
            elif role == "user":
                parts.append(content)
        question = "\n\n".join(parts)

        # Debug: log credential shapes to terminal (not values)
        print(f"[FiservAI] endpoint  : {self._endpoint!r}")
        print(f"[FiservAI] api_key   : {self._api_key[:4]}...{self._api_key[-4:]} (len={len(self._api_key)})")
        print(f"[FiservAI] api_secret: {self._api_secret[:4]}...{self._api_secret[-4:]} (len={len(self._api_secret)})")

        client = FiservAI.FiservAI(
            self._api_key,
            self._api_secret,
            self._endpoint,
            temperature=0.0,
        )

        # Run the async call from this synchronous thread
        resp = asyncio.run(client.chat_completion_async(question))

        # Handle both plain-string and object responses
        if isinstance(resp, str):
            return resp
        # If the library returns an object, try common attribute names
        for attr in ("content", "text", "message", "result"):
            if hasattr(resp, attr):
                return getattr(resp, attr) or ""
        return str(resp)
