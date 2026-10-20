"""論証の抽出（Claude 1回）と、抽出結果のコードによる検証

LLM が出した引用が原文に実在するか、参照する id が存在するかを機械的に確かめる。
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel

from .graph import Ambiguity, Argument, Attack, Inference, Prop, Sense, Warn

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_AMBIGUITIES = 4
MAX_SENSES = 3

ExtKind = Literal["premise", "definition", "assumption", "intermediate", "conclusion"]
ExtPattern = Literal[
    "deduction", "restatement", "generic_application", "subclass",
    "induction", "abduction", "analogy", "causal", "authority",
]


class ExtProp(BaseModel):
    id: str
    quote: str
    text: str
    kind: ExtKind
    paraphrases: List[str]


class ExtInference(BaseModel):
    id: str
    premises: List[str]
    conclusion: str
    pattern: ExtPattern


class ExtAttack(BaseModel):
    kind: Literal["rebut", "undercut"]
    source: str
    target: str


class ExtReading(BaseModel):
    prop: str
    text: str


class ExtSense(BaseModel):
    label: str
    description: str
    readings: List[ExtReading]


class ExtAmbiguity(BaseModel):
    kind: Literal["quantifier", "word_sense", "other"]
    term: str
    senses: List[ExtSense]


class ExtArgument(BaseModel):
    language: Literal["ja", "en"]
    props: List[ExtProp]
    inferences: List[ExtInference]
    attacks: List[ExtAttack]
    ambiguities: List[ExtAmbiguity]


EXTRACT_SYSTEM = """あなたは論証の構造解析器です。与えられた文章から、論証グラフを抽出してください。
推論が妥当かどうかは判断せず、書かれている構造をそのまま取り出します。

language: 入力の主な言語（ja または en）。text と paraphrases は必ずこの言語で書く。

props（命題）:
- 1つの命題は1つの主張。複文は分ける。「ゆえに」などの接続語は text に含めない。
- id は p1, p2, ... と出現順。省略された前提を補ってはいけない。
- quote: 命題の根拠になった原文の一部を、一字一句そのまま写す（要約・言い換え禁止）。
- text: 修辞（強調・断定・説得の言い回し）を除いた中立な1文。「誰々は〜と言う」ではなく主張そのもの。
- kind: premise（根拠なく置かれた前提）/ definition（定義）/ assumption（仮定）/
  intermediate（途中の結論）/ conclusion（最終結論）
- paraphrases: 意味を変えない言い換えを2つ。量化（すべて・たいてい・ある）を変えてはいけない。

inferences（推論）:
- id は s1, s2, ... 。premises（前提の命題 id）から conclusion（結論の命題 id）を導く。
- pattern:
  deduction（演繹: 前提が真なら必ず結論が真になる形式。後件肯定など誤った形式も、演繹のつもりなら deduction）/
  restatement（言い換え）/ generic_application（総称文「鳥は飛ぶ」の個体への適用）/
  subclass（クラスから部分クラスへ「鳥は飛ぶ→ペンギンは飛ぶ」）/ induction（帰納・一般化）/
  abduction（仮説形成）/ analogy（類推）/ causal（因果）/ authority（権威に基づく論証）

attacks（攻撃。無ければ空）:
- rebut: source の命題が target の命題を直接否定する。
- undercut: source の命題が、target の推論 id の適用を無効にする（例外の指摘など）。
  攻撃元 source は props に含まれる命題でなければならない。

ambiguities（曖昧さ。論証の成否に関わるものだけ。無ければ空。最大4件）:
- kind: quantifier（量化の曖昧さ。「鳥は飛ぶ」が全称か総称か）/
  word_sense（同じ語が複数の意味で使えるために、論証が成り立つかどうかが変わる）/ other
- term: 曖昧な語または文。
- senses: 2〜3個の意味。label は短い名前、description はその意味の説明。
  readings は、その意味で読んだときの命題の書き換え（prop は命題 id、text はその意味で書き直した中立な1文）。
  量化なら、曖昧な命題1つに対する書き換え。語義なら、その語を使うすべての命題の書き換えを、すべての意味について揃える。
- 1つの命題を複数の ambiguity に含めてはいけない。明らかに曖昧でないものは含めない。"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def build_argument(ext: ExtArgument, text: str, max_paraphrases: int = 2) -> Argument:
    """抽出結果を検証して Argument にする。不整合は警告にして捨てる"""
    arg = Argument(language=ext.language)
    source = _norm(text)
    ids = set()
    for p in ext.props:
        if p.id in ids:
            continue
        ids.add(p.id)
        arg.props.append(Prop(p.id, p.text, p.kind, p.quote, p.paraphrases[:max_paraphrases]))
        if p.quote and _norm(p.quote) not in source:
            arg.warnings.append(Warn("quote_not_found", {"id": p.id}))
    eids = set()
    for e in ext.inferences:
        missing = [q for q in e.premises + [e.conclusion] if q not in ids]
        if missing or e.id in eids:
            arg.warnings.append(Warn("dangling", {"id": e.id, "ref": ",".join(missing) or e.id}))
            continue
        eids.add(e.id)
        arg.inferences.append(Inference(e.id, list(e.premises), e.conclusion, e.pattern))
    for a in ext.attacks:
        ok_target = a.target in (ids if a.kind == "rebut" else eids)
        if a.source not in ids or not ok_target:
            arg.warnings.append(Warn("dangling", {"id": f"{a.kind}:{a.source}->{a.target}",
                                                  "ref": a.source if a.source not in ids else a.target}))
            continue
        arg.attacks.append(Attack(a.kind, a.source, a.target))
    used = set()
    for i, a in enumerate(ext.ambiguities[:MAX_AMBIGUITIES]):
        senses = [Sense(s.label, s.description, {r.prop: r.text for r in s.readings if r.prop in ids})
                  for s in a.senses[:MAX_SENSES]]
        touched = {q for s in senses for q in s.readings}
        if len(senses) < 2 or not touched or touched & used:
            arg.warnings.append(Warn("dangling", {"id": f"ambiguity:{a.term}", "ref": ",".join(sorted(touched & used)) or a.term}))
            continue
        used |= touched
        for s in senses:  # 書き換えが無い命題は原文のままとする
            for q in touched:
                s.readings.setdefault(q, arg.prop(q).text)
        arg.ambiguities.append(Ambiguity(f"m{len(arg.ambiguities) + 1}", a.kind, a.term, senses))
    if arg.props and not any(p.kind == "conclusion" for p in arg.props):
        arg.warnings.append(Warn("no_conclusion"))
    return arg


def request(text: str, model: str = DEFAULT_MODEL, client: Optional[anthropic.Anthropic] = None) -> ExtArgument:
    """Claude に論証全体を1回で抽出させる（検証前の生の結果）"""
    client = client or anthropic.Anthropic()
    resp = client.messages.parse(
        model=model, max_tokens=8192, system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": text}], output_format=ExtArgument)
    return resp.parsed_output


def extract(text: str, model: str = DEFAULT_MODEL, client: Optional[anthropic.Anthropic] = None,
            max_paraphrases: int = 2) -> Argument:
    return build_argument(request(text, model, client), text, max_paraphrases)
