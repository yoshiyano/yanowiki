"""プラグイン機構。

プラグインの読み込み・引数の解釈・markdown-itへの記法の登録・呼び出しをまとめる。
1つのプラグインの不備がwiki全体を巻き込まないよう、例外はすべてこの中で受け止め、
使っている箇所だけのエラー表示に変える。
"""
import importlib.util
import inspect
import os
import re
import sys
import traceback
from html import escape

from bottle import HTTPResponse
from markdown_it import MarkdownIt

from wikilib import htmlpolicy
from mdit_py_plugins.anchors import anchors_plugin

from wikilib import cjkemphasis
from wikilib import mdcomment
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote.index import (
    render_footnote_anchor, render_footnote_anchor_name, render_footnote_block_close,
    render_footnote_block_open, render_footnote_caption, render_footnote_close,
    render_footnote_open, render_footnote_ref,
)

from wikilib.paths import (
    PLUGIN_DEFAULT_INFO, PLUGIN_DIR, PLUGIN_MAX_DEPTH, PLUGIN_URLPATH,
)
from wikilib.paths import farm_plugin_dir
from wikilib.render import is_pukiwiki, render_softbreak
from wikilib.subst import render_display_time
from wikilib.web import plain, static_file
from wikilib.wikiconfig import is_debug, plugin_debug_enabled

# 見出しにidを振る範囲。目次のリンク先だけでなく、ページ内アンカー（#見出し）や
# セクション編集の宛先にも使うため、表示の都合（toc_depth）とは切り離して
# システム側の方針として全レベルに振る。記法が増えても同じ約束にするための取り決め。
HEADING_ID_MAX_LEVEL = 6


class PluginArgumentError(Exception):
    """プラグインが自分の判断で「この呼びかたは正しくない」と伝えるための例外。

    `_convert`/`_inline`/`_action` の中で `raise PluginArgumentError("理由")` する。
    `call_plugin`/`render_plugin_action` がこれを捕まえ、宣言（`PLUGIN_INFO["args"]`）
    レベルのエラーとまったく同じ見た目（`plugin_error_html`）で表示する。

    選べる値の一覧・フォルダとして解決できるかといった、宣言だけでは表せない
    プラグイン固有の検証に使う（`ls`のフォルダ確認、`recent`の`;`区切りの
    確認など）。プラグイン側は表示の組み立てかたを一切知らなくてよく、
    理由の文字列を渡すだけでよい。

    予期しない不具合（それ以外の例外）とは扱いを変えている。**トレースバックは
    出さない**——想定内の「使いかたが違う」を伝えるためのもので、実装の中身を
    見せる必要が無いため。"""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason

def discover_plugin_paths(farm_plugin_dir):
    """プラグインファイルを {プラグイン名: パス} で返す。

    全Wiki共通の plugin/ → 個別Wiki固有の plugin/ の順に見て、同名は個別Wiki固有で上書きする
    （個別Wikiの設定が全Wiki共通の設定を上書きする、というこのシステム全体の考えかたに揃えている。
    テーマが個別Wiki固有を優先するのと同じ）。
    "." や "_" で始まるファイルは対象外（編集中の一時ファイルや共有モジュール置き場のため）。"""
    paths = {}
    for plugin_dir in (PLUGIN_DIR, farm_plugin_dir):
        if not plugin_dir or not os.path.isdir(plugin_dir):
            continue
        for fname in sorted(os.listdir(plugin_dir)):
            if not fname.endswith(".py") or fname.startswith((".", "_")):
                continue
            paths[fname[:-3]] = os.path.join(plugin_dir, fname)
    return paths


# 1回の要求の中で読み込んだプラグインを置いておく、要求の environ のキー
REQUEST_PLUGIN_CACHE_KEY = "wikisystem.plugin_registry"


def _request_plugin_cache():
    """いまの要求の中で使い回す、読み込み済みのプラグインの入れもの。要求の外なら None。"""
    try:
        from bottle import request
        environ = request.environ
    except (RuntimeError, AttributeError, KeyError, ImportError):
        return None
    if not isinstance(environ, dict):
        return None
    return environ.setdefault(REQUEST_PLUGIN_CACHE_KEY, {})


def load_plugins(farm_plugin_dir):
    """プラグインを読み込んで {名前: エントリ} を返す。

    エントリは {"module":…, "info":…, "error":…}。読み込みに失敗しても例外は投げず、
    error にメッセージを残して次へ進む。1つのプラグインの不備でwiki全体が
    見られなくなるのを避けるため（エラーはそのプラグインを使っている箇所にだけ表示する）。

    **1回の要求の中では、読み込んだものを使い回す**（Wiki設計者の指示、2026-09-27）。
    `#pagediv`・`#include`・`#calendar_viewer` などで別のページを差し込むたびに
    `build_markdown_renderer` が呼ばれ、そのたびに全プラグインをファイルから読み込み
    直していた（差し込むページが7つある実ページのプレビューで21回・約900回の読み込み、
    描画0.34秒のうち0.18秒）。使い回すのは同じ要求の中だけで、**要求ごとに読み込み直す
    これまでの決まりは変えない**（プラグインを直せば、次の要求から効く）。入れものは
    要求の environ（`REQUEST_PLUGIN_CACHE_KEY`）に置くので、要求をまたいで残らない。
    要求の外（CLI・取り込みの描き直し）では、これまでどおり毎回読み込む。

    同じ要求の中で、同じモジュール（プラグインのモジュール変数）を共有することになる。
    プラグインは状態を `context` に持つ決まりなので、差し支えない。"""
    cache = _request_plugin_cache()
    key = str(farm_plugin_dir)
    if cache is not None and key in cache:
        return cache[key]
    registry = _load_plugins_uncached(farm_plugin_dir)
    if cache is not None:
        cache[key] = registry
    return registry


def _load_plugins_uncached(farm_plugin_dir):
    registry = {}
    for name, path in discover_plugin_paths(farm_plugin_dir).items():
        entry = {"module": None, "info": dict(PLUGIN_DEFAULT_INFO), "error": None, "path": path}
        try:
            spec = importlib.util.spec_from_file_location(f"wikiplugin_{name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            entry["module"] = module
            info = getattr(module, "PLUGIN_INFO", None)
            if isinstance(info, dict):
                entry["info"].update(info)
        except Exception:
            entry["error"] = traceback.format_exc()
        if entry["info"].get("args"):
            entry["info"]["args"] = _expand_flag_sugar(entry["info"]["args"])
        schema = entry["info"].get("args") or ()
        _warn_rest_params_conflict(name, schema)
        _warn_unknown_arg_keys(name, schema)
        if not entry["error"]:
            schema_error = _validate_args_schema(name, schema)
            if schema_error:
                entry["error"] = schema_error
        registry[name] = entry
    return registry


def _warn_rest_params_conflict(plugin_name, schema):
    """`rest_params: True` より後ろに引数の宣言が続いていたら、それらが
    無視されることをサーバーコンソールへ警告する（読み込みのたびに1回。
    呼び出しのたびではない）。"""
    rest_at = next((i for i, spec in enumerate(schema) if spec.get("rest_params")), None)
    if rest_at is None:
        return
    ignored = [spec["name"] for spec in schema[rest_at + 1:]]
    if ignored:
        print(
            f"[plugin:{plugin_name}] rest_params（{schema[rest_at]['name']}）より後ろの"
            f"引数宣言は無視されます: {', '.join(ignored)}",
            file=sys.stderr,
        )


# `PLUGIN_INFO["args"]`の1つの項目が持てるキーの一覧。`_warn_unknown_arg_keys`
# が、ここに無いキー（`defualt`のような宣言キー自体の打ち間違い等）を
# 検出するのに使う。新しいキーを実装で読むようになったら、ここにも足すこと。
ALLOWED_ARG_SPEC_KEYS = {
    "name", "default", "candidate", "type", "min", "max", "label",
    "num_order", "flag", "rest_params", "link", "kw_only",
}


def _warn_unknown_arg_keys(plugin_name, schema):
    """`args`の各項目に、`ALLOWED_ARG_SPEC_KEYS`に無いキーが書かれていたら
    サーバーコンソールへ警告する（読み込みのたびに1回）。

    宣言キー自体の打ち間違い（`defualt`等）や、`kw_only`のように意味を
    持たない位置で書いた新機能のキーは、これまで黙って無視されていた
    （束ねる側がspecの中身のキーを検証していなかったため）。それに
    気づけるようにするのが目的で、`_warn_rest_params_conflict`と同じく
    プラグインの読み込み自体は失敗させない（気づく手段があれば形式は
    問わないため、厳格な読み込みエラーにはしていない）。"""
    for spec in schema:
        unknown = sorted(set(spec) - ALLOWED_ARG_SPEC_KEYS)
        if unknown:
            print(
                f"[plugin:{plugin_name}] {spec.get('name', '?')}: "
                f"argsの宣言に知らないキーがあります（無視されます）: {', '.join(unknown)}",
                file=sys.stderr,
            )


def _expand_flag_sugar(schema):
    """`"flag": True` を `candidate`/`type` の宣言に展開する（読み込み時に1回）。

        {"name": "wrap", "flag": True, "default": False}
            ↓
        {"name": "wrap", "candidate": ["wrap"], "type": "bool", "default": False}

    「その項目自身の名前と同じ単語が書かれていれば True」という、本家
    PukiWikiに頻出する真偽フラグの糖衣構文。展開後は普通の`candidate`/
    `type`宣言と同じに扱われる（`flag`自体はこの先どこも読まない）。"""
    expanded = []
    for spec in schema:
        if spec.get("flag"):
            spec = dict(spec)
            spec.setdefault("candidate", [spec["name"]])
            spec.setdefault("type", "bool")
        expanded.append(spec)
    return expanded


def _validate_args_schema(plugin_name, schema):
    """`args`宣言そのものの不備を確かめる（プラグイン読み込み時に1回）。
    問題が無ければNone、あればそのままentryのerrorにできる理由の文字列を返す。

    ここでの「エラー」はプラグインが使い物にならなくなる不備（num_orderの
    欠番・candidateのタプルの形・自由順序なのにdefaultが無い）。宣言順が
    num_orderの昇順になっていないだけなら、動作はできるのでエラーにはせず
    _warn_rest_params_conflictと同じ形の警告にとどめる。"""
    uses_num_order = any(spec.get("num_order") for spec in schema)

    for spec in schema:
        shape_error = _validate_candidate_shape(spec.get("candidate"))
        if shape_error:
            return f"[{plugin_name}] {spec['name']}: {shape_error}"

    if not uses_num_order:
        return None

    positives = sorted(spec["num_order"] for spec in schema
                       if isinstance(spec.get("num_order"), int) and spec["num_order"] > 0)
    if positives != list(range(1, len(positives) + 1)):
        return (f"[{plugin_name}] num_orderが1から始まる連番になっていません: "
               f"{positives}")

    negatives = [spec["num_order"] for spec in schema
                if isinstance(spec.get("num_order"), int) and spec["num_order"] < 0]
    if any(n != -1 for n in negatives):
        return (f"[{plugin_name}] num_orderの負の値は-1のみ許容されます: "
               f"{negatives}")
    if len(negatives) > 1:
        return (f"[{plugin_name}] num_orderが負の項目（残りの位置引数の受け皿）は"
               f"1つまでです（{len(negatives)}個あります）")

    declared_order = [spec["num_order"] for spec in schema
                      if isinstance(spec.get("num_order"), int) and spec["num_order"] > 0]
    if declared_order != sorted(declared_order):
        print(
            f"[plugin:{plugin_name}] args の宣言順がnum_orderの昇順になっていません"
            f"（{declared_order}）。動作はしますが、読みにくいので順番を揃えることを勧めます。",
            file=sys.stderr,
        )

    for spec in schema:
        if not spec.get("num_order") and "default" not in spec:
            return (f"[{plugin_name}] {spec['name']}: num_orderの無い項目は"
                   "defaultも必須です（自由順序の項目は「書かれているかどうか」で"
                   "存在を判定するため、位置での必須化ができません）。")

    for spec in schema:
        if not spec.get("kw_only"):
            continue
        if spec.get("num_order"):
            return (f"[{plugin_name}] {spec['name']}: kw_only と num_order は"
                   "同時に指定できません（位置に固定することと、位置には出ない"
                   "ことが矛盾します）。")
        if spec.get("flag"):
            return (f"[{plugin_name}] {spec['name']}: kw_only と flag は"
                   "同時に指定できません（単語を書くだけで有効になるという"
                   "flagの趣旨と、名前付き専用であることが矛盾します）。")
    return None


def call_plugin_setup(registry, context):
    """各プラグインの _setup(context) を呼ぶ。HTTPリクエストごとに1回。
    例外はそのプラグインのerrorに記録するだけで、他のプラグインには波及させない。"""
    for entry in registry.values():
        module = entry["module"]
        if entry["error"] or module is None:
            continue
        setup = getattr(module, "_setup", None)
        if not callable(setup):
            continue
        try:
            setup(context)
        except Exception:
            entry["error"] = traceback.format_exc()


def parse_plugin_args(argstr):
    """プラグインの引数をカンマ区切りで解析し、(位置引数のlist, 名前付き引数のdict) を返す。

    key=value は名前付き引数、それ以外は位置引数になる。
    引用符（" または '）で囲めば、カンマや = を含む値も1つの引数として渡せる。

    カンマの間に何も書かない空の区切り（`#name(a,,c)` の2つ目）は、
    「この位置は指定しない」という意味の位置引数として None を積む
    （`bind_plugin_args` はこれを「省略された」と同じに扱い、宣言の既定値を
    使う）。手前を素通りさせて後ろだけ位置で書きたいとき、手前をすべて
    名前で書かずに済む（`#ls(, , MTIME_REV)` で folder と recursive を
    省き、3つ目の sort だけ位置で指定できる）。

    ただし `#name()` のように**そもそも引数を書いていない**場合は、この
    「空の位置引数」とは区別し、args も kwargs も空のままにする。"""
    parts = split_plugin_args(argstr)
    if len(parts) == 1 and parts[0].strip() == "":
        return [], {}  # 引数をまったく書いていない（空の位置引数1個、ではない）

    args, kwargs = [], {}
    for raw in parts:
        item = raw.strip()
        if not item:
            args.append(None)  # 空の区切り＝「ここは飛ばす」の位置引数
            continue
        key, sep, value = partition_plugin_arg(item)
        if sep:
            kwargs[key] = unquote_plugin_arg(value.strip())
        else:
            args.append(unquote_plugin_arg(item))
    return args, kwargs


def split_plugin_args(argstr):
    """引用符の中のカンマを区切りとみなさずに分割する。"""
    parts, buf, quote = [], [], None
    for ch in argstr:
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def partition_plugin_arg(item):
    """引用符の外にある最初の "=" で key と value に分ける。無ければ ("", "", "")。"""
    quote = None
    for i, ch in enumerate(item):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "=":
            return item[:i].strip(), "=", item[i + 1:]
    return item, "", ""


def unquote_plugin_arg(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


# ---- 引数の位置つき解析（プラグイン引数中のリンク値をリネーム時に書き換えるため） --

def _split_plugin_args_with_offsets(argstr):
    """split_plugin_args と同じ分割を、各部分の argstr 内での開始位置つきで返す。
    [(部分文字列, 開始位置), ...]。"""
    parts, buf, quote, part_start = [], [], None, 0
    for i, ch in enumerate(argstr):
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append(("".join(buf), part_start))
            buf = []
            part_start = i + 1
        else:
            buf.append(ch)
    parts.append(("".join(buf), part_start))
    return parts


def _find_unquoted_eq(item):
    """partition_plugin_arg と同じ規則で、引用符の外にある最初の"="の位置を返す。
    無ければ None。"""
    quote = None
    for i, ch in enumerate(item):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "=":
            return i
    return None


def _strip_span(s, base):
    """s の前後の空白を除いた文字列と、その (開始, 終了)（base を起点とした
    絶対位置）を返す。"""
    stripped = s.strip()
    if not stripped:
        return "", base, base
    lead = len(s) - len(s.lstrip())
    start = base + lead
    return stripped, start, start + len(stripped)


def _unquote_span(s, start):
    """クオートで囲まれていれば剥がした値と、その実際の値の (開始, 終了) を返す。
    s は既に前後の空白を取り除いた文字列、start はその s の開始絶対位置。"""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1], start + 1, start + len(s) - 1
    return s, start, start + len(s)


def parse_plugin_args_spans(argstr):
    """parse_plugin_args と同じ解析をしつつ、各値の argstr 内での位置
    （クオートを除いた実際の値そのものの範囲）も一緒に返す。

    (args, kwargs) を返す。
        args:   [(値, (開始, 終了)) または None, ...]（None＝空の区切り）
        kwargs: {キー: (値, (開始, 終了))}

    値そのものは parse_plugin_args と同じ（unquote済み）。位置は
    「リネームでプラグイン引数中のページ名を書き換える」ためだけに使う
    （wikilib.pluginlinks を参照）。"""
    parts = _split_plugin_args_with_offsets(argstr)
    if len(parts) == 1 and parts[0][0].strip() == "":
        return [], {}

    args, kwargs = [], {}
    for raw, offset in parts:
        item, item_start, _item_end = _strip_span(raw, offset)
        if not item:
            args.append(None)
            continue
        eq = _find_unquoted_eq(item)
        if eq is not None:
            key = item[:eq].strip()
            value_start = item_start + eq + 1
            vstripped, vstart, _vend = _strip_span(item[eq + 1:], value_start)
            value, vstart2, vend2 = _unquote_span(vstripped, vstart)
            kwargs[key] = (value, (vstart2, vend2))
        else:
            value, vstart2, vend2 = _unquote_span(item, item_start)
            args.append((value, (vstart2, vend2)))
    return args, kwargs


# PLUGIN_INFO["args"] で宣言する型のうち、値そのものを変換するもの。
# "str"（既定・宣言省略時も同じ）は変換しない。
BOOL_TRUE_WORDS = ("true", "yes", "on", "1")
BOOL_FALSE_WORDS = ("false", "no", "off", "0")


def _coerce_bool(raw):
    """"true"/"yes"/"on"/"1" と "false"/"no"/"off"/"0"（大文字小文字を問わない）
    を bool にする。(値, エラー文言) を返す。エラーなら値はNone。"""
    word = str(raw).strip().lower()
    if word in BOOL_TRUE_WORDS:
        return True, None
    if word in BOOL_FALSE_WORDS:
        return False, None
    return None, f"{raw}（true か false で指定してください）"


def _coerce_int(raw, minimum=None, maximum=None):
    """整数にする。min/max を宣言していれば範囲も確かめる。(値, エラー文言) を返す。"""
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None, f"{raw}（数字で指定してください）"
    if minimum is not None and value < minimum:
        return None, f"{raw}（{minimum}以上で指定してください）"
    if maximum is not None and value > maximum:
        return None, f"{raw}（{maximum}以下で指定してください）"
    return value, None


def _coerce_float(raw, minimum=None, maximum=None):
    """小数にする（整数の書きかたも受け付ける）。min/max を宣言していれば
    範囲も確かめる。(値, エラー文言) を返す。"""
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None, f"{raw}（数で指定してください）"
    if minimum is not None and value < minimum:
        return None, f"{raw}（{minimum}以上で指定してください）"
    if maximum is not None and value > maximum:
        return None, f"{raw}（{maximum}以下で指定してください）"
    return value, None


def _resolve_arg_value(raw, spec):
    """1つの値を、宣言（`candidate`/`type`/`min`/`max`）にかけて確かめる。
    (値, エラー文言) を返す（問題無ければエラーはNone）。

    candidate は文字列としての書かれかたを確かめるものなので、型変換より
    先に生の文字列へ適用する（型変換したあとの値ではなく、常に文字列を
    相手にする）。candidate が一致した場合は、一覧に書かれた表記（大文字
    小文字）に揃えた文字列を受け取る。

    **`flag: True` の項目は、`candidate`（自分の名前）に一致した時点で
    `True` を返す。** その先の型変換（`_coerce_bool`）にはかけない
    ——一致した単語そのもの（例: `"wrap"`）を`true`/`false`の書きかたと
    誤解して変換しようとすると、必ず失敗するため。"""
    raw, err = _check_candidate(raw, spec.get("candidate"))
    if err is not None:
        label = spec.get("label", spec["name"])
        return None, f"{label}の指定が正しくありません: {err}"
    if spec.get("flag"):
        return True, None
    kind = spec.get("type", "str")
    if kind == "bool":
        value, err = _coerce_bool(raw)
    elif kind == "int":
        value, err = _coerce_int(raw, spec.get("min"), spec.get("max"))
    elif kind == "float":
        value, err = _coerce_float(raw, spec.get("min"), spec.get("max"))
    else:
        value, err = raw, None
    if err is not None:
        label = spec.get("label", spec["name"])
        return None, f"{label}の指定が正しくありません: {err}"
    return value, None


def _is_blank(raw):
    return raw is None or (isinstance(raw, str) and raw.strip() == "")


def bind_plugin_args(args, kwargs, schema):
    """位置引数（args）と名前付き引数（kwargs）を、宣言（schema）の順番に沿って
    `{名前: 値}` へ束ねる。(束ねた結果, エラー文言) を返す（エラーなら結果はNone）。

    schema は `PLUGIN_INFO["args"]` の形。1つの項目は次の形。

        {"name": "folder"}                                   型省略＝文字列のまま。defaultが無いので必須
        {"name": "recursive", "type": "bool", "default": False, "label": "再帰"}
        {"name": "num", "type": "int", "default": 10, "min": 1, "label": "表示件数"}
        {"name": "target", "label": "対象"}                   defaultが無いので必須
        {"name": "note", "default": None, "label": "備考"}    defaultがNone＝省略してよい。値は気にしない
        {"name": "sort", "candidate": ["FNAME", "MTIME", "TITLE"], "default": "FNAME"}
        {"name": "code", "candidate": [(r"[A-Za-z]{2}-\\d{3}", "re")]}  正規表現で検証。defaultが無いので必須
        {"name": "target", "link": True}                       値をページ/添付への参照として扱う
        {"name": "rest"}                                     rest_params: True と組み合わせて可変長引数に使う（下記）
        {"name": "wrap", "flag": True, "default": False}      flag糖衣構文（下記）
        {"name": "src", "num_order": 1, "candidate": [FREE_TEXT]}  自由順序＋位置固定（下記）
        {"name": "exclude", "kw_only": True, "default": None}     自由順序専用・名前付きでしか書けない（下記）

    **`default` を宣言していない項目は必須。** 省略（空文字列も含む）される
    とそこでエラーになる。値がどんなものでもよく、書かなくても構わない項目
    には、`"default": None` を明記して必須ではないことを示す（`default` の
    値そのものは使わないが、キーがあることで「必須ではない」と区別する）。

    **`link: True` はこの関数では読まない。** `wikilib.links.plugin_arg_links`
    が、この項目の解決済みの値をページ本文のリンクと同じ扱い（リンク元
    データベースへの記録＝「このページからどこを参照しているか」の一部）に
    するための目印。値が実際にこのWiki内の場所を指しているかどうか（外部URL
    なら対象外、等）は `wikilib.pagelinks.resolve_href` が判断するので、
    ここでは「この引数はリンクかもしれない」と宣言するだけでよい。
    リネーム時に値そのものを書き換える処理（`wikilib.pluginlinks`）は、
    ここではなく `bind_plugin_args_spans`（この関数と同じ束ねを行いつつ、
    argstr内の位置も一緒に返す版）を使う。

    `candidate`（許す値の一覧）は、書かれた文字列をそのまま確かめる簡易
    ルール。文字列（大文字小文字を区別しない完全一致）に加え、
    `(パターン, "re")`（正規表現。`re.fullmatch` で全体一致）・
    `(文字列, "case")`（大文字小文字を区別する完全一致）のタプルを
    混ぜて書ける。詳しくは `_check_candidate` を参照。

    宣言された型（`"bool"`/`"int"`/`"float"`）は、ここで値に変換する。変換できない場合は
    そこで打ち切ってエラー文言を返す（`label` があればそれを、無ければ `name` を
    使って「〇〇の指定が正しくありません」の形にする）。それ以外の検証
    （選べる値の一覧・ページとして解決できるか等）は、宣言では表せない
    プラグイン固有の意味づけなので、`_convert` 側で束ねた値をさらに確かめる。

    **宣言に無い引数はエラーにする。** 黙って無視すると、書いた側が
    「効いているつもり」のまま気づけず混乱するため（位置引数が多すぎる・
    名前付き引数の名前を間違えた、のどちらも対象）。

    ## `num_order` を1つも宣言していない場合（既定・後方互換）

    **宣言の並びが、そのまま位置引数の順番になる**（旧来どおり）。
    「1つ目だけ名前で書いて、2つ目以降は位置で書く」（`#ls(folder=Tech,
    true)`）ときに、2つ目のために書いた `"true"` が繰り上がって1つ目の枠に
    誤って入らないよう、**名前で埋まった枠は飛ばして次の枠に入る。**

    `rest_params: True` を付けた項目は、残りの位置引数を丸ごと1つの
    文字列として受け取る（可変長引数）。値は消費されずに残っている `args`
    を `","` で結合したもの、何も残っていなければ `""`。型変換・
    `candidate`・`default`/必須の判定は行わない。**この項目より後ろに
    書かれた宣言は無視される**（`load_plugins` が読み込み時にサーバー
    コンソールへ警告を出す）。キーワード（`名前=値`）では指定できない。

    ```python
    "args": [{"name": "a"}, {"name": "rest", "rest_params": True}]
        → #name(1, x, y, z) は a="1", rest="x,y,z"
        → #name(1) は a="1", rest=""
    ```

    ## `num_order` を1つでも宣言している場合（自由順序）

    1つでも `num_order` を書くと、schema全体がこちらの解決順序で束ねられる
    （新旧を1つのschema内で混ぜない）。**この場合、`num_order`を書かない
    項目は`default`も必須**（自由順序の項目は「書かれているかどうか」で
    存在を判定するため、位置での必須化ができない）。宣言時に守られていな
    ければ、プラグインの読み込みが失敗する。

    - **正の整数**: 位置引数の何番目に固定するか（1始まり、1からの連番で
      なければプラグイン読み込み時のエラーになる）。値が空（コンマの間を
      飛ばした省略）なら `default` を使う。**値はあるが `candidate`
      に合わない場合は、通常どおり検証エラーになる**（黙ってスキップする
      のは「空だった場合」だけ）。
    - **負の整数**: 他のどの固定位置・自由順序の項目にも当てはまらな
      かった、残っている位置引数をすべて拾い `","` で連結する
      （`rest_params` に近いが、こちらは他の項目との併用が前提）。
      キーワード（`名前=値`）で指定した場合は連結せず、その値をそのまま
      使う。**負の値として使えるのは `-1` だけ**（大小に意味を持たせない
      ため）。schema内に負の`num_order`の項目を2つ以上書くと、どちらが
      拾うか曖昧になるため、プラグイン読み込み時のエラーになる
      （1つのschemaに書けるのは高々1つ）。
    - **無し**: 自由な位置・自由な順序。**残っている位置引数を、宣言順に
      1つずつ試し**、`candidate` に一致した最初の項目がその値を
      受け取る（一致条件を書いていない項目は「何にでもマッチする」＝
      `FREE_TEXT` と同じ扱い）。**一度あるトークンがどれかの項目の値として
      確定したら、他の項目に再割り当てされることはない。** 複数の項目が
      同じトークンにマッチしうる場合、**宣言順で先に書かれたほうが採用
      される**（例: `fg`/`bg` が同じ色指定を共有する場合、単独のトークンは
      常に `fg` に決まる。`bg` だけを指定したいなら `bg=...` と名前で書く）。

    どの項目にも当てはまらない位置引数が残り、かつ負の`num_order`の項目も
    無い場合は「引数の解釈に失敗しました。」でエラーになる。

    `kw_only: True` を付けた項目は、上の「無し」（自由順序）の候補から
    常に外れる——`candidate`の一致すら試さない。位置引数に紛れ込むことが
    無いので、打ち間違えた位置引数を誤って拾ってしまう（＝黙って通って
    しまう）ことがない。`exclude=...`のように名前付きで書いた場合は
    ステップ1で従来どおり受け取り、`candidate`/`type`/`min`/`max`の検証も
    そのまま働く。**`num_order`か`flag`と同時に書くとプラグイン読み込み
    エラーになる**（位置固定・省略記法のどちらも「名前付き専用」と
    意味が矛盾するため）。`num_order`を1つも使わないschemaでは、そもそも
    自由順序の解決には入らないため`kw_only`を書いても意味が無く、
    宣言してもエラーにはしない（無視される）。

    `flag: True` は次の省略記法（本家PukiWikiに頻出する「単語を書くだけで
    有効になる」真偽フラグ）。

    ```python
    {"name": "wrap", "flag": True, "default": False}
        # {"name": "wrap", "candidate": ["wrap"], "type": "bool", "default": False} と同じ
    ```

    「存在すれば`True`」の判定のみで、`wrap=false`のような明示的な打ち消し
    は書けない（書くと通常の「知らない引数です」等のエラーになる）。"""
    resolved, err, _spans = _bind_plugin_args_impl(
        [None if v is None else (v, None) for v in args],
        {k: (v, None) for k, v in kwargs.items()},
        schema)
    return resolved, err


def bind_plugin_args_spans(args, kwargs, schema):
    """bind_plugin_args と同じ束ねを行いつつ、各値が argstr 内のどこに
    書かれていたか（span）も一緒に返す。

    args/kwargs は `parse_plugin_args_spans` の戻り値をそのまま渡す
    （値が `(値, (開始, 終了))` の形をしていること）。

    (束ねた結果, エラー文言, {名前: (開始, 終了)}) を返す。エラー時は
    3つ目も None。span がわからない名前（default を使った・rest_params で
    連結した・自由順序で割り当てられなかった等）は3つ目の辞書に入らない
    ——**値を書き換えたい側は、名前がこの辞書に無ければ「安全に書き換えられる
    位置が無い」として諦めること**（wikilib.pluginlinks を参照）。"""
    return _bind_plugin_args_impl(args, kwargs, schema)


def _bind_plugin_args_impl(args, kwargs, schema):
    """bind_plugin_args / bind_plugin_args_spans の共通実装。args/kwargs の
    値は常に `(値, span)` の形（span は None でもよい）。
    (束ねた結果, エラー文言, {名前: span}) を返す（span が無いキーは含めない）。"""
    if any(spec.get("num_order") for spec in schema):
        return _bind_free_order_args_impl(args, kwargs, schema)
    return _bind_positional_args_impl(args, kwargs, schema)


def _bind_positional_args_impl(args, kwargs, schema):
    """`num_order` を1つも使わない、旧来の宣言順＝位置引数の順番での束ねかた。"""
    resolved = {}
    spans = {}
    pos = 0
    # rest_params より後ろの宣言は対象から外す（load_plugins が読み込み時に
    # 警告を出す。ここでは黙って切り捨てるだけでよい）
    rest_at = next((i for i, spec in enumerate(schema) if spec.get("rest_params")), None)
    effective = schema if rest_at is None else schema[:rest_at + 1]
    active = [spec for spec in effective if not spec.get("rest_params")]
    names = {spec["name"] for spec in active}
    unknown = [key for key in kwargs if key not in names]
    if unknown:
        return None, f"知らない引数です: {', '.join(unknown)}", None
    for spec in effective:
        name = spec["name"]
        if spec.get("rest_params"):
            # 残りの位置引数を丸ごと1つの文字列にする（可変長引数）。
            # キーワードでは受け付けない・型変換やcandidate・
            # default/必須の判定もしない（常にこの形で値が入る）。
            # 連結後は元の位置が失われるので span は持たせない
            resolved[name] = ",".join("" if item is None else (item[0] or "") for item in args[pos:])
            pos = len(args)
            continue
        if name in kwargs:
            raw, span = kwargs[name]
        elif pos < len(args):
            item = args[pos]
            raw, span = item if item is not None else (None, None)
            pos += 1
        else:
            raw, span = None, None
        if _is_blank(raw):
            if "default" not in spec:
                label = spec.get("label", name)
                return None, f"{label}を指定してください。", None
            resolved[name] = spec.get("default")
            continue
        value, err = _resolve_arg_value(raw, spec)
        if err is not None:
            return None, err, None
        resolved[name] = value
        if span is not None:
            spans[name] = span
    if pos < len(args):
        return None, f"引数が多すぎます（{len(active)}個までです）。", None
    return resolved, None, spans


def _bind_free_order_args_impl(args, kwargs, schema):
    """`num_order` を使う、自由順序での束ねかた（詳しくは bind_plugin_args を参照）。"""
    names = {spec["name"] for spec in schema}
    unknown = [key for key in kwargs if key not in names]
    if unknown:
        return None, f"知らない引数です: {', '.join(unknown)}", None

    fixed = sorted((s for s in schema if isinstance(s.get("num_order"), int) and s["num_order"] > 0),
                   key=lambda s: s["num_order"])
    free = [s for s in schema if not s.get("num_order")]
    rest = [s for s in schema if isinstance(s.get("num_order"), int) and s["num_order"] < 0]

    resolved = {}
    spans = {}
    done = set()  # キーワードで確定済みの名前

    # 1) キーワードで明示された分を先に確定させる（固定・自由順序・残り物、どれでも）
    for spec in schema:
        name = spec["name"]
        if name not in kwargs:
            continue
        raw, span = kwargs[name]
        # 残り物の項目をキーワードで書いた場合も、連結の対象にしないだけで
        # candidate/type の検証は他の項目と同じにかける（以前はここだけ
        # 素通ししており、style属性等へそのまま埋め込む引数で検証をすり抜け
        # られる抜け穴になっていた）
        value, err = _resolve_arg_value(raw, spec)
        if err is not None:
            return None, err, None
        resolved[name] = value
        if span is not None:
            spans[name] = span
        done.add(name)

    # 2) 正の num_order を固定位置として埋める
    tokens = list(args)  # 消費した位置は None に潰していく（元のargsは変えない）
    for spec in fixed:
        name = spec["name"]
        if name in done:
            continue
        idx = spec["num_order"] - 1
        item = tokens[idx] if idx < len(tokens) else None
        raw, span = item if item is not None else (None, None)
        if idx < len(tokens):
            tokens[idx] = None
        if _is_blank(raw):
            if "default" not in spec:
                label = spec.get("label", name)
                return None, f"{label}を指定してください。", None
            resolved[name] = spec.get("default")
            continue
        value, err = _resolve_arg_value(raw, spec)
        if err is not None:
            return None, err, None
        resolved[name] = value
        if span is not None:
            spans[name] = span

    # 3) 残っているトークンを、自由順序の項目へ宣言順に割り当てる
    for i, item in enumerate(tokens):
        if item is None:
            continue
        raw, span = item
        for spec in free:
            name = spec["name"]
            if name in done or name in resolved:
                continue
            if spec.get("kw_only"):
                # 位置引数の割り当て候補から常に外れる（candidateの一致すら
                # 試さない）。名前付き（kwargs）指定はステップ1で既に処理済み。
                continue
            value, err = _resolve_arg_value(raw, spec)
            if err is None:
                resolved[name] = value
                if span is not None:
                    spans[name] = span
                tokens[i] = None
                break

    for spec in free:
        name = spec["name"]
        if name not in done and name not in resolved:
            resolved[name] = spec.get("default")

    # 4) 残ったトークンはすべて負の num_order（-1のみ許容、schema内に高々1個）へ連結する
    leftover = [item[0] for item in tokens if item is not None]
    if rest:
        target = rest[0]
        if target["name"] not in done:
            resolved[target["name"]] = ",".join(leftover)
    elif leftover:
        return None, "引数の解釈に失敗しました。", None

    return resolved, None, spans


# candidate に混ぜて書ける「何にでもマッチする」パターン（自由順序の項目を
# 自由な文字列で受け取りたいときに使う。詳しくは _check_candidate 参照）。
FREE_TEXT = ("^.*$", "re")


def _check_candidate(raw, candidate):
    """`candidate`（許す値の一覧）を宣言していれば、そこに含まれるか確かめる。

    一覧の要素は、文字列（**大文字小文字を区別しない**完全一致。
    "fname" でも "FNAME" と一致する）と、`(パターン, 種別)` の2要素タプル
    （`"case"`＝大文字小文字を区別する完全一致、`"re"`＝正規表現。
    `re.fullmatch` で全体一致を見る）を混ぜて書ける。`FREE_TEXT`
    （`("^.*$", "re")`）は「何にでもマッチする」ためにあらかじめ用意した値。

    一致すれば (一覧に書かれた表記に揃えた値, None) を返す。文字列要素に
    大文字小文字を区別せず一致した場合、書いたままの表記ではなく**候補側の
    表記**に揃える（プラグイン側で改めて正規化しなくて済むように）。タプル
    （`"case"`/`"re"`）に一致した場合は、書いたままの値をそのまま返す
    （揃える先の「候補側の表記」が無いため）。
    宣言していなければ (raw, None) をそのまま返す。"""
    if candidate is None:
        return raw, None
    values = list(candidate)
    for v in values:
        if isinstance(v, tuple):
            pattern, kind = v
            if kind == "case" and raw == pattern:
                return raw, None
            if kind == "re" and re.fullmatch(pattern, str(raw)) is not None:
                return raw, None
            continue
        if str(raw).lower() == str(v).lower():
            return v, None
    return None, f"{raw}（" + " / ".join(_candidate_label(v) for v in values) + "）"


def _candidate_label(v):
    """エラー文言で候補の一覧を示すときの表記。タプルはパターンだけ見せる。"""
    return v[0] if isinstance(v, tuple) else str(v)


def _validate_candidate_shape(candidate):
    """`candidate` にタプルを混ぜて書いた場合の形を確かめる（プラグイン読み込み
    時に使う）。おかしければ理由の文字列を、問題無ければ None を返す。"""
    for v in candidate or ():
        if not isinstance(v, tuple):
            continue
        if len(v) != 2 or not isinstance(v[0], str) or v[1] not in ("case", "re"):
            return f"candidateのタプルの形が正しくありません: {v!r}"
    return None


def build_markdown_renderer(config, farm_plugin_dir, context=None, policy=None):
    md_conf = config.get("markdown") or {}
    engine = MarkdownIt(md_conf.get("preset", "gfm-like"))
    # 生HTMLをパーサーに認識させるか。認識させなければ、書かれたものは
    # 文字になる（htmlpolicy参照）。**ここはMarkdownの解析にだけ効く。**
    # PukiWikiの解析は wikilib.pukiwiki が行い、そちらは pukiwiki.allow_html
    # を見る（render.parse_source）
    # policy を渡すと、そのエンジンでは常にその水準で解釈する
    # （プラグインが自分の渡すテキストの扱いを決める場合。Wiki設計者の指示、
    # 2026-09-02）。渡さなければ設定（allow_html）に従う
    if policy is None:
        engine.options["html"] = htmlpolicy.parses_html(
            htmlpolicy.normalize_policy(md_conf.get("allow_html", False)))
        htmlpolicy.install(engine)
    else:
        policy = htmlpolicy.normalize_policy(policy)
        engine.options["html"] = htmlpolicy.parses_html(policy)
        htmlpolicy.install(engine, policy)
    if not md_conf.get("linkify", True):
        engine.disable("linkify")
    elif not md_conf.get("linkify_fuzzy", True):
        # linkify自体は有効のまま、"http://"の無い裸の語まで拾う判定だけ止める。
        # 既定（fuzzy_link有効）だと "CLAUDE.md" のような拡張子付きの語も
        # ドメインらしいと判定されリンクになってしまう
        # （"http://CLAUDE.md" になる。実際にこれで誤変換が起きた）。
        # "https://..." で始まる本物のURLの自動リンクはこの設定と無関係に働く。
        engine.linkify.set({"fuzzy_link": False, "fuzzy_email": False})
    # 日本語の中の **強調** が落ちるのをゆるめる（wikilib.cjkemphasis）。
    # 処理系全体に効く差し替えなので、組み立てるたびに呼んでも1度しか効かない
    cjkemphasis.install()
    if md_conf.get("anchors", True):
        # 見出しにidを振る。範囲は h1〜h6 の全部で、目次の深さ（toc_depth）とは切り離す。
        # idは目次のリンク先だけでなく、ページ内アンカー（#見出し）や
        # セクション編集の宛先にも使う「システム側の機能」だから
        # （どの見出しに振るかを表示の都合で決めてはいけない）。
        engine.use(anchors_plugin, min_level=1, max_level=HEADING_ID_MAX_LEVEL)

    # 定義リスト（Pandoc形式。`用語` の次行に `: 説明`）。トークンの形は
    # PukiWiki記法の定義リスト（`:項目名|説明文`、wikilib.pukiwiki.append_deflist）
    # と同じ dl/dt/dd に揃っているため、テーマのCSSは1種類で両方に効く。
    engine.use(deflist_plugin)

    # `<!-- … -->` をコメントとして取り除く（allow_html の設定によらない。wikilib.mdcomment）
    mdcomment.install(engine)

    install_token_renderers(engine)

    registry = load_plugins(farm_plugin_dir)
    # context を受け取らない呼び出し（wikilib.links の抽出など）でも、この engine
    # で見つかったプラグイン呼び出しがどの PLUGIN_INFO（args の "link" 宣言等）
    # に対応するかを引けるようにしておく。実行（call_plugin）はしない、
    # 静的な参照だけの用途のため、レジストリを持たせるだけで安全。
    engine.plugin_registry = registry
    if context is not None:
        context.registry = registry
        context.config = config
        call_plugin_setup(registry, context)
    register_plugin_rules(engine)

    # 旧来の register(md) 形式（markdown-it-py を直接拡張するプラグイン）も引き続き使える
    for name, entry in registry.items():
        module = entry["module"]
        if entry["error"] or module is None:
            continue
        register = getattr(module, "register", None)
        if callable(register):
            try:
                register(engine)
            except Exception:
                entry["error"] = traceback.format_exc()
    return engine

class PluginContext:
    """プラグインの各関数に渡す実行時の情報。

    plugins  … 名前→エントリのレジストリ（他のプラグインを呼びたい場合に使える）
    partial  … 部分プレビュー中か。Trueのとき need_outer_info なプラグインは処理されない
    ext      … いま描いているページの記法の拡張子（".md"/".txt"）。expand_*で
               プラグインの出力を再展開するとき、どちらの記法で解釈するかに使う
               （wikilib.plugins.expand_body）。ページの記法と無関係な
               画面（バックアップ管理・検索など）は既定の ".md" のままでよい。
    plugin_debug_override … ページ内で `#plugin_debug(true)` が使われたか
               （`plugin/plugin_debug.py`が立てる）。config の `plugin.debug`
               と OR で合わせるだけで、config が有効なものを無効化はできない
               （wikilib.plugins.plugin_debug_enabled ではなく、呼び出し側で
               このフラグと config の値を OR する）。
    theme_override … ページ単位でテーマ（theme.name相当）を差し替えたい
               プラグイン（wikitheme等）が立てる値。本文の描画から
               wikilib.themes.render_theme までこのインスタンスが同じまま
               流れることを使った差込口で、立てられていればconfigの
               theme.nameより優先される（wikiPluginからの依頼、2026-09-04）。
               既定はNone（config通りの動作のまま変わらない）。
               **閲覧者がセレクタで選んだテーマ（cookie）のほうが強い。**
               ページの指定を絶対にすると、そのページだけセレクタが黙って
               効かなくなるため（wikilib.themes.render_theme のdocstring
               参照。Wiki設計者の判断、2026-09-04）。
    view_block … 「このページの本文を出さない」とプラグインが決めたときの
               中身（`block_view` が立てる）。閲覧期間の設定など、
               **認証とは別の理由で表示を止めたい**プラグインのための
               差込口（Wiki設計者の指示、2026-09-05）。既定はNone。
               詳しくは `block_view` を参照。
    explicit_farm … URLが`/=<Wiki名>`を明示していたか。`base_url`は
               この値を織り込んで組み立て済みなので、通常は`base_url`を
               そのまま使えば足りる。`accounts.back_page_url`のように
               `(config, farm, wiki_dir, explicit_farm)`を引数に取る
               既存の関数へ、contextの外からそのまま渡すためだけに持たせて
               ある（Wiki設計者の指示、2026-09-11。`#login`プラグインの`_action`
               がアカウント側の関数を呼ぶために追加）。
    privilege … いまの閲覧者のアクセス権の判定器（`auth.PagePrivilege`）。
               `context.privilege.check(ページ名)` で `W`/`R`/`-` を返す
               （Wiki設計者の指示、2026-09-15）。詳しくは `privilege` を参照。
    """

    def __init__(self, config=None, farm=None, wiki_dir=None, page="", base_url="", partial=False,
                ext=".md", explicit_farm=False):
        self.config = config or {}
        self.farm = farm
        self.wiki_dir = wiki_dir
        self.page = page
        self.base_url = base_url
        self.partial = partial
        self.ext = ext
        self.explicit_farm = explicit_farm
        self.registry = {}
        self.used_plugins = set()  # このリクエストで実際に呼び出されたプラグイン名
        self.plugin_debug_override = False
        self.theme_override = None
        self.view_block = None
        self._privilege = None

    @property
    def privilege(self):
        """いまの閲覧者のアクセス権の判定器（`auth.PagePrivilege`）。

            context.privilege.check("Tech/Secret")   # → "W" / "R" / "-"

        **プラグインが自分で判定器を作らずに済むように置いてある**（Wiki設計者の指示、
        2026-09-15。「各プラグインでも privilege 回答への対応ができるように」）。
        閲覧者は `auth.current_uid` から取るので、成り代わり（`auth.act_as`）にも従う。

        別のページの本文を読むなら、`pagedb.published_ref` が返す `ref.privilege` を
        見ればよく、これは要らない。**平文を読み書きする場面**（`resolve_page_ref` は
        `privilege` を持たない）や、ページ名だけを並べる場面で使う。

        最初に聞かれたときに1回だけ作り、この context のあいだ使い回す。context は
        1回の要求ごとに作られるので、記録の変更が次の要求まで効かないことはない。
        途中で `act_as` の相手を変えても作り直さない点には注意。

        Wiki名は `wiki_dir` から求める（`published_ref` と同じ）。`farm` を持たない
        context（試験など）でも、cookie の照合が壊れないようにするため。"""
        if self._privilege is None:
            # auth は themes を、themes はこのモジュールを読むので、呼び出し時に読み込む
            from wikilib import auth
            from wikilib.pagesync import farm_of_wiki_dir
            uid = auth.current_uid(self.wiki_dir, farm_of_wiki_dir(self.wiki_dir))
            self._privilege = auth.page_privilege(self.wiki_dir, uid)
        return self._privilege

    def block_view(self, message, by="", status=200):
        """このページの本文を**出さない**よう頼む。受け付けたらTrue。

        閲覧期間の設定のように、**認証とは別の理由で表示を止めたい**
        プラグインのための窓口（Wiki設計者の指示、2026-09-05）。本文の描画から
        `wikilib.themes.render_with_theme` まで、このインスタンスが同じまま
        流れることを使っている（`theme_override` と同じ仕掛け）。

        message … 本文の代わりに出すHTML。プラグインが自分で組み立てる
                  （Wikiテキストで受け取りたいなら、渡す前に
                  `expand_body` などで展開しておく）

        止まったページは、本文が `message` に差し替わり、目次が消え、題名は
        ページ名になる（本文から取った見出しは使わない）。**編集リンクは
        そのまま残る**——閲覧できないことと編集できないことは別物で、閲覧を
        止めるプラグインが編集まで止めてよい理由が無いため（Wiki設計者の指示、
        2026-09-05）。編集そのものを止めたいなら、閲覧停止の上位の指定として
        別に用意する話になる。
        by      … 止めたプラグインの名前。記録と、追いかけるときの手がかり
        status  … 返すHTTPステータス。既定は200

        **先に立てたものが効く。** 同じページに止めるプラグインが2つあった
        ときは、上に書いてあるほうの言い分が残る（あとから来たものが黙って
        書き換えると、どちらが効いたのか読み手にも書き手にも分からなくなる）。

        ## これは「見せない」であって「読ませない」ではない

        止まるのは**ページを開いたときの本文の描画だけ**である。本文そのものは
        平文ファイルにもDBにも残っており、次のどれからも読めてしまう。

            編集画面（そのページのURLへ cmd=edit をPOST）
            見出し単位の取り出し（/.section/<ページ名>）
            編集画面の「履歴」タブ（そのページのURLへ cmd=history をPOST）
            検索の結果に出る抜粋、`#ls` や `#recent` に出るタイトル

        **秘密を守る用途には使えない。** 「時期が来るまで出さない」「役目を
        終えたので下げる」といった、見せかたの制御に使うもの。読ませたく
        ないものは、そもそも置かないか、前段のWebサーバー等で止めること。

        ## 別のページの本文を変換するプラグインは、自分で見に行くこと

        **ここが立つのは、その変換に渡した context だけ。** `#include` の
        ように**別のページの本文を別の context（`sub`）で変換する**
        プラグインは、変換したあとに `sub.view_block` を自分で見て、
        あればその `message` に差し替えなければならない。

            html, _, _ = render_source(engine, ref.body, ref.ext, ..., sub)
            if sub.view_block:
                html = sub.view_block["message"]

        見に行かないと、**止めたはずの本文がそのまま取り込み先に出る**
        （プラグインの戻り値は空文字列で、文言はこちらに入っているため）。
        止まるのは差し込まれた場所だけで、**取り込み元のページは普通に
        表示してよい**（Wiki設計者の判断、2026-09-05）。

        同じことをするプラグインを新しく作るときは、まず
        `plugin/include.py` の扱いを見ること（Wiki設計者の指示、2026-09-05）。
        共通の仕組みにまとめるかどうかは、そういうプラグインがもう1つ
        出てきた時点で改めて考える。
        """
        if self.view_block is not None:
            return False
        self.view_block = {"message": message, "by": by, "status": status}
        return True

    def deny_view(self, by=""):
        """このページを、**標準の「閲覧する権限がありません」の画面（403）で止める**。
        受け付けたらTrue。

        `block_view` の、権限用の定型版（Wiki設計者の指示、2026-09-21。`#readauth` の
        閲覧権限なしのメッセージを、wikiSystemの標準エラーページにそろえる）。
        文言を持たず、ページの権限（`config/privileges`）で断られたときと**同じ本文・同じ案内**
        （未ログインならログインのリンクつき。`wikilib.views.no_view_body_html`）を出し、
        ステータスは403にする。ほかは `block_view` と同じ（先に立てたものが効く。
        「見せない」であって「読ませない」ではない。別のページを変換するプラグインは
        `view_block` を自分で見る）。

        プラグインが自分の文言を出したいときは、これまでどおり `block_view` を使う。"""
        # views は plugins を読むので、呼び出し時に読み込む
        from wikilib import auth
        from wikilib.pagesync import farm_of_wiki_dir
        from wikilib.views import no_view_body_html

        logged_in = bool(self.wiki_dir) and auth.current_uid(
            self.wiki_dir, farm_of_wiki_dir(self.wiki_dir)) is not None
        return self.block_view(no_view_body_html(self.base_url, self.page, logged_in),
                               by=by, status=403)

    @property
    def plugins(self):
        return self.registry

    @property
    def debug(self):
        return is_debug(self.config)

    def page_headings(self, max_depth=6):
        """このページの見出し一覧を [{level, id, title}, ...] で返す。
        levelはページ内で最も浅い見出しを1とした相対的な深さ（目次と同じ数えかた）。

        **DBに取り出し済みの目次を読む。** 全文をパースし直さずに済み、
        表示されている内容（同じくDB）と食い違わない。まだ取り出していない
        ページ（作り直した直後など）だけ、その場でパースして補う。

        **閲覧の権限が無いページ（`-`）なら空**（Wiki設計者の指示、2026-09-15）。
        見出しは本文の一部なので、`#include` で読めないページを差し込もうとした
        場合などに、目次から漏れないようにする。"""
        from wikilib.auth import PAGE_NONE
        from wikilib.pagedb import load_page_info, published_ref
        from wikilib.render import build_toc, parse_source, split_title, uses_title_heading

        if not self.wiki_dir:
            return []
        ref = published_ref(self.wiki_dir, self.page)
        if ref is None or not ref.exists or ref.privilege == PAGE_NONE:
            return []
        info = load_page_info(self.wiki_dir, ref.subpath)
        if info is not None:
            return [e for e in info["toc"] if e["level"] <= max_depth]

        md_conf = (self.config or {}).get("markdown") or {}
        engine = MarkdownIt(md_conf.get("preset", "gfm-like"))
        engine.use(anchors_plugin, min_level=1, max_level=HEADING_ID_MAX_LEVEL)
        tokens = parse_source(engine, ref.body, ref.ext)
        _, tokens, _ = split_title(
            tokens, uses_title_heading(ref.ext, md_conf.get("first_h1_as_title", True)))
        return [e for e in build_toc(tokens) if e["level"] <= max_depth]

    # `recent_pages` は 2026-09-17 に外した。ページの一覧は `wikilib.pagelist` から
    # 取る（`pagelist.walk(...)` が返す `PageItem` に名前・タイトル・更新日時が揃い、
    # **閲覧の権限もそこで見る**）。並べ替えと件数の切り出しは使う側の仕事になった
    # ——`#recent` が「更新の新しい順に上から n 件」という見せかたを決めている。


PLUGIN_BLOCK_HEAD_RE = re.compile(r'^#([A-Za-z_][\w\-]*)\(')
PLUGIN_BLOCK_ONELINE_RE = re.compile(r'\{([^{}]*)\}')
PLUGIN_BLOCK_FENCE_RE = re.compile(r'(\{\{+)')
# インラインプラグインの頭部分（&name(args)）。body（{…}）は波括弧の対応を
# 数える必要があるため、正規表現には含めない（match_plugin_inline参照）
PLUGIN_INLINE_HEAD_RE = re.compile(r'&([A-Za-z_][\w\-]*)\(([^()]*)\)')


def match_plugin_inline(text, pos=0):
    """&name(args); / &name(args){body}; を、波括弧の対応を数えて正しく
    分解する。(name, args, body, args_start, args_end, end) を返す。
    text[pos:] がこの形に合わなければ None。

    match_plugin_block と同じ理由（expand_plugin で中身に別のインライン
    プラグイン呼び出しを入れ子にできるようになったため、単純な
    `\\{([^{}]*)\\}` だと、bodyの中に別の `{...}` があると最初の内側の `}`
    で終端と誤認識してしまう。例: `&color(fg=red){&size(115%){text};};`）。
    args側の丸括弧非対応（`[^()]*`）は変えない（既知の制約。color.pyの
    技術資料参照）。"""
    head = PLUGIN_INLINE_HEAD_RE.match(text, pos)
    if not head:
        return None
    name, args = head.group(1), head.group(2)
    args_start, args_end = head.start(2), head.end(2)
    i = head.end()
    body = None
    if i < len(text) and text[i] == "{":
        depth = 1
        j = i + 1
        n = len(text)
        while j < n:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body = text[i + 1:j]
                    i = j + 1
                    break
            j += 1
        else:
            return None  # 対応する閉じ括弧が見つからない
    if i < len(text) and text[i] == ";":
        return name, args, body, args_start, args_end, i + 1
    return None


def match_plugin_block(line):
    """#name(args)tail を、丸括弧の対応を数えて正しく分解する。
    (name, args, tail, args_start, args_end) を返す。閉じ括弧が見つからなければ
    None。args_start/args_end は line 内での args の開始・終了位置（プラグイン
    引数中のリンク値をリネーム時に書き換えるための位置情報。wikilib.pluginlinks
    を参照）。

    単純な貪欲マッチ（旧`(.*)`）だと、argsやtail（本体の{…}）に丸括弧が
    複数あるとき「行内の最後の)」まで引数として飲み込んでしまい、続く
    本体の取り出しに失敗していた（#note(type=tip){[リンク](/)}等）。
    引用符の中の丸括弧は対応として数えない（#note(label="a)b")のような
    値でも誤動作しないように）。"""
    head = PLUGIN_BLOCK_HEAD_RE.match(line)
    if not head:
        return None
    name = head.group(1)
    i = head.end()  # 開き括弧の直後
    depth = 1
    quote = None
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return name, line[head.end():i], line[i + 1:], head.end(), i
        i += 1
    return None  # 対応する閉じ括弧が無い


def plugin_block_rule(state, startLine, endLine, silent):
    start = state.bMarks[startLine] + state.tShift[startLine]
    line = state.src[start:state.eMarks[startLine]]
    m = match_plugin_block(line)
    if not m:
        return False

    name, args, tail = m[0], m[1], m[2].rstrip()
    body = None
    body_error = None
    lastLine = startLine

    oneline_m = PLUGIN_BLOCK_ONELINE_RE.fullmatch(tail)
    fence_m = PLUGIN_BLOCK_FENCE_RE.fullmatch(tail)
    if tail == "":
        pass  # 本体無し（#recent(5) 等）
    elif oneline_m:
        body = oneline_m.group(1)
    elif fence_m:
        fence = fence_m.group(1)
        # 開いた波括弧と同じ数以上の閉じ括弧が現れるまでを本文とする
        close_re = re.compile(r'^\}{' + str(len(fence)) + r',}\s*$')
        nextLine = startLine + 1
        lines = []
        found = False
        while nextLine < endLine:
            s = state.bMarks[nextLine] + state.tShift[nextLine]
            if close_re.match(state.src[s:state.eMarks[nextLine]]):
                found = True
                break
            lines.append(state.getLines(nextLine, nextLine + 1, state.blkIndent, False))
            nextLine += 1
        if found:
            body = "\n".join(lines)
            lastLine = nextLine
        else:
            # 閉じ括弧が見つからなくても、プラグインとしては受け取ってエラーを返す
            # （そうしないと書いた側には「ただの文字列になった」としか見えず、
            # 何が悪いのか気づけないため）
            body_error = f"本体を閉じる{'}' * len(fence)}が見つかりません（別の行に置いてください）。"
    else:
        # 1行の {…} にも、複数行の {{…}} にも当てはまらない書きかた
        # （例: {…} と {{…}} を1行で混同している）。これも同じ理由で
        # プラグインとして受け取り、エラーとして伝える。
        body_error = "本体（{…}）の書きかたが正しくありません。"

    if silent:
        return True

    token = state.push("plugin_block", "div", 0)
    token.meta = {"name": name, "args": args, "body": body, "body_error": body_error}
    token.map = [startLine, lastLine + 1]
    state.line = lastLine + 1
    return True


def plugin_inline_rule(state, silent):
    m = match_plugin_inline(state.src, state.pos)
    if not m:
        return False
    name, args, body, _args_start, _args_end, end = m
    if not silent:
        token = state.push("plugin_inline", "span", 0)
        token.meta = {"name": name, "args": args, "body": body}
    state.pos = end
    return True


def register_plugin_rules(engine):
    # alt に list/blockquote 等を含めることで、リスト項目や引用の中でもブロックプラグインが働く
    engine.block.ruler.before(
        "fence", "plugin_block", plugin_block_rule,
        {"alt": ["paragraph", "reference", "blockquote", "list"]},
    )
    # 既定のエンティティ処理より先に割り込ませる（&name(); が &amp; にされないように）
    engine.inline.ruler.before("entity", "plugin_inline", plugin_inline_rule)
    engine.add_render_rule("plugin_block", make_plugin_render("_convert", "#"))
    engine.add_render_rule("plugin_inline", make_plugin_render("_inline", "&"))


def render_footnote_ref_with_tip(self, tokens, idx, options, env):
    """注釈の参照（`[1]`）を描く。標準の描画に、中身を `title` として添える。

    **注釈はページの末尾にまとまる**ので、読んでいる場所からは中身が見えない。
    マウスを乗せれば確かめられるようにする（Wiki設計者の指示、2026-09-03）。

    中身は `wikilib.pukiwiki.append_annotations` が参照トークンの `meta["tip"]`
    に入れてある（描画のときには一覧側のトークンが見えないため、作る側で
    持たせている）。**注釈はPukiWiki記法（`((…))`）だけの書きかた**で、
    Markdown記法の脚注（`^[…]`・`[^1]`）は有効にしていないため、ここで見るのは
    その1つだけでよい。取れなければ何も足さない（番号をたどれば末尾で読める）。"""
    html = render_footnote_ref(self, tokens, idx, options, env)
    tip = (tokens[idx].meta or {}).get("tip")
    if not tip:
        return html
    return html.replace("<a href=", f'<a title="{escape(tip, quote=True)}" href=', 1)


def make_plugin_render(func_name, sigil):
    """ブロック用・インライン用のレンダリング関数を作る。呼び出す関数名だけが違う。"""
    def render(self, tokens, idx, options, env):
        token = tokens[idx]
        meta = token.meta
        context = (env or {}).get("wiki")
        return call_plugin(context, meta["name"], meta["args"], meta["body"], func_name, sigil,
                           body_error=meta.get("body_error"))
    return render


def render_subst_ref(self, tokens, idx, options, env):
    """`subst_ref` トークン（`&_date;` 等）の描画規則。プラグインと同じく
    `env["wiki"]` からcontextを受け取るが、呼ぶ先はレジストリではなく
    `wikilib.subst`（プラグインではないため）。"""
    meta = tokens[idx].meta
    context = (env or {}).get("wiki")
    return render_display_time(context, meta["name"], meta["arg"])


def render_char_ref(self, tokens, idx, options, env):
    """`char_ref` トークン（`&amp;`・`&#38;`のような文字実体参照・数値
    文字参照。wikilib.pukiwiki.amp_tokens参照）をそのまま返す。

    `wikilib.htmlpolicy`の`allow_html`は`html_inline`/`html_block`に
    かかるが、`char_ref`はそこに含めていない——ここへ来る内容は数字だけの
    数値参照か、Python標準のhtml.entities.html5に実在が確認できた名前
    だけに限られ、タグ・属性・スクリプトを注入する余地が無いため
    （allow_htmlの対象は「未知の生HTML」であって、検証済みの1文字ぶんの
    参照はそもそも対象外という判断。Wiki設計者の報告、2026-09-04）。"""
    return tokens[idx].content


def render_extra_rule_html(self, tokens, idx, options, env):
    """`extra_rule_html` トークン（PukiWiki記法の「ユーザ定義ルール」
    COLOR()/BGCOLOR()/SIZE()/BOLD 等、wikilib.extrarules.match_extra_rule
    による置換結果。wikilib.pukiwiki.parse_inline参照）をそのまま返す。

    `char_ref` と同じ理由でhtmlpolicyのallow_htmlの対象外にしている。
    こちらは検証済みの1文字ぶんの参照ではなく任意のHTML片だが、
    書いたのは**読み手ではなくWiki管理者**（config/pukiwiki.extrarules.yaml、
    無ければ雛形のconfig/pukiwiki.extrarules.example.yaml）という点で
    信頼レベルが本文の生HTMLとは違う。雛形のdocstringにも「危険な内容を
    書けてしまうので、ここに書くのは管理者だけにしてください」と明記
    されている。

    `pukiwiki.allow_html`（既定false）の対象を本文の生HTML
    （html_inline/html_block）に絞ったのは2026-09-02のXSS対策だが、
    COLOR()等の標準ルールが生成するHTMLも同じhtml_inlineトークンで
    出していたため、既定設定のままではこの標準ルールが常にエスケープされ
    効かなくなっていた（Wiki設計者の報告、2026-09-18に確認）。管理者が
    書いた設定は読み手の生HTMLと同列に扱うべきではないため、専用の
    トークン種別に分けて対象外にした。"""
    return tokens[idx].content


def call_plugin(context, name, args, body, func_name, sigil, depth=0, body_error=None):
    """プラグインを1つ呼び出し、HTML断片を返す。

    プラグインの不備はこの箇所だけのエラー表示にとどめ、ページ全体は描画し続ける。"""
    label = sigil + name
    if context is None:
        return plugin_error_html(name, "プラグインを実行できる状態ではありません", "", False)

    entry = (context.registry or {}).get(name)
    if entry is None:
        return plugin_error_html(
            name, "そのようなプラグインは見つかりません",
            f"plugin/{name}.py を用意するか、綴りを確認してください。", context.debug)
    if entry["error"]:
        return plugin_error_html(
            name, "プラグインの読み込みでエラーが発生しました",
            entry["info"].get("help", ""), context.debug, entry["error"])

    info = entry["info"]
    if info.get("need_outer_info") and context.partial:
        return plugin_notice_html(f"{label} は部分プレビューでは処理されません")

    # モジュールは読み込めているので、これ以降のエラーには _help()（無ければ
    # docstring）を添えられる。plugin_debug_enabled が有効なときだけ実際に見せる
    # （#plugin_debug(true) がページ内で使われていた場合も同様。config が
    # 有効な場合を無効化することはできない）
    long_help = plugin_help_text(entry["module"])
    show_long_help = plugin_debug_enabled(context.config) or context.plugin_debug_override

    # 本体（{…}）の書きかたそのものが崩れている場合、プラグインを呼ばずに
    # ここで終える（記法の誤りであって、プラグイン側の話ではないため）
    if body_error:
        return plugin_error_html(name, body_error, info.get("help", ""), context.debug,
                                 long_help=long_help, show_long_help=show_long_help)

    func = getattr(entry["module"], func_name, None)
    if not callable(func):
        kind = "ブロック" if func_name == "_convert" else "インライン"
        return plugin_error_html(
            name, f"このプラグインは{kind}記法に対応していません",
            info.get("help", ""), context.debug,
            long_help=long_help, show_long_help=show_long_help)

    # 実際に呼び出したプラグインとして記録しておく。ページ描画後、このページで
    # 使われたプラグインのCSSだけをまとめて読み込むために使う。
    context.used_plugins.add(name)

    # インラインプラグインの中身をブロックとして展開すると <p> で包まれて
    # しまうため、文中に置かれたものは常にインラインとして展開する
    is_inline = func_name == "_inline"

    try:
        positional, keyword = parse_plugin_args(args)
        resolved, err = bind_plugin_args(positional, keyword, info.get("args") or ())
        if err is not None:
            return plugin_error_html(name, err, info.get("help", ""), context.debug,
                                     long_help=long_help, show_long_help=show_long_help)
        # **中身（body）は、プラグインを呼ぶ前に展開しておく**
        # （Wiki設計者の指示、2026-09-02）。プラグインは展開済みのHTMLを受け取り、
        # 自分のHTMLに埋めて返す。返ってきたものは再パースしない
        result = func(resolved, expand_body(body, info, context, depth, is_inline),
                      context)
    except PluginArgumentError as exc:
        return plugin_error_html(name, exc.reason, info.get("help", ""), context.debug,
                                 long_help=long_help, show_long_help=show_long_help)
    except Exception:
        return plugin_error_html(
            name, "プラグインの実行でエラーが発生しました",
            info.get("help", ""), context.debug, traceback.format_exc(),
            long_help=long_help, show_long_help=show_long_help)

    if result is None:
        return ""
    # **プラグインが返したものは、そのまま出す。**（Wiki設計者の指示、2026-09-02）
    # 以前はここで返り値をもう一度パースしていた。中身を展開するのが目的
    # だったが、プラグイン自身が返したタグまで同じ1回のパースに乗るため、
    # 「本文のHTMLを止めるとプラグインの外枠まで文字になる」「外枠を通すと
    # 中身に書かれたHTMLも通る」という、どちらにも倒せない形になっていた。
    # 中身は上（funcを呼ぶ前）で展開済みなので、ここでは何もしない
    return str(result)


def expand_body(text, info, context, depth, is_inline=False):
    """プラグインに渡す中身（body）を、宣言された展開オプションに従って展開する。

    既定ではどれも無効＝書かれたものをそのままプラグインへ渡す。プラグインの入れ子は
    プラグインごとに考えかたが違うため、受け入れるものだけが明示的に宣言する形にしている。

    **どちらの記法で展開するかは、いま描いているページの記法
    （`context.ext`）に合わせる。** 以前はここが常にMarkdownで固定されて
    いて、PukiWikiページの中でプラグインの中身にPukiWiki記法（強調・
    リンクなど）を書いても展開されなかった。

    **中身が空（または空白だけ）なら、展開せずそのまま返す。** プラグインは
    `if not body:` のように「書かれていないか」を見て断ることがあり、その
    判断は**展開する前の生のテキスト**で行われるべきものだから（Wiki設計者の指示、
    2026-09-02）。展開を通すと空白だけの中身が消えて、これまで通っていた
    書きかたが断られるようになりかねない。

    `None`（`#comment()` のように中身を書いていない）もそのまま返す。
    プラグイン側が `None` と空文字を見分けている場合があるため。"""
    if text is None or not text.strip():
        return text
    want_plugin = info.get("expand_plugin")
    want_block = info.get("expand_block") and not is_inline
    want_inline = info.get("expand_inline")
    if not (want_plugin or want_block or want_inline):
        return text
    if depth >= PLUGIN_MAX_DEPTH:
        # プラグイン同士が互いを呼び合うような書き方をされても止まるようにする
        return plugin_notice_html("プラグインの入れ子が深すぎるため、ここで展開を打ち切りました")

    # プラグインが水準を決めていれば、それに従って展開する
    policy = htmlpolicy.resolve_policy(
        info.get("body_html"), context.config, getattr(context, "ext", ".md"))
    sub = build_expand_renderer(context, info, depth, policy)
    env = {"wiki": context}
    if is_pukiwiki(getattr(context, "ext", ".md")):
        return expand_pukiwiki_output(text, sub, context, want_block, env, policy)
    if want_block:
        return sub.render(text, env)
    return sub.renderInline(text, env)


def expand_pukiwiki_output(text, engine, context, want_block, env, policy=None):
    """PukiWiki記法での再展開。パーサーだけ `wikilib.pukiwiki` のものを使い、
    レンダラー（`plugin_block`/`plugin_inline` のレンダー規則を含む）は
    `build_expand_renderer` が組み立てた `engine` をそのまま使う。

    `pukiwiki.append_plugin_block` がMarkdown側とトークンの形を揃えて
    あるので、レンダー規則をそのまま共有できる（`engine.block.ruler`/
    `engine.inline.ruler` へ足したパーサー側の規則はMarkdown解析にしか
    効かないが、それらを登録していても実害は無い＝PukiWiki解析では
    そもそも参照されないため、build_expand_renderer 自体は記法によらず
    共通のまま使える）。"""
    from wikilib import pukiwiki
    from wikilib.extrarules import load_extra_rules
    from wikilib.interwiki import load_interwiki

    extra_rules = interwiki = None
    wikiname = True
    if context.wiki_dir is not None:
        extra_rules = load_extra_rules(context.config, context.wiki_dir)
        interwiki = load_interwiki(context.wiki_dir)
        wikiname = bool((context.config.get("pukiwiki") or {}).get("wikiname", True))
    allow_html = htmlpolicy.parses_html(htmlpolicy.resolve_policy(
        policy, context.config, getattr(context, "ext", ".md")))

    if want_block:
        tokens = pukiwiki.parse(text, extra_rules=extra_rules, interwiki=interwiki,
                                wikiname=wikiname, allow_html=allow_html)
    else:
        tokens = [pukiwiki.parse_inline_lines(
            text, extra_rules=extra_rules, interwiki=interwiki,
            wikiname=wikiname, allow_html=allow_html)]
    return engine.renderer.render(tokens, engine.options, env)


def install_token_renderers(engine):
    """markdown-it の標準に無いトークンの描きかたを登録する。

    ページ本体を描く engine と、プラグインの中身を描き直す engine
    （`build_expand_renderer`）の**両方がここを通る**。登録の無いトークンは
    markdown-it-py がタグ名の無い空タグ（`< />`）として出してしまうので、
    片方だけ足し忘れると、プラグインの中身でだけ表示が壊れる
    （`&size(150%){A&amp;B};` が `A< />B` になっていた）。"""
    # 脚注（footnote_ref など）は描画規則だけ使う。`engine.use(footnote_plugin)` は
    # Markdown記法そのもの（`[^1]` / `[^1]: …`）まで有効にしてしまうが、それは
    # [使えない書きかた](/Syntax/Markdown#使えない書きかた)で意図的に無効と
    # 明記した仕様のため使わない。PukiWiki記法の注釈 `((…))`
    # （wikilib.pukiwiki.append_annotations）がこの描画規則だけを使ってHTML化する。
    for name, render_func in (
        ("footnote_ref", render_footnote_ref_with_tip),
        ("footnote_block_open", render_footnote_block_open),
        ("footnote_block_close", render_footnote_block_close),
        ("footnote_open", render_footnote_open),
        ("footnote_close", render_footnote_close),
        ("footnote_anchor", render_footnote_anchor),
        ("footnote_caption", render_footnote_caption),
        ("footnote_anchor_name", render_footnote_anchor_name),
    ):
        engine.add_render_rule(name, render_func)

    # &_date; &_time; &_now; &lastmod; &lastmod(ページ名); …プラグインではない
    # 組み込みの置換（wikilib.subst）。PukiWiki記法（wikilib.pukiwiki）だけが
    # トークン化する（Syntax/PukiWikiにしか無い書きかたのため）。
    engine.add_render_rule("subst_ref", render_subst_ref)

    # &amp; &#38; …文字実体参照・数値文字参照（wikilib.pukiwiki.amp_tokens）。
    # これもPukiWiki記法だけがトークン化する。allow_htmlの対象外にするため
    # html_inlineではなく専用のchar_refで受ける（render_char_ref参照）。
    engine.add_render_rule("char_ref", render_char_ref)

    # COLOR()/BGCOLOR()/SIZE()/BOLD 等の「ユーザ定義ルール」の置換結果
    # （wikilib.extrarules.match_extra_rule）。同じ理由でhtml_inlineではなく
    # 専用のextra_rule_htmlで受ける（render_extra_rule_html参照）。
    engine.add_render_rule("extra_rule_html", render_extra_rule_html)

    # 段落の途中の改行。日本語だけの境目では空白を残さない
    # （wikilib.render.render_softbreak）。Markdown記法・PukiWiki記法の
    # どちらも同じ softbreak トークンになるので、ここ1か所で両方に効く。
    engine.add_render_rule("softbreak", render_softbreak)


def build_expand_renderer(context, info, depth, policy=None):
    """再展開用の markdown-it インスタンスを、許可された要素だけ有効にして組み立てる。

    PukiWikiとして展開する場合も、パーサーだけ `wikilib.pukiwiki` に差し替え、
    ここで作るインスタンスはレンダラー（`expand_pukiwiki_output` 参照）として
    共通に使う。"""
    md_conf = (context.config or {}).get("markdown") or {}
    engine = MarkdownIt(md_conf.get("preset", "gfm-like"))
    # 中身（body）を、どの水準で解釈するか。既定はそのページの設定に従う。
    # **プラグインが自分で決めることもできる**（PLUGIN_INFO の "body_html"、
    # あるいはこの関数の policy 引数。Wiki設計者の指示、2026-09-02）。
    # プラグインが返したHTMLのほうはそもそもパーサーを通さないので、
    # どちらの設定にも関わらずそのまま出る（call_plugin参照）
    policy = htmlpolicy.resolve_policy(
        info.get("body_html") if policy is None else policy,
        context.config, getattr(context, "ext", ".md"))
    engine.options["html"] = htmlpolicy.parses_html(policy)
    htmlpolicy.install(engine, policy)
    # プラグインの中身（body）をPukiWiki記法として再展開すると、COLOR() などの
    # 置換結果（extra_rule_html）や文字参照（char_ref）のトークンが出る
    # （wikilib.pukiwiki.parse_inline）。ページ本体と同じ描きかたを登録する
    install_token_renderers(engine)
    # Markdown記法の中身でも `<!-- … -->` はコメント（wikilib.mdcomment）
    mdcomment.install(engine)

    if info.get("expand_plugin"):
        # ブロックプラグイン記法（#name(...)）が展開されるかどうかは、ここでは
        # 決めない。ここはルールを登録するだけで、実際にブロックとして
        # 再解釈するかどうか（render を呼ぶか renderInline を呼ぶか）は
        # 呼び出し側（expand_body の want_block）が決める。
        # want_block が偽なら renderInline が呼ばれ、ブロックルールは
        # そもそも実行されないため、expand_block が偽の場合はここで
        # 登録していても展開されない。
        engine.block.ruler.before(
            "fence", "plugin_block", plugin_block_rule,
            {"alt": ["paragraph", "reference", "blockquote", "list"]},
        )
        engine.add_render_rule("plugin_block", make_nested_render("_convert", "#", depth + 1))

        # インラインプラグイン記法（&name();）は、インライン記法の一種として
        # expand_inline に従う。expand_block/renderInline の関係と対称に
        # なるよう、expand_inline が偽ならここで登録しない
        # （renderInline はブロックルールと違って常に実行されるため、
        # ルール自体を登録しないことでしか展開を止められない）。
        if info.get("expand_inline"):
            engine.inline.ruler.before("entity", "plugin_inline", plugin_inline_rule)
            # 展開の深さを1つ進めた状態で呼ぶ
            engine.add_render_rule("plugin_inline", make_nested_render("_inline", "&", depth + 1))

    if not info.get("expand_inline"):
        # インライン要素を許可していない場合、標準のインライン装飾は無効にする
        for rule in ("emphasis", "link", "image", "backticks", "strikethrough", "autolink"):
            try:
                engine.inline.ruler.disable(rule)
            except (KeyError, ValueError):
                pass
    return engine


def make_nested_render(func_name, sigil, depth):
    def render(self, tokens, idx, options, env):
        meta = tokens[idx].meta
        context = (env or {}).get("wiki")
        return call_plugin(context, meta["name"], meta["args"], meta["body"], func_name, sigil, depth,
                           body_error=meta.get("body_error"))
    return render


def plugin_help_text(module):
    """`_help()` があればその戻り値、無ければモジュールのdocstringを返す。

    プラグインが実行できないとき、`plugin_debug_enabled` が有効な場合だけ
    `plugin_error_html` がこれを折りたたみで添える。トレースバック（`is_debug`）
    が実装の中身を追う開発者向けなのに対し、こちらは「どう書けば動くか」を
    示す、プラグインの使い手・作り手向けのもの。

    `_help()` が例外を投げた場合は空文字にする（説明を出そうとして本体の
    エラー表示自体が壊れては本末転倒なため）。モジュールが無い（読み込みに
    失敗した等）場合も空文字。"""
    if module is None:
        return ""
    help_func = getattr(module, "_help", None)
    if callable(help_func):
        try:
            return str(help_func() or "").strip()
        except Exception:
            return ""
    return (inspect.getdoc(module) or "").strip()


def plugin_error_html(label, message, help_text, debug, detail="",
                      long_help="", show_long_help=False):
    """プラグインが実行できないときの表示。

    **ページの見た目を壊さないよう、標準では1行の太字だけにする**
    （`** 名前 plugin error : 使いかた` の形。色は `.plugin-error-summary` で
    付ける）。個別の理由（`message`）はページの読み手より直す人向けの情報
    なので、標準では出さない。

    `show_long_help`（`plugin.debug`）が有効なときだけ、行の末尾に
    `[詳細]` を足して開閉できるようにし、開いた中に `message` と
    `long_help`（`_help()`。無ければモジュールのdocstring）を並べる。

    トレースバック（`detail`）は `debug`（server.yamlのdebug、実装の中身を
    追う開発者向け）で出す、これとは別口の開閉。`plugin.debug` が無効でも
    `debug` が有効なら独立して見られるよう、常に外側に置く。"""
    name = escape(label.lstrip("#&"))
    line = f"** {name} plugin error : {escape(help_text)}" if help_text \
        else f"** {name} plugin error"

    html = ['<div class="plugin-error">']
    if show_long_help and (message or long_help):
        html.append(
            '<details class="plugin-error-summary">'
            f'<summary><strong>{line} '
            '<span class="plugin-error-toggle">'
            '<span class="is-closed">[詳細]</span>'
            '<span class="is-open">[閉じる]</span>'
            '</span></strong></summary>'
        )
        if message:
            html.append(f'<p class="plugin-error-message">{escape(message)}</p>')
        if long_help:
            html.append(f'<pre>{escape(long_help)}</pre>')
        html.append('</details>')
    else:
        html.append(f'<p class="plugin-error-summary"><strong>{line}</strong></p>')
    if debug and detail:
        html.append(
            '<details class="plugin-error-detail"><summary>詳細（トレースバック）</summary>'
            f'<pre>{escape(detail)}</pre></details>'
        )
    html.append("</div>")
    return "".join(html)


def plugin_notice_html(message):
    return f'<div class="plugin-notice">{escape(message)}</div>'


def plugin_asset_path(farm_plugin_dir, name, ext):
    """プラグインが自前で持つ資材（例: CSS）のパスを探す。
    discover_plugin_paths と同じ優先順位（個別Wiki固有が全Wiki共通を上書き）で、
    "plugin/<name>.py" と同じ名前の "<name><ext>" を探す。無ければNone。"""
    found = None
    for plugin_dir in (PLUGIN_DIR, farm_plugin_dir):
        if not plugin_dir:
            continue
        candidate = os.path.join(plugin_dir, name + ext)
        if os.path.isfile(candidate):
            found = candidate
    return found


def plugin_asset_urls(base_url, farm_plugin_dir, used_plugins, ext):
    """このページで実際に使われたプラグインのうち、その資材を持つものだけURLにする。
    出現順ではなく名前順にして、毎回同じ並びになるようにしている。"""
    urls = []
    for name in sorted(used_plugins):
        if plugin_asset_path(farm_plugin_dir, name, ext) is not None:
            urls.append(f"{base_url}/{PLUGIN_URLPATH}/{name}{ext}")
    return urls


def plugin_style_urls(base_url, farm_plugin_dir, used_plugins):
    """使われたプラグインのCSS（plugin/<name>.css）のURL一覧。"""
    return plugin_asset_urls(base_url, farm_plugin_dir, used_plugins, ".css")


def plugin_script_urls(base_url, farm_plugin_dir, used_plugins):
    """使われたプラグインのJavaScript（plugin/<name>.js）のURL一覧。

    CSSと同じ考えかたで、プラグインが動きを持つ場合はそれも自分で連れてくる。
    読み込みは defer なので、置き場所によらずDOMが揃ってから走る。"""
    return plugin_asset_urls(base_url, farm_plugin_dir, used_plugins, ".js")


def serve_plugin_asset(wiki_dir, name, ext=".css"):
    """プラグイン自身が持つCSS/JSを配信する（/.plugin/<name>.css、/.plugin/<name>.js）。
    プラグインで使う資材は、基本的にテーマではなくプラグイン自身が持つ
    （note.py なら plugin/note.css）。個別Wiki固有のプラグインが同名で
    上書きしている場合は、そちらを優先する。"""
    path = plugin_asset_path(farm_plugin_dir(wiki_dir), name, ext)
    if path is None:
        return plain("no page", status=404)
    return static_file(os.path.basename(path), root=os.path.dirname(path))


def render_plugin_action(wiki_dir, config, farm, explicit_farm, name):
    """/.plugin/<name> でプラグインの _action(context) を呼ぶ。
    フォームの送信先やAPIの提供に使う。戻り値はそのままレスポンスになる
    （文字列を返せばHTMLとして、bottleのHTTPResponseを返せばそのまま返る）。"""
    if not name:
        return plain("no page", status=404)

    from wikilib.themes import make_plugin_context  # 循環を避けるため呼び出し時に読み込む

    context = make_plugin_context(config, farm, wiki_dir, PLUGIN_URLPATH + "/" + name, explicit_farm)
    context.config = config
    context.registry = load_plugins(farm_plugin_dir(wiki_dir))
    call_plugin_setup(context.registry, context)

    entry = context.registry.get(name)
    if entry is None:
        return plain("no page", status=404)
    if entry["error"]:
        body = plugin_error_html(name, "プラグインの読み込みでエラーが発生しました",
                                 entry["info"].get("help", ""), context.debug, entry["error"])
        return HTTPResponse(body=body, status=500, content_type="text/html; charset=utf-8")

    action = getattr(entry["module"], "_action", None)
    if not callable(action):
        return plain("no page", status=404)

    try:
        result = action(context)
    except PluginArgumentError as exc:
        body = plugin_error_html(name, exc.reason,
                                 entry["info"].get("help", ""), context.debug,
                                 long_help=plugin_help_text(entry["module"]),
                                 show_long_help=plugin_debug_enabled(context.config) or context.plugin_debug_override)
        return HTTPResponse(body=body, status=400, content_type="text/html; charset=utf-8")
    except Exception:
        body = plugin_error_html(name, "プラグインの実行でエラーが発生しました",
                                 entry["info"].get("help", ""), context.debug, traceback.format_exc(),
                                 long_help=plugin_help_text(entry["module"]),
                                 show_long_help=plugin_debug_enabled(context.config) or context.plugin_debug_override)
        return HTTPResponse(body=body, status=500, content_type="text/html; charset=utf-8")

    if isinstance(result, HTTPResponse):
        return result
    if result is None:
        return plain("")
    return HTTPResponse(body=str(result), status=200, content_type="text/html; charset=utf-8")
