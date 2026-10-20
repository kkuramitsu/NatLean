# NatLean — 自然言語版 Lean

[![CI](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml/badge.svg)](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml)

NatLean は、自然言語で書かれた論証を **Lean のように1ステップずつ検証する** ツールです。

論証を命題と推論のグラフに分け、各推論について「前提がすべて真なら結論が真である確率」を
決定モデル（[Jev](https://typesafe.ai) または Claude Haiku）で推定し、結論がどれだけ支えられているかを
**確率の区間**（依存を仮定しない下限、独立を仮定した推定、上限）として示します。弱いステップは `sorry` として、
結論の下限を最も押し下げている要素（最も弱い環）とともに指摘します。

```
$ natlean examples/fallacy.txt --lang en
p1  [premise] すべての人は死ぬ    assumed
p2  [premise] ソクラテスは死ぬ    assumed
p3  [conclusion] ソクラテスは人である    ✗ L=0.06 P̂=0.07 U=0.09  sorry
      s1: p1, p2 ⊢ p3  [deduction]  r=[0.06, 0.09]

Goal p3: NOT PROVED (lower bound 0.06)
  weakest links:
    inference s1 (+0.94)
```

表示は日本語と英語に対応しています（`--lang ja|en`）。

## インストール

```bash
pip install natlean          # Python 3.10 以上
export ANTHROPIC_API_KEY=sk-ant-...     # 論証の抽出に使う
export TYPESAFE_API_KEY=...             # Jev を使う場合（無ければ Claude で判定）
```

## 使い方

### クイックスタート

```bash
echo "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。" | natlean - --lang ja
```

```
p1  [premise] すべての人は死ぬ    仮定
p2  [premise] ソクラテスは人である    仮定
p3  [conclusion] ソクラテスは死ぬ    ✓ L=0.95 P̂=0.96 U=0.98
      s1: p1, p2 ⊢ p3  [deduction]  r=[0.95, 0.98]

ゴール p3: 証明済み（下限 0.95）

(L=下限（依存を仮定しない） P̂=独立を仮定した推定 U=上限; 判定モデル: jev:jev-latest jev-1.13.0)
```

命題の文は、抽出で修辞を除いた中立な形に書き直されます（「人はみな」→「すべての人は」）。
数値は決定モデルの出力なので、実行ごとに少し変わります。

入力は、論証が書かれた日本語または英語の文章です（ファイル、または `-` で標準入力）。
前提・推論・結論は文章から自動で取り出すので、「ゆえに」「したがって」などの接続語があるほうが確実です。
`examples/` にサンプルがあります。

| ファイル | 内容 | 結果の目安 |
|---|---|---|
| `deduction.txt` | 正しい演繹（三段論法） | ✓ 下限 0.9 台 |
| `fallacy.txt` | 後件肯定の誤謬 | ✗ 下限 0.1 以下 |
| `induction.txt` | 2羽から全カラスへの過度な一般化 | ✗ |
| `penguin.txt` | 「鳥は飛ぶ」に例外（ペンギン）を足す | ✗ 最も弱い環は掘り崩し（`a1`） |
| `generic.txt` | 「鳥は飛ぶ」を全称と総称に読む | 読み方で下限が変わる警告 |
| `equivocation.txt` | 「何もない」の読み替え | ✗ |
| `evidence_claim.txt` | 根拠文書つきの推論（`--evidence examples/evidence`） | 前提の確かさと引用元を表示 |

### 出力の読み方

```
p3  [conclusion] ペンギンは飛ぶ    ✗ L=0.35 P̂=0.39 U=0.95  sorry
      s1: p1, p2 ⊢ p3  [generic_application]  r=[0.82, 0.95]
m1  解釈 鳥は飛ぶ: 全称 0.14 / 総称 0.86
a1  p4 ⊣ s1  [undercut]  0.57
  ! s1: 抽出は generic_application、判定モデルは deduction と分類した

ゴール p3: 根拠不足（下限 0.35）
  最も弱い環:
    攻撃 a1（これが無ければ）(+0.47)
```

| 表示 | 意味 |
|---|---|
| `pN` / `sN` / `aN` / `mN` | 命題 / 推論 / 攻撃 / 曖昧さ（解釈）の id |
| `L` | 下限。前提どうしの依存を仮定しない安全側の値。**判定にはこれを使う** |
| `P̂` | 前提が独立だとした場合の推定値（楽観的な値） |
| `U` | 上限。誤謬は、前提が確かでも上限が低いことで分かる |
| `r=[…]` | 推論の確かさ（前提がすべて真なら結論が真である確率）の区間 |
| `[deduction]` など | 推論のパターン（演繹・言い換え・総称の適用・部分クラス・帰納・仮説形成・類推・因果・権威） |
| `p4 ⊣ s1 [undercut]` | 攻撃。`rebut` は結論の否定、`undercut` は推論の適用を無効にする（例外の指摘） |
| `↳ ファイル#番号 裏付け 0.96` | 根拠文書の引用（`--evidence` を使ったとき） |
| `!` | 警告（下の表） |
| `✓` / `?` / `✗` | `L` ≥ しきい値 / `P̂` ≥ しきい値 / それ未満（`sorry`） |
| 最も弱い環 | その要素が確実だったとしたときに、ゴールの下限がどれだけ上がるか |

主な警告:

| 警告 | 意味 |
|---|---|
| 判断が一貫しない | 言い換えや否定で判定が揺れた（区間が 0.2 より広い） |
| 抽出は A、判定モデルは B と分類した | 推論パターンの食い違い |
| 部分クラスへの推論 | 「鳥は飛ぶ → ペンギンは飛ぶ」型。例外かもしれず保証がない |
| 「X」の読み方で下限が変わる | 曖昧さ。どの読み方なら下限がいくつか |
| 読み替えで成り立って見える恐れ（多義の誤謬） | ある読み方なら推論は妥当だが前提が偽、別の読み方なら前提は真だが推論が妥当でない。`--mode estimate` のとき |
| 循環論法 / 衝突 / 二重計上 | 閉路、支持の下限が反駁の上限を超えた、複数の根拠が前提や出どころを共有している |
| 引用が原文に見つからない | 抽出が原文から離れた恐れ |

終了コードは、すべての結論が `✓` なら `0`、そうでなければ `1`、エラーは `2` です（CI に組み込めます）。

### 前提の扱い（モード）

| モード | 動作 |
|---|---|
| `assume`（既定） | 前提をすべて真と置き、**論証の妥当性だけ**を測る（Lean の仮定と同じ） |
| `estimate` | 前提の確かさ p も決定モデルで推定する。多義の誤謬の検出はこのモードで動く |
| `--evidence` を指定 | 自動で `estimate` になり、根拠文書に照らして p を推定する |

### 根拠文書で前提を確かめる

```bash
natlean essay.txt --evidence docs/            # ディレクトリ（直下の .txt / .md）
natlean essay.txt --evidence a.txt --evidence b.md
```

1ファイルが1つの出どころです。前提ごとに関連する箇所（passage）を探し、「裏付け・否定・無関係」と
「その根拠のもとで真か」を判定します。関連する記述が無い前提は、モデルの事前知識で推定して警告します。
同じファイルに基づく複数の根拠は独立とみなしません。

### オプション

| オプション | 既定 | 説明 |
|---|---|---|
| `file` | 必須 | 入力ファイル。`-` で標準入力 |
| `--lang {ja,en}` | 環境から判定 | 表示言語。`NATLEAN_LANG`、`LANG` の順に見て、`ja` で始まれば日本語、それ以外は英語 |
| `--mode {assume,estimate}` | `assume` | 前提の扱い（上の表） |
| `--evidence PATH` | なし | 根拠文書のファイルまたはディレクトリ（複数可） |
| `--backend {jev,claude}` | `TYPESAFE_API_KEY` があれば `jev`、無ければ `claude` | 確率を推定するモデル |
| `--jev-model` | `jev-latest` | Jev のモデル名（`jev-preview` も選べる） |
| `--model` | `claude-haiku-5-5` | 論証の抽出と、`claude` バックエンドに使う Claude |
| `--threshold` | `0.8` | 「証明済み」とみなす下限 |
| `--paraphrases` | `2` | 命題あたりの言い換えの数（多いほど区間は広く、呼び出しは増える） |
| `--no-interpret` | 混合する | 曖昧さ（全称/総称、語義）の解釈の混合をしない |
| `--max-readings` | `16` | 評価する解釈の割り当ての数の上限（超えた分は保守的に扱う） |
| `--log FILE` | なし | 判断ログ兼キャッシュ（JSONL） |
| `--json` | 無効 | JSON で出力 |

`--log` を付けると、モデルへの問いと答え、応答が返したモデルの実体のバージョン（例 `jev-1.13.0`）を記録します。
同じ問いはファイルから返すので、2回目以降は速く無料で、結果も再現できます。

### JSON 出力

`--json` のキーは、表示言語に関係なく英語で固定です。

```bash
natlean essay.txt --json | jq '.goals[] | {id, status, lo, est, hi}'
```

主なキー: `ok`、`goals`（`status` は `proved` / `plausible` / `unproved`、`lo`・`est`・`hi`）、`props`（`cites`・`p`）、
`inferences`（`pattern`・`r`）、`attacks`、`ambiguities`、`readings`、`warnings`（`code` と引数）、`backend`。

### Python から

```python
from natlean import NatLean, report

res = NatLean(lang="ja").check("人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。")
print(report(res))                 # Lean 風のテキスト
print(res.ok)                      # すべてのゴールが証明済みか
g = res.goals[0]
print(res.final(g))                # ゴールの区間 PropResult(lo=…, est=…, hi=…)
for w in res.warnings:             # 警告 Warn(code, args)
    print(w.code, w.args)
```

設定は引数で渡します。

```python
from natlean import NatLean, EvidenceIndex, JevBackend, ClaudeBackend

nl = NatLean(
    JevBackend(model="jev-latest"),              # または ClaudeBackend(samples=3)
    mode="estimate",
    evidence=EvidenceIndex.from_paths(["docs/"]),
    threshold=0.7,
    log="decisions.jsonl",
)
res = nl.check(text)
```

論証を自分でグラフとして組み立てて、抽出を使わずに判定することもできます。
確率の伝播（`propagate`）は決定モデルを使わない純関数なので、APIキーなしでも試せます。

```python
from natlean import Argument, Prop, Inference, Interval, propagate

arg = Argument(
    props=[Prop("p1", "人はみな死ぬ", p=Interval.point(0.99)),
           Prop("p2", "ソクラテスは人である", p=Interval.point(0.999)),
           Prop("p3", "ソクラテスは死ぬ", kind="conclusion")],
    inferences=[Inference("s1", ["p1", "p2"], "p3", "deduction", Interval.point(1.0))],
)
print(propagate(arg).props["p3"].lo)   # 0.989
```

## 仕組み

| Lean | NatLean |
|---|---|
| 仮定 `h : P` | 前提（確かさ p） |
| ゴール `⊢ Q` | 結論 |
| タクティク1ステップ | 推論1ステップ（確かさ r） |
| 型検査 OK / エラー | 下限 L による ✓ / ? / ✗ |
| `sorry` | 根拠不足のステップ |

1. **抽出**: Claude が命題・推論（演繹、総称の適用、部分クラス、帰納など）・攻撃（反駁と掘り崩し）を抽出する。
2. **推定**: 決定モデルが r（と必要なら p）を、言い換え・否定・2系統の問いで複数回問い、最小〜最大の区間にする。
   決定モデルには論証の全文を見せず、前提と結論だけを渡す（説得力ではなく論理的な支持を測るため）。
3. **伝播**（コードのみ）: 下限は `r.lo × max(0, 1 − Σ(1 − 前提の下限))`、上限は `1 − q.lo × (1 − r.hi)`。
   掘り崩しは r を下げ、反駁は上限を下げる。閉路上の推論は使わない。
4. **解釈の混合**: 「鳥は飛ぶ」（全称か総称か）や、途中で意味が変わる語のような曖昧さは、意味ごとに命題を書き換えて
   グラフ全体を評価し、意味の確からしさで混合する。読み方で結論の下限が変わるときと、
   「全称と読めば推論は妥当だが前提が偽、総称と読めば前提は真だが推論が弱い」のように
   読み替えで成り立って見えるとき（多義の誤謬。`--mode estimate` のみ）は警告する。
5. **根拠文書**（`--evidence`）: 前提を根拠文書の該当箇所（passage）に照らして `P(前提 | 根拠)` として推定し、
   どの出どころ（ファイル）の何番目の passage に基づくかをレポートに示す。同じ出どころに基づく複数の根拠は独立とみなさず、
   二重計上を警告する。
6. **判定**: `L ≥ threshold` で ✓、独立なら成立（`P̂ ≥ threshold`）で ?、それ未満は ✗（sorry）。

設計の詳細は [`tex/design.tex`](tex/design.tex) にあります。

## 制限事項

- `assume` モードでは前提の真偽は検証しません（すべて仮定として受け入れます）。
- 確率は決定モデルの出力で、まだ校正（calibration）していません。
- 根拠文書の検索は文字 2-gram の重なりだけで、意味的な検索ではありません。常識的な前提は、関連の薄い passage に
  引きずられて根拠なしの推定より低くなることがあります。
- 曖昧さの抽出は LLM によるため、実行ごとに見つかったり見つからなかったりします（多義の誤謬は特に揺れます）。
- Jev は早期アクセスで、`jev-latest` の中身が変わりえます。応答のバージョンを判断ログ（`--log`）に残します。

## 開発

```bash
pip install -e ".[dev]"
pytest -m "not api"     # オフラインのテストのみ
pytest -m api           # 実 API を呼ぶテスト（ANTHROPIC_API_KEY、Jev は TYPESAFE_API_KEY も必要）
```

## ライセンス

MIT
