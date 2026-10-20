"""NatLean 本体: 抽出 → 推定 → 伝播"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

from .decision import CachedModel, DecisionModel, make_backend
from .estimate import estimate_attack, estimate_inference, estimate_prop
from .extract import DEFAULT_MODEL, extract
from .graph import PATTERNS, Argument, Interval, Warn
from .i18n import resolve_lang
from .propagate import Propagation, goals, propagate, status, weakest_links, wide_warnings


@dataclass
class Result:
    argument: Argument
    propagation: Propagation
    threshold: float
    lang: str
    backend: str = ""
    decision_version: str = ""
    goals: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """すべてのゴールが証明済みか"""
        return all(status(self.propagation.props[g], self.threshold) == "proved" for g in self.goals)

    @property
    def warnings(self) -> List[Warn]:
        return self.argument.warnings + self.propagation.warnings


class NatLean:
    def __init__(self, decision: Optional[DecisionModel] = None, *, mode: str = "assume",
                 extract_model: str = DEFAULT_MODEL, client: Optional[anthropic.Anthropic] = None,
                 paraphrases: int = 2, threshold: float = 0.8, lang: Optional[str] = None,
                 log: Optional[str] = None, workers: int = 8):
        if mode not in ("assume", "estimate"):
            raise ValueError(f"unknown mode: {mode}")
        self.decision = CachedModel(decision or make_backend(claude_model=extract_model, client=client), log)
        self.mode = mode
        self.extract_model = extract_model
        self.client = client
        self.paraphrases = paraphrases
        self.threshold = threshold
        self.lang = resolve_lang(lang)
        self.workers = workers

    def estimate(self, arg: Argument) -> None:
        """決定モデルで p・r・攻撃の強さ・パターンの分類を推定して arg に書き込む"""
        lang = arg.language if arg.language in ("ja", "en") else "en"
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            if self.mode == "estimate":
                concluded = {e.conclusion for e in arg.inferences}
                leaves = [p for p in arg.props if p.id not in concluded]
                for p, iv in zip(leaves, ex.map(lambda p: estimate_prop(self.decision, p, lang), leaves)):
                    p.p = iv
            infs = list(ex.map(lambda e: estimate_inference(self.decision, arg, e, lang), arg.inferences))
            atks = list(ex.map(lambda a: estimate_attack(self.decision, arg, a, lang), arg.attacks))
        for e, (r, probs) in zip(arg.inferences, infs):
            e.r, e.pattern_probs = r, probs
            top = max(probs, key=probs.get)
            if top != e.pattern and probs[top] >= 0.6:
                arg.warnings.append(Warn("pattern_mismatch", {"id": e.id, "given": e.pattern, "chosen": top}))
            if e.pattern == "subclass":
                arg.warnings.append(Warn("subclass", {"id": e.id}))
        for a, iv in zip(arg.attacks, atks):
            a.strength = iv

    def check_argument(self, arg: Argument) -> Result:
        self.estimate(arg)
        prop = propagate(arg)
        prop.warnings += wide_warnings(arg)
        gs = goals(arg)
        return Result(arg, prop, self.threshold, self.lang, self.decision.name, self.decision.version, gs)

    def check(self, text: str) -> Result:
        arg = extract(text, self.extract_model, self.client, self.paraphrases)
        return self.check_argument(arg)
