"""NatLean: 自然言語版 Lean（試作）

文章を主張(Claim)に分割し、文間の推論パターン（演繹・帰納など）を判定し、
各推論ステップの妥当性を軽量LLM(Haiku)で確率的にチェックする。

CLI は natlean.cli を参照。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-haiku-5-5"

Role = Literal["premise", "definition", "inference", "conclusion"]
Pattern = Literal[
    "none", "deduction", "induction", "abduction",
    "analogy", "causal", "restatement", "example",
]
Label = Literal["valid", "plausible", "weak", "invalid", "contradicts"]

# ラベル → 数値スコア
LABEL_SCORE = {"valid": 1.0, "plausible": 0.75, "weak": 0.4, "invalid": 0.1, "contradicts": 0.0}

# 推論パターンごとの信頼度の上限（演繹は必然、帰納・類推は蓋然的）
PATTERN_CAP = {
    "none": 1.0, "deduction": 1.0, "restatement": 1.0, "example": 0.9,
    "induction": 0.8, "abduction": 0.7, "causal": 0.7, "analogy": 0.6,
}

# パターンごとの検証観点
PATTERN_CRITERIA = {
    "deduction": "前提がすべて真なら結論は必ず真か。反例となる状況を構成できないか。"
                 "後件肯定・前件否定・媒概念不周延などの形式的誤謬がないか。",
    "induction": "事例の数と代表性は十分か。過度な一般化になっていないか。",
    "abduction": "他にもっともらしい説明はないか。最良の説明と言えるか。",
    "analogy": "類似点は結論に関係する本質的な点か。重要な相違点はないか。",
    "causal": "相関と因果を混同していないか。交絡要因や逆因果の可能性はないか。",
    "restatement": "意味が変わっていないか。強めたり弱めたりしていないか。",
    "example": "例は主張を正しく具体化しているか。",
}


# ---------- LLM 出力スキーマ ----------

class ParsedClaim(BaseModel):
    id: str
    text: str
    role: Role
    depends_on: List[str]
    pattern: Pattern


class ParsedArgument(BaseModel):
    claims: List[ParsedClaim]


class StepJudgement(BaseModel):
    label: Label
    reason: str


# ---------- 内部データ ----------

@dataclass
class Verdict:
    score: float
    spread: float
    labels: List[str]
    reason: str


@dataclass
class Claim:
    id: str
    text: str
    role: str
    depends_on: List[str] = field(default_factory=list)
    pattern: str = "none"
    verdict: Optional[Verdict] = None
    conf: float = 1.0

    @property
    def is_step(self) -> bool:
        return bool(self.depends_on) and self.role in ("inference", "conclusion")


SEGMENT_SYSTEM = """あなたは論証の構造解析器です。与えられた文章を、検証可能な原子的主張(claim)に分割してください。

規則:
- 1つの claim は1つの命題。複文（「AなのでB」）は A と B に分ける。
- 「ゆえに」「したがって」「なので」などの接続語は text から除き、構造(depends_on)で表す。
- id は c1, c2, ... と出現順に振る。
- role: premise（根拠なく置かれた前提）/ definition（定義）/ inference（途中の推論）/ conclusion（最終結論）
- depends_on: その claim を導くのに使われた先行 claim の id。前提・定義は空リスト。
- pattern: depends_on からその claim への推論の型。
  deduction（演繹）/ induction（帰納）/ abduction（仮説形成）/ analogy（類推）/
  causal（因果）/ restatement（言い換え）/ example（例示）。前提・定義は none。
- 推論が妥当かどうかは判断しない。書かれている構造をそのまま抽出する。"""

CHECK_SYSTEM = """あなたは論証の1ステップを検証する厳密な査読者です。
前提はすべて真であると仮定し、そこから主張が導けるかだけを判定してください（前提自体の真偽は問わない）。

label:
- valid: 前提から必然的に、または推論型に照らして十分に導ける
- plausible: おおむね導けるが、暗黙の前提や小さな飛躍がある
- weak: 飛躍が大きい、根拠が不十分
- invalid: 前提から導けない（誤謬を含む）
- contradicts: 前提と矛盾する

reason は日本語で1〜2文。"""


class NatLean:
    def __init__(self, model: str = DEFAULT_MODEL, samples: int = 3,
                 client: Optional[anthropic.Anthropic] = None):
        self.model = model
        self.samples = samples
        self.client = client or anthropic.Anthropic()

    # ① ② ③ 分割・構造解析・パターン分類
    def segment(self, text: str) -> List[Claim]:
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=SEGMENT_SYSTEM,
            messages=[{"role": "user", "content": text}],
            output_format=ParsedArgument,
        )
        parsed = resp.parsed_output
        return [Claim(**c.model_dump()) for c in parsed.claims]

    # ④ 1ステップの検証（k 回サンプリングして平均）
    def _judge_once(self, premises: List[Claim], claim: Claim) -> StepJudgement:
        prem = "\n".join(f"- [{p.id}] {p.text}" for p in premises)
        criteria = PATTERN_CRITERIA.get(claim.pattern, "")
        prompt = (
            f"前提:\n{prem}\n\n"
            f"主張 [{claim.id}]: {claim.text}\n\n"
            f"推論の型: {claim.pattern}\n"
            f"検証の観点: {criteria}"
        )
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            system=CHECK_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=StepJudgement,
        )
        return resp.parsed_output

    def check_step(self, premises: List[Claim], claim: Claim) -> Verdict:
        with ThreadPoolExecutor(max_workers=self.samples) as ex:
            judgements = list(ex.map(lambda _: self._judge_once(premises, claim),
                                     range(self.samples)))
        scores = [LABEL_SCORE[j.label] for j in judgements]
        # 最も低い評価の理由を代表として残す（弱点を見せるため）
        worst = min(judgements, key=lambda j: LABEL_SCORE[j.label])
        return Verdict(score=mean(scores), spread=pstdev(scores),
                       labels=[j.label for j in judgements], reason=worst.reason)

    def check(self, text: str) -> List[Claim]:
        claims = self.segment(text)
        by_id = {c.id: c for c in claims}
        for c in claims:
            if c.is_step:
                premises = [by_id[d] for d in c.depends_on if d in by_id]
                c.verdict = self.check_step(premises, c)
        propagate(claims)
        return claims


# ⑤ 信頼度の伝播: conf = p_step × cap(pattern) × Π conf(前提)
def propagate(claims: List[Claim]) -> None:
    by_id = {c.id: c for c in claims}
    for c in claims:  # claims は出現順なので依存先は先に計算済み
        if not c.is_step or c.verdict is None:
            c.conf = 1.0
            continue
        conf = c.verdict.score * PATTERN_CAP.get(c.pattern, 1.0)
        for d in c.depends_on:
            if d in by_id:
                conf *= by_id[d].conf
        c.conf = conf


def status(conf: float, threshold: float) -> str:
    if conf >= threshold:
        return "✓"
    if conf >= 0.5:
        return "?"
    return "✗"


# ⑥ 出力
def report(claims: List[Claim], threshold: float = 0.8) -> str:
    lines = []
    for c in claims:
        if not c.is_step:
            lines.append(f"{c.id:<4}[{c.role}] {c.text}    assumed")
            continue
        deps = ",".join(c.depends_on)
        mark = status(c.conf, threshold)
        sorry = "  sorry" if mark == "✗" else ""
        lines.append(f"{c.id:<4}[{c.pattern}] {deps} ⊢ {c.text}    {mark} {c.conf:.2f}{sorry}")
        if c.verdict:
            lines.append(f"      └ {'/'.join(c.verdict.labels)}: {c.verdict.reason}")
    goals = [c for c in claims if c.role == "conclusion"] or [claims[-1]]
    for g in goals:
        ok = g.conf >= threshold
        lines.append("")
        lines.append(f"Goal {g.id}: {'PROVED' if ok else 'NOT PROVED'} (conf={g.conf:.2f})")
        if not ok:
            weakest = min((c for c in claims if c.is_step), key=lambda c: c.conf, default=None)
            if weakest:
                lines.append(f"  weakest link: {weakest.id}")
    return "\n".join(lines)
