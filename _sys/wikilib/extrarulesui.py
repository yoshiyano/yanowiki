"""PukiWiki記法の定義ルール（COLOR()/SIZE()/フェイスマーク等）を、設定画面
（`/.admin/configwiki` の「定義ルール」タブ）から編集する。

書き換えるのは `wikidata/<Wiki名>/config/pukiwiki.extrarules.yaml` ——**その
Wikiぶんだけ**。共通の定義（`config/pukiwiki.extrarules.example.yaml`）は触らない。

## 「このWikiで独自に持つ」の印は、ファイル全体につく

定義ルールは配列で、**個別Wikiにファイルがあれば共通のものは丸ごと読まれない**
（`wikilib.extrarules.load_extra_rules`）。`default.yaml` のように項目単位で
重ねられないので、印も1つだけにした。

- 印を付ける … 共通の定義をコピーして、このWiki専用のファイルを作る。
  最初は共通と同じ内容なので、見た目は変わらない
- 印を外す … このWikiの定義を捨てて、共通に戻る。**捨てるものが独自の
  編集結果なので、直前のファイルを必ず控える**（他の項目と違い、
  画面が書いたままのファイルでも控える。失うものがあるため）

印が無いあいだは、共通の定義を読み取り専用で見せる。

## 直したその場で保存する（他のタブと同じ）

**変更は1件ずつ窓口へ送り、画面にある配列をまとめて送り直すことはしない。**
まとめて送ると、別の人が先に直したものを古い画面の値で上書きしてしまう。
そのうえで、番号（何番目か）で指すので、**送るときに「直す前の中身」も一緒に
送らせ、いまのファイルと食い違えば断る**——先に誰かが並びを変えていた
ときに、別のルールを直してしまわないため。

## 保存させないもの

- 正規表現として読めないもの（理由を添えて断る）
- **空の文字列に当たるパターン**（`a*` など）。位置が進まず、解析が
  止まらなくなる恐れがある
- 置換文字列の `\\N` が、パターンのグループの数を超えているもの
  （黙って空になり、書いた人が気づけない）

## 試験欄

入力した文章に、いま効いている定義（と、追加前の「下書き」のルール）を
掛けて、**HTMLと描画結果、ルールごとの当たり箇所**を返す。当たり箇所の
探索は**別のプロセスで時間を切って行う**。重い正規表現（`(a+)+$` など）を
同じプロセスで走らせると、サーバー全体が固まるため。

権限は設定画面と同じ（管理者と助手）。**置換文字列はHTMLとしてそのまま
出力される**ので、書けるのは信頼できる人だけにする、という前提は
`wikilib.extrarules` と同じ（設定画面は `allow_html` も変えられる人だけが
入れる）。
"""
import json
import os
import re
import subprocess
import sys
from html import escape

from wikilib import htmlpolicy, pukiwiki
from wikilib.extrarules import ExtraRules, _compile_rules, facemark_enabled
from wikilib.interwiki import load_interwiki
from wikilib.paths import BASE_DIR, EXTRARULES_CONFIG_PATH, farm_extrarules_config_path
from wikilib.wikiconfig import (
    backup_config, config_backups, example_of, read_yaml, save_config_file,
)

# 定義の種類（ファイルのキー, 画面の見出し, 説明）。並びが画面の並び。
KINDS = [
    ("line_rules", "ユーザ定義ルール",
     "文章の中で、<code>COLOR(red){…}</code> のような書きかたを置き換えます。"
     "<strong>上にあるものが優先</strong>されます（同じ場所に当たるルールが"
     "複数あるとき）。"),
    ("facemark_rules", "フェイスマーク定義ルール",
     "<code>&amp;smile;</code> のような書きかたを絵文字などに置き換えます。"
     "<code>default.yaml</code> の <code>pukiwiki.facemark</code> を "
     "「いいえ」にすると、この一覧は一括で使われなくなります。"),
]
KIND_KEYS = [key for key, _t, _h in KINDS]

TEXT_LIMIT = 2000        # 試験欄の文章の長さの上限
PROBE_SECONDS = 3        # 当たり箇所の探索に許す時間
HITS_PER_RULE = 20       # ルール1つについて出す当たり箇所の数

DEFAULT_SAMPLE = "COLOR(red):''強調'' と BOLD{太字} を試す &smile;"

_GROUP_REF_RE = re.compile(r"\\(\d+)")


# ---- 読み書き ----------------------------------------------------------------

def own_path(wiki_dir):
    return farm_extrarules_config_path(wiki_dir)


def has_own(wiki_dir):
    return os.path.isfile(own_path(wiki_dir))


def _common_data():
    return read_yaml(example_of(EXTRARULES_CONFIG_PATH))


def _norm(entry):
    """配列の1件を (パターン, 置換文字列) にする。壊れた1件は空として見せる。"""
    if not isinstance(entry, dict):
        return "", ""
    pattern, replace = entry.get("pattern"), entry.get("replace")
    return ("" if pattern is None else str(pattern),
            "" if replace is None else str(replace))


def entries_of(data, kind):
    """`(パターン, 置換文字列)` の列。"""
    raw = (data or {}).get(kind)
    return [_norm(e) for e in raw] if isinstance(raw, list) else []


def effective_data(wiki_dir):
    """いま効いている定義（このWikiのファイルがあればそれ、無ければ共通）。"""
    return read_yaml(own_path(wiki_dir)) if has_own(wiki_dir) else _common_data()


def check_rule(pattern, replace):
    """定義1件を保存してよいか。よければ空文字列、だめなら断りの文言。"""
    if not pattern:
        return "パターン（正規表現）が空です。"
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"パターンが正規表現として正しくありません: {e}"
    if compiled.search(""):
        return ("空の文字列に当たるパターンは使えません（位置が進まず、解析が"
                "止まらなくなる恐れがあります）。")
    wanted = {int(n) for n in _GROUP_REF_RE.findall(replace)}
    if wanted and max(wanted) > compiled.groups:
        return (f"置換文字列に \\{max(wanted)} とありますが、"
                f"パターンの括弧（グループ）は {compiled.groups} 個です。")
    return ""


# ---- 編集の操作 --------------------------------------------------------------

def _save(wiki_dir, data):
    return save_config_file(own_path(wiki_dir), data)


def _load_own(wiki_dir):
    """このWikiの定義を読む。無ければ (None, 断りの文言)。"""
    if not has_own(wiki_dir):
        return None, "このWikiの独自の定義がありません。先に印を付けてください。"
    return read_yaml(own_path(wiki_dir)), ""


def _row(data, kind, body):
    """`body` が指す1件を返す。(配列, 番号, 断りの文言)。

    **番号と一緒に、直す前の中身も照合する**（モジュール冒頭参照）。"""
    if kind not in KIND_KEYS:
        return None, -1, "知らない種類です。"
    rows = data.setdefault(kind, [])
    if not isinstance(rows, list):
        rows = data[kind] = []
    try:
        index = int(body.get("index"))
    except (TypeError, ValueError):
        return None, -1, "どの行かが分かりません。"
    if not 0 <= index < len(rows):
        return None, -1, "その行はもうありません。画面を開き直してください。"
    now = _norm(rows[index])
    if now != (body.get("old_pattern") or "", body.get("old_replace") or ""):
        return None, -1, ("その行は、ほかの人（または別の画面）が先に書き換えました。"
                          "画面を開き直してください。")
    return rows, index, ""


def apply_op(wiki_dir, body):
    """定義の編集を1件受けて書き込む。`(成否, 文言)` を返す。

    op: `own`（印の付け外し）・`set`・`add`・`del`・`move`。"""
    op = body.get("op")
    if op == "own":
        return _set_own(wiki_dir, bool(body.get("on")))

    data, problem = _load_own(wiki_dir)
    if data is None:
        return False, problem
    kind = body.get("kind")
    if kind not in KIND_KEYS:
        return False, "知らない種類です。"

    if op in ("set", "add"):
        pattern = body.get("pattern") or ""
        replace = body.get("replace") or ""
        problem = check_rule(pattern, replace)
        if problem:
            return False, problem
        entry = {"pattern": pattern, "replace": replace}
        if op == "add":
            rows = data.setdefault(kind, [])
            if not isinstance(rows, list):
                rows = data[kind] = []
            rows.append(entry)
        else:
            rows, index, problem = _row(data, kind, body)
            if rows is None:
                return False, problem
            rows[index] = entry
    elif op == "del":
        rows, index, problem = _row(data, kind, body)
        if rows is None:
            return False, problem
        del rows[index]
    elif op == "move":
        rows, index, problem = _row(data, kind, body)
        if rows is None:
            return False, problem
        target = index + (-1 if body.get("direction") == "up" else 1)
        if not 0 <= target < len(rows):
            return False, "これ以上動かせません。"
        rows[index], rows[target] = rows[target], rows[index]
    else:
        return False, "知らない操作です。"

    ok, _saved, message = _save(wiki_dir, data)
    return ok, message


def _set_own(wiki_dir, on):
    path = own_path(wiki_dir)
    if on:
        if has_own(wiki_dir):
            return True, "すでにこのWikiの定義があります。"
        common = _common_data()
        data = {key: [{"pattern": p, "replace": r} for p, r in entries_of(common, key)]
                for key in KIND_KEYS}
        ok, _saved, message = _save(wiki_dir, data)
        return ok, ("共通の定義をコピーして、このWikiの定義を作りました。"
                    if ok else message)
    if not has_own(wiki_dir):
        return True, "このWikiの定義はありません（共通の定義が効いています）。"
    # 独自の編集結果を捨てるので、画面が書いたままのものでも必ず控える
    saved = backup_config(path)
    if saved is None:
        return False, "控えを取れなかったので、消しませんでした。"
    try:
        os.remove(path)
    except OSError as e:
        return False, f"消せませんでした（{e}）。"
    return True, (f"このWikiの定義を捨てて、共通の定義に戻しました。"
                  f"直前のものは «{os.path.basename(saved)}» に控えました。")


# ---- 試験 --------------------------------------------------------------------

# 当たり箇所の探索。**別のプロセスで走らせる**（モジュール冒頭参照）。
# 標準ライブラリだけで書き、入出力はASCIIのJSONに限る（文字コードの食い違いを避ける）。
_PROBE = r"""
import json, re, sys
data = json.load(sys.stdin)
out = []
for rule in data["rules"]:
    try:
        compiled = re.compile(rule["pattern"])
    except re.error as e:
        out.append({"error": str(e)})
        continue
    hits = []
    for m in compiled.finditer(data["text"]):
        if m.end() == m.start():
            continue
        hits.append({"start": m.start(), "end": m.end(), "text": m.group(0),
                     "groups": list(m.groups())})
        if len(hits) >= data["limit"]:
            break
    out.append({"hits": hits})
json.dump(out, sys.stdout)
"""


def probe_rules(rules, text, seconds=PROBE_SECONDS):
    """各ルールが、文章のどこに当たるかを調べる。

    戻り値は `(結果の列, 断りの文言)`。結果は `rules` と同じ並びで、
    `{"hits": [...]}` か `{"error": "..."}`。時間を超えたら
    `(None, 文言)`。"""
    payload = json.dumps({"rules": [{"pattern": p} for p, _r in rules],
                          "text": text, "limit": HITS_PER_RULE})
    try:
        done = subprocess.run([sys.executable, "-c", _PROBE],
                              input=payload.encode("ascii"), capture_output=True,
                              timeout=seconds)
    except subprocess.TimeoutExpired:
        return None, (f"{seconds}秒以内に終わりませんでした。正規表現が重すぎる"
                      "（同じ文字の繰り返しの入れ子など）可能性があります。")
    if done.returncode != 0:
        return None, "当たり箇所を調べられませんでした。"
    try:
        return json.loads(done.stdout.decode("ascii")), ""
    except ValueError:
        return None, "当たり箇所を調べられませんでした。"


def _draft_rule(body):
    """試験欄に添えられた、追加前の下書き。(種類, パターン, 置換) か None。"""
    draft = body.get("draft")
    if not isinstance(draft, dict) or not (draft.get("pattern") or ""):
        return None
    kind = draft.get("kind")
    return (kind if kind in KIND_KEYS else "line_rules",
            draft.get("pattern") or "", draft.get("replace") or "")


def run_test(wiki_dir, config, farm, explicit_farm, body):
    """試験欄の窓口。`{"ok", "message", "result"}` の辞書を返す。

    いま効いている定義に、あれば下書きを**末尾に足して**掛ける（下書きは
    まだ保存されていないので、優先順位は最も低い）。"""
    text = (body.get("text") or "")[:TEXT_LIMIT]
    data = effective_data(wiki_dir)
    facemark = facemark_enabled(config)
    rules = []   # (種類, 番号, パターン, 置換, 出典)
    for kind in KIND_KEYS:
        if kind == "facemark_rules" and not facemark:
            continue
        for i, (p, r) in enumerate(entries_of(data, kind)):
            rules.append((kind, i, p, r, ""))
    draft = _draft_rule(body)
    if draft is not None:
        problem = check_rule(draft[1], draft[2])
        if problem:
            return {"ok": False, "message": "下書きのルール: " + problem}
        rules.append((draft[0], len(entries_of(data, draft[0])), draft[1], draft[2],
                      "下書き"))

    hits, problem = probe_rules([(p, r) for _k, _i, p, r, _o in rules], text)
    if hits is None:
        return {"ok": False, "message": problem}

    compiled = _compile_rules([{"pattern": p, "replace": r}
                               for _k, _i, p, r, _o in rules])
    html = _render(wiki_dir, config, farm, explicit_farm, text, ExtraRules(compiled))
    return {"ok": True, "message": "", "result": _result_html(rules, hits, html)}


def _render(wiki_dir, config, farm, explicit_farm, text, extra_rules):
    """文章を、この定義で実際の表示と同じ経路でHTMLにする。"""
    # 循環を避けるため、ここで取り込む
    from wikilib.paths import farm_plugin_dir
    from wikilib.plugins import build_markdown_renderer
    from wikilib.themes import make_plugin_context
    context = make_plugin_context(config, farm, wiki_dir, "", explicit_farm)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    pconf = config.get("pukiwiki") or {}
    tokens = pukiwiki.parse(
        text, extra_rules=extra_rules, interwiki=load_interwiki(wiki_dir),
        wikiname=bool(pconf.get("wikiname", True)),
        allow_html=htmlpolicy.parses_html(htmlpolicy.html_policy(config, ".txt")))
    return engine.renderer.render(tokens, engine.options, {"wiki": context}).strip()


# ---- 画面 --------------------------------------------------------------------

def _hit_html(hit):
    groups = "".join(
        f'<span class="wcfg-rx-group">\\{n}={escape(g)}</span>'
        for n, g in enumerate(hit["groups"], 1) if g is not None)
    return (f'<li><code>{escape(hit["text"])}</code>'
            f'<span class="wcfg-rx-pos">（{hit["start"]}〜{hit["end"]}文字目）</span>'
            f'{groups}</li>')


def _result_html(rules, hits, html):
    """試験の結果。HTMLの文字列、描画、ルールごとの当たり。"""
    title = dict((k, t) for k, t, _h in KINDS)
    items = []
    total = 0
    for (kind, index, pattern, _replace, origin), found in zip(rules, hits):
        label = f'{title[kind]} {index + 1}' + (f'（{origin}）' if origin else '')
        if "error" in found:
            items.append(f'<li class="wcfg-rx-bad"><strong>{escape(label)}</strong>'
                         f' 正規表現エラー: {escape(found["error"])}</li>')
            continue
        if not found["hits"]:
            continue
        total += len(found["hits"])
        more = ("（先頭の%d件のみ）" % HITS_PER_RULE
                if len(found["hits"]) >= HITS_PER_RULE else "")
        items.append(
            f'<li><strong>{escape(label)}</strong> <code>{escape(pattern)}</code>{more}'
            f'<ul>{"".join(_hit_html(h) for h in found["hits"])}</ul></li>')
    hit_block = (f'<ul class="wcfg-rx-hits">{"".join(items)}</ul>' if items else
                 '<p class="wcfg-hint">どのルールにも当たりませんでした。</p>')
    return f"""<div class="wcfg-rx-out">
  <h4>表示（描画結果）</h4>
  <iframe class="wcfg-rx-frame" sandbox
          srcdoc="{escape(html or '<p>（空）</p>')}"></iframe>
  <h4>出力されたHTML</h4>
  <pre class="wcfg-rx-html">{escape(html)}</pre>
  <h4>ルールごとの当たり箇所（{total}件）</h4>
  <p class="wcfg-help">各ルールを<strong>別々に</strong>探したもので、実際の適用は
    上のルールが優先され、当たった部分は下のルールでは使われません。</p>
  {hit_block}
</div>"""


def _row_html(index, pattern, replace, editable):
    disabled = "" if editable else " disabled"
    attrs = (f'data-index="{index}" data-pattern="{escape(pattern)}" '
             f'data-replace="{escape(replace)}"')
    return f"""      <li class="wcfg-rx-row" {attrs}>
        <span class="wcfg-rx-no">{index + 1}</span>
        <input type="text" class="wcfg-rx-pattern" value="{escape(pattern)}"
               spellcheck="false" autocomplete="off" aria-label="パターン（正規表現）"{disabled}>
        <input type="text" class="wcfg-rx-replace" value="{escape(replace)}"
               spellcheck="false" autocomplete="off" aria-label="置換文字列"{disabled}>
        <span class="wcfg-rx-tools">
          <button type="button" data-act="up" title="上へ"{disabled}>↑</button>
          <button type="button" data-act="down" title="下へ"{disabled}>↓</button>
          <button type="button" data-act="del" title="削除"{disabled}>削除</button>
        </span>
        <span class="wcfg-said" role="status"></span>
      </li>"""


def _kind_html(kind, title, help_html, entries, editable):
    rows = "\n".join(_row_html(i, p, r, editable)
                     for i, (p, r) in enumerate(entries))
    disabled = "" if editable else " disabled"
    return f"""    <section class="wcfg-rx-kind" data-kind="{kind}">
      <h3>{escape(title)} <span class="wcfg-rx-count">{len(entries)}件</span></h3>
      <p class="wcfg-help">{help_html}</p>
      <div class="wcfg-rx-cols"><span></span><span>パターン（正規表現）</span>
        <span>置換文字列（<code>\\1</code> などが捕捉した部分）</span><span></span></div>
      <ol class="wcfg-rx-list">
{rows}
      </ol>
      <div class="wcfg-rx-add">
        <span class="wcfg-rx-no">＋</span>
        <input type="text" class="wcfg-rx-pattern" data-role="new-pattern"
               placeholder="新しいパターン" spellcheck="false" autocomplete="off"
               aria-label="追加するパターン"{disabled}>
        <input type="text" class="wcfg-rx-replace" data-role="new-replace"
               placeholder="置換文字列" spellcheck="false" autocomplete="off"
               aria-label="追加する置換文字列"{disabled}>
        <span class="wcfg-rx-tools">
          <button type="button" data-act="try" title="この下書きを、保存せずに試験欄で試す"{disabled}>試す</button>
          <button type="button" data-act="add"{disabled}>追加</button>
        </span>
        <span class="wcfg-said" role="status"></span>
      </div>
    </section>"""


def body_html(wiki_dir):
    """印と、種類ごとの一覧。**操作のたびに、この部分だけを作り直して返す。**"""
    own = has_own(wiki_dir)
    data = effective_data(wiki_dir)
    sections = "\n".join(_kind_html(k, t, h, entries_of(data, k), own)
                         for k, t, h in KINDS)
    if own:
        state = ('<p class="wcfg-hint">このWikiの定義（'
                 f'<code>{escape(os.path.relpath(own_path(wiki_dir), BASE_DIR))}</code>）'
                 'が効いています。直したその場で保存します。</p>')
    else:
        state = ('<p class="wcfg-hint">このWikiには独自の定義がありません。'
                 '<strong>共通の定義</strong>（<code>config/pukiwiki.extrarules.'
                 'example.yaml</code>）が効いています（下は読み取り専用）。'
                 '編集するには、印を付けてください。</p>')
    backups = config_backups(own_path(wiki_dir))
    backup_html = ""
    if backups:
        items = "".join(f"<li><code>{escape(os.path.basename(p))}</code></li>"
                        for p in backups)
        backup_html = (f'<details class="wcfg-backups"><summary>控え（新しい順、'
                       f'{len(backups)}件）</summary><ul>{items}</ul>'
                       '<p class="wcfg-help">置き場所は設定ファイルと同じフォルダです。'
                       '戻すときはファイルを置き換えてください。</p></details>')
    return f"""    <div class="wcfg-rx-own">
      <label class="wcfg-use"><input type="checkbox" data-role="own"
        {'checked' if own else ''}> このWikiで独自の定義を持つ</label>
      <span class="wcfg-said" data-role="own-said" role="status"></span>
    </div>
    {state}
{sections}
    {backup_html}"""


def panel_html(wiki_dir, opening_key, key):
    """「定義ルール」タブの中身。"""
    hidden = "" if key == opening_key else " hidden"
    return f"""  <div class="wcfg-panel" data-panel="{key}"{hidden}>
    <p class="wcfg-lead">PukiWiki記法の<strong>置き換えルール</strong>
      （<code>COLOR(red){{…}}</code>・<code>&amp;smile;</code> など）を編集します。
      <strong>上のものが優先</strong>されます。書き込みは直したその場です。</p>
    <div class="wcfg-rx" data-sample="{escape(DEFAULT_SAMPLE)}">
      <section class="wcfg-rx-test">
        <h3>試験</h3>
        <p class="wcfg-help">文章を入れると、いま効いている定義を掛けた結果が出ます。
          下の「試す」で、<strong>まだ保存していない下書き</strong>のルールも
          いっしょに試せます。</p>
        <textarea class="wcfg-rx-text" rows="3" maxlength="{TEXT_LIMIT}"
                  spellcheck="false" aria-label="試験する文章">{escape(DEFAULT_SAMPLE)}</textarea>
        <div class="wcfg-rx-testbar">
          <button type="button" data-act="test">試す</button>
          <span class="wcfg-said" data-role="test-said" role="status"></span>
        </div>
        <div class="wcfg-rx-result" aria-live="polite"></div>
      </section>
      <div class="wcfg-rx-body">
{body_html(wiki_dir)}
      </div>
    </div>
  </div>"""
