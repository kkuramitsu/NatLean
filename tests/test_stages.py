"""抽出の段（Segment・Normalize・Link）のオフラインテスト"""
from types import SimpleNamespace

from natlean import Draft, FakeBackend, Link, NatLean, Normalize, Segment, run_stages
from natlean.decision import Choice, Noul
from natlean.extract import ExtProp
from natlean.stages import Normalized

JA = "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"


def test_segment_splits_and_strips_connectives():
    d = Segment()(Draft(JA))
    assert d.language == "ja"
    assert [p.id for p in d.props] == ["p1", "p2", "p3"]
    assert d.props[2].quote == "ゆえに、ソクラテスは死ぬ。" and d.props[2].text == "ソクラテスは死ぬ"
    assert all(p.quote in JA for p in d.props)


def test_segment_english_keeps_decimals_and_splits_lines():
    d = Segment()(Draft("Birds fly. Pi is 3.14!\nTherefore, Tweety flies."))
    assert d.language == "en"
    assert [p.text for p in d.props] == ["Birds fly", "Pi is 3.14", "Tweety flies"]


def test_segment_output_passes_validation_without_warnings():
    arg = run_stages(JA, [Segment()])
    assert len(arg.props) == 3 and not [w for w in arg.warnings if w.code == "quote_not_found"]


class FakeClient:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(parse=self.parse)

    def parse(self, **kw):
        self.calls.append(kw)
        target = kw["messages"][0]["content"].rsplit("target:\n", 1)[1]
        return SimpleNamespace(parsed_output=Normalized(text=f"N({target})", paraphrases=["a", "b", "c"]))


def test_normalize_rewrites_text_and_limits_paraphrases_keeping_quote():
    c = FakeClient()
    d = Normalize(client=c, paraphrases=2)(Segment()(Draft(JA)))
    assert d.props[0].text == "N(人はみな死ぬ。)" and d.props[0].quote == "人はみな死ぬ。"
    assert d.props[0].paraphrases == ["a", "b"] and len(c.calls) == 3
    assert JA in c.calls[0]["messages"][0]["content"]  # 全文は文脈として渡る


def test_normalize_without_props_makes_no_call():
    c = FakeClient()
    Normalize(client=c)(Draft("x"))
    assert c.calls == []


def handler(support, rebut=(), undercut=(), pattern="deduction"):
    """support / rebut は (a, b) の本文の組、undercut は source の本文"""
    def h(state, name, q):
        if isinstance(q, Choice):
            return {k: 1.0 if k == pattern else 0.0 for k in q.criteria}
        if name == "support":
            return 0.9 if (state["a"], state["b"]) in support else 0.1
        if name == "rebut":
            return 0.9 if (state["a"], state["b"]) in rebut else 0.1
        if "source" in state and "premises" in state:
            return 0.9 if state["source"] in undercut else 0.1
        return 0.9
    return h


def segmented(text=JA):
    return Segment()(Draft(text))


def test_link_builds_inference_pattern_and_kinds():
    s = {("人はみな死ぬ", "ソクラテスは死ぬ"), ("ソクラテスは人である", "ソクラテスは死ぬ")}
    d = Link(FakeBackend(handler(s)))(segmented())
    assert [(e.premises, e.conclusion, e.pattern) for e in d.inferences] == [(["p1", "p2"], "p3", "deduction")]
    assert [p.kind for p in d.props] == ["premise", "premise", "conclusion"]
    assert d.attacks == []


def test_link_keeps_only_the_stronger_direction():
    # 両向きとも支持と判定されても、確率の高い向きだけを残す
    def h(state, name, q):
        if isinstance(q, Choice):
            return {k: 1.0 / len(q.criteria) for k in q.criteria}
        if name == "support":
            return 0.9 if (state["a"], state["b"]) == ("ソクラテスは人である", "ソクラテスは死ぬ") else (
                0.6 if (state["a"], state["b"]) == ("ソクラテスは死ぬ", "ソクラテスは人である") else 0.1)
        return 0.1
    d = Link(FakeBackend(h))(segmented("人はみな死ぬ。ソクラテスは人である。ソクラテスは死ぬ。"))
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p2"], "p3")]


def test_link_chain_marks_intermediate():
    s = {("人はみな死ぬ", "ソクラテスは人である"), ("ソクラテスは人である", "ソクラテスは死ぬ")}
    d = Link(FakeBackend(handler(s)))(segmented("人はみな死ぬ。ソクラテスは人である。ソクラテスは死ぬ。"))  # 手がかり無し
    assert [p.kind for p in d.props] == ["premise", "intermediate", "conclusion"]


def test_link_rebut_beats_weaker_support():
    d = Link(FakeBackend(handler(set(), rebut={("ソクラテスは死ぬ", "人はみな死ぬ")})))(segmented())
    assert [(a.kind, a.source, a.target) for a in d.attacks] == [("rebut", "p3", "p1")]
    assert d.inferences == []


def test_link_undercut_only_from_props_outside_the_inference():
    text = "鳥は飛ぶ。ピーちゃんは鳥である。ピーちゃんは飛ぶ。ピーちゃんは翼を折っている。"
    s = {("鳥は飛ぶ", "ピーちゃんは飛ぶ"), ("ピーちゃんは鳥である", "ピーちゃんは飛ぶ")}
    d = Link(FakeBackend(handler(s, undercut={"ピーちゃんは翼を折っている"})))(segmented(text))
    assert [(a.kind, a.source, a.target) for a in d.attacks] == [("undercut", "p4", "s1")]


def test_link_window_skips_distant_pairs():
    fake = FakeBackend(handler(set()))
    Link(fake, window=1)(segmented())
    pairs = {(s["a"], s["b"]) for s, qs in fake.calls if "a" in s}
    assert ("人はみな死ぬ", "ソクラテスは死ぬ") not in pairs and ("人はみな死ぬ", "ソクラテスは人である") in pairs


def test_staged_pipeline_runs_end_to_end_offline():
    s = {("人はみな死ぬ", "ソクラテスは死ぬ"), ("ソクラテスは人である", "ソクラテスは死ぬ")}
    fake = FakeBackend(handler(s))
    nl = NatLean(fake, stages=[Segment(), Link(fake)], interpret=False)
    res = nl.check(JA)
    assert res.goals == ["p3"] and [e.id for e in res.argument.inferences] == ["s1"]
    assert not [w for w in res.argument.warnings]


def test_segment_records_connective_cues():
    d = Segment()(Draft("ソクラテスは死ぬ。なぜなら、ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"))
    assert d.cues == {"p2": "reason", "p3": "conclusion"}
    assert [p.text for p in d.props] == ["ソクラテスは死ぬ", "ソクラテスは人である", "ソクラテスは死ぬ"]


def scored(table, default=0.1):
    """(a, b) の本文の組 → support の確率"""
    def h(state, name, q):
        if isinstance(q, Choice):
            return {k: 1.0 if k == "deduction" else 0.0 for k in q.criteria}
        if name == "support":
            return table.get((state["a"], state["b"]), default)
        return 0.1
    return h


def test_link_cue_fixes_direction_against_a_stronger_reverse_score():
    # 後件肯定: 内容だけなら「人である」→「死ぬ」の方が強いが、「ゆえに」が指す向きを採る
    t = {("人はみな死ぬ", "ソクラテスは人である"): 0.6, ("ソクラテスは死ぬ", "ソクラテスは人である"): 0.6,
         ("ソクラテスは人である", "ソクラテスは死ぬ"): 0.95}
    text = "人はみな死ぬ。ソクラテスは死ぬ。ゆえに、ソクラテスは人である。"
    d = Link(FakeBackend(scored(t)))(segmented(text))
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p1", "p2"], "p3")]
    assert [p.kind for p in d.props] == ["premise", "premise", "conclusion"]


def test_link_cue_pairs_need_only_relevance():
    # 向きが手がかりで決まる組は、低めの CUE_FLOOR 以上なら前提にする（強さは r が測る）
    t = {("人はみな死ぬ", "ソクラテスは死ぬ"): 0.15, ("ソクラテスは人である", "ソクラテスは死ぬ"): 0.4}
    d = Link(FakeBackend(scored(t)))(segmented())
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p2"], "p3")]


def test_link_cue_does_not_accept_unrelated_sentences():
    assert Link(FakeBackend(scored({}, default=0.1)))(segmented()).inferences == []


def test_link_conclusion_cue_ignores_later_sentences():
    text = "鳥は飛ぶ。ゆえに、ピーちゃんは飛ぶ。ただし、ピーちゃんはペンギンである。"
    t = {("鳥は飛ぶ", "ピーちゃんは飛ぶ"): 0.6, ("ピーちゃんはペンギンである", "ピーちゃんは飛ぶ"): 0.9}
    d = Link(FakeBackend(scored(t)))(segmented(text))
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p1"], "p2")]


def test_link_reason_cue_makes_the_reason_the_premise():
    t = {("ソクラテスは人である", "ソクラテスは死ぬ"): 0.9, ("ソクラテスは死ぬ", "ソクラテスは人である"): 0.95}
    d = Link(FakeBackend(scored(t)))(segmented("ソクラテスは死ぬ。なぜなら、ソクラテスは人である。"))
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p2"], "p1")]


def test_link_does_not_rebut_between_premise_and_conclusion():
    def h(state, name, q):
        if isinstance(q, Choice):
            return {k: 1.0 if k == "deduction" else 0.0 for k in q.criteria}
        return 0.9 if name == "support" and state["b"] == "ソクラテスは死ぬ" else (
            0.9 if name == "rebut" and state["b"] == "人はみな死ぬ" else 0.1)
    d = Link(FakeBackend(h))(segmented())
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p1", "p2"], "p3")]
    assert not [a for a in d.attacks if a.kind == "rebut" and a.target == "p1" and a.source == "p3"]


def test_link_with_cues_ignores_uncued_pairs():
    # 前提どうし（p1→p2）は強く支持と判定されても、接続語のある文章では辺にしない
    t = {("人はみな死ぬ", "ソクラテスは死ぬ"): 0.6, ("ソクラテスは人である", "ソクラテスは死ぬ"): 0.6,
         ("人はみな死ぬ", "ソクラテスは人である"): 0.95}
    d = Link(FakeBackend(scored(t)))(segmented())
    assert [(e.premises, e.conclusion) for e in d.inferences] == [(["p1", "p2"], "p3")]
