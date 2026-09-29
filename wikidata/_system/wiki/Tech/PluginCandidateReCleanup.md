# candidateの旧機能（CANDIDATE_CASE_SENSITIVE・独立したreキー）の削除（要望）

wikiPlugin から wikiSystem 本体（`_sys/wikilib/plugins.py`）への実装依頼です。
**2026-08-24に対応済みです**。

## 背景

`num_order` の実装（2026-08-23）で、`candidate` の一覧に `(パターン, "re")`（正規表現）と
`(文字列, "case")`（大文字小文字を区別する完全一致）を混ぜて書けるようになりました。
これで次の2つの旧機能は完全に代替されたため、書きかたを1つにするために削除しました。

| 旧機能 | 代わりの書きかた |
|---|---|
| `args` の項目に直接書く `"re"` キー | `"candidate": [(r"…", "re")]` |
| `candidate` の先頭に置く `CANDIDATE_CASE_SENSITIVE`（`"x_IGN_CASE!"`） | 区別したい要素だけを `(文字列, "case")` にする（要素ごとに混在できる） |

同梱プラグインで旧機能を使っていたのは `ref.py` の `size`（`"re"` キー）だけで、
`"candidate": [(SIZE_PATTERN, "re")]` へ移しました。

## 削除したもの（`_sys/wikilib/plugins.py`）

- `CANDIDATE_CASE_SENSITIVE` 定数と、`_check_candidate`・`_validate_candidate_shape` の中の判定
- `_check_re` 関数と、`_resolve_arg_value` からの呼び出し
- `bind_plugin_args` の docstring の、旧機能に触れた説明

## 削除後の動き

`"re"` キーを書いても、知らない項目として無視されます（エラーにはなりません）。
`candidate` に `"x_IGN_CASE!"` を書くと、ただの候補の1つとして扱われます。
