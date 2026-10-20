"""解釈の混合と多義の誤謬の検出

曖昧さ（量化・語義）の意味の割り当て σ ごとに、影響を受ける命題を書き換えてグラフ全体を評価し、
重み w(σ) で混合する。
  L = Σ w(σ) L_σ                  （打ち切った割り当ては下限 0）
  U = Σ w(σ) U_σ + (打ち切った質量)  （打ち切った割り当ては上限 1）

意味 k を固定したとき、L_σ を 推論の妥当性 R（前提をすべて確実としたときの下限）と
前提の妥当性 P（推論をすべて確実とし攻撃を除いたときの下限）に分けて見る。
R が高い意味では P が低く、P が高い意味では R が低いとき、その語の読み替えで論証が
成り立って見えているだけなので、多義の誤謬（量化なら全称と総称の取り違え）として警告する。
P は estimate モードでしか動かない（assume モードでは前提を真と置くので P は常に 1）。
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence, Set, Tuple

from .graph import Ambiguity, Argument, Interval, Warn
from .propagate import PropResult, propagate

MAX_READINGS = 16     # 評価する割り当ての数の上限
DEPENDENT = 0.3       # 意味によって下限がこれ以上変わるなら「解釈依存」
MIN_SENSE_W = 0.1     # 解釈依存の判定に使う意味の最小の確からしさ
TRADEOFF = 0.3        # 多義の誤謬とみなす R・P の差

# 影響を受ける命題 id の集合 → その p・r・攻撃を再推定する関数
Estimator = Callable[[Argument, Set[str]], None]


@dataclass
class Mixture:
    goals: Dict[str, PropResult] = field(default_factory=dict)
    # 曖昧さ id → 意味の label → ゴール id → その意味に固定したときの下限
    marginals: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    evaluated: int = 0      # 評価した割り当ての数
    truncated: float = 0.0  # 打ち切った割り当ての質量
    warnings: List[Warn] = field(default_factory=list)


def variant(arg: Argument, assign: Dict[str, Dict[str, str]]) -> Argument:
    """assign: 曖昧さ id → {命題 id: 書き換えた文}。該当する命題の文を置き換えた複製を返す"""
    v = copy.deepcopy(arg)
    for readings in assign.values():
        for pid, text in readings.items():
            p = v.prop(pid)
            p.text, p.paraphrases = text, []
    return v


def _goal_results(arg: Argument, estimate: Estimator, touched: Set[str], goals: Sequence[str],
                  assign: Dict[str, Dict[str, str]]) -> Dict[str, Tuple[PropResult, float, float]]:
    """ゴールごとに (L・est・U の区間, 推論の妥当性 R, 前提の妥当性 P)"""
    v = variant(arg, assign)
    estimate(v, touched)
    res = propagate(v)
    concluded = {e.conclusion for e in v.inferences}
    valid = propagate(v, boost={p.id for p in v.props if p.id not in concluded})
    for e in v.inferences:
        e.r = Interval.point(1.0)
    v.attacks = []
    plaus = propagate(v)
    return {g: (res.props[g], valid.props[g].lo, plaus.props[g].lo) for g in goals}


def _assignments(ambs: List[Ambiguity], kmax: int) -> Tuple[List[Tuple[float, Tuple[int, ...]]], float]:
    """重みの大きい順に高々 kmax 個の割り当て (w, 各曖昧さの意味の番号) と、打ち切った質量"""
    combos = []
    for idx in itertools.product(*(range(len(a.senses)) for a in ambs)):
        w = 1.0
        for a, k in zip(ambs, idx):
            w *= a.senses[k].w
        combos.append((w, idx))
    combos.sort(key=lambda c: -c[0])
    kept = combos[:kmax]
    return kept, max(0.0, 1.0 - sum(w for w, _ in kept))


def mix(arg: Argument, estimate: Estimator, goals: Sequence[str], kmax: int = MAX_READINGS) -> Mixture:
    ambs = arg.ambiguities
    out = Mixture()
    if not ambs or not goals:
        return out
    touched = {q for a in ambs for q in a.props}
    kept, out.truncated = _assignments(ambs, kmax)
    if out.truncated > 1e-9:
        out.warnings.append(Warn("readings_truncated", {"mass": out.truncated}))
    lo = {g: 0.0 for g in goals}
    est = {g: 0.0 for g in goals}
    hi = {g: out.truncated for g in goals}
    # (曖昧さ id, 意味の番号) → [(w, {ゴール: (L, R, P)})]
    cond: Dict[Tuple[str, int], List[Tuple[float, Dict[str, Tuple[float, float, float]]]]] = {}
    for w, idx in kept:
        assign = {a.id: a.senses[k].readings for a, k in zip(ambs, idx)}
        res = _goal_results(arg, estimate, touched, goals, assign)
        for g in goals:
            lo[g] += w * res[g][0].lo
            est[g] += w * res[g][0].est
            hi[g] += w * res[g][0].hi
        row = {g: (res[g][0].lo, res[g][1], res[g][2]) for g in goals}
        for a, k in zip(ambs, idx):
            cond.setdefault((a.id, k), []).append((w, row))
        out.evaluated += 1
    out.goals = {g: PropResult(lo[g], min(max(est[g], lo[g]), hi[g]), max(hi[g], lo[g])) for g in goals}

    for a in ambs:
        out.marginals[a.id] = {}
        by_sense: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
        for k, s in enumerate(a.senses):
            rows = cond.get((a.id, k), [])
            tot = sum(w for w, _ in rows)
            if tot <= 0:
                continue
            by_sense[s.label] = {g: tuple(sum(w * r[g][i] for w, r in rows) / tot for i in range(3)) for g in goals}
            out.marginals[a.id][s.label] = {g: by_sense[s.label][g][0] for g in goals}
        likely = [s.label for s in a.senses if s.w >= MIN_SENSE_W and s.label in by_sense]
        for g in goals:
            out.warnings += _warn_reading(g, a, by_sense, likely)
    return out


def _warn_reading(g: str, a: Ambiguity, by_sense, likely: List[str]) -> List[Warn]:
    if len(likely) < 2:
        return []
    out = []
    ls = [(by_sense[lab][g][0], lab) for lab in likely]
    if max(ls)[0] - min(ls)[0] > DEPENDENT:
        (hi_v, hi_l), (lo_v, lo_l) = max(ls), min(ls)
        out.append(Warn("reading_dependent", {"id": g, "term": a.term, "best": hi_l, "best_lo": hi_v,
                                              "worst": lo_l, "worst_lo": lo_v}))
    valid = max(likely, key=lambda lab: by_sense[lab][g][1])
    plaus = max(likely, key=lambda lab: by_sense[lab][g][2])
    r_v, p_v = by_sense[valid][g][1:]
    r_p, p_p = by_sense[plaus][g][1:]
    if valid != plaus and r_v - r_p > TRADEOFF and p_p - p_v > TRADEOFF:
        out.append(Warn("equivocation", {"id": g, "term": a.term, "valid": valid, "valid_r": r_v, "valid_p": p_v,
                                         "plaus": plaus, "plaus_r": r_p, "plaus_p": p_p}))
    return out
