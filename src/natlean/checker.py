"""NatLean 本体: 抽出 → 推定 → 伝播"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Set

import anthropic

from .decision import CachedModel, DecisionModel, make_backend
from .estimate import estimate_attack, estimate_inference, estimate_prop, estimate_senses
from .extract import DEFAULT_MODEL, extract
from .graph import Argument, Warn
from .interpret import MAX_READINGS, Mixture, mix
from .i18n import resolve_lang
from .propagate import Propagation, PropResult, goals, propagate, status, wide_warnings


@dataclass
class Result:
    argument: Argument
    propagation: Propagation
    threshold: float
    lang: str
    backend: str = ""
    decision_version: str = ""
    goals: List[str] = field(default_factory=list)
    mixture: Optional[Mixture] = None

    def final(self, goal: str) -> PropResult:
        """ゴールの確率の区間。曖昧さがあれば、意味の割り当てで混合した値"""
        if self.mixture and goal in self.mixture.goals:
            return self.mixture.goals[goal]
        return self.propagation.props[goal]

    @property
    def ok(self) -> bool:
        """すべてのゴールが証明済みか"""
        return all(status(self.final(g), self.threshold) == "proved" for g in self.goals)

    @property
    def warnings(self) -> List[Warn]:
        extra = self.mixture.warnings if self.mixture else []
        return self.argument.warnings + self.propagation.warnings + extra


class NatLean:
    def __init__(self, decision: Optional[DecisionModel] = None, *, mode: str = "assume",
                 extract_model: str = DEFAULT_MODEL, client: Optional[anthropic.Anthropic] = None,
                 paraphrases: int = 2, threshold: float = 0.8, lang: Optional[str] = None,
                 log: Optional[str] = None, workers: int = 8,
                 interpret: bool = True, max_readings: int = MAX_READINGS):
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
        self.interpret = interpret
        self.max_readings = max_readings

    def estimate(self, arg: Argument, touched: Optional[Set[str]] = None) -> None:
        """決定モデルで p・r・攻撃の強さ・パターンの分類を推定して arg に書き込む。

        touched を渡すと、その命題が関わる p・r・攻撃の強さだけを再推定する（解釈ごとの書き換え用）。
        None なら全体を推定し、パターンの警告も出す。"""
        lang = arg.language if arg.language in ("ja", "en") else "en"
        full = touched is None
        hit = (lambda *ids: True) if full else (lambda *ids: any(i in touched for i in ids))
        concluded = {e.conclusion for e in arg.inferences}
        leaves = [p for p in arg.props if p.id not in concluded and hit(p.id)] if self.mode == "estimate" else []
        eis = [e for e in arg.inferences if hit(*e.premises, e.conclusion)]
        ein = {e.id for e in eis}
        ais = [a for a in arg.attacks if hit(a.source) or (a.target in ein if a.kind == "undercut" else hit(a.target))]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for p, iv in zip(leaves, ex.map(lambda p: estimate_prop(self.decision, p, lang), leaves)):
                p.p = iv
            infs = list(ex.map(lambda e: estimate_inference(self.decision, arg, e, lang), eis))
            atks = list(ex.map(lambda a: estimate_attack(self.decision, arg, a, lang), ais))
        for e, (r, probs) in zip(eis, infs):
            e.r, e.pattern_probs = r, probs
            if not full:
                continue
            top = max(probs, key=probs.get)
            if top != e.pattern and probs[top] >= 0.6:
                arg.warnings.append(Warn("pattern_mismatch", {"id": e.id, "given": e.pattern, "chosen": top}))
            if e.pattern == "subclass":
                arg.warnings.append(Warn("subclass", {"id": e.id}))
        for a, iv in zip(ais, atks):
            a.strength = iv

    def check_argument(self, arg: Argument) -> Result:
        self.estimate(arg)
        prop = propagate(arg)
        prop.warnings += wide_warnings(arg)
        gs = goals(arg)
        mixture = None
        if self.interpret and arg.ambiguities:
            lang = arg.language if arg.language in ("ja", "en") else "en"
            for a in arg.ambiguities:
                estimate_senses(self.decision, arg, a, lang)
            mixture = mix(arg, lambda v, touched: self.estimate(v, touched), gs, self.max_readings)
        return Result(arg, prop, self.threshold, self.lang, self.decision.name, self.decision.version,
                      gs, mixture)

    def check(self, text: str) -> Result:
        arg = extract(text, self.extract_model, self.client, self.paraphrases)
        return self.check_argument(arg)
