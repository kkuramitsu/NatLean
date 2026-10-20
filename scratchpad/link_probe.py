"""Link の support の問いの言い方を比べる（Jev・課金あり）"""
from natlean import JevBackend
from natlean.decision import Noul

Q = {
    "A": "a が真であることは、b を信じる理由になるか。",
    "B": "a は、b を論証するための前提の候補として挙げられるか。a の真偽や、a だけで b が十分に示されるかは問わず、b の根拠として関連があるかだけを答えよ。",
    "C": "b を主張する人が、その理由の一つとして a を挙げるのは自然か。",
}
pairs = {
    "generic p1->p3": ("鳥は飛ぶ", "ペンギンは飛ぶ"), "generic p2->p3": ("ペンギンは鳥である", "ペンギンは飛ぶ"),
    "induction p1->p3": ("昨日見たカラスは黒かった", "世界中のカラスはすべて黒い"),
    "equiv p1->p3": ("永遠の幸福にまさるものは何もない", "ハムサンドは永遠の幸福にまさる"),
    "equiv p2->p3": ("ハムサンドは何もないよりはましである", "ハムサンドは永遠の幸福にまさる"),
    "fallacy p1->p3": ("人はみな死ぬ", "ソクラテスは人である"), "fallacy p2->p3": ("ソクラテスは死ぬ", "ソクラテスは人である"),
    "penguin p4->p3 (exception)": ("ピーちゃんはペンギンである", "ピーちゃんは飛ぶ"),
    "NEG unrelated": ("ソクラテスは人である", "鳥は飛ぶ"), "NEG unrelated2": ("昨日見たカラスは黒かった", "ソクラテスは死ぬ"),
}
jev = JevBackend()
print(f"{'':28s}" + "".join(f"{k:>7s}" for k in Q))
for name, (a, b) in pairs.items():
    row = [jev.ask({"a": a, "b": b}, {"q": Noul(q)})["q"] for q in Q.values()]
    print(f"{name:28s}" + "".join(f"{v:7.2f}" for v in row))
