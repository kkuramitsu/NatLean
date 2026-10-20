"""確率の伝播（純関数。決定モデルは使わない）

各命題について次の3つを計算する。
  lo   依存関係を仮定しない下限。推論は r.lo × max(0, 1 - Σ(1 - 前提の lo))（Fréchet）
  hi   上限。推論は 1 - q.lo × (1 - r.hi)、反駁があればさらに 1 - (反駁の下限)
  est  独立を仮定した推定値。同じ前提が複数経路から効いても二重に掛けない

掘り崩しは推論の r を下げる: r_eff.lo = r.lo × (1 - min(1, Σ 攻撃元の hi × 適用度の hi))。
閉路上の推論と攻撃は支持に使わない。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .graph import Argument, Interval, Warn

EPS = 1e-9
WIDE = 0.2  # これより幅の広い区間は「判断が一貫しない」として警告する


@dataclass
class PropResult:
    lo: float
    est: float
    hi: float
    conflict: bool = False
    double_count: bool = False
    # 独立推定に使った葉の命題と推論の集合
    leaves: FrozenSet[str] = frozenset()
    edges: FrozenSet[str] = frozenset()
    sources: FrozenSet[str] = frozenset()  # 使った葉の命題が引用した根拠の出どころ


@dataclass
class EdgeResult:
    lo: float  # この推論だけから得た結論の下限
    hi: float
    r_eff_lo: float
    r_eff_est: float


@dataclass
class Propagation:
    props: Dict[str, PropResult] = field(default_factory=dict)
    edges: Dict[str, EdgeResult] = field(default_factory=dict)
    cyclic: List[str] = field(default_factory=list)  # 支持に使わなかった推論・攻撃の id
    warnings: List[Warn] = field(default_factory=list)


def goals(arg: Argument) -> List[str]:
    """結論の命題。無ければ他の推論の前提にならない命題、それも無ければ最後の命題"""
    ids = [p.id for p in arg.props if p.kind == "conclusion"]
    if not ids:
        used = {q for e in arg.inferences for q in e.premises}
        ids = [p.id for p in arg.props if p.id not in used and any(e.conclusion == p.id for e in arg.inferences)]
    if not ids and arg.props:
        ids = [arg.props[-1].id]
    return ids


def attack_id(i: int) -> str:
    return f"a{i + 1}"


def _cyclic_items(arg: Argument) -> Set[str]:
    """命題の依存グラフの強連結成分の内側にある推論・攻撃の id を返す"""
    concl_of = {e.id: e.conclusion for e in arg.inferences}
    edges: List[Tuple[str, str, str]] = []  # (from, to, item id)
    for e in arg.inferences:
        edges += [(q, e.conclusion, e.id) for q in e.premises]
    for i, a in enumerate(arg.attacks):
        dst = a.target if a.kind == "rebut" else concl_of.get(a.target)
        if dst is not None:
            edges.append((a.source, dst, attack_id(i)))
    succ: Dict[str, List[str]] = {}
    for u, v, _ in edges:
        succ.setdefault(u, []).append(v)

    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    stack: List[str] = []
    on: Set[str] = set()
    comp: Dict[str, int] = {}

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in succ.get(v, []):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on.discard(w)
                comp[w] = index[v]  # 成分の代表は根の index
                if w == v:
                    break

    for p in arg.props:
        if p.id not in index:
            visit(p.id)
    return {item for u, v, item in edges if comp.get(u) == comp.get(v)}


def propagate(arg: Argument, boost: Optional[Set[str]] = None, drop: Optional[Set[str]] = None) -> Propagation:
    """boost に入れた葉の命題・推論の id は確実（1）とみなし、drop に入れた攻撃の id は無視する。
    最も弱い環の計算に使う"""
    boost = boost or set()
    out = Propagation()
    props = {p.id: p for p in arg.props}
    concl_of = {e.id: e.conclusion for e in arg.inferences}
    out.cyclic = sorted(_cyclic_items(arg))
    dropped = set(out.cyclic) | (drop or set())
    supports: Dict[str, list] = {}
    for e in arg.inferences:
        if e.id not in dropped:
            supports.setdefault(e.conclusion, []).append(e)
    rebuts: Dict[str, list] = {}
    undercuts: Dict[str, list] = {}
    for i, a in enumerate(arg.attacks):
        if attack_id(i) in dropped:
            continue
        (rebuts if a.kind == "rebut" else undercuts).setdefault(a.target, []).append(a)

    leaf_p: Dict[str, float] = {}
    edge_val: Dict[str, float] = {}

    def value(pid: str) -> PropResult:
        if pid in out.props:
            return out.props[pid]
        sup = supports.get(pid, [])
        if not sup:
            iv = Interval.point(1.0) if pid in boost else props[pid].p
            leaf_p[pid] = iv.est
            res = PropResult(iv.lo, iv.est, iv.hi, leaves=frozenset([pid]), sources=props[pid].sources)
        else:
            res = _combine(pid, sup)
        for a in rebuts.get(pid, []):
            u = value(a.source)
            neg_lo = a.strength.lo * u.lo
            res.hi = min(res.hi, 1.0 - neg_lo)
            res.est *= 1.0 - a.strength.est * u.est
        if res.lo > res.hi + EPS:
            res.conflict = True
            out.warnings.append(Warn("conflict", {"id": pid, "lo": res.lo, "hi": res.hi}))
            res.hi = res.lo
        res.est = min(max(res.est, res.lo), res.hi)
        out.props[pid] = res
        return res

    def edge(e) -> Tuple[EdgeResult, PropResult]:
        prem = [value(q) for q in e.premises]
        q_lo = max(0.0, 1.0 - sum(1.0 - p.lo for p in prem))
        r = Interval.point(1.0) if e.id in boost else e.r
        d_hi, keep = 0.0, 1.0
        for a in undercuts.get(e.id, []):
            u = value(a.source)
            d_hi += u.hi * a.strength.hi
            keep *= 1.0 - u.est * a.strength.est
        r_lo = r.lo * (1.0 - min(1.0, d_hi))
        r_est = r.est * keep
        edge_val[e.id] = r_est
        leaves = frozenset().union(*(p.leaves for p in prem))
        edges_ = frozenset().union(*(p.edges for p in prem)) | {e.id}
        est = 1.0
        for x in leaves:
            est *= leaf_p[x]
        for x in edges_:
            est *= edge_val[x]
        er = EdgeResult(r_lo * q_lo, 1.0 - q_lo * (1.0 - r.hi), r_lo, r_est)
        sources = frozenset().union(*(p.sources for p in prem))
        return er, PropResult(er.lo, est, er.hi, leaves=leaves, edges=edges_, sources=sources)

    def _combine(pid: str, sup: list) -> PropResult:
        parts = []
        for e in sup:
            er, pr = edge(e)
            out.edges[e.id] = er
            parts.append(pr)
        lo = max(p.lo for p in parts)
        hi = min(p.hi for p in parts)
        keys = [p.leaves | p.edges for p in parts]
        pairs = [(i, j) for i in range(len(parts)) for j in range(i)]
        shared = {s for i, j in pairs for s in parts[i].sources & parts[j].sources}
        overlap = any(keys[i] & keys[j] for i, j in pairs)
        if len(parts) == 1:
            best = parts[0]
            return PropResult(lo, best.est, hi, leaves=best.leaves, edges=best.edges, sources=best.sources)
        if not overlap and not shared:
            miss = 1.0
            for p in parts:
                miss *= 1.0 - p.est
            return PropResult(lo, 1.0 - miss, hi,
                              leaves=frozenset().union(*(p.leaves for p in parts)),
                              edges=frozenset().union(*(p.edges for p in parts)),
                              sources=frozenset().union(*(p.sources for p in parts)))
        best = max(parts, key=lambda p: p.est)
        if overlap:
            out.warnings.append(Warn("double_count", {"id": pid}))
        if shared:  # 同じ出どころの根拠を独立とみなすと過大評価になる
            out.warnings.append(Warn("shared_source", {"id": pid, "source": ", ".join(sorted(shared))}))
        return PropResult(lo, best.est, hi, double_count=True, leaves=best.leaves, edges=best.edges,
                          sources=best.sources)

    for p in arg.props:
        value(p.id)
    for e in arg.inferences:  # 結論の支持に使われなかった推論（閉路上）は計算しない
        if e.id not in dropped and e.id not in out.edges:
            out.edges[e.id] = edge(e)[0]
    for item in out.cyclic:
        out.warnings.append(Warn("cycle", {"id": item}))
    return out


def weakest_links(arg: Argument, goal: str, top: int = 3) -> List[Tuple[str, str, float]]:
    """ゴールの下限を最も押し下げている要素。(種別, id, 1 に置き換えたときの下限の増分)

    種別は "leaf"（葉の前提）、"edge"（推論）、"attack"（その攻撃が無かったとしたときの増分）。"""
    base = propagate(arg).props[goal].lo
    used_edges = {e.id for e in arg.inferences}
    cands = [("edge", eid) for eid in sorted(used_edges)]
    concl = {e.conclusion for e in arg.inferences}
    cands += [("leaf", p.id) for p in arg.props if p.id not in concl]
    cands += [("attack", attack_id(i)) for i in range(len(arg.attacks))]
    gains = []
    for kind, x in cands:
        if kind == "attack":
            gain = propagate(arg, drop={x}).props[goal].lo - base
        else:
            gain = propagate(arg, {x}).props[goal].lo - base
        if gain > EPS:
            gains.append((kind, x, gain))
    return sorted(gains, key=lambda g: -g[2])[:top]


def status(res: PropResult, threshold: float) -> str:
    if res.lo >= threshold - EPS:
        return "proved"
    if res.est >= threshold - EPS:
        return "plausible"
    return "unproved"


def wide_warnings(arg: Argument) -> List[Warn]:
    """区間が広すぎる（モデルの判断が一貫しない）命題・推論の警告"""
    out = []
    for p in arg.props:
        if p.p.width > WIDE:
            out.append(Warn("wide", {"id": p.id, "lo": p.p.lo, "hi": p.p.hi}))
    for e in arg.inferences:
        if e.r.width > WIDE:
            out.append(Warn("wide", {"id": e.id, "lo": e.r.lo, "hi": e.r.hi}))
    return out
