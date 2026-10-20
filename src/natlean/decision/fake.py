"""テスト用バックエンド。handler(state, name, question) が確率を返す"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .base import Answer, Choice, Noul, Question


class FakeBackend:
    def __init__(self, handler: Optional[Callable[[object, str, Question], Answer]] = None,
                 noul: float = 0.9):
        self.name = "fake"
        self.version = "fake-1"
        self.handler = handler
        self.default = noul
        self.calls: List[Tuple[object, Dict[str, Question]]] = []

    def ask(self, state: object, questions: Dict[str, Question]) -> Dict[str, Answer]:
        self.calls.append((state, questions))
        out: Dict[str, Answer] = {}
        for k, q in questions.items():
            if self.handler is not None:
                out[k] = self.handler(state, k, q)
            elif isinstance(q, Noul):
                out[k] = self.default
            else:
                out[k] = {c: 1.0 / len(q.criteria) for c in q.criteria}
        return out
