"""Jev（TypeSafe の決定モデル）のバックエンド

POST /v1/systemone に {model, state, questions} を送る。state は同じリクエストの全質問で共通。
SDK は使わず HTTP を直接呼ぶ（早期アクセス中で SDK の互換性が壊れやすいため）。
"""
from __future__ import annotations

import os
import time
from typing import Dict, Optional

import httpx

from .base import Answer, Choice, DecisionError, Noul, Question

URL = "https://api.typesafe.ai/v1/systemone"
ENV_KEY = "TYPESAFE_API_KEY"
RETRY_STATUS = (429, 500, 502, 503, 504)


class JevBackend:
    def __init__(self, model: str = "jev-latest", api_key: Optional[str] = None,
                 url: str = URL, retries: int = 3, timeout: float = 60.0):
        self.name = f"jev:{model}"
        self.model = model
        self.version = model  # 最初の応答で実体（例 jev-1.13.0）に置き換わる
        self.api_key = api_key or os.environ.get(ENV_KEY)
        if not self.api_key:
            raise DecisionError(f"{ENV_KEY} is not set")
        self.url = url
        self.retries = retries
        self.http = httpx.Client(timeout=timeout)

    @staticmethod
    def _encode(q: Question) -> dict:
        if isinstance(q, Noul):
            return {"type": "noul", "instructions": q.instructions}
        return {"type": "choice", "instructions": q.instructions, "criteria": dict(q.criteria)}

    def ask(self, state: object, questions: Dict[str, Question]) -> Dict[str, Answer]:
        body = {"model": self.model, "state": state,
                "questions": {k: self._encode(q) for k, q in questions.items()}}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(self.retries + 1):
            try:
                resp = self.http.post(self.url, json=body, headers=headers)
            except httpx.TransportError as e:
                if attempt == self.retries:
                    raise DecisionError(f"Jev request failed: {e}") from e
            else:
                if resp.status_code == 200:
                    break
                if resp.status_code not in RETRY_STATUS or attempt == self.retries:
                    raise DecisionError(f"Jev returned HTTP {resp.status_code}: {resp.text[:200]}")
            time.sleep(2 ** attempt)
        data = resp.json()
        self.version = data.get("model", self.version)
        out: Dict[str, Answer] = {}
        for k, a in data["answers"].items():
            out[k] = a["noul"] if a["type"] == "noul" else dict(a["probabilities"])
        return out
