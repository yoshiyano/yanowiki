"""プラグインの引数に書いたページ名を、リネーム時に書き換える。

`wikilib.pagelinks` が本文の記法上のリンク（`[表示](先)`・`[[表示>先]]`）を
書き換えるのと同じことを、`PLUGIN_INFO["args"]` で `"link": True` と宣言
された引数の値に対しても行う。

これまでは「気づく」ところまでしか無かった。`"link": True` の値は
`wikilib.links.plugin_arg_links` によってリンク元データベースには記録され
backlinksからも見つかっていたが、リネーム時に**値そのものを書き換える処理は
無く**、実際には古い名前のまま本文に残ってしまっていた（詳しくは
`Tech/RenamePage#現状の課題`）。

## 位置の見つけかた

プラグインの呼び出しは記法ごとに書きかたが違う（Markdown: `#name(args)`
`&name(args);`、PukiWiki: 見た目は同じだが別の正規表現）。ここでは新しく
パーサを書き起こさず、それぞれの記法が本文をパースするのに使っている
既存の正規表現（`wikilib.plugins`・`wikilib.pukiwiki`）をそのまま再利用し、
argsグループがマッチした文字位置をそのまま使う。

本文中の文字列を直接正規表現で走査する点は `pagelinks.link_spans` と同じ
（`links` テーブルの設計と同様、位置ではなく「書かれた文字列が何を指すか」
だけをキャッシュに持てば、書き換えのたびに位置は本文へ素直にかければ
見つかる）。コードブロック・インラインコードに書かれた、プラグイン呼び出しに
似た文字列を誤って拾わないよう、`pagelinks.excluded_ranges` と同じ考えかたで
除外する。

## 値の書き換えかた

1つ1つの値については `pagelinks.rewritten_href` をそのまま使う（絶対/相対の
選びかた・動いた場合の見直しは `pagelinks.rewrite_links` と完全に同じルール
にするため）。argstr の中の「値だけ」（クオートを除いた実際の値の範囲。
`wikilib.plugins.parse_plugin_args_spans` が返す）を新しい文字列に差し替える。
クオートで囲まれていた場合、クオートそのものは範囲に含まれないのでそのまま残る。
"""
from wikilib import pukiwiki
from wikilib.pagelinks import default_engine, excluded_ranges, is_excluded, resolve_href, rewritten_href
from wikilib.paths import pagepath_of_subpath
from wikilib.plugins import (
    PLUGIN_BLOCK_HEAD_RE, bind_plugin_args_spans,
    match_plugin_block, match_plugin_inline, parse_plugin_args_spans,
)


def _line_starts(text):
    """各行の開始位置（本文全体での絶対オフセット）を、行の並びと一緒に返す。"""
    lines = text.split("\n")
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    return lines, starts


def _md_calls(text):
    """Markdown記法の本文から、プラグイン呼び出しを (名前, argstr, 開始, 終了)
    で前から順に返す。開始・終了は argstr（丸括弧の中身）の絶対位置。

    ブロックは `plugins.match_plugin_block` を1行ずつ試す（本体の `{…}`/`{{…}}`
    の中身は複数行にまたがりうるが、args自体は開始行の中で閉じる作りのため、
    行単位の走査で足りる。入れ子のプラグイン呼び出しも、その行がそのまま
    別の呼び出しとして拾われる）。"""
    calls = []
    lines, starts = _line_starts(text)
    for lineno, line in enumerate(lines):
        if not PLUGIN_BLOCK_HEAD_RE.match(line):
            continue
        m = match_plugin_block(line)
        if not m:
            continue
        name, args, _tail, args_start, args_end = m
        base = starts[lineno]
        calls.append((name, args, base + args_start, base + args_end))
    pos = 0
    while True:
        idx = text.find("&", pos)
        if idx == -1:
            break
        m = match_plugin_inline(text, idx)
        if m:
            name, args, _body, args_start, args_end, end = m
            calls.append((name, args, args_start, args_end))
            pos = end
        else:
            pos = idx + 1
    return calls


def _puki_calls(text):
    """PukiWiki記法の本文から、同じ形で呼び出しを返す。"""
    calls = []
    lines, starts = _line_starts(text)
    for lineno, line in enumerate(lines):
        m = pukiwiki.PLUGIN_BLOCK_RE.match(line)
        if not m or m.group(2) is None:
            continue  # 括弧を省いた呼びかた（#contents 等）は引数が無い
        base = starts[lineno]
        calls.append((m.group(1), m.group(2), base + m.start(2), base + m.end(2)))
    pos = 0
    while True:
        found = pukiwiki.find_amp_token(text, pos)
        if not found:
            break
        _amp_start, result = found
        if result[0] == "plugin":
            _, name, args, _body, args_start, args_end, end = result
            if args is not None:
                calls.append((name, args, args_start, args_end))
            pos = end
        else:
            pos = result[-1]
    return calls


def plugin_call_spans(text, ext, engine=None):
    """本文中のプラグイン呼び出しを (名前, argstr, 開始, 終了) で返す
    （地の文＝コードブロック・インラインコードに書かれたものは除く）。"""
    calls = _puki_calls(text) if ext == ".txt" else _md_calls(text)
    if not calls:
        return calls
    tokens = pukiwiki.parse(text) if ext == ".txt" else (engine or default_engine()).parse(text)
    ranges = excluded_ranges(text, tokens)
    if not ranges:
        return calls
    return [c for c in calls if not is_excluded(c[2], c[3], ranges)]


def rewrite_plugin_arg_links(text, ext, subpath, renames, registry, old_subpath=None,
                             wiki_dir=None, interwiki=None, engine=None):
    """本文中のプラグイン呼び出しの引数（`"link": True` と宣言されたもの）に
    書かれたページ名を書き換える。(新しい本文, 書き換えた数) を返す。

    renames・old_subpath の意味は `pagelinks.rewrite_links` と同じ
    （renames は {旧ページパス: 新ページパス}、old_subpath はこのページ自身が
    動いた場合にその動く前の実体パスを渡す）。registry は
    `wikilib.plugins.load_plugins` の戻り値（`engine.plugin_registry`）。

    宣言に `candidate` があるなど、書かれた値と解決後の値が食い違いうる
    引数は対象外（`bind_plugin_args_spans` が返す span は「型変換前の生の
    位置」なので、そこにある文字列がそのまま href と一致する前提で書き換える。
    通常 `link: True` の引数は自由入力のページ名・URLであり `candidate` とは
    組み合わせないため、実用上は問題にならない）。"""
    lookup = {"/" + old: new for old, new in (renames or {}).items()}
    moved = old_subpath is not None and old_subpath != subpath
    if not lookup and not moved:
        return text, 0
    if not registry:
        return text, 0

    calls = plugin_call_spans(text, ext, engine=engine)
    if not calls:
        return text, 0

    resolve_base = old_subpath if moved else subpath
    new_base = pagepath_of_subpath(subpath)

    edits = []
    for name, argstr, call_start, _call_end in calls:
        entry = registry.get(name)
        if entry is None or entry.get("error"):
            continue
        schema = (entry.get("info") or {}).get("args") or ()
        link_names = [item["name"] for item in schema if item.get("link")]
        if not link_names:
            continue
        args, kwargs = parse_plugin_args_spans(argstr)
        resolved, err, spans = bind_plugin_args_spans(args, kwargs, schema)
        if err is not None:
            continue
        for lname in link_names:
            span = spans.get(lname)
            if span is None:
                continue  # defaultを使った・rest_paramsで連結された等、安全に書き換えられる位置が無い
            href = resolved.get(lname)
            if not isinstance(href, str) or not href.strip():
                continue
            resolved_link = resolve_href(resolve_base, href, wiki_dir, interwiki)
            if resolved_link is None:
                continue
            _kind, owner, filename = resolved_link
            if not moved and owner not in lookup:
                continue
            new_owner = lookup.get(owner, owner[1:])
            if filename and moved and new_owner == new_base:
                continue
            new_href = rewritten_href(href, subpath, new_owner, filename,
                                      old_owner=owner,
                                      old_subpath=old_subpath if moved else None)
            if new_href == href:
                continue
            rel_start, rel_end = span
            edits.append((call_start + rel_start, call_start + rel_end, new_href))

    if not edits:
        return text, 0
    edits.sort()
    out, last = [], 0
    for start, end, new_text in edits:
        out.append(text[last:start])
        out.append(new_text)
        last = end
    out.append(text[last:])
    return "".join(out), len(edits)
