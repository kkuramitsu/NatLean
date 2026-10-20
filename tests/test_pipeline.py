"""抽出の段（Stage）のオフラインテスト"""
from natlean import FakeBackend, NatLean
from natlean.extract import ExtArgument, ExtInference, ExtProp
from natlean.pipeline import Draft, OneShotClaude, run_stages

TEXT = "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"


def prop(i, quote, kind="premise"):
    return ExtProp(id=i, quote=quote, text=quote, kind=kind, paraphrases=[])


def parse_stage(draft):
    """文を句点で切って命題にする、LLM を使わない段"""
    qs = [s + "。" for s in draft.text.split("。") if s]
    draft.language = "ja"
    draft.props = [prop("p1", qs[0]), prop("p2", qs[1]), prop("p3", qs[2], "conclusion")]
    return draft


def link_stage(draft):
    draft.inferences = [ExtInference(id="s1", premises=["p1", "p2"], conclusion="p3", pattern="deduction")]
    return draft


def test_draft_roundtrip():
    ext = ExtArgument(language="ja", props=[prop("p1", "a")], inferences=[], attacks=[], ambiguities=[])
    assert Draft.from_ext("a", ext).to_ext() == ext


def test_draft_unknown_language_falls_back_to_en():
    assert Draft("x", language="fr").to_ext().language == "en"


def test_run_stages_applies_in_order_and_validates():
    arg = run_stages(TEXT, [parse_stage, link_stage])
    assert [p.id for p in arg.props] == ["p1", "p2", "p3"]
    assert [e.id for e in arg.inferences] == ["s1"]
    assert not arg.warnings


def test_run_stages_warns_on_dangling_reference_from_a_stage():
    def bad(draft):
        draft.inferences = [ExtInference(id="s1", premises=["p1", "p9"], conclusion="p3", pattern="deduction")]
        return draft
    arg = run_stages(TEXT, [parse_stage, bad])
    assert arg.inferences == [] and [w.code for w in arg.warnings] == ["dangling"]


def test_natlean_uses_custom_stages():
    nl = NatLean(FakeBackend(), stages=[parse_stage, link_stage], interpret=False)
    res = nl.check(TEXT)
    assert res.goals == ["p3"]


def test_default_stage_is_one_shot_claude():
    nl = NatLean(FakeBackend(), extract_model="m")
    assert isinstance(nl.stages[0], OneShotClaude) and nl.stages[0].model == "m"
