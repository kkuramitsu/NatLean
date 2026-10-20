"""natlean コマンド

    natlean examples/deduction.txt
    echo "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。" | natlean - --lang ja
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .checker import NatLean
from .decision import DecisionError, make_backend
from .extract import DEFAULT_MODEL
from .i18n import resolve_lang, t
from .report import report, to_json


def build_parser(lang: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="natlean", description=t("cli.description", lang), add_help=False)
    ap.add_argument("-h", "--help", action="help", help=t("cli.help", lang))
    ap.add_argument("file", help=t("cli.file", lang))
    ap.add_argument("--lang", choices=["ja", "en"], help=t("cli.lang", lang))
    ap.add_argument("--mode", choices=["assume", "estimate"], default="assume", help=t("cli.mode", lang))
    ap.add_argument("--backend", choices=["jev", "claude"], help=t("cli.backend", lang))
    ap.add_argument("--jev-model", default="jev-latest", help=t("cli.jev_model", lang))
    ap.add_argument("--model", default=DEFAULT_MODEL, help=t("cli.model", lang))
    ap.add_argument("--threshold", type=float, default=0.8, help=t("cli.threshold", lang))
    ap.add_argument("--paraphrases", type=int, default=2, help=t("cli.paraphrases", lang))
    ap.add_argument("--no-interpret", action="store_true", help=t("cli.no_interpret", lang))
    ap.add_argument("--max-readings", type=int, default=16, help=t("cli.max_readings", lang))
    ap.add_argument("--log", help=t("cli.log", lang))
    ap.add_argument("--json", action="store_true", help=t("cli.json", lang))
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def _pre_lang(argv: List[str]) -> Optional[str]:
    """ヘルプを書く前に --lang だけ先に読む"""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = build_parser(resolve_lang(_pre_lang(argv)))
    args = ap.parse_args(argv)
    lang = resolve_lang(args.lang)

    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        if not text.strip():
            print(t("cli.error.empty", lang), file=sys.stderr)
            return 2
        decision = make_backend(args.backend, jev_model=args.jev_model, claude_model=args.model)
        res = NatLean(decision, mode=args.mode, extract_model=args.model, paraphrases=args.paraphrases,
                      threshold=args.threshold, lang=lang, log=args.log,
                      interpret=not args.no_interpret, max_readings=args.max_readings).check(text)
    except DecisionError as e:
        print(t("cli.error.generic", lang, msg=e), file=sys.stderr)
        return 2
    except OSError as e:
        print(t("cli.error.generic", lang, msg=e), file=sys.stderr)
        return 2

    print(json.dumps(to_json(res), ensure_ascii=False, indent=2) if args.json else report(res, lang))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
