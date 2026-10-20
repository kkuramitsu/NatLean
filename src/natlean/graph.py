"""論証グラフのデータ型

命題をノード、推論をハイパーエッジ、攻撃（反駁・掘り崩し）を別の辺として持つ。
確率はすべて区間 Interval で持ち、下限 lo は依存を仮定しない安全側、est は独立を仮定した推定値。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List, Literal, Sequence

Lang = Literal["ja", "en"]
Kind = Literal["premise", "definition", "assumption", "intermediate", "conclusion"]
Pattern = Literal[
    "deduction", "restatement", "generic_application", "subclass",
    "induction", "abduction", "analogy", "causal", "authority",
]
PATTERNS = (
    "deduction", "restatement", "generic_application", "subclass",
    "induction", "abduction", "analogy", "causal", "authority",
)
# 前提が真なら結論が必ず真になるべき型。それ以外は「蓋然的に支持する」型
STRICT_PATTERNS = ("deduction", "restatement")
AttackKind = Literal["rebut", "undercut"]


@dataclass(frozen=True)
class Interval:
    lo: float
    est: float
    hi: float

    @classmethod
    def point(cls, x: float) -> "Interval":
        return cls(x, x, x)

    @classmethod
    def of(cls, values: Sequence[float]) -> "Interval":
        """プローブで得た複数の値から、最小・平均・最大の区間を作る"""
        return cls(min(values), mean(values), max(values))

    @property
    def width(self) -> float:
        return self.hi - self.lo


@dataclass
class Warn:
    """警告。表示文は i18n の `warn.<code>` を args で埋めて作る"""
    code: str
    args: Dict[str, object] = field(default_factory=dict)


@dataclass
class Prop:
    id: str
    text: str
    kind: str = "premise"
    quote: str = ""
    paraphrases: List[str] = field(default_factory=list)
    p: Interval = Interval(1.0, 1.0, 1.0)  # assume モードでは真と置く


@dataclass
class Inference:
    id: str
    premises: List[str]
    conclusion: str
    pattern: str = "deduction"
    r: Interval = Interval(1.0, 1.0, 1.0)
    pattern_probs: Dict[str, float] = field(default_factory=dict)


@dataclass
class Attack:
    """kind=rebut: source が target（命題）を否定する。strength は P(target が偽 | source が真)。
    kind=undercut: source が target（推論）の適用を無効にする。strength は適用が無効になる確率。"""
    kind: str
    source: str
    target: str
    strength: Interval = Interval(1.0, 1.0, 1.0)


@dataclass
class Argument:
    language: str = "ja"
    props: List[Prop] = field(default_factory=list)
    inferences: List[Inference] = field(default_factory=list)
    attacks: List[Attack] = field(default_factory=list)
    warnings: List[Warn] = field(default_factory=list)

    def prop(self, pid: str) -> Prop:
        return next(p for p in self.props if p.id == pid)

    def inference(self, eid: str) -> Inference:
        return next(e for e in self.inferences if e.id == eid)
