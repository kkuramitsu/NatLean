"""表示メッセージの日英カタログ

メッセージはキーで引く。警告は `warn.<code>` で、グラフの警告 Warn の args を埋め込む。
"""
from __future__ import annotations

import os
from typing import Optional

LANGS = ("ja", "en")

MESSAGES = {
    # --- レポート ---
    "assumed": {"ja": "仮定", "en": "assumed"},
    "status.proved": {"ja": "証明済み", "en": "PROVED"},
    "status.plausible": {"ja": "独立なら成立", "en": "PLAUSIBLE"},
    "status.unproved": {"ja": "根拠不足", "en": "NOT PROVED"},
    "goal": {"ja": "ゴール {id}: {status}（下限 {lo:.2f}）", "en": "Goal {id}: {status} (lower bound {lo:.2f})"},
    "weakest": {"ja": "最も弱い環:", "en": "weakest links:"},
    "weakest.leaf": {"ja": "前提 {id}", "en": "premise {id}"},
    "weakest.edge": {"ja": "推論 {id}", "en": "inference {id}"},
    "weakest.attack": {"ja": "攻撃 {id}（これが無ければ）", "en": "attack {id} (without it)"},
    "readings": {"ja": "解釈 {term}:", "en": "readings of {term}:"},
    "cite": {"ja": "↳ {source}#{index} {relation} {p:.2f}", "en": "↳ {source}#{index} {relation} {p:.2f}"},
    "relation.supports": {"ja": "裏付け", "en": "supports"},
    "relation.contradicts": {"ja": "否定", "en": "contradicts"},
    "legend": {"ja": "L=下限（依存を仮定しない） P̂=独立を仮定した推定 U=上限",
               "en": "L=lower bound (no independence assumed)  P̂=independent estimate  U=upper bound"},
    "backend": {"ja": "判定モデル: {name}", "en": "decision model: {name}"},
    # --- 警告 ---
    "warn.subclass": {"ja": "{id}: クラスから部分クラスへの推論は保証がない（部分クラスが例外かもしれない）",
                      "en": "{id}: inference from a class to a subclass has no guarantee (the subclass may be an exception)"},
    "warn.wide": {"ja": "{id}: モデルの判断が一貫しない（区間 {lo:.2f}〜{hi:.2f}）",
                  "en": "{id}: the model's judgments are inconsistent (interval {lo:.2f}-{hi:.2f})"},
    "warn.pattern_mismatch": {"ja": "{id}: 抽出は {given}、判定モデルは {chosen} と分類した",
                              "en": "{id}: extraction says {given}, the decision model classifies it as {chosen}"},
    "warn.conflict": {"ja": "{id}: 支持の下限 {lo:.2f} が反駁による上限 {hi:.2f} を超えている（衝突）",
                      "en": "{id}: the support lower bound {lo:.2f} exceeds the upper bound {hi:.2f} from rebuttals (conflict)"},
    "warn.double_count": {"ja": "{id}: 複数の根拠が前提を共有しており、独立とみなすと過大評価になる",
                          "en": "{id}: the supports share premises, so assuming independence would overestimate"},
    "warn.cycle": {"ja": "{id}: 循環論法（閉路上の推論は支持に使わない）",
                   "en": "{id}: circular reasoning (inferences on a cycle are not used as support)"},
    "warn.quote_not_found": {"ja": "{id}: 引用が原文に見つからない（抽出が原文から離れている恐れ）",
                             "en": "{id}: the quote is not found in the input (extraction may have drifted)"},
    "warn.dangling": {"ja": "{id}: 存在しない命題・推論 {ref} を参照しているので無視した",
                      "en": "{id}: refers to unknown {ref}; ignored"},
    "warn.reading_dependent": {
        "ja": "{id}: 「{term}」の読み方で下限が変わる（{best} なら {best_lo:.2f}、{worst} なら {worst_lo:.2f}）",
        "en": "{id}: the lower bound depends on how \"{term}\" is read ({best}: {best_lo:.2f}, {worst}: {worst_lo:.2f})"},
    "warn.equivocation": {
        "ja": "{id}: 「{term}」の読み替えで成り立って見える恐れ（多義の誤謬）。"
              "{valid} と読めば推論は妥当（{valid_r:.2f}）だが前提が成り立たず（{valid_p:.2f}）、"
              "{plaus} と読めば前提は成り立つ（{plaus_p:.2f}）が推論が妥当でない（{plaus_r:.2f}）",
        "en": "{id}: the argument may only seem to hold by shifting the reading of \"{term}\" (equivocation). "
              "Read as {valid}, the inference is valid ({valid_r:.2f}) but the premises fail ({valid_p:.2f}); "
              "read as {plaus}, the premises hold ({plaus_p:.2f}) but the inference is not valid ({plaus_r:.2f})"},
    "warn.readings_truncated": {
        "ja": "解釈の組み合わせが多いため、確からしさの小さい割り当て（質量 {mass:.2f}）を打ち切った（下限は低く、上限は高くなる）",
        "en": "too many combinations of readings; dropped the least likely ones (mass {mass:.2f}), which lowers L and raises U"},
    "warn.shared_source": {
        "ja": "{id}: 複数の根拠が同じ出どころ（{source}）に基づくため、独立とみなさず大きい方をとった",
        "en": "{id}: several supports rest on the same source ({source}); not treated as independent, the larger one is used"},
    "warn.no_evidence": {
        "ja": "{id}: 根拠文書に該当する記述が無く、モデルの事前知識で推定した",
        "en": "{id}: no relevant passage in the evidence; estimated from the model's prior knowledge"},
    "warn.evidence_conflict": {
        "ja": "{id}: 根拠文書の記述が食い違っている（裏付けと否定が混在）",
        "en": "{id}: the evidence passages disagree (both supporting and contradicting)"},
    "warn.no_conclusion": {"ja": "結論が指定されていないため、最後の命題をゴールとした",
                           "en": "no conclusion was marked; the last proposition is used as the goal"},
    # --- CLI ---
    "cli.description": {"ja": "NatLean: 自然言語の論証を確率的にチェックする",
                        "en": "NatLean: probabilistic checking of natural-language arguments"},
    "cli.help": {"ja": "このヘルプを表示して終了", "en": "show this help message and exit"},
    "cli.file": {"ja": "入力ファイル（- で標準入力）", "en": "input file (- for stdin)"},
    "cli.lang": {"ja": "表示言語（既定: 環境から判定）", "en": "display language (default: from environment)"},
    "cli.mode": {"ja": "assume: 前提を真と置く / estimate: 前提の確かさも推定する",
                 "en": "assume: treat premises as true / estimate: also estimate premise probabilities"},
    "cli.backend": {"ja": "判定バックエンド（既定: TYPESAFE_API_KEY があれば jev、無ければ claude）",
                    "en": "decision backend (default: jev if TYPESAFE_API_KEY is set, else claude)"},
    "cli.jev_model": {"ja": "Jev のモデル名", "en": "Jev model name"},
    "cli.model": {"ja": "抽出と claude バックエンドに使う Claude のモデル", "en": "Claude model for extraction and the claude backend"},
    "cli.threshold": {"ja": "「証明済み」とみなす下限のしきい値", "en": "lower-bound threshold for PROVED"},
    "cli.paraphrases": {"ja": "命題あたりの言い換え数", "en": "paraphrases per proposition"},
    "cli.no_interpret": {"ja": "曖昧さ（量化・語義）の解釈の混合をしない", "en": "do not mix over readings of ambiguous terms"},
    "cli.max_readings": {"ja": "評価する解釈の割り当ての数の上限", "en": "maximum number of reading assignments to evaluate"},
    "cli.evidence": {"ja": "根拠文書のファイルまたはディレクトリ（複数可。指定すると --mode の既定は estimate）",
                     "en": "evidence file or directory (repeatable; makes estimate the default --mode)"},
    "cli.log": {"ja": "判断ログ兼キャッシュの JSONL ファイル", "en": "JSONL file for the decision log and cache"},
    "cli.json": {"ja": "JSON で出力", "en": "output JSON"},
    "cli.error.backend": {"ja": "エラー: {name} の API キーが設定されていません（{env}）",
                          "en": "error: no API key for {name} ({env} is not set)"},
    "cli.error.generic": {"ja": "エラー: {msg}", "en": "error: {msg}"},
    "cli.error.empty": {"ja": "エラー: 入力が空です", "en": "error: the input is empty"},
}


def resolve_lang(lang: Optional[str] = None) -> str:
    """--lang、NATLEAN_LANG、LANG の順に決める。ja で始まれば日本語、それ以外は英語"""
    for cand in (lang, os.environ.get("NATLEAN_LANG"), os.environ.get("LANG")):
        if cand:
            return "ja" if cand.lower().startswith("ja") else "en"
    return "en"


def t(key: str, lang: str, **kw) -> str:
    text = MESSAGES[key][lang]
    return text.format(**kw) if kw else text
