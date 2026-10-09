"""natlean コマンド

    natlean examples/deduction.txt
    echo "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。" | natlean -
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import List, Optional

from . import __version__
from .core import DEFAULT_MODEL, NatLean, report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="natlean",
                                 description="NatLean: 自然言語の論証をステップごとにチェックする")
    ap.add_argument("file", help="入力ファイル（- で標準入力）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--samples", type=int, default=3, help="1ステップあたりの判定回数")
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    if args.file == "-":
        text = sys.stdin.read()
    else:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    claims = NatLean(model=args.model, samples=args.samples).check(text)

    if args.json:
        print(json.dumps([asdict(c) for c in claims], ensure_ascii=False, indent=2))
    else:
        print(report(claims, args.threshold))
    goals = [c for c in claims if c.role == "conclusion"] or claims[-1:]
    return 0 if all(g.conf >= args.threshold for g in goals) else 1


if __name__ == "__main__":
    sys.exit(main())
