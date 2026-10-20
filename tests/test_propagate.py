"""伝播計算のオフラインテスト（決定モデルを使わない）"""
import pytest

from natlean import Argument, Attack, Inference, Interval, Prop, propagate, status, weakest_links
from natlean.propagate import goals


def P(i, p=1.0, kind="premise"):
    return Prop(i, i, kind, p=Interval.point(p))


def E(i, prem, concl, r=1.0, pattern="deduction"):
    return Inference(i, prem, concl, pattern, Interval.point(r))


def test_socrates_frechet_lower_bound():
    arg = Argument(props=[P("p1", 0.99), P("p2", 0.999), P("c", kind="conclusion")],
                   inferences=[E("s1", ["p1", "p2"], "c")])
    c = propagate(arg).props["c"]
    assert c.lo == pytest.approx(0.989)
    assert c.est == pytest.approx(0.99 * 0.999)  # 独立なら積
    assert c.hi == pytest.approx(1.0)


def test_frechet_clamps_at_zero():
    arg = Argument(props=[P("p1", 0.4), P("p2", 0.4), P("c")], inferences=[E("s1", ["p1", "p2"], "c")])
    assert propagate(arg).props["c"].lo == 0.0


def test_chain_of_five_steps_multiplies_not_adds():
    # 一本の鎖は段ごとに掛けるので 0.9^5。5つの前提を一度に連言するときだけ 0.5 まで落ちる
    props = [P("n0")] + [P(f"n{i}") for i in range(1, 6)]
    infs = [E(f"s{i}", [f"n{i-1}"], f"n{i}", r=0.9) for i in range(1, 6)]
    assert propagate(Argument(props=props, inferences=infs)).props["n5"].lo == pytest.approx(0.9 ** 5)
    flat = Argument(props=[P(f"p{i}", 0.9) for i in range(5)] + [P("c")],
                    inferences=[E("s", [f"p{i}" for i in range(5)], "c")])
    assert propagate(flat).props["c"].lo == pytest.approx(0.5)


def test_upper_bound_flags_fallacy():
    # 後件肯定: r の上限が 0.3 なら、前提がほぼ確実でも結論の上限は低い
    arg = Argument(props=[P("p1", 0.95), P("c")],
                   inferences=[Inference("s1", ["p1"], "c", "deduction", Interval(0.1, 0.2, 0.3))])
    c = propagate(arg).props["c"]
    assert c.hi == pytest.approx(1 - 0.95 * 0.7)
    assert c.hi < 0.4


def test_shared_ancestor_frechet_is_conservative():
    arg = Argument(props=[P("a", 0.8), P("b"), P("c"), P("d")],
                   inferences=[E("s1", ["a"], "b"), E("s2", ["a"], "c"), E("s3", ["b", "c"], "d")])
    d = propagate(arg).props["d"]
    # b, c の下限はそれぞれ 0.8。連言の下限は 1-(0.2+0.2)=0.6（共有を仮定しない安全側）
    assert d.lo == pytest.approx(0.6)
    assert d.est == pytest.approx(0.8)


def test_independent_supports_noisy_or():
    arg = Argument(props=[P("a", 0.5), P("b", 0.5), P("c")],
                   inferences=[E("s1", ["a"], "c"), E("s2", ["b"], "c")])
    c = propagate(arg).props["c"]
    assert c.lo == pytest.approx(0.5)  # 安全側は max
    assert c.est == pytest.approx(0.75)  # 独立なら 1-(0.5*0.5)
    assert not c.double_count


def test_overlapping_supports_warn_and_take_max():
    arg = Argument(props=[P("a", 0.5), P("b", 0.9), P("c")],
                   inferences=[E("s1", ["a"], "c"), E("s2", ["a", "b"], "c")])
    res = propagate(arg)
    assert res.props["c"].double_count
    assert res.props["c"].est == pytest.approx(0.5)
    assert any(w.code == "double_count" for w in res.warnings)


def test_rebuttal_caps_upper_bound_and_conflicts():
    arg = Argument(props=[P("a"), P("u"), P("c")],
                   inferences=[E("s1", ["a"], "c")],
                   attacks=[Attack("rebut", "u", "c", Interval.point(0.9))])
    res = propagate(arg)
    c = res.props["c"]
    assert c.lo == pytest.approx(1.0)
    assert c.conflict and any(w.code == "conflict" for w in res.warnings)
    weak = Argument(props=[P("a"), P("u", 0.5), P("c")],
                    inferences=[E("s1", ["a"], "c", r=0.6)],
                    attacks=[Attack("rebut", "u", "c", Interval.point(0.8))])
    c2 = propagate(weak).props["c"]
    assert c2.hi == pytest.approx(1 - 0.8 * 0.5)
    assert not c2.conflict


def test_undercut_penguin():
    arg = Argument(props=[P("bird"), P("tweety"), P("penguin"), P("flies", kind="conclusion")],
                   inferences=[E("s1", ["bird", "tweety"], "flies", r=0.9, pattern="generic_application")],
                   attacks=[Attack("undercut", "penguin", "s1", Interval.point(0.99))])
    f = propagate(arg).props["flies"]
    assert f.lo == pytest.approx(0.9 * 0.01)
    assert f.hi == pytest.approx(1.0 - 1.0 * (1 - 0.9))  # 掘り崩しは上限を上げない
    gains = weakest_links(arg, "flies")
    assert gains[0][:2] == ("attack", "a1")


def test_cycle_is_detected_and_not_used_as_support():
    arg = Argument(props=[P("a"), P("b"), P("c")],
                   inferences=[E("s1", ["a"], "b"), E("s2", ["b"], "a"), E("s3", ["b"], "c")])
    res = propagate(arg)
    assert set(res.cyclic) == {"s1", "s2"}
    assert any(w.code == "cycle" for w in res.warnings)
    assert res.props["b"].lo == 1.0  # 閉路を外すと b は葉として扱われる


def test_self_loop_is_cyclic():
    arg = Argument(props=[P("a")], inferences=[E("s1", ["a"], "a")])
    assert propagate(arg).cyclic == ["s1"]


def test_weakest_link_ranking():
    arg = Argument(props=[P("a", 0.9), P("b", 0.5), P("c")],
                   inferences=[E("s1", ["a", "b"], "c", r=0.8)])
    gains = weakest_links(arg, "c")
    assert [g[1] for g in gains] == ["b", "s1", "a"]
    assert gains[0][2] == pytest.approx(0.8 * (0.9 - 0.4))


def test_goals_default_to_conclusion_then_sink():
    arg = Argument(props=[P("a"), P("b"), P("c", kind="conclusion")],
                   inferences=[E("s1", ["a"], "b"), E("s2", ["b"], "c")])
    assert goals(arg) == ["c"]
    arg.props[2].kind = "intermediate"
    assert goals(arg) == ["c"]


def test_status_thresholds():
    arg = Argument(props=[P("a", 0.7), P("c")], inferences=[E("s1", ["a"], "c")])
    r = propagate(arg).props["c"]
    assert status(r, 0.6) == "proved"
    assert status(r, 0.8) == "unproved"
