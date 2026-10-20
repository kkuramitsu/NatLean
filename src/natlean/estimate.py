"""決定モデルへの問いの組み立てと、答えの区間化

論証の全文は決定モデルに見せない（論証文は読み手を説得するための文なので、全文を見せると
論理的な支持ではなく説得力を測ってしまう）。p には命題1文、r には前提と結論だけを state に入れる。
区間は、言い換え・否定・2系統の問いのずれ（最小〜最大）から作る。同じ問いの繰り返しはしない。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .decision import Choice, DecisionModel, Noul, Question
from .evidence import EvidenceIndex
from .graph import STRICT_PATTERNS, Ambiguity, Argument, Attack, Cite, Inference, Interval, Prop, Warn

# 問いのテンプレート（入力の言語で選ぶ）
Q = {
    "ja": {
        "true": "この文は真か。",
        "negate": "「{s}」というのは誤りである。",
        "holds_strict": "premises がすべて真だとして、conclusion は必ず真か。",
        "counter": "premises がすべて真で conclusion が偽となる状況はありうるか。",
        "holds_prob": "premises がすべて真だとして、conclusion は真である可能性が高いか。",
        "pattern": "premises から conclusion を導く推論は、どの型か。",
        "rebut": "source が真だとして、target は偽か。",
        "undercut": "source が真なら、premises から conclusion を導くこの推論は適用できなくなるか。",
        "sense": "この文脈で、term はどの意味で使われているか。",
        "relation": "evidence は statement を裏付けるか、否定するか、無関係か。",
        "true_given": "evidence を根拠として、statement は真か。",
    },
    "en": {
        "true": "Is this statement true?",
        "negate": 'It is false that "{s}".',
        "holds_strict": "Assuming all premises are true, must the conclusion be true?",
        "counter": "Is there a situation where all premises are true and the conclusion is false?",
        "holds_prob": "Assuming all premises are true, is the conclusion likely to be true?",
        "pattern": "What type of inference leads from the premises to the conclusion?",
        "rebut": "Assuming source is true, is target false?",
        "undercut": "If source is true, does the inference from the premises to the conclusion cease to apply?",
        "sense": "In this context, in which sense is the term used?",
        "relation": "Does the evidence support the statement, contradict it, or is it unrelated?",
        "true_given": "Taking the evidence as the basis, is the statement true?",
    },
}

# 推論パターンの説明（Choice の選択肢）
PATTERN_DOC = {
    "ja": {
        "deduction": "前提が真なら結論が必ず真になる形式（三段論法、全称の個体への適用、モーダス・ポネンスなど）",
        "restatement": "意味を変えない言い換え",
        "generic_application": "「鳥は飛ぶ」のような例外を許す一般論を個体に適用する",
        "subclass": "クラスについての主張を、その部分クラスに当てはめる",
        "induction": "いくつかの事例から一般化する",
        "abduction": "観察を最もよく説明する仮説を結論とする",
        "analogy": "似ている点から他の点も似ていると結論する",
        "causal": "原因と結果の関係を結論する",
        "authority": "権威や専門家の発言を根拠にする",
    },
    "en": {
        "deduction": "a form where true premises force the conclusion (syllogism, universal instantiation, modus ponens)",
        "restatement": "a rewording that keeps the meaning",
        "generic_application": "applying an exception-tolerant generalization such as 'birds fly' to an individual",
        "subclass": "applying a claim about a class to one of its subclasses",
        "induction": "generalizing from a few cases",
        "abduction": "concluding the hypothesis that best explains an observation",
        "analogy": "concluding that things alike in some respects are alike in another",
        "causal": "concluding a cause-and-effect relation",
        "authority": "relying on an authority or expert statement",
    },
}


# 根拠 passage と命題の関係（Choice の選択肢）
RELATION_DOC = {
    "ja": {"supports": "passage は命題を裏付ける", "contradicts": "passage は命題を否定する",
           "unrelated": "passage は命題と無関係である"},
    "en": {"supports": "the passage supports the statement", "contradicts": "the passage contradicts the statement",
           "unrelated": "the passage is unrelated to the statement"},
}
UNRELATED = 0.5  # 無関係の確率がこれ未満の passage を根拠として使う


def _noul(model: DecisionModel, state: object, instr: str) -> float:
    return model.ask(state, {"q": Noul(instr)})["q"]


def _estimate_prior(model: DecisionModel, prop: Prop, lang: str) -> Interval:
    """根拠なしの p。原文・言い換え・否定（の補数）への「真か」の答えの区間"""
    q = Q[lang]
    vals = [_noul(model, {"statement": s}, q["true"]) for s in [prop.text, *prop.paraphrases]]
    vals.append(1.0 - _noul(model, {"statement": q["negate"].format(s=prop.text)}, q["true"]))
    return Interval.of(vals)


def estimate_prop(model: DecisionModel, prop: Prop, lang: str,
                  evidence: Optional[EvidenceIndex] = None) -> Tuple[Interval, List[Cite], List[Warn]]:
    """命題の確かさ p と、引用した根拠、警告

    根拠が無ければ根拠なしの推定。根拠があれば P(命題 | passage) を passage ごとに求め、
    無関係でない passage の値（と、命題の否定への補数）の最小・平均・最大を区間とする。"""
    if evidence is None:
        return _estimate_prior(model, prop, lang), [], []
    q = Q[lang]
    cites: List[Cite] = []
    vals: List[float] = []
    for passage, _ in evidence.search(prop.text):
        state = {"statement": prop.text, "evidence": passage.text}
        ans = model.ask(state, {"rel": Choice(q["relation"], dict(RELATION_DOC[lang])),
                                "true": Noul(q["true_given"])})
        rel = ans["rel"]
        if rel.get("unrelated", 0.0) >= UNRELATED:
            continue
        neg = _noul(model, {"statement": q["negate"].format(s=prop.text), "evidence": passage.text}, q["true_given"])
        vals += [ans["true"], 1.0 - neg]
        cites.append(Cite(passage.source, passage.index,
                          "supports" if rel.get("supports", 0.0) >= rel.get("contradicts", 0.0) else "contradicts",
                          ans["true"]))
    warns: List[Warn] = []
    if not cites:
        warns.append(Warn("no_evidence", {"id": prop.id}))
        return _estimate_prior(model, prop, lang), [], warns
    if {c.relation for c in cites} == {"supports", "contradicts"}:
        warns.append(Warn("evidence_conflict", {"id": prop.id}))
    return Interval.of(vals), cites, warns


def _inference_state(arg: Argument, e: Inference, conclusion: str) -> dict:
    return {"premises": [arg.prop(q).text for q in e.premises], "conclusion": conclusion}


def estimate_inference(model: DecisionModel, arg: Argument, e: Inference,
                       lang: str) -> Tuple[Interval, Dict[str, float]]:
    """推論の確かさ r と、推論パターンの分類確率

    strict な型は「必ず真か」と「反例はありうるか（の補数）」の2系統、蓋然的な型は「可能性が高いか」で問う。
    結論の言い換えにも同じ問いを投げる。"""
    q = Q[lang]
    strict = e.pattern in STRICT_PATTERNS
    concl = arg.prop(e.conclusion)
    qs: Dict[str, Question] = {
        "holds": Noul(q["holds_strict"] if strict else q["holds_prob"]),
        "pattern": Choice(q["pattern"], dict(PATTERN_DOC[lang])),
    }
    if strict:
        qs["counter"] = Noul(q["counter"])
    ans = model.ask(_inference_state(arg, e, concl.text), qs)
    vals = [ans["holds"]]
    if strict:
        vals.append(1.0 - ans["counter"])
    for para in concl.paraphrases:
        vals.append(_noul(model, _inference_state(arg, e, para), qs["holds"].instructions))
    return Interval.of(vals), ans["pattern"]


def estimate_attack(model: DecisionModel, arg: Argument, a: Attack, lang: str) -> Interval:
    q = Q[lang]
    if a.kind == "rebut":
        state = {"source": arg.prop(a.source).text, "target": arg.prop(a.target).text}
        return Interval.point(_noul(model, state, q["rebut"]))
    e = arg.inference(a.target)
    state = {"source": arg.prop(a.source).text, **_inference_state(arg, e, arg.prop(e.conclusion).text)}
    return Interval.point(_noul(model, state, q["undercut"]))


def estimate_senses(model: DecisionModel, arg: Argument, a: Ambiguity, lang: str) -> None:
    """曖昧さ a の各意味の確からしさ w を求めて a.senses[*].w に書く（合計 1 に正規化）

    state には語と、影響を受ける命題の原文だけを入れる。"""
    state = {"term": a.term, "sentences": [arg.prop(q).text for q in a.props]}
    probs = model.ask(state, {"q": Choice(Q[lang]["sense"],
                                          {s.label: s.description or s.label for s in a.senses})})["q"]
    total = sum(probs.get(s.label, 0.0) for s in a.senses)
    for s in a.senses:
        s.w = probs.get(s.label, 0.0) / total if total > 0 else 1.0 / len(a.senses)
