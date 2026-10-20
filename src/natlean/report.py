"""Lean 風のテキスト出力と JSON 出力"""
from __future__ import annotations

from dataclasses import asdict
from typing import List

from .checker import Result
from .graph import Interval
from .i18n import t
from .propagate import attack_id, status, weakest_links

MARK = {"proved": "✓", "plausible": "?", "unproved": "✗"}


def _warn(w, lang: str) -> str:
    return t(f"warn.{w.code}", lang, **w.args)


def report(res: Result, lang: str = "") -> str:
    lang = lang or res.lang
    arg, prop = res.argument, res.propagation
    lines: List[str] = []
    by_concl = {}
    for e in arg.inferences:
        by_concl.setdefault(e.conclusion, []).append(e)
    for p in arg.props:
        r = res.final(p.id) if p.id in res.goals else prop.props[p.id]
        es = by_concl.get(p.id, [])
        if not es:
            tag = f"p={p.p.est:.2f}" if p.cites or p.p != Interval(1.0, 1.0, 1.0) else t("assumed", lang)
            lines.append(f"{p.id:<4}[{p.kind}] {p.text}    {tag}")
            for c in p.cites:
                rel = t(f"relation.{c.relation}", lang)
                lines.append(f"      {t('cite', lang, source=c.source, index=c.index, relation=rel, p=c.p)}")
            continue
        mark = MARK[status(r, res.threshold)]
        sorry = "  sorry" if mark == "✗" else ""
        lines.append(f"{p.id:<4}[{p.kind}] {p.text}    {mark} L={r.lo:.2f} P̂={r.est:.2f} U={r.hi:.2f}{sorry}")
        for e in es:
            premises = ", ".join(e.premises)
            lines.append(f"      {e.id}: {premises} ⊢ {e.conclusion}  [{e.pattern}]  "
                         f"r=[{e.r.lo:.2f}, {e.r.hi:.2f}]")
    for a in arg.ambiguities:
        senses = " / ".join(f"{s.label} {s.w:.2f}" for s in a.senses)
        lines.append(f"{a.id:<4}{t('readings', lang, term=a.term)} {senses}")
    for i, a in enumerate(arg.attacks):
        lines.append(f"{attack_id(i):<4}{a.source} ⊣ {a.target}  [{a.kind}]  {a.strength.est:.2f}")
    for w in res.warnings:
        lines.append(f"  ! {_warn(w, lang)}")
    for g in res.goals:
        r = res.final(g)
        lines.append("")
        lines.append(t("goal", lang, id=g, status=t(f"status.{status(r, res.threshold)}", lang), lo=r.lo))
        if status(r, res.threshold) != "proved" and not res.mixture:
            wl = weakest_links(arg, g)
            if wl:
                lines.append("  " + t("weakest", lang))
                for kind, x, gain in wl:
                    lines.append(f"    {t('weakest.' + kind, lang, id=x)} (+{gain:.2f})")
    lines.append("")
    lines.append(f"({t('legend', lang)}; {t('backend', lang, name=f'{res.backend} {res.decision_version}'.strip())})")
    return "\n".join(lines)


def _result(r) -> dict:
    d = asdict(r)
    d["leaves"], d["edges"], d["sources"] = sorted(r.leaves), sorted(r.edges), sorted(r.sources)
    return d


def to_json(res: Result) -> dict:
    """キーは言語に依存しない英語の固定名"""
    prop = res.propagation
    return {
        "language": res.argument.language,
        "backend": res.backend,
        "threshold": res.threshold,
        "ok": res.ok,
        "goals": [{"id": g, "status": status(res.final(g), res.threshold), **_result(res.final(g))}
                  for g in res.goals],
        "ambiguities": [asdict(a) for a in res.argument.ambiguities],
        "readings": ({"evaluated": res.mixture.evaluated, "truncated": res.mixture.truncated,
                      "marginals": res.mixture.marginals} if res.mixture else None),
        "props": [{**asdict(p), "result": _result(prop.props[p.id])} for p in res.argument.props],
        "inferences": [{**asdict(e), "result": asdict(prop.edges[e.id]) if e.id in prop.edges else None}
                       for e in res.argument.inferences],
        "attacks": [asdict(a) for a in res.argument.attacks],
        "warnings": [{"code": w.code, **w.args} for w in res.warnings],
    }
