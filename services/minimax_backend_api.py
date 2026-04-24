from __future__ import annotations

import os
from typing import Any, Dict, Iterator

import openai

MINIMAX_MODELS = [
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
]


def is_minimax_model(model: str) -> bool:
    return str(model or "").lower().startswith("minimax")


class MinimaxBackendAPI:
    """MiniMax OpenAI-compatible API client.

    Wraps the MiniMax chat API (OpenAI-compatible) and exposes the same interface
    as OpenAIBackendAPI for text chat completions.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("MINIMAX_API_KEY", "")
        base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": 0,
                    "owned_by": "minimax",
                    "permission": [],
                    "root": model_id,
                    "parent": None,
                }
                for model_id in MINIMAX_MODELS
            ],
        }

    def chat_completions(
        self,
        messages: list[Dict[str, Any]],
        model: str = "MiniMax-M2.7",
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """Call MiniMax chat completions API with OpenAI-compatible interface.

        Notes:
        - MiniMax temperature must be in (0.0, 1.0], defaults to 1.0.
        - response_format is not supported and is omitted.
        """
        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 1.0,
            "stream": stream,
        }
        if stream:
            return self._stream_chat_completions(params)
        response = self.client.chat.completions.create(**params)
        return response.model_dump(exclude_none=True)

    def _stream_chat_completions(self, params: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        with self.client.chat.completions.create(**params) as stream:
            for chunk in stream:
                yield chunk.model_dump(exclude_none=True)
