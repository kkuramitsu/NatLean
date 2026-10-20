"""実 API を呼ぶテスト（課金あり）

    pytest -m "not api"     # 除外
    pytest -m jev           # Jev を使うものだけ
"""
import os

import pytest

from natlean import ClaudeBackend, JevBackend, NatLean

SOCRATES = "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"
FALLACY = "人はみな死ぬ。ソクラテスは死ぬ。ゆえに、ソクラテスは人である。"
HASTY = "昨日見たカラスは黒かった。今日見たカラスも黒かった。ゆえに、世界中のカラスはすべて黒い。"
PENGUIN = "鳥は飛ぶ。ピーちゃんは鳥である。ゆえに、ピーちゃんは飛ぶ。ただし、ピーちゃんはペンギンである。"


def needs(*envs):
    missing = [e for e in envs if not os.environ.get(e)]
    return pytest.mark.skipif(bool(missing), reason=f"{', '.join(missing)} 未設定")


claude_api = lambda fn: pytest.mark.api(needs("ANTHROPIC_API_KEY")(fn))
jev_api = lambda fn: pytest.mark.api(pytest.mark.jev(needs("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY")(fn)))


@pytest.fixture(scope="module")
def jev():
    return NatLean(JevBackend(), lang="en")


def top(res):
    return res.propagation.props[res.goals[-1]]


@jev_api
def test_jev_socrates_valid(jev):
    res = jev.check(SOCRATES)
    assert len(res.argument.props) == 3
    assert top(res).lo >= 0.8 and res.ok


@jev_api
def test_jev_affirming_the_consequent(jev):
    assert top(jev.check(FALLACY)).hi < 0.5


@jev_api
def test_jev_hasty_induction(jev):
    assert top(jev.check(HASTY)).lo < 0.5


@jev_api
def test_jev_penguin_undercut_is_the_weakest_link(jev):
    res = jev.check(PENGUIN)
    assert res.argument.attacks, "掘り崩しが抽出されていない"
    assert not res.ok


@claude_api
def test_claude_backend_socrates():
    res = NatLean(ClaudeBackend(samples=3), lang="en").check(SOCRATES)
    assert top(res).lo >= 0.8


@claude_api
def test_claude_backend_fallacy():
    res = NatLean(ClaudeBackend(samples=3), lang="en").check(FALLACY)
    assert top(res).hi < 0.5
