"""解釈の混合と多義の誤謬のオフラインテスト（FakeBackend）"""
import pytest

from natlean import Argument, FakeBackend, Inference, NatLean, Prop, report, to_json
from natlean.decision import Choice
from natlean.extract import ExtAmbiguity, ExtArgument, ExtInference, ExtProp, ExtReading, ExtSense, build_argument
from natlean.graph import Ambiguity, Sense
from natlean.estimate import Q
from natlean.interpret import mix, variant

GENERIC = "鳥は典型的に飛ぶ"
UNIVERSAL = "すべての鳥は例外なく飛ぶ"


def bird_argument():
    return Argument(
        language="ja",
        props=[Prop("p1", "鳥は飛ぶ"), Prop("p2", "ピーちゃんは鳥である"), Prop("p3", "ピーちゃんは飛ぶ", "conclusion")],
        inferences=[Inference("s1", ["p1", "p2"], "p3", "generic_application")],
        ambiguities=[Ambiguity("m1", "quantifier", "鳥は飛ぶ", [
            Sense("generic", "総称", {"p1": GENERIC}),
            Sense("universal", "全称", {"p1": UNIVERSAL})])])


def handler(w_generic, r_by_reading):
    """意味の確からしさと、前提の読みごとの r を返すハンドラ"""
    def h(state, name, q):
        if isinstance(q, Choice):
            if "term" in state:
                return {"generic": w_generic, "universal": 1 - w_generic}
            return {k: 1 / len(q.criteria) for k in q.criteria}
        prem = state.get("premises", [])
        for reading, r in r_by_reading.items():
            if reading in prem:
                return asked(q, r)
        return asked(q, 0.5)
    return h


def asked(q, holds):
    """「反例はありうるか」の問いには補数を返す（厳密な型では 1 - counter も r の材料になる）"""
    return 1 - holds if q.instructions == Q["ja"]["counter"] else holds


def run(arg, fake, **kw):
    return NatLean(fake, lang="en", paraphrases=0, **kw).check_argument(arg)


def test_mixture_is_weighted_average_of_readings():
    res = run(bird_argument(), FakeBackend(handler(0.7, {GENERIC: 0.9, UNIVERSAL: 0.1})))
    g = res.final("p3")
    assert g.lo == pytest.approx(0.7 * 0.9 + 0.3 * 0.1)
    assert g.hi >= g.lo
    assert res.mixture.evaluated == 2 and res.mixture.truncated == pytest.approx(0)


def test_reading_dependence_warning_and_marginals():
    res = run(bird_argument(), FakeBackend(handler(0.6, {GENERIC: 0.9, UNIVERSAL: 0.1})))
    warns = [w for w in res.warnings if w.code == "reading_dependent"]
    assert len(warns) == 1 and warns[0].args["best"] == "generic"
    assert res.mixture.marginals["m1"]["generic"]["p3"] == pytest.approx(0.9)


def test_no_warning_when_readings_agree():
    res = run(bird_argument(), FakeBackend(handler(0.6, {GENERIC: 0.9, UNIVERSAL: 0.85})))
    assert not any(w.code == "reading_dependent" for w in res.warnings)


def test_minor_reading_does_not_trigger_warning():
    res = run(bird_argument(), FakeBackend(handler(0.95, {GENERIC: 0.9, UNIVERSAL: 0.1})))
    assert not any(w.code == "reading_dependent" for w in res.warnings)  # 全称は w=0.05 < 0.1


def test_truncation_is_conservative():
    full = run(bird_argument(), FakeBackend(handler(0.7, {GENERIC: 0.9, UNIVERSAL: 0.1}))).final("p3")
    cut = run(bird_argument(), FakeBackend(handler(0.7, {GENERIC: 0.9, UNIVERSAL: 0.1})), max_readings=1)
    g = cut.final("p3")
    assert g.lo == pytest.approx(0.7 * 0.9) and g.lo < full.lo
    assert g.hi >= full.hi
    assert cut.mixture.truncated == pytest.approx(0.3)
    assert any(w.code == "readings_truncated" for w in cut.warnings)


def test_estimate_mode_rewrites_premise_probability():
    # 全称と読むと前提が偽（p が低い）、総称と読むと真。estimate モードでは p も読みで変わる
    def h(state, name, q):
        if isinstance(q, Choice):
            return {"generic": 0.5, "universal": 0.5} if "term" in state else {"deduction": 1.0}
        if "statement" in state:
            s = state["statement"]
            true = 0.05 if UNIVERSAL in s else 0.95
            return 1 - true if "誤り" in s else true  # 否定のラッパーには補数を返す
        return asked(q, 0.9)
    arg = bird_argument()
    arg.inferences[0].pattern = "deduction"
    res = NatLean(FakeBackend(h), mode="estimate", lang="en", paraphrases=0).check_argument(arg)
    marg = res.mixture.marginals["m1"]
    assert marg["generic"]["p3"] > marg["universal"]["p3"] + 0.3


def test_variant_rewrites_only_affected_props_and_keeps_original():
    arg = bird_argument()
    v = variant(arg, {"m1": arg.ambiguities[0].senses[1].readings})
    assert v.prop("p1").text == UNIVERSAL and arg.prop("p1").text == "鳥は飛ぶ"
    assert v.prop("p2").text == arg.prop("p2").text


def test_no_interpret_flag_skips_mixture():
    res = run(bird_argument(), FakeBackend(handler(0.7, {GENERIC: 0.9, UNIVERSAL: 0.1})), interpret=False)
    assert res.mixture is None
    assert res.final("p3") is res.propagation.props["p3"]


# ---------- 多義の誤謬 ----------

def sandwich():
    """意味 valid では推論が妥当だが前提が偽、意味 plausible では前提は真だが推論が妥当でない"""
    return Argument(
        language="ja",
        props=[Prop("p1", "永遠の幸福にまさるものは何もない"), Prop("p2", "ハムサンドは何もないよりましだ"),
               Prop("p3", "ハムサンドは永遠の幸福にまさる", "conclusion")],
        inferences=[Inference("s1", ["p1", "p2"], "p3", "deduction")],
        ambiguities=[Ambiguity("m1", "word_sense", "何もない", [
            Sense("valid", "無を項目とする", {"p1": "VALID-1", "p2": "VALID-2"}),
            Sense("plausible", "存在者がない", {"p1": "PLAUS-1", "p2": "PLAUS-2"})])])


def trade_off_handler(p_valid=0.05, r_plaus=0.05):
    def h(state, name, q):
        if isinstance(q, Choice):
            return {"valid": 0.5, "plausible": 0.5} if "term" in state else {"deduction": 1.0}
        if "statement" in state:
            s = state["statement"]
            true = p_valid if "VALID" in s else 0.95
            return 1 - true if "誤り" in s else true
        return asked(q, 0.95 if "VALID-1" in state.get("premises", []) else r_plaus)
    return h


def run_estimate(arg, handler_):
    return NatLean(FakeBackend(handler_), mode="estimate", lang="en", paraphrases=0).check_argument(arg)


def test_equivocation_detected_when_validity_and_plausibility_split():
    res = run_estimate(sandwich(), trade_off_handler())
    eq = [w for w in res.warnings if w.code == "equivocation"]
    assert len(eq) == 1
    a = eq[0].args
    assert (a["valid"], a["plaus"]) == ("valid", "plausible")
    assert a["valid_r"] == pytest.approx(0.95) and a["valid_p"] < 0.1
    assert a["plaus_p"] == pytest.approx(0.9) and a["plaus_r"] < 0.1  # 前提2つの Fréchet: 1-(0.05+0.05)
    assert not res.ok


def test_no_equivocation_when_one_reading_is_both_valid_and_plausible():
    res = run_estimate(sandwich(), trade_off_handler(p_valid=0.95))
    assert not any(w.code == "equivocation" for w in res.warnings)
    assert res.mixture.marginals["m1"]["valid"]["p3"] > 0.8  # この意味では結論が支持される


def test_no_equivocation_in_assume_mode():
    res = run(sandwich(), FakeBackend(trade_off_handler()))  # 前提を真と置くので P は常に 1
    assert not any(w.code == "equivocation" for w in res.warnings)


def test_equivocation_between_universal_and_generic_readings():
    # 全称と総称の取り違え: 全称と読めば推論は妥当だが前提が偽、総称と読めば前提は真だが推論は弱い
    def h(state, name, q):
        if isinstance(q, Choice):
            return {"generic": 0.5, "universal": 0.5} if "term" in state else {"deduction": 1.0}
        if "statement" in state:
            s = state["statement"]
            true = 0.05 if UNIVERSAL in s else 0.95
            return 1 - true if "誤り" in s else true
        return asked(q, 0.95 if UNIVERSAL in state.get("premises", []) else 0.1)
    arg = bird_argument()
    arg.inferences[0].pattern = "deduction"
    res = run_estimate(arg, h)
    eq = [w for w in res.warnings if w.code == "equivocation"]
    assert len(eq) == 1 and eq[0].args["valid"] == "universal" and eq[0].args["plaus"] == "generic"


# ---------- 出力・抽出の検証 ----------

@pytest.mark.parametrize("lang", ["ja", "en"])
def test_report_shows_readings_and_warnings(lang):
    res = run(bird_argument(), FakeBackend(handler(0.6, {GENERIC: 0.9, UNIVERSAL: 0.1})))
    text = report(res, lang)
    assert "generic 0.60" in text and "universal 0.40" in text
    assert ("解釈 鳥は飛ぶ" if lang == "ja" else "readings of 鳥は飛ぶ") in text


def test_json_contains_ambiguities_and_readings():
    res = run(bird_argument(), FakeBackend(handler(0.6, {GENERIC: 0.9, UNIVERSAL: 0.1})))
    a = to_json(res)
    assert a["ambiguities"][0]["term"] == "鳥は飛ぶ"
    assert a["readings"]["evaluated"] == 2


def ext_with(ambs):
    props = [ExtProp(id=i, quote=t, text=t, kind="premise", paraphrases=[]) for i, t in
             (("p1", "鳥は飛ぶ"), ("p2", "ピーちゃんは鳥だ"), ("p3", "ピーちゃんは飛ぶ"))]
    return ExtArgument(language="ja", props=props, attacks=[], ambiguities=ambs,
                       inferences=[ExtInference(id="s1", premises=["p1", "p2"], conclusion="p3", pattern="generic_application")])


def amb(term, props_by_sense):
    return ExtAmbiguity(kind="quantifier", term=term, senses=[
        ExtSense(label=lab, description=lab, readings=[ExtReading(prop=p, text=f"{lab}:{p}") for p in ps])
        for lab, ps in props_by_sense.items()])


def test_build_argument_validates_ambiguities():
    text = "鳥は飛ぶ。ピーちゃんは鳥だ。ピーちゃんは飛ぶ。"
    ok = amb("鳥は飛ぶ", {"generic": ["p1"], "universal": ["p1"]})
    one_sense = amb("x", {"only": ["p1"]})
    dup = amb("y", {"a": ["p1"], "b": ["p1"]})          # p1 はすでに別の曖昧さが使っている
    unknown = amb("z", {"a": ["p9"], "b": ["p9"]})      # 存在しない命題だけ
    arg = build_argument(ext_with([ok, one_sense, dup, unknown]), text)
    assert [a.term for a in arg.ambiguities] == ["鳥は飛ぶ"]
    assert sum(1 for w in arg.warnings if w.code == "dangling") == 3


def test_build_argument_fills_missing_readings_with_original():
    text = "鳥は飛ぶ。ピーちゃんは鳥だ。ピーちゃんは飛ぶ。"
    a = amb("鳥", {"a": ["p1", "p2"], "b": ["p1"]})
    arg = build_argument(ext_with([a]), text)
    assert arg.ambiguities[0].senses[1].readings["p2"] == "ピーちゃんは鳥だ"
