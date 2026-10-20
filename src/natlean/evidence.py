"""根拠文書の検索

ユーザーが指定したファイルを passage に分け、命題と文字 2-gram の重なりが大きいものを返す。
1ファイルを1つの出どころ（source）として扱う。埋め込みは使わない（日英どちらでも動かすため）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

MAX_CHARS = 600     # passage の最大の長さ
TOP_K = 3           # 命題あたりの passage の数
MIN_SCORE = 0.2     # 命題の 2-gram のうち passage に現れる割合の下限
EXTENSIONS = (".txt", ".md")


@dataclass(frozen=True)
class Passage:
    source: str   # 出どころ（ファイル名）
    index: int    # 出どころの中での passage の番号（1 始まり）
    text: str


def _bigrams(text: str) -> Set[str]:
    s = re.sub(r"[\s\W_]+", "", text.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s} - {""}


def split_passages(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    """空行で段落に分け、長い段落は文の区切りでまとめ直して max_chars 以内にする"""
    out: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        sentences = re.findall(r".+?(?:[。．.!?！？]+|$)\s*", para, flags=re.S)
        buf = ""
        for sent in sentences:
            if buf and len(buf) + len(sent) > max_chars:
                out.append(buf.strip())
                buf = ""
            buf += sent
            while len(buf) > max_chars:  # 句点の無い長い文は強制的に切る
                out.append(buf[:max_chars].strip())
                buf = buf[max_chars:]
        if buf.strip():
            out.append(buf.strip())
    return out


class EvidenceIndex:
    def __init__(self, docs: Dict[str, str], max_chars: int = MAX_CHARS):
        self.passages: List[Passage] = []
        for source, text in docs.items():
            for i, p in enumerate(split_passages(text, max_chars), 1):
                self.passages.append(Passage(source, i, p))
        self._grams = [_bigrams(p.text) for p in self.passages]

    @classmethod
    def from_paths(cls, paths: Iterable[str]) -> "EvidenceIndex":
        """ファイルまたはディレクトリ（直下の .txt / .md）から作る"""
        docs: Dict[str, str] = {}
        for path in paths:
            files = ([os.path.join(path, f) for f in sorted(os.listdir(path)) if f.endswith(EXTENSIONS)]
                     if os.path.isdir(path) else [path])
            for f in files:
                with open(f, encoding="utf-8") as fh:
                    docs[os.path.basename(f)] = fh.read()
        return cls(docs)

    def search(self, query: str, k: int = TOP_K, min_score: float = MIN_SCORE) -> List[Tuple[Passage, float]]:
        q = _bigrams(query)
        if not q:
            return []
        scored = [(p, len(q & g) / len(q)) for p, g in zip(self.passages, self._grams)]
        hits = [(p, s) for p, s in scored if s >= min_score]
        return sorted(hits, key=lambda h: -h[1])[:k]
