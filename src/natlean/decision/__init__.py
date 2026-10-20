"""決定モデル: 前提の確かさ・推論の確かさ・分類を確率で返す部品

バックエンドは Jev（TypeSafe）、Claude、テスト用の Fake。どれも `DecisionModel` を満たす。
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Protocol, Union

from .base import Answer, Choice, DecisionError, Noul, Question
from .cache import CachedModel
from .claude import ClaudeBackend
from .fake import FakeBackend
from .jev import JevBackend

__all__ = [
    "Answer", "Choice", "Noul", "Question", "DecisionError", "DecisionModel",
    "CachedModel", "ClaudeBackend", "FakeBackend", "JevBackend", "make_backend",
]


class DecisionModel(Protocol):
    name: str      # 設定上の名前（キャッシュの鍵）
    version: str   # 応答が返した実体のバージョン（判断ログに残す）

    def ask(self, state: object, questions: Dict[str, Question]) -> Dict[str, Answer]:
        """同じ state に対する名前付きの質問群に答える。
        Noul には確率（float）、Choice には選択肢ごとの確率（dict）を返す。"""
        ...


def make_backend(name: Optional[str] = None, *, jev_model: str = "jev-latest",
                 claude_model: str = "claude-haiku-5-5", client=None) -> DecisionModel:
    """name が None なら TYPESAFE_API_KEY があれば jev、無ければ claude"""
    if name is None:
        name = "jev" if os.environ.get("TYPESAFE_API_KEY") else "claude"
    if name == "jev":
        return JevBackend(model=jev_model)
    if name == "claude":
        return ClaudeBackend(model=claude_model, client=client)
    raise ValueError(f"unknown backend: {name}")
