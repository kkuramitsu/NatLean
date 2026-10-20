"""判断ログ兼キャッシュ

(バックエンド名, state, 質問) をキーに、答えを JSONL に追記する。
同じキーの問いはファイルから返すので、判断を再現でき、増分チェックもできる。
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict
from typing import Dict, Optional

from .base import Answer, Question


class CachedModel:
    def __init__(self, inner, path: Optional[str] = None):
        self.inner = inner
        self.path = path
        self.cache: Dict[str, Answer] = {}
        self.lock = threading.Lock()
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        rec = json.loads(line)
                        self.cache[rec["key"]] = rec["answer"]
            except FileNotFoundError:
                pass

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def version(self) -> str:
        return self.inner.version

    def _key(self, state: object, qname: str, q: Question) -> str:
        blob = json.dumps([self.inner.name, state, qname, type(q).__name__, asdict(q)],
                          ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def ask(self, state: object, questions: Dict[str, Question]) -> Dict[str, Answer]:
        keys = {k: self._key(state, k, q) for k, q in questions.items()}
        with self.lock:
            hit = {k: self.cache[h] for k, h in keys.items() if h in self.cache}
        miss = {k: q for k, q in questions.items() if k not in hit}
        if miss:
            got = self.inner.ask(state, miss)
            with self.lock:
                for k, ans in got.items():
                    self.cache[keys[k]] = ans
                    if self.path:
                        rec = {"key": keys[k], "backend": self.inner.name, "version": self.inner.version,
                               "state": state, "question": asdict(miss[k]), "name": k, "answer": ans}
                        with open(self.path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            hit.update(got)
        return {k: hit[k] for k in questions}
