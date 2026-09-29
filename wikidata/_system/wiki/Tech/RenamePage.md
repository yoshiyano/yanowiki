# リネームの仕組み

#code()

編集者は、編集画面の「[ファイル一覧](/FilesGuide)」から名前を変えたり別の場所へ移したりします（中身はこのページの仕組み）。
このページは実装の全体像と課題です。DBのスキーマは[ページのデータベース](/Tech/PageDataBase)、
細かい決まり（絶対/相対の判断など）は[リファレンス](/Tech/Reference/Rename)にあります。

ページ・フォルダの名前や置き場所を変える（ファイル一覧から、`pagerename.py`）と、それを
指していたリンクが自動で書き換わります。手がかりは、保存のたびにDB
（`pageinfo/wikiall.db`）へ集めているリンク元の記録です。

## リンクをどう集めているか

保存のたびに、本文から参照先を取り出して `links` テーブル
（`source, href, kind, owner, filename`）に記録します（`wikilib.links.extract_page_info`）。
取り出しかたは2つです。

1. **本文のリンク構文**（`[[…]]`・`[…](…)`）: `pagelinks.link_spans` で本文を走査する
   （`wikilib.links.page_links`）。
2. **プラグインの引数**: `PLUGIN_INFO["args"]` で `"link": True` と宣言された引数の値
   （`wikilib.links.plugin_arg_links`）。プラグインは実行せず `bind_plugin_args` で束ねるだけ
   なので、重いプラグインがあっても安全です。

どちらも `pagelinks.resolve_href` で「ページか、添付か、対象外（外部URL・InterWiki・
別Wiki・ページ内アンカー）か」を判定するので、扱いは食い違いません。

`owner`（指している先）に索引があり、逆リンクはそこを引くだけ（`pagedb.backlinks_of`）
で求まります。リネームが直す相手を知る手段はこれだけです。

## リネームの流れ

`pagerename.rename_page`:

1. ページ（フォルダなら配下も）の実体を動かす。
2. `pagedb.rename_page` でDBの行を付け替える（本文は変わらないので拾い直さない）。
3. 動いたページを指していたページを逆リンクから集める（`pagerename.fix_links`）。
   DBに記録が無ければ、直す対象に挙がらない。
4. 集めたページの本文を `pagelinks.rewrite_links` と
   `pluginlinks.rewrite_plugin_arg_links` で書き換えて保存し直す（編集画面からの保存と
   同じ扱いで、差分もDBの再登録も伴う）。

書き換えるときは、相対・絶対を近さで選び直します。遠くなった相対リンクは絶対リンクに、
すぐ隣まで近づいた絶対リンクは相対リンクにします（`../../p3/page/age/ten` のような
書きかたを残さないため。決まりは[リファレンス](/Tech/Reference/Rename#絶対と相対はどちらで書くか)、
実装は `pagelinks.rewritten_href`）。

プラグインの引数は、値の文字位置が正確に分からないと置き換えられないので、
`parse_plugin_args_spans`/`bind_plugin_args_spans`（束ねの規則は同じで、値の位置も返す）を
使います。既定値を使った値や `rest_params` で連結された値など、位置が一意に決まらない
ものは書き換えません。呼び出しの位置は、描画と同じ正規表現（`plugins.match_plugin_block`・
`plugins.PLUGIN_INLINE_RE`、`pukiwiki.PLUGIN_BLOCK_RE`・`pukiwiki.INLINE_RE`）で見つけます。

## 移し先に選ばれたページは、フォルダの入口になる

`X.txt` とフォルダ `X/` は同居できません（`resolve_page_ref` はフォルダがあれば中の
`index` を読むので、`X.txt` が読めなくなる。`pagedb.shadowed_pages` が拾う状態）。

そこで、まだ下位を持たないページを移し先に選ぶと、そのページを `X/index` へ移してから
フォルダにします（`pagerename.make_folder_entry`）。本文・添付・変更の記録・書きかけと
DBの実体パスをまとめて付け替えます。ページパスは `X` のままなので、URLもリンクも
変わりません。

## `{{ }}` の中は対象外

プラグインの中身（`#name(){{` … `}}`）に書かれたリンクは直しません
（Wiki設計者の判断、2026-09-05）。`pagelinks.excluded_ranges` が地の文から除くのは
`fence` / `code_block` / `html_block` だけで、`plugin_block` の中身は見ていないため、
いまは「プラグインによって直ったり直らなかったりする」状態です。

`#code` は中身をそのまま見せ、`#note` は中身をWikiテキストとして描くので、一律には
除けません。正しく分けるには `PLUGIN_INFO` に「中身をそのまま見せる」の宣言が要りますが、
そこまではせず、「`{{ }}` の中にリンクを書かない」を
[共通の書きかた](/Syntax/Common#プラグインの呼びかた)に書き手の決まりとして置きました。

## 現状の課題

### 入れ子になったプラグイン呼び出しは抽出されない

`#note(){{ #ls(folder=Tech/Old) }}` の内側の `#ls` は見つかりません。
`plugin_arg_links` はプラグインを実行せずに解析するので、本体は未解釈の文字列のままです。

### 区切り文字で複数の値を持つ引数と相性が悪い

`recent.py` の `exclude`（`;` 区切り・ワイルドカードあり）のような引数に `"link": True` を
付けると、`target=Tech/A;Tech/B` が「Tech/A;Tech/B」という存在しないページへの参照として
記録されます。`"link": True` は単一のページ/添付パスを持つ引数に限ります
（[プラグイン仕様の`link`の節](/Tech/dev_plugin/spec/args_options#link-引数の値をページ添付への参照として扱う)）。

### 1つの引数のミスで、その呼び出し全体の抽出が止まる

同じ呼び出しの他の引数が間違っていると（`bind_plugin_args` がエラーを返すと）、
`link` 引数も抽出されません。

```pukiwiki
#ls(folder=Tech/A, unknownarg=1)
→ folder は正しいのに、unknownarg のせいで抽出0件
```

描画はエラー表示になるので気づけますが、直してもリネームで見つからないまま残ります。

## `"link": True` の宣言状況

書きかたは[プラグイン仕様の引数の宣言（args）](/Tech/dev_plugin/spec/args#引数の宣言args)にあります。
いま宣言しているのは `img`・`include`・`ls`・`navi`・`ref` の5つです（宣言の追加は
wikiPlugin プロジェクトの作業）。
