# CLAUDE.md

NatLean は「自然言語版 Lean」。自然言語の論証を命題と推論のグラフに分け、前提の確かさ p と推論の確かさ r を決定モデル（Jev または Claude Haiku）で推定し、確率の区間（下限・独立推定・上限）として伝播させる。設計は `tex/design.tex`。

## 構成

- `src/natlean/graph.py` — データ型（`Prop` / `Inference` / `Attack` / `Argument` / `Interval` / `Warn`）
- `src/natlean/extract.py` — 論証の抽出（Claude 1回、`messages.parse`）と、引用・参照のコードによる検証
- `src/natlean/decision/` — 決定モデル。`jev.py`（TypeSafe Jev）、`claude.py`、`fake.py`（テスト用）、`cache.py`（判断ログ兼キャッシュ）
- `src/natlean/estimate.py` — 問いの組み立てと区間化。日英の問いのテンプレートと推論パターンの説明
- `src/natlean/propagate.py` — 伝播計算。**純関数で、決定モデルを使わない**
- `src/natlean/evidence.py` — 根拠文書の passage 分割と検索（文字 2-gram）。1ファイル＝1つの出どころ
- `src/natlean/interpret.py` — 曖昧さの意味の割り当てごとに評価して混合し、読み方への依存と多義の誤謬（R と P のトレードオフ）を警告する
- `src/natlean/checker.py` — `NatLean` クラス（抽出 → 推定 → 伝播）
- `src/natlean/report.py` — テキストと JSON の出力
- `src/natlean/i18n.py` — 表示メッセージの日英カタログ
- `src/natlean/cli.py` — `natlean` コマンド
- `src/natlean/__init__.py` — 公開 API と `__version__`（バージョンの唯一の定義元）
- `tests/` — `test_propagate.py`・`test_estimate.py` はオフライン、`test_api.py` は実 API（`@api`、Jev は `@jev` も）
- `scratchpad/` — 実験用スクリプト（`jev_probe.py`: Jev の挙動の確認）
- `tex/design.tex` — 設計書、`tex/main.tex` — 論文草稿
- `.github/workflows/ci.yml` — CI。Python 3.10〜3.14 でオフラインテスト、ビルドと `twine check`。main への push 時のみ `api` テスト（Secret `ANTHROPIC_API_KEY`、`TYPESAFE_API_KEY`）

## パイプライン

1. `extract` — Claude が命題（引用・正規化文・言い換え）・推論（前提→結論、パターン）・攻撃（反駁・掘り崩し）を抽出。引用が原文に無ければ警告
2. `NatLean.estimate` — 決定モデルで r（と必要なら p、攻撃の強さ）を区間として推定。パターンも分類して食い違いを警告。根拠文書があれば葉の p を P(命題 | passage) にし、引用（`Prop.cites`）を残す
3. `propagate` — 下限は Fréchet（`r.lo × max(0, 1 − Σ(1 − lo))`）、上限は `1 − q.lo × (1 − r.hi)`、独立推定は葉と推論を一度ずつ掛ける。複数の支持が葉・推論・根拠の出どころを共有すれば独立とみなさず max をとる。閉路上の推論は使わない
4. `interpret.mix` — 曖昧さがあれば、意味の割り当てごとに書き換えて評価し混合（打ち切った質量は下限 0・上限 1 として保守的に扱う）
5. `report` — Lean 風のテキスト（`--json` で JSON）。曖昧さがあるとゴールの値は混合後（`Result.final`）

## コマンド

```bash
pip install -e ".[dev]"
pytest -m "not api"          # オフライン（速い・無料）
pytest -m api                # 実 API（ANTHROPIC_API_KEY。Jev は TYPESAFE_API_KEY も。課金あり）
natlean examples/fallacy.txt --lang en
python scratchpad/jev_probe.py jev-latest
python -m build && twine check dist/*
cd tex && latexmk -lualatex design.tex
```

## 規約

- コメント・docstring は日本語。**表示メッセージ（CLI・レポート・警告）は `i18n.py` に ja/en の両方を書く**。JSON のキーは英語で固定。
- 警告は `Warn("code", {...})` で作り、`i18n.py` に `warn.code` を足す（`test_all_warn_codes_have_messages` が確認する）。
- 決定モデルには論証の全文を見せない。p には命題1文（根拠があれば passage 1つ）、r には前提と結論だけを state に入れる。
- 同じ問いを繰り返して平均しない（Jev は再現性が高い）。区間は言い換え・否定・2系統の問いのずれから作る。
- Jev は `jev-latest` / `jev-preview` の別名しか選べない。応答の `model`（実体のバージョン）を判断ログに残す。SDK は使わず `decision/jev.py` で HTTP を呼ぶ。
- Claude の呼び出しは `client.messages.parse(output_format=PydanticModel)`。文字列を自前でパースしない。既定モデルは `claude-haiku-5-5`。Haiku 5.5 は `temperature` などを既定値以外にすると 400 になるので渡さない。
- 推論パターンを追加するときは `graph.py` の `Pattern`・`PATTERNS`、`estimate.py` の `PATTERN_DOC`（ja/en）、`extract.py` の `ExtPattern` と `EXTRACT_SYSTEM` の4か所をそろえる。厳密な型なら `STRICT_PATTERNS` にも入れる。
- 判定ロジックやプロンプトを変えたら、オフラインテストに加えて `pytest -m api` で実 API の挙動も確認する。
- バージョンを上げるときは `src/natlean/__init__.py` の `__version__` だけを変える。

## 今後の課題

- 曖昧さの抽出の揺れ（同じ入力でも見つかったり見つからなかったりする）の抑え方。曖昧さがあるときの最弱環の計算
- 根拠文書の検索の改善（意味的な検索、関連の薄い passage の除外）。検索の差し替え
- 正解ラベル付きデータ（FOLIO、EntailmentBank など）による較正（等張回帰）
- 区間の幅が大きい箇所だけ上位モデルで再判定（`--escalate`）
- Jev の日本語と英語の精度比較、誘導耐性の追加確認
