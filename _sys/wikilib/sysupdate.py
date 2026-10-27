"""公開版（GitHub の yanowiki）からの更新（`/.admin/update`）。

新しいバージョンが出ていれば、既定のWikiのタイトル右端の info で知らせる。押すと、
いまのバージョン・最新のバージョン・その間の更新履歴（ChangeLog）を見せる画面が開き、
「更新して再起動する」で公開版を取り込んで再起動する（Wiki設計者の指示、2026-10-27）。

## 決まっていること（設計者がクロコの案を承認、2026-10-27「A〜F すべてクロコ案で進めて」）

- **知らせる相手は、既定のWikiの管理者と、再起動を許された助手だけ**（`/.restart` と同じ範囲。
  権限は `site.restart`）。全員に出すと、古いバージョンのまま動いていることが外から分かる
- **最新版は、yanowiki の main にある `wiki.py` の `VERSION` と、更新履歴のページを、そのまま
  取ってきて読む**（`raw_base`）。先にブランチの最新のコミットを GitHub の API に聞き、そのコミットを
  指して読む（`latest_commit`。ブランチ名で読むと、ファイルごとに古い内容が返ることがあるため）。見に行くブランチは `server.yaml` の `update.branch` で変えられる
  （既定 main。更新の試験のため。Wiki設計者の指示、2026-10-27）。問い合わせはサーバーが裏で行い、ページを開くたびには行わない。
  つながらなければ何も知らせない
- **更新は clone し直さず、インストールの案内と同じ手順で行う**: `git fetch` → `git reset --hard`
  （取ってきたもの）→ `uv sync --inexact` → 再起動。clone し直すと、`config/server.yaml`・`_venv`・
  各Wikiのデータを移し替える必要があるため。途中で失敗したら、更新の前のコミットへ戻す
- **作業ツリーが公開版のまま（取ってきた先が yanowiki・ブランチが main・`_system` の外に手元の
  変更が無い）のときだけ更新できる**。開発の作業ツリー（dev）で行うと、作業中のものが消えるため。
  `_system` のWikiの手直しは更新で消えるので、画面で知らせる
- 画面は `/.admin/update`（管理の道具は `/.admin` の下へつなぐ。2026-09-08）
- 設定で自動的に更新する仕組みは作らない（再起動の失敗や `_system` の上書きを、誰も見ていない
  ときに起こさないため）

## クロコの実装例（設計者は未確認）

- 最新版を調べるのは、権限のある人が既定のWikiを開いたとき、前に調べてから `CHECK_INTERVAL`
  （1日。更新の試験のあいだは暫定で10分だった）たっていれば、裏のスレッドで行う。起動時に始める形にしないのは、gunicorn などの WSGI で
  動かしたときに起動時の処理が通らないため。画面の「今すぐ調べる」でも調べ直せる
- 今のバージョンは、手元の `wiki.py` から同じ読みかた（`parse_version`）で読む。値を1か所に保つため
"""
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from html import escape

from bottle import request

from wikilib.paths import UPDATE_URLPATH

SOURCE_URL = "https://github.com/yoshiyano/yanowiki"
SOURCE_REMOTE = "yoshiyano/yanowiki"      # origin の URL がこれを含めば公開版の作業ツリー
RAW_ROOT = "https://raw.githubusercontent.com/yoshiyano/yanowiki/"
# ブランチの最新のコミットを聞く先（GitHub の API。認証なしで1時間に60回まで）
COMMIT_API = "https://api.github.com/repos/yoshiyano/yanowiki/commits/"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_BRANCH = "main"
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
CHANGELOG_PATH = "wikidata/_system/wiki/ChangeLog/index.md"
# 確かめる間隔。1日（更新の試験のあいだは暫定で10分にしていた。1.2.0 で1日に戻した。Wiki設計者の判断、2026-10-27）
CHECK_INTERVAL = 24 * 60 * 60
FETCH_TIMEOUT = 10
SYSTEM_WIKI_PREFIX = "wikidata/_system/"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERSION_RE = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
# 更新履歴の見出し（「## 1.1.1（2026-10-06）」）
SECTION_RE = re.compile(r"^##\s+(\d+(?:\.\d+)*)\b.*$", re.MULTILINE)


# ---- 見に行くブランチ -------------------------------------------------------------

def source_branch(config=None):
    """見に行く公開版のブランチ。`server.yaml` の `update.branch`（既定 main）。

    更新の試験のために、試験ブランチ（`update-test` など）を見られるようにしてある（Wiki設計者の指示、
    2026-10-27）。値は git の引数とURLに入るので、ブランチ名に使える文字だけを受け、それ以外は既定に戻す。"""
    if config is None:
        from wikilib.wikiconfig import load_config
        config = load_config()
    branch = str(((config or {}).get("update") or {}).get("branch") or DEFAULT_BRANCH)
    if not BRANCH_RE.match(branch) or ".." in branch:
        return DEFAULT_BRANCH
    return branch


def raw_base(ref=None):
    """raw のURLの土台。`ref` はコミット（40桁）かブランチ名。"""
    return RAW_ROOT + (ref or source_branch()) + "/"


# ---- バージョン ---------------------------------------------------------------

def parse_version(text):
    """`wiki.py` の中身から `VERSION` を読む。見つからなければ None。"""
    m = VERSION_RE.search(text or "")
    return m.group(1) if m else None


def current_version(root=REPO_ROOT):
    """手元の `wiki.py` の `VERSION`。"""
    try:
        with open(os.path.join(root, "wiki.py"), encoding="utf-8") as f:
            return parse_version(f.read())
    except OSError:
        return None


def version_key(version):
    """比べるための並び（"1.1.1" → (1, 1, 1)）。数でない部分は 0 とみなす。"""
    return tuple(int(p) if p.isdigit() else 0 for p in str(version or "").split("."))


def is_newer(latest, current):
    if not latest or not current:
        return False
    a, b = version_key(latest), version_key(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def changelog_sections(markdown, current):
    """更新履歴のうち、`current` より新しいバージョンの節を、書いてある順に返す。
    `[{"version", "text"}]`。`text` は見出しの行から次の節の手前まで。"""
    found = list(SECTION_RE.finditer(markdown or ""))
    out = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(markdown)
        if is_newer(m.group(1), current):
            out.append({"version": m.group(1), "text": markdown[m.start():end].rstrip() + "\n"})
    return out


# ---- 最新版を調べる -------------------------------------------------------------

_lock = threading.Lock()
_latest = {"checked_at": None, "version": None, "changelog": "", "error": None, "branch": None,
           "commit": None, "checking": False}


def _fetch(path, opener=urllib.request.urlopen, ref=None):
    with opener(raw_base(ref) + path, timeout=FETCH_TIMEOUT) as r:
        return r.read().decode("utf-8")


def latest_commit(branch, opener=urllib.request.urlopen):
    """ブランチの最新のコミット（40桁）を GitHub の API に聞く。

    **ブランチ名で raw を読むと、ファイルごとに数分間古い内容が返ることがある**（2026-10-27 の更新の試験で、
    `wiki.py` は新しく更新履歴は古い、という食い違いが起きた）。コミットを指した raw は中身が変わらないので、
    先にコミットを1つ聞き、それを指して読む（Wiki設計者の指示、2026-10-27）。取り込みもこのコミットを指すので、
    画面で見せた版と取り込む版が一致する。"""
    req = urllib.request.Request(COMMIT_API + branch, headers={
        "Accept": "application/vnd.github.sha", "User-Agent": "wikiSystem-update"})
    with opener(req, timeout=FETCH_TIMEOUT) as r:
        sha = r.read().decode("ascii", "replace").strip()
    if not COMMIT_RE.match(sha):
        raise ValueError("コミットを読めませんでした")
    return sha


def check_now(opener=urllib.request.urlopen, branch=None):
    """GitHub に問い合わせて、最新版の情報を覚え直す。覚えた内容の写しを返す。"""
    branch = branch or source_branch()
    result = {"checked_at": time.time(), "version": None, "changelog": "", "error": None,
              "branch": branch, "commit": None}
    try:
        result["commit"] = latest_commit(branch, opener)
        result["version"] = parse_version(_fetch("wiki.py", opener, result["commit"]))
        if result["version"] is None:
            result["error"] = "公開版の wiki.py からバージョンを読めませんでした。"
    except Exception as e:   # つながらない・見つからない。知らせないだけにする
        result["error"] = "公開版を調べられませんでした（{}）。".format(e)
    if result["version"] is not None:
        # 更新履歴が無くても（1.1.1 までの公開版には無い）、バージョンは知らせる
        try:
            result["changelog"] = _fetch(CHANGELOG_PATH, opener, result["commit"])
        except Exception:
            result["changelog"] = ""
    with _lock:
        _latest.update(result)
        _latest["checking"] = False
        return dict(_latest)


def latest():
    """覚えている最新版の情報の写し（まだ調べていなければ `checked_at` が None）。"""
    with _lock:
        return dict(_latest)


def check_in_background():
    """前に調べてから `CHECK_INTERVAL` たっていれば、裏のスレッドで調べ直す（待たない）。"""
    with _lock:
        stale = _latest["checked_at"] is None or time.time() - _latest["checked_at"] >= CHECK_INTERVAL
        if not stale or _latest["checking"]:
            return
        _latest["checking"] = True
    threading.Thread(target=check_now, daemon=True).start()


def available(current=None):
    """新しいバージョンが出ていれば、その番号。無い・まだ分からなければ None。"""
    info = latest()
    current = current or current_version()
    return info["version"] if is_newer(info["version"], current) else None


# ---- 作業ツリー -------------------------------------------------------------------

def _git(root, *args, timeout=60):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def find_uv():
    """`uv` の場所。サーバーの PATH に無いことがあるので、インストールの案内が入れる場所も見る。"""
    found = shutil.which("uv")
    if found:
        return found
    for path in ("~/.local/bin/uv", "~/.cargo/bin/uv", "~/.local/bin/uv.exe", "~/.cargo/bin/uv.exe"):
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return path
    return None


def checkout_state(root=REPO_ROOT):
    """更新できる作業ツリーか。`{"problems": [理由], "system_changes": [_system の変更のパス]}`。
    `problems` が空なら更新できる。"""
    problems, system_changes = [], []
    if not shutil.which("git"):
        return {"problems": ["git が見つかりません。"], "system_changes": []}
    if not os.path.isdir(os.path.join(root, ".git")):
        return {"problems": ["git で取ってきた作業ツリーではありません（インストールの案内の"
                             " git clone で入れたものだけ更新できます）。"], "system_changes": []}
    if find_uv() is None:
        problems.append("uv が見つかりません（部品を入れ直せません）。")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        problems.append("ブランチが main ではありません（いまは {}）。".format(branch or "不明"))
    url = _git(root, "remote", "get-url", "origin").stdout.strip()
    if SOURCE_REMOTE not in url:
        problems.append("取ってきた先（origin）が公開版（{}）ではありません。".format(SOURCE_URL))
    status = _git(root, "status", "--porcelain", "--untracked-files=no")
    if status.returncode != 0:
        problems.append("作業ツリーの状態を読めませんでした。")
    others = []
    for line in status.stdout.splitlines():
        path = line[3:].strip().strip('"')
        (system_changes if path.startswith(SYSTEM_WIKI_PREFIX) else others).append(path)
    if others:
        problems.append("手元で書き換えたファイルがあります（{}）。更新すると消えるため、"
                        "更新できません。".format("、".join(others[:5]) + ("ほか" if len(others) > 5 else "")))
    return {"problems": problems, "system_changes": system_changes}


def run_update(commit, root=REPO_ROOT, run=subprocess.run):
    """公開版のコミット `commit`（画面で見せたもの）を取り込む（fetch → reset → uv sync）。
    途中で失敗したら、前のコミットへ戻す。`{"ok", "message", "from", "to"}` を返す。再起動は呼ぶ側が行う。

    手元のブランチは main のままで、その中身を取ってきたコミットに合わせる（試験ブランチは main と
    履歴がつながっていなくてよい）。"""
    def step(args, timeout, env=None):
        return run(args, cwd=root, capture_output=True, text=True, timeout=timeout, env=env)

    def tail(proc):
        return ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:]

    if not COMMIT_RE.match(commit or ""):
        return {"ok": False, "message": "取り込むコミットが分かりません（何も変えていません）。", "from": "", "to": ""}
    before = step(["git", "rev-parse", "HEAD"], 30).stdout.strip()
    fetch = step(["git", "fetch", "--depth", "1", "origin", commit], 300)
    if fetch.returncode != 0:
        return {"ok": False, "message": "公開版を取ってこられませんでした（何も変えていません）。\n" + tail(fetch),
                "from": before, "to": before}
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT="_venv")
    uv = find_uv() or "uv"
    reset = step(["git", "reset", "--hard", "FETCH_HEAD"], 120)
    sync = step([uv, "sync", "--inexact"], 900, env) if reset.returncode == 0 else None
    if reset.returncode == 0 and sync.returncode == 0:
        after = step(["git", "rev-parse", "HEAD"], 30).stdout.strip()
        return {"ok": True, "message": "", "from": before, "to": after}
    failed = reset if reset.returncode != 0 else sync
    step(["git", "reset", "--hard", before], 120)
    step([uv, "sync", "--inexact"], 900, env)
    return {"ok": False, "message": "更新の途中で失敗したので、更新の前に戻しました。\n" + tail(failed),
            "from": before, "to": before}


# ---- 画面（/.admin/update） --------------------------------------------------------

def _staff_record(wiki_dir, farm, summary):
    from wikilib import stafflog

    staff = stafflog.actor(wiki_dir, farm)
    if staff is not None:
        stafflog.record(wiki_dir, staff, "update", "", summary)


def _changelog_html(config, farm, wiki_dir, explicit_farm, sections):
    from wikilib.paths import farm_plugin_dir
    from wikilib.plugins import build_markdown_renderer
    from wikilib.render import render_source
    from wikilib.themes import make_plugin_context

    if not sections:
        return ""
    context = make_plugin_context(config, farm, wiki_dir, UPDATE_URLPATH, explicit_farm)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    html, _, _ = render_source(engine, "".join(s["text"] for s in sections), ".md", False, context)
    return '<section class="update-changelog content">{}</section>'.format(html)


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def render_update(wiki_dir, config, farm, explicit_farm):
    """`/.admin/update`。GET で今と最新のバージョン・更新履歴、POST の `cmd=check` で調べ直し、
    `cmd=update` で更新して再起動する。関門は `/.restart` と同じ（既定のWikiの管理者と、
    `site.restart` を許された助手。Wiki名を含むURLは断る）。"""
    from wikilib import sysui
    from wikilib.restart import describe, detect_mode, request_restart
    from wikilib.themes import make_plugin_context

    denied = sysui.require_on_default_farm(config, farm, wiki_dir, explicit_farm,
                                           UPDATE_URLPATH, "site.restart")
    if denied is not None:
        return denied
    context = make_plugin_context(config, farm, wiki_dir, UPDATE_URLPATH, explicit_farm)
    action = context.base_url + "/" + UPDATE_URLPATH
    current = current_version()
    cmd = request.forms.getunicode("cmd") if request.method == "POST" else None

    if cmd == "update":
        state = checkout_state()
        if state["problems"]:
            body = '<div class="update"><p class="update-error">更新できません。</p><ul>{}</ul></div>'.format(
                "".join("<li>{}</li>".format(escape(p)) for p in state["problems"]))
            return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", body,
                              status=409)
        # 取り込むのは画面で見せたコミット。押すまでの間にもっと新しい版が出ていたら（または
        # 調べられなければ）、見せていない版を取り込まないよう断る
        shown = request.forms.getunicode("commit") or ""
        if not COMMIT_RE.match(shown) or check_now()["commit"] != shown:
            body = ('<div class="update"><p class="update-error">画面を開いてから、公開版が変わりました'
                    '（または調べられませんでした）。更新の画面を開き直して、変わることを確かめてから'
                    '押してください。</p><p><a href="{}">更新の画面へ戻る</a></p></div>').format(escape(action))
            return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", body,
                              status=409)
        result = run_update(shown)
        if not result["ok"]:
            body = ('<div class="update"><p class="update-error">更新できませんでした。</p>'
                    '<pre class="update-log">{}</pre><p><a href="{}">更新の画面へ戻る</a></p></div>').format(
                escape(result["message"]), escape(action))
            return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", body,
                              status=500)
        new_version = current_version() or ""
        _staff_record(wiki_dir, farm, "{} から {} へ更新した".format(current or "?", new_version or "?"))
        mode, _ = request_restart(request.environ)
        body = (
            '<div class="update">'
            '<p class="update-message">{} から {} へ更新しました。再起動を受け付けました。</p>'
            '<p class="update-note">{}</p>'
            '<p class="update-hint">数秒ほどで戻ります。つながらない場合は、少し待ってから'
            '<a href="{}/">トップページ</a>を開き直してください。</p>'
            "</div>").format(escape(current or "?"), escape(new_version or "?"),
                             escape(describe(mode, request.environ)), escape(context.base_url))
        return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", body)

    info = check_now() if cmd == "check" else latest()
    if info["checked_at"] is None:
        info = check_now()
    newer = is_newer(info["version"], current)
    rows = [
        ("いまのバージョン", escape(current or "不明")),
        ("最新のバージョン", escape(info["version"] or "不明")
         + ('（{} に調べました）'.format(escape(_when(info["checked_at"]))) if info["checked_at"] else "")),
        ("公開版", '<a href="{0}" rel="noopener">{0}</a>（ブランチ {1}{2}）'.format(
            escape(SOURCE_URL), escape(info.get("branch") or source_branch()),
            "・コミット " + escape(info["commit"][:7]) if info.get("commit") else "")),
    ]
    parts = ['<div class="update"><table class="update-versions">',
             "".join("<tr><th>{}</th><td>{}</td></tr>".format(k, v) for k, v in rows), "</table>"]
    if info["error"]:
        parts.append('<p class="update-error">{}</p>'.format(escape(info["error"])))
    parts.append('<form method="post" action="{}"><button type="submit" name="cmd" value="check">'
                 "今すぐ調べる</button></form>".format(escape(action)))
    if not newer:
        if info["version"]:
            parts.append('<p class="update-message">いまのバージョンが最新です。</p>')
        parts.append("</div>")
        return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", "".join(parts))

    parts.append("<h2>更新で変わること</h2>")
    parts.append(_changelog_html(config, farm, wiki_dir, explicit_farm,
                                 changelog_sections(info["changelog"], current))
                 or "<p>更新履歴に、このバージョンの記録がありません。</p>")
    state = checkout_state()
    parts.append("<h2>更新する</h2>")
    parts.append("<p>公開版を取り込み（git fetch → git reset --hard → uv sync --inexact）、サービスを"
                 "再起動します。{}途中で失敗したときは、更新の前に戻します。</p>".format(
                     escape(describe(detect_mode(request.environ), request.environ))))
    if state["system_changes"]:
        parts.append('<p class="update-warn">このサーバーで書き換えた _system のWikiのページは、更新で'
                     "公開版の内容に戻ります: {}</p>".format(escape("、".join(state["system_changes"]))))
    if state["problems"]:
        parts.append('<p class="update-error">この作業ツリーは更新できません。</p><ul>{}</ul>'.format(
            "".join("<li>{}</li>".format(escape(p)) for p in state["problems"])))
    parts.append('<form method="post" action="{}"><input type="hidden" name="commit" value="{}">'
                 '<button type="submit" name="cmd" value="update"{}>'
                 "更新して再起動する</button></form></div>".format(
                     escape(action), escape(info.get("commit") or ""),
                     " disabled" if state["problems"] else ""))
    return sysui.page(wiki_dir, config, farm, explicit_farm, UPDATE_URLPATH, "更新", "".join(parts))

