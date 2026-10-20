"""抽出の段（Stage）の連なり

各段は Draft を受けて Draft を返す。段を入れ替えれば、命題の正規化だけ、辺の判定だけ、といった
差し替えができる。最後の Draft は `build_argument` が検証して Argument にする。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

import anthropic

from .extract import (DEFAULT_MODEL, ExtAmbiguity, ExtArgument, ExtAttack, ExtInference, ExtProp,
                      build_argument, request)
from .graph import Argument


@dataclass
class Draft:
    """段の間を流れる抽出途中の論証。検証前なので、参照の不整合なども含みうる"""
    text: str
    language: str = "en"
    props: List[ExtProp] = field(default_factory=list)
    inferences: List[ExtInference] = field(default_factory=list)
    attacks: List[ExtAttack] = field(default_factory=list)
    ambiguities: List[ExtAmbiguity] = field(default_factory=list)
    cues: Dict[str, str] = field(default_factory=dict)  # 命題 id → 接続語の手がかり（conclusion / reason）

    @classmethod
    def from_ext(cls, text: str, ext: ExtArgument) -> "Draft":
        return cls(text, ext.language, list(ext.props), list(ext.inferences),
                   list(ext.attacks), list(ext.ambiguities))

    def to_ext(self) -> ExtArgument:
        lang = self.language if self.language in ("ja", "en") else "en"
        return ExtArgument(language=lang, props=self.props, inferences=self.inferences,
                           attacks=self.attacks, ambiguities=self.ambiguities)


class Stage(Protocol):
    def __call__(self, draft: Draft) -> Draft:
        """draft を更新して返す（渡された draft を書き換えてもよい）"""
        ...


class OneShotClaude:
    """Claude 1回で、命題・推論・攻撃・曖昧さを全部抽出する段（従来の抽出）"""

    def __init__(self, model: str = DEFAULT_MODEL, client: Optional[anthropic.Anthropic] = None):
        self.model = model
        self.client = client

    def __call__(self, draft: Draft) -> Draft:
        return Draft.from_ext(draft.text, request(draft.text, self.model, self.client))


def run_stages(text: str, stages: Sequence[Stage], max_paraphrases: int = 2) -> Argument:
    """段を順に適用し、結果を検証して Argument にする"""
    draft = Draft(text)
    for stage in stages:
        draft = stage(draft)
    return build_argument(draft.to_ext(), text, max_paraphrases)
