"""既存の1回抽出と、段（Segment → Normalize → Link）の抽出を比べる（実 API・課金あり）

    python scratchpad/compare_extract.py [examples/*.txt]
"""
import glob
import sys
import time

from natlean import JevBackend, Link, NatLean, Normalize, OneShotClaude, Segment, run_stages

jev = JevBackend()
VARIANTS = {
    "oneshot": lambda: [OneShotClaude()],
    "staged": lambda: [Segment(), Normalize(), Link(jev)],
    "staged-nonorm": lambda: [Segment(), Link(jev)],
}


def shape(arg):
    inf = [f"{'+'.join(e.premises)}->{e.conclusion}[{e.pattern}]" for e in arg.inferences]
    atk = [f"{a.kind}:{a.source}->{a.target}" for a in arg.attacks]
    kinds = "".join({"premise": "P", "intermediate": "I", "conclusion": "C", "definition": "D", "assumption": "A"}[p.kind]
                    for p in arg.props)
    return f"props={len(arg.props)}({kinds}) inf={inf} atk={atk} amb={len(arg.ambiguities)} warn={[w.code for w in arg.warnings]}"


paths = sys.argv[1:] or sorted(glob.glob("examples/*.txt"))
for path in paths:
    text = open(path, encoding="utf-8").read()
    print(f"\n== {path}: {text.strip()[:70]!r}")
    for name, make in VARIANTS.items():
        t = time.time()
        try:
            arg = run_stages(text, make())
            res = NatLean(jev, stages=make(), interpret=False).check_argument(arg)
            g = res.goals[-1] if res.goals else None
            iv = res.propagation.props[g] if g else None
            top = f"{g}: lo={iv.lo:.2f} est={iv.est:.2f} hi={iv.hi:.2f}" if iv else "no goal"
            print(f"  {name:14s} {time.time() - t:5.1f}s {shape(arg)}\n  {'':14s} goal {top}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name:14s} ERROR {type(e).__name__}: {e}")
