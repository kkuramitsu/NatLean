"""決定モデルの共通の型"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Union


class DecisionError(RuntimeError):
    """決定モデルの呼び出しに失敗した"""


@dataclass(frozen=True)
class Noul:
    """はい/いいえの問い。答えは「はい」の確率"""
    instructions: str


@dataclass(frozen=True)
class Choice:
    """選択肢から選ぶ問い。criteria は 選択肢名 → 当てはまる場合の説明。答えは選択肢ごとの確率"""
    instructions: str
    criteria: Dict[str, str]


Question = Union[Noul, Choice]
Answer = Union[float, Dict[str, float]]
