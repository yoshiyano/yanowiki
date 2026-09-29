"""既にあるWikiを消す（/.delwiki）。

**消す前に必ず `wikidata/<Wiki名>.<yymmdd_hhmmss>.7z` へ固めてから、実体を
消す**（Wiki設計者の指示、2026-09-18）。戻したくなったら `wikidata/` で
その書庫を展開すればよい——中身は `<Wiki名>/…` の形で入っているので、
展開しただけで元の場所に戻る。

    cd wikidata && 7z x sandbox.260918_143012.7z

`/.newwiki` の裏返しにあたる操作だが、**作るのと消すのでは取り返しの付きかたが
違う**ので、確かめる段を4つに分けてある。

    1. 消すWikiの名前          どれを消すのかを、一覧から選ばせず手で書かせる
    2. そのWikiの管理者のパスワード   そのWikiを預かっている人であることの証し
    3. ディスク使用量と最終更新日     **いまそのWikiを実際に見ていること**の証し
    4. 最後の確認                     ここで初めて消える

**書庫づくりは2の直後から始める**（Wiki設計者の指示）。3と4を書いている間に
裏で進むので、待たされる時間が短くなる。**最後にやめたときは書庫も消す**ので、
途中で引き返しても何も残らない。

## 3段目は「見ていること」を確かめるためにある

名前だけなら、消す気の無いWikiの名前を写し間違えただけでも通ってしまう。
ディスク使用量とトップページの最終更新日は、**そのWikiのトップページを実際に
開かないと分からない値**（どちらもテーマのフッタに出ている）で、しかも
Wikiごとに違う。ここを通れたということは、少なくとも消す対象を一度は
自分の目で見ている。

  DiskUsage: Page/Attached 1.2MB/349KB   → 「1.2MB/349KB」を書いてもらう
  Last-modified: 2026-09-18 14:33        → 「2026-09-18」を書いてもらう

打ち方の揺れ（前置きごと貼り付けた・区切りが `/` ・時刻まで書いた）は
こちらで吸収する（`wikilib.wikimark`）。**確かめたいのは値を知っているかどうかで、
書式を揃える練習ではない。** この2つは `./wiki.py resetpw` が取り違え防止に
使っているものと同じで、値の作りかたも突き合わせも `wikimark` にまとめてある。

## 段と段の間は署名付きの合札でつなぐ

一段ごとに画面が変わるので、次の画面へ「前の段を通った」ことを持ち越す必要が
ある。**プロセスの中に覚えておくやりかたは採らない**——gunicorn のように
ワーカーが複数ある構えだと、次のPOSTが別のワーカーに着いた時点で忘れられて
しまう。代わりに、この設置に固有の文字列（`auth.site_secret`）で署名した
合札をフォームに埋めて持ち回る（`token_of`）。**署名にはログイン中のuidも
混ぜる**ので、他人の画面から札だけ取り出しても使えない。

合札は段ごとに別（`PURPOSE_ARCHIVE` / `PURPOSE_CHECKED`）にしてある。
1つで通していると、3段目を飛ばして最後のPOSTだけを組み立てられる。

## 書庫が今どうなっているかは、ファイルの名前で分かる

書庫づくりの進み具合も同じ理由でプロセスの中に持てない。そこで**作りかけは
`.7z.part`、出来上がりは `.7z`、しくじったら `.7z.error`** と名前を変える
（`archive_state`）。どのワーカーが受けても、置き場所を見れば状態が分かる。

## 消せないもの

**既定のWiki（`farm.default`）は消せない。** 名前を付けずに開いたときに出る
Wikiなので、消すとサービスの入口そのものが無くなる。別のWikiを既定に
してから出直してもらう。

関門は `/.newwiki`・`/.allwiki` と同じ `sysui.require_on_default_farm`
（既定Wikiの管理者と助手だけ。`/=<Wiki名>/.delwiki` は既定Wikiのものでも403）。
Wikiを増やせる人と減らせる人を別の組にする理由が無いので揃えてある。
"""
import hashlib
import hmac
import os
import shutil
import subprocess
import threading
import time
from html import escape
from urllib.parse import quote as urlquote

from bottle import request

from wikilib import allwiki, auth, diskusage, pagedb, paths, stafflog, sysui, userdb, wikimark
from wikilib.paths import (
    DELWIKI_DIR, DELWIKI_URLPATH, FARM_PREFIX, farm_wiki_dir, safe_join,
)
from wikilib.userdb import ADMIN_UIDNUM
from wikilib.web import serve_asset
from wikilib.wikiconfig import load_default_farm

# 書庫の名前に入れる日時（Wiki設計者の指示、2026-09-18の `<wiki名>.YYMMDD_HHMMSS.7z`）。
# ページのバックアップ（`pageinfo/backup/`）が使っているのと同じ形に揃えてある
STAMP_FORMAT = "%y%m%d_%H%M%S"

DONE_SUFFIX = ".7z"          # 出来上がり
PART_SUFFIX = ".7z.part"     # 作りかけ
ERROR_SUFFIX = ".7z.error"   # しくじった理由

# 書庫づくりのスレッドの名前（テストが終わりを待つときの目印）
ARCHIVE_THREAD_NAME = "delwiki-archive"

# 7zを作る道具。名前が環境によって違うので、見つかった順に使う
SEVENZIP_PROGRAMS = ("7z", "7za", "7zz")

# フォームの段。**どの段から送られてきたか**を hidden で持ち回る
STEP_NAME = "name"          # 1段目: 消すWikiの名前
STEP_PASSWORD = "password"  # 2段目: 管理者のパスワード
STEP_CHECK = "check"        # 3段目: ディスク使用量と最終更新日
STEP_FINAL = "final"        # 4段目: 最後の確認

# 合札の用途。段ごとに分ける（冒頭の説明を参照）
PURPOSE_ARCHIVE = "archive"  # 2段目を通った（書庫づくりが始まっている）
PURPOSE_CHECKED = "checked"  # 3段目を通った

TOKEN_LENGTH = 32  # 合札の長さ（16進）。総当たりには十分で、URLにもフォームにも収まる


# ---- 置き場所 ---------------------------------------------------------------

def wikidata_dir():
    """`wikidata/` の場所。**毎回 `paths` から読む。**

    テストが `paths.WIKIDATA_DIR` を仮置き場へ差し替えるので、読み込み時に
    自分の名前へ束ねてしまうと届かない（`wikilib.allwiki` が同じ理由で
    テスト側から差し替えられている）。"""
    return paths.WIKIDATA_DIR


def archive_base(name, stamp, root=None):
    """書庫の置き場所（拡張子を除いたところまで）。`root` を省くと `wikidata_dir()`。"""
    return os.path.join(root or wikidata_dir(), "{}.{}".format(name, stamp))


def done_path(name, stamp, root=None):
    return archive_base(name, stamp, root) + DONE_SUFFIX


def part_path(name, stamp, root=None):
    return archive_base(name, stamp, root) + PART_SUFFIX


def error_path(name, stamp, root=None):
    return archive_base(name, stamp, root) + ERROR_SUFFIX


def new_stamp(when=None):
    return time.strftime(STAMP_FORMAT, time.localtime(when))


# ---- 合札 -------------------------------------------------------------------

def token_of(purpose, name, stamp, uid):
    """段を通ったことの証し。`auth.site_secret()` で署名する。

    混ぜるのは**用途・Wiki名・日時・ログイン中のuid**。uidを混ぜてあるので、
    他人の画面から札だけ写しても、その人のログイン状態では通らない。"""
    message = "\n".join((purpose, name, stamp, uid or ""))
    signed = hmac.new(auth.site_secret().encode("utf-8"),
                      message.encode("utf-8"), hashlib.sha256)
    return signed.hexdigest()[:TOKEN_LENGTH]


def token_ok(purpose, name, stamp, uid, token):
    """合札が正しいか。**突き合わせは `compare_digest` で**（どこまで合って
    いたかが応答時間から漏れないように）。

    **比べるのはバイト列にしてから。** `compare_digest` は非ASCIIを含む文字列
    どうしを比べられず `TypeError` を投げるので、フォームに日本語を入れられた
    だけで500になってしまう（合札はフォームから来る＝中身は選べない）。"""
    if not token:
        return False
    expected = token_of(purpose, name, stamp, uid).encode("ascii")
    return hmac.compare_digest(expected, token.encode("utf-8", "replace"))


# ---- 消してよい相手か -------------------------------------------------------

def target_problem(name, config):
    """消せない理由。問題なければ None。

    **名前は実在する一覧（`allwiki.wiki_names()`）との一致で見る。** 形を
    正規表現で確かめるやりかたに比べ、`../` のような細工が入り込む余地が
    最初から無い。"""
    if not name:
        return "消すWikiの名前を入れてください。"
    if name not in allwiki.wiki_names():
        # 名前を隠す意味は無い（この画面に入れる人は一覧も見られる）
        return "「{}」というWikiはありません。".format(name)
    if name == load_default_farm(config):
        return ("「{}」は既定のWikiなので消せません。"
                "名前を付けずに開いたときに出るWikiです——"
                "消す前に、別のWikiを既定にしてください。".format(name))
    if safe_join(wikidata_dir(), name) is None:
        return "その名前のWikiは消せません。"
    return None


def admin_row(wiki_dir):
    """そのWikiの管理者（`uidnum = 1`）。記録が無ければ None。

    **`uid` が `admin` かどうかでは探さない。** 一覧の画面から名前は
    書き換えられるので、管理者の座が紐づいているのは番号のほう
    （`userdb.is_admin` の説明を参照）。"""
    if not userdb.exists(wiki_dir):
        return None
    return userdb.get_user(wiki_dir, ADMIN_UIDNUM)


# ---- 3段目に通す値 ----------------------------------------------------------
#
# 値の作りかたと突き合わせは `wikilib.wikimark` が持つ。**`./wiki.py resetpw` の
# 取り違え防止と同じ仕組み**（Wiki設計者の指示、2026-09-08で入ったもの）で、
# あちらは端末にフッターを丸ごと貼る形、こちらは入力欄を2つ並べる形と、
# 訊きかただけが違う。


def usage_text(wiki_dir):
    """そのWikiのディスク使用量（`1.2MB/349KB`）。画面にも出すので名前を残す。"""
    return wikimark.usage_text(wiki_dir)


def check_passes(wiki_dir, typed_usage, typed_day):
    """3段目の答え合わせ。**どちらが違ったかは言わない**（`wikimark.typed_matches`）。"""
    return wikimark.typed_matches(wiki_dir, typed_usage, typed_day)


# ---- 書庫づくり -------------------------------------------------------------

def sevenzip_program():
    """7zを作る道具の場所。見つからなければ None。"""
    for program in SEVENZIP_PROGRAMS:
        found = shutil.which(program)
        if found:
            return found
    return None


def start_archive(name, stamp):
    """書庫づくりを始める。(始められたか, 知らせる文言) を返す。

    **待たずに戻る。** 呼んだ側（2段目のPOST）はすぐ3段目の画面を返し、
    圧縮はその裏で進む（Wiki設計者の指示、2026-09-18。「アーカイブ作業は
    admin パスワードが得られた時点から開始する」）。"""
    program = sevenzip_program()
    if program is None:
        return False, ("7z を作る道具が見つかりません（{}）。"
                       "消す前に固める先が用意できないので、ここで止めます。"
                       .format(" / ".join(SEVENZIP_PROGRAMS)))
    if os.path.exists(done_path(name, stamp)) or os.path.exists(part_path(name, stamp)):
        return False, "同じ名前の書庫がすでにあります。少し待ってからやり直してください。"
    _clear(error_path(name, stamp))
    # 置き場所はここで1度だけ決めて渡す。裏のスレッドが途中で `wikidata_dir()` を
    # 読み直すと、テストが差し替えを戻した後に本物の `wikidata/` へ書いてしまう
    thread = threading.Thread(target=run_archive,
                              args=(program, name, stamp, wikidata_dir()),
                              name=ARCHIVE_THREAD_NAME, daemon=True)
    thread.start()
    return True, ""


def run_archive(program, name, stamp, root):
    """7zへ固める本体（別スレッドで動く）。

    `wikidata/` を作業場所にして `<Wiki名>` ごと渡すので、中身は
    `<Wiki名>/…` の形で入る——**`wikidata/` で展開しただけで元に戻る。**

    出来上がるまでは `.7z.part` の名前で作り、終わってから `.7z` へ
    付け替える（`os.replace`）。**途中で落ちた書庫が、出来上がりの顔で
    残らないようにするため。**"""
    part = part_path(name, stamp, root)
    try:
        # `--` で以降を名前として扱わせる（`-` で始まるフォルダ名でも壊れない）。
        # `-t7z` は必ず要る——拡張子が `.part` なので、付けないと形式を
        # 拡張子から決めようとして別物になる
        done = subprocess.run(
            [program, "a", "-t7z", "-bd", "-y", "--", part, "./" + name],
            cwd=root, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        _fail(name, stamp, root, str(e))
        return
    if done.returncode != 0:
        output = (done.stdout or b"").decode("utf-8", "replace").strip()
        _fail(name, stamp, root, "7z が {} で終わりました。\n{}".format(
            done.returncode, output[-2000:]))
        return
    try:
        os.replace(part, done_path(name, stamp, root))
    except OSError as e:
        _fail(name, stamp, root, str(e))


def _fail(name, stamp, root, reason):
    """しくじった理由を書き残し、作りかけを片づける。"""
    _clear(part_path(name, stamp, root))
    try:
        with open(error_path(name, stamp, root), "w", encoding="utf-8") as f:
            f.write(reason + "\n")
    except OSError:
        pass


def _clear(path):
    try:
        os.remove(path)
    except OSError:
        pass


def archive_state(name, stamp):
    """書庫の今（`"done"` / `"working"` / `"error"` / `"missing"`, 添える文言）。

    **見るのはファイルの名前だけ。** プロセスをまたいでも同じ答えになる
    （冒頭の説明を参照）。"""
    done = done_path(name, stamp)
    if os.path.isfile(done):
        return "done", diskusage.format_size(_size_of(done))
    error = error_path(name, stamp)
    if os.path.isfile(error):
        try:
            with open(error, encoding="utf-8") as f:
                return "error", f.read().strip()
        except OSError:
            return "error", ""
    part = part_path(name, stamp)
    if os.path.isfile(part):
        return "working", diskusage.format_size(_size_of(part))
    return "missing", ""


def _size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def wait_for_archive(name, stamp, timeout=30.0, interval=0.2):
    """書庫が出来上がる（かしくじる）まで待つ。最後に見た状態を返す。

    **画面からは使わない**（応答を止めてまで待つ場面が無い——4段目は
    出来ていなければ「まだです」と出して押し直してもらう）。テストと、
    道具から続けて呼びたいときのためのもの。"""
    limit = time.time() + timeout
    while True:
        state, detail = archive_state(name, stamp)
        if state in ("done", "error"):
            return state, detail
        if time.time() >= limit:
            return state, detail
        time.sleep(interval)


def discard_archive(name, stamp):
    """書庫を片づける（やめたとき。Wiki設計者の指示、2026-09-18）。

    **作りかけ・出来上がり・しくじりの記録を全部消す。** 引き返した跡が
    `wikidata/` に残らないようにするためで、消せなかったものは黙って諦める
    （残っていても害は無い）。"""
    for path in (done_path(name, stamp), part_path(name, stamp),
                 error_path(name, stamp)):
        _clear(path)


# ---- 消す -------------------------------------------------------------------

def remove_wiki(name):
    """Wikiの実体を消す。(成否, 知らせる文言) を返す。

    **呼ぶ側が、書庫が出来ていることを確かめてから呼ぶこと**（ここは
    確かめない）。"""
    root = safe_join(wikidata_dir(), name)
    if root is None or not os.path.isdir(root):
        return False, "「{}」は見つかりませんでした。".format(name)
    try:
        shutil.rmtree(root)
    except OSError as e:
        return False, "消せませんでした（{}）。".format(e)
    # 使用量の数え直しを促す（この場では数えない。`diskusage.invalidate`）
    diskusage.invalidate(os.path.join(root, "wiki"))
    return True, "Wiki「{}」を消しました。".format(name)


# ---- 画面 -------------------------------------------------------------------

def render_delwiki(wiki_dir, config, farm, explicit_farm):
    """`/.delwiki` の画面。GETで1段目、POSTで次の段へ進む。

    **既定Wikiの管理者と助手だけが開ける**（`/.newwiki` と同じ関門）。
    確かめるのは**中身を組み立てる前、POSTを処理する前**。"""
    denied = sysui.require_on_default_farm(config, farm, wiki_dir, explicit_farm,
                                           DELWIKI_URLPATH)
    if denied is not None:
        return denied

    page = _page_of(wiki_dir, config, farm, explicit_farm)
    if request.method != "POST":
        return page("Wikiを消す", _step_name_html(wiki_dir, config, farm, explicit_farm))

    uid = auth.current_uid(wiki_dir, farm)
    step = _form("step")
    name = _form("name")
    stamp = _form("stamp")
    token = _form("token")

    # 「やめる」はどの段からでも来る。**書庫を片づけてから1段目へ戻す**
    if _form("cancel"):
        return _cancel(page, wiki_dir, config, farm, explicit_farm, name, stamp,
                       uid, token)

    if step == STEP_NAME:
        return _to_password(page, wiki_dir, config, farm, explicit_farm, name)
    if step == STEP_PASSWORD:
        return _to_check(page, wiki_dir, config, farm, explicit_farm, name, uid)
    if step == STEP_CHECK:
        return _to_final(page, wiki_dir, config, farm, explicit_farm, name, stamp,
                         uid, token)
    if step == STEP_FINAL:
        return _do_delete(page, wiki_dir, config, farm, explicit_farm, name, stamp,
                          uid, token)
    return page("Wikiを消す", _step_name_html(wiki_dir, config, farm, explicit_farm))


def _form(key):
    return (request.forms.getunicode(key, "") or "").strip()


def _page_of(wiki_dir, config, farm, explicit_farm):
    """この画面の外枠を作る関数を返す（`sysui.page` の引数を畳んでおくだけ）。"""
    def page(title, body, status=200):
        return sysui.page(wiki_dir, config, farm, explicit_farm, DELWIKI_URLPATH,
                          title, body, css_url=f"{DELWIKI_URLPATH}.css",
                          status=status)
    return page


def _base_url(wiki_dir, config, farm, explicit_farm):
    from wikilib.themes import make_plugin_context
    context = make_plugin_context(config, farm, wiki_dir, DELWIKI_URLPATH,
                                  explicit_farm)
    return context.base_url


def _cancel(page, wiki_dir, config, farm, explicit_farm, name, stamp, uid, token):
    """やめる。**合札が通れば書庫も消す。**

    合札が通らないときは何も消さない——他人のPOSTで書庫だけ消されるのを
    防ぐため。画面は同じように1段目へ戻す（何が起きたかは伝えない）。"""
    if name and stamp and (token_ok(PURPOSE_ARCHIVE, name, stamp, uid, token)
                           or token_ok(PURPOSE_CHECKED, name, stamp, uid, token)):
        discard_archive(name, stamp)
        note = "やめました。作りかけの書庫も片づけました。"
    else:
        note = "やめました。"
    return page("Wikiを消す",
                _step_name_html(wiki_dir, config, farm, explicit_farm, note=note))


# 1段目 -> 2段目

def _to_password(page, wiki_dir, config, farm, explicit_farm, name):
    problem = target_problem(name, config)
    if problem:
        return page("Wikiを消す",
                    _step_name_html(wiki_dir, config, farm, explicit_farm,
                                    name=name, problem=problem))
    target_dir = farm_wiki_dir(name)
    if admin_row(target_dir) is None:
        return page("Wikiを消す",
                    _step_name_html(wiki_dir, config, farm, explicit_farm, name=name,
                                    problem="「{}」にはアカウントの記録がありません。"
                                            "`./wiki.py initusers ={}` で用意してから"
                                            "やり直してください。".format(name, name)))
    return page("Wikiを消す",
                _step_password_html(wiki_dir, config, farm, explicit_farm, name))


# 2段目 -> 3段目（ここで書庫づくりが始まる）

def _to_check(page, wiki_dir, config, farm, explicit_farm, name, uid):
    problem = target_problem(name, config)
    if problem:
        return page("Wikiを消す",
                    _step_name_html(wiki_dir, config, farm, explicit_farm,
                                    name=name, problem=problem))
    target_dir = farm_wiki_dir(name)
    admin = admin_row(target_dir)
    if admin is None:
        return page("Wikiを消す",
                    _step_name_html(wiki_dir, config, farm, explicit_farm, name=name,
                                    problem="「{}」にはアカウントの記録がありません。"
                                            .format(name)))
    typed = _form("admin_pw")
    # **照合は `auth.try_password` に通す**——記録（`authlog`）も回数による
    # ロックも、ログイン画面と同じ扱いにするため。ここだけ素通しにすると、
    # そのWikiの管理者のパスワードを当て放題に試せる窓口になる
    user, locked, left = auth.try_password(target_dir, admin["uid"],
                                           admin["uid"], typed)
    if user is None:
        # `lock_warning` はURLのクエリから来た文字列を受け取る前提の関数
        # （`plugin/login.py` がそう呼んでいる）。こちらは数のまま受け取るので、
        # 渡すときに文字列へ直す。まだ数えるところまで行っていなければ None
        warning = "" if left is None else auth.lock_warning(str(left))
        note = ("「{}」の管理者のパスワードが違います。".format(name)
                + ("このアカウントはロックされています。" if locked else warning))
        return page("Wikiを消す",
                    _step_password_html(wiki_dir, config, farm, explicit_farm, name,
                                        problem=note.strip()),
                    status=403)

    stamp = new_stamp()
    started, trouble = start_archive(name, stamp)
    if not started:
        return page("Wikiを消す",
                    _step_name_html(wiki_dir, config, farm, explicit_farm,
                                    name=name, problem=trouble))
    token = token_of(PURPOSE_ARCHIVE, name, stamp, uid)
    return page("Wikiを消す",
                _step_check_html(wiki_dir, config, farm, explicit_farm, name, stamp,
                                 token))


# 3段目 -> 4段目

def _to_final(page, wiki_dir, config, farm, explicit_farm, name, stamp, uid, token):
    if not token_ok(PURPOSE_ARCHIVE, name, stamp, uid, token):
        return _lost(page, wiki_dir, config, farm, explicit_farm)
    target_dir = farm_wiki_dir(name)
    if target_dir is None or not os.path.isdir(target_dir):
        return _lost(page, wiki_dir, config, farm, explicit_farm)
    if not check_passes(target_dir, _form("usage"), _form("updated")):
        return page("Wikiを消す",
                    _step_check_html(wiki_dir, config, farm, explicit_farm, name,
                                     stamp, token,
                                     problem="入れてもらった値が、いまの「{}」と"
                                             "合いません。そのWikiのトップページを"
                                             "開いて、フッタの値を確かめてください。"
                                             .format(name)),
                    status=403)
    checked = token_of(PURPOSE_CHECKED, name, stamp, uid)
    return page("Wikiを消す",
                _step_final_html(wiki_dir, config, farm, explicit_farm, name, stamp,
                                 token, checked))


# 4段目 -> 実行

def _do_delete(page, wiki_dir, config, farm, explicit_farm, name, stamp, uid, token):
    checked = _form("checked")
    # **3段目の合札も要る。** 片方だけで通していると、値の確かめを飛ばした
    # POSTを組み立てられる
    if not (token_ok(PURPOSE_ARCHIVE, name, stamp, uid, token)
            and token_ok(PURPOSE_CHECKED, name, stamp, uid, checked)):
        return _lost(page, wiki_dir, config, farm, explicit_farm)

    state, detail = archive_state(name, stamp)
    if state != "done":
        # **出来上がるまで消さない。** 待たせずに、押し直してもらう
        return page("Wikiを消す",
                    _step_final_html(wiki_dir, config, farm, explicit_farm, name,
                                     stamp, token, checked,
                                     problem=_not_ready_note(state, detail)),
                    status=409)

    staff = stafflog.actor(wiki_dir, farm)
    ok, message = remove_wiki(name)
    if ok and staff is not None:
        # 記録は既定のWiki（この画面を開いたWiki）に残す。消したWikiの記録は書庫の中
        stafflog.record(wiki_dir, staff, "wiki.delete", name, "消した（書庫から戻せる）",
                        before={"name": name, "archive": os.path.basename(done_path(name, stamp))},
                        after=None)
    if not ok:
        return page("Wikiを消す",
                    _step_final_html(wiki_dir, config, farm, explicit_farm, name,
                                     stamp, token, checked, problem=message),
                    status=500)
    return page("Wikiを消しました",
                _done_html(wiki_dir, config, farm, explicit_farm, name, stamp,
                           message, detail))


def _not_ready_note(state, detail):
    if state == "error":
        return ("書庫を作れませんでした。実体は消していません。"
                "やめてから、やり直してください（{}）。".format(detail or "理由不明"))
    if state == "missing":
        return "書庫が見つかりません。実体は消していません。やり直してください。"
    return ("書庫をまだ作っている途中です（いま {}）。"
            "実体は消していません。少し待ってから、もう一度押してください。"
            .format(detail or "作成中"))


def _lost(page, wiki_dir, config, farm, explicit_farm):
    """合札が通らなかったとき。**理由は分けて伝えない**（`sysui.require` と同じ構え）。"""
    return page("Wikiを消す",
                _step_name_html(wiki_dir, config, farm, explicit_farm,
                                problem="手続きの続きが確かめられませんでした。"
                                        "最初からやり直してください。"),
                status=403)


# ---- 画面の中身 -------------------------------------------------------------
#
# 段ごとに1つずつ。**どの段も同じURL（/.delwiki）へPOSTし、hidden の `step` で
# 「どの段から送られてきたか」を名乗る。** 段ごとにURLを分けると、途中のURLを
# 直に叩かれたときに前の段を通ったかどうかが分からなくなる。

def _notice(message, bad=True):
    return sysui.notice(message, bad=bad, prefix="delwiki")


def _hidden(**values):
    return "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">'
        for k, v in values.items() if v)


def _cancel_button(label="やめる"):
    """**「やめる」もPOST。** hidden を持ち回れないと、書庫を片づけられない。"""
    return f'<button type="submit" class="delwiki-cancel" name="cancel" value="1">{escape(label)}</button>'


def _step_bar(current):
    """いまどの段か。4段あることが最初から見えていれば、途中で戸惑わない。"""
    steps = ((STEP_NAME, "Wikiの名前"), (STEP_PASSWORD, "管理者のパスワード"),
             (STEP_CHECK, "いまの様子"), (STEP_FINAL, "最後の確認"))
    cells = []
    for number, (key, label) in enumerate(steps, start=1):
        cls = "delwiki-step delwiki-step-now" if key == current else "delwiki-step"
        cells.append(f'<li class="{cls}"><span class="delwiki-step-no">{number}</span>'
                     f'{escape(label)}</li>')
    return '<ol class="delwiki-steps">' + "".join(cells) + "</ol>"


def _target_url(wiki_dir, config, farm, explicit_farm, name):
    """消そうとしているWikiのトップページ。**3段目の値はここに出ている。**"""
    base = _base_url(wiki_dir, config, farm, explicit_farm)
    root = base.rsplit("/" + FARM_PREFIX, 1)[0]
    return "{}/{}{}/".format(root, FARM_PREFIX, urlquote(name))


def _step_name_html(wiki_dir, config, farm, explicit_farm, name="", problem="",
                    note=""):
    """1段目。**一覧から選ばせず、名前を手で書かせる。**

    押し間違いで消えないようにするためで、`/.allwiki` を見ればどんなWikiが
    あるかは分かる（そちらへの案内は置いてある）。"""
    action = _base_url(wiki_dir, config, farm, explicit_farm) + "/" + DELWIKI_URLPATH
    base = escape(_base_url(wiki_dir, config, farm, explicit_farm))
    return f"""{_notice(problem)}{_notice(note, bad=False)}
{_step_bar(STEP_NAME)}
<div class="delwiki">
  <p class="delwiki-lead">Wikiを1つ消します。消す前に
    <code>wikidata/&lt;Wiki名&gt;.&lt;yymmdd_hhmmss&gt;.7z</code> へ固めるので、
    あとから展開すれば元に戻せます。</p>
  <form class="delwiki-form" method="post" action="{escape(action)}">
    {_hidden(step=STEP_NAME)}
    <div class="delwiki-row">
      <label for="dw-name">消すWikiの名前</label>
      <input id="dw-name" type="text" name="name" value="{escape(name)}"
             placeholder="例: sandbox" autocomplete="off" required>
    </div>
    <p class="delwiki-hint">一覧から選ぶ形にはしていません（押し間違いで消えないように）。
      どんなWikiがあるかは <a href="{base}/.allwiki">Wikiの一覧</a> で見られます。
      既定のWiki（名前を付けずに開いたときに出るWiki）は消せません。</p>
    <div class="delwiki-actions">
      <button type="submit" class="delwiki-go">次へ</button>
      <a class="delwiki-cancel" href="{base}/">やめる</a>
    </div>
  </form>
</div>"""


def _step_password_html(wiki_dir, config, farm, explicit_farm, name, problem=""):
    """2段目。**消そうとしているWikiの管理者のパスワード**を入れてもらう。

    この画面に入れるのは既定Wikiの管理者と助手だが、それだけで隣のWikiを
    消せてしまうのは強すぎる。**そのWikiを預かっている人であること**を、
    もう一段確かめる。"""
    action = _base_url(wiki_dir, config, farm, explicit_farm) + "/" + DELWIKI_URLPATH
    return f"""{_notice(problem)}
{_step_bar(STEP_PASSWORD)}
<div class="delwiki">
  <p class="delwiki-lead">消すのは Wiki
    <strong class="delwiki-target">{escape(name)}</strong> です。
    このWikiの管理者（<code>admin</code>）のパスワードを入れてください。</p>
  <form class="delwiki-form" method="post" action="{escape(action)}">
    {_hidden(step=STEP_PASSWORD, name=name)}
    <div class="delwiki-row">
      <label for="dw-adminpw">「{escape(name)}」の管理者のパスワード</label>
      <input id="dw-adminpw" type="password" name="admin_pw"
             autocomplete="current-password" required>
    </div>
    <p class="delwiki-hint">この画面を開いている人（既定Wikiの管理者・助手）とは別に、
      <strong>消される側のWikiを預かっている人であること</strong>を確かめます。
      まちがえた回数は、ふだんのログインと同じように数えられます。</p>
    <p class="delwiki-hint">これが通った時点で、<strong>裏で書庫づくりが始まります。</strong>
      最後にやめれば、作りかけの書庫も片づけます。</p>
    <div class="delwiki-actions">
      <button type="submit" class="delwiki-go">次へ</button>
      {_cancel_button()}
    </div>
  </form>
</div>"""


def _step_check_html(wiki_dir, config, farm, explicit_farm, name, stamp, token,
                     problem=""):
    """3段目。**いまそのWikiを見ていることを確かめる。**

    正解は画面に出さない（出したら確かめる意味が無い）。代わりに、
    **どこを見れば書いてあるか**は伝える——隠し事の当てっこではなく、
    消す対象を一度自分の目で見てもらうための段なので。"""
    action = _base_url(wiki_dir, config, farm, explicit_farm) + "/" + DELWIKI_URLPATH
    target = escape(_target_url(wiki_dir, config, farm, explicit_farm, name))
    return f"""{_notice(problem)}
{_step_bar(STEP_CHECK)}
<div class="delwiki">
  <p class="delwiki-lead">消すのは Wiki
    <strong class="delwiki-target">{escape(name)}</strong> です。
    <strong>いまのそのWikiの様子</strong>を書いてください。</p>
  <p class="delwiki-hint">どちらも
    <a href="{target}" target="_blank" rel="noopener">「{escape(name)}」のトップページ</a>
    を開くと、フッタ（画面のいちばん下）に出ています。
    <code>DiskUsage: Page/Attached …</code> と <code>Last-modified: …</code> です。</p>
  <form class="delwiki-form" method="post" action="{escape(action)}">
    {_hidden(step=STEP_CHECK, name=name, stamp=stamp, token=token)}
    <div class="delwiki-row">
      <label for="dw-usage">ディスク使用量</label>
      <input id="dw-usage" type="text" name="usage" placeholder="例: 1.2MB/349KB"
             autocomplete="off" required>
    </div>
    <div class="delwiki-row">
      <label for="dw-updated">トップページの最終更新日</label>
      <input id="dw-updated" type="text" name="updated" placeholder="例: 2026-09-18"
             autocomplete="off" required>
    </div>
    <p class="delwiki-hint">フッタの行をそのまま貼り付けても通ります。
      日付は <code>2026/09/18</code> や <code>20260918</code> の書きかたでも構いません。</p>
    <p class="delwiki-hint delwiki-working">書庫
      <code>{escape(name)}.{escape(stamp)}.7z</code> を、いま裏で作っています。</p>
    <div class="delwiki-actions">
      <button type="submit" class="delwiki-go">次へ</button>
      {_cancel_button("やめる（書庫も消す）")}
    </div>
  </form>
</div>"""


def _step_final_html(wiki_dir, config, farm, explicit_farm, name, stamp, token,
                     checked, problem=""):
    """4段目。最後の確認。**ここで初めて消える。**

    書庫がまだ出来ていなければ、押されても消さずにこの画面へ戻す
    （`_do_delete`）。待たせるより、状況を見せて押し直してもらうほうが早い。"""
    action = _base_url(wiki_dir, config, farm, explicit_farm) + "/" + DELWIKI_URLPATH
    target_dir = farm_wiki_dir(name)
    state, detail = archive_state(name, stamp)
    ready = state == "done"
    labels = {"done": "できました", "working": "作っています",
              "error": "しくじりました", "missing": "ありません"}
    pages = "—"
    if target_dir and pagedb.is_usable(target_dir):
        pages = "{}ページ".format(len(pagedb.all_subpaths(target_dir)))
    usage = usage_text(target_dir) if target_dir else "—"
    return f"""{_notice(problem)}
{_step_bar(STEP_FINAL)}
<div class="delwiki">
  <p class="delwiki-lead delwiki-final">Wiki
    <strong class="delwiki-target">{escape(name)}</strong> を
    <strong>消します。</strong>下の書庫を残して、実体（<code>wikidata/{escape(name)}/</code>
    の中身すべて）を消します。</p>
  <table class="delwiki-table">
    <tbody>
      <tr><th>消すWiki</th><td><code>wikidata/{escape(name)}/</code></td></tr>
      <tr><th>ページ数</th><td>{escape(pages)}</td></tr>
      <tr><th>ディスク使用量</th><td>{escape(usage)}</td></tr>
      <tr><th>残す書庫</th>
          <td><code>wikidata/{escape(name)}.{escape(stamp)}.7z</code></td></tr>
      <tr><th>書庫の状態</th>
          <td class="delwiki-state delwiki-state-{escape(state)}">{escape(labels.get(state, state))}
            {escape(detail)}</td></tr>
    </tbody>
  </table>
  <p class="delwiki-hint">戻したくなったら、<code>wikidata/</code> でこの書庫を展開してください
    （<code>cd wikidata &amp;&amp; 7z x {escape(name)}.{escape(stamp)}.7z</code>）。
    アカウントの記録も履歴も、そのまま入っています。</p>
  <form class="delwiki-form" method="post" action="{escape(action)}">
    {_hidden(step=STEP_FINAL, name=name, stamp=stamp, token=token, checked=checked)}
    <div class="delwiki-actions">
      <button type="submit" class="delwiki-go delwiki-danger"{"" if ready else " disabled"}>
        消す</button>
      {_cancel_button("やめる（書庫も消す）")}
    </div>
    {"" if ready else '<p class="delwiki-hint">書庫ができるまで押せません。'
                      'この画面を読み込み直すと、いまの状態が出ます。</p>'}
  </form>
</div>"""


def _done_html(wiki_dir, config, farm, explicit_farm, name, stamp, message, size):
    base = escape(_base_url(wiki_dir, config, farm, explicit_farm))
    return f"""{_notice(message, bad=False)}
<div class="delwiki">
  <p class="delwiki-lead">Wiki <strong class="delwiki-target">{escape(name)}</strong>
    の実体を消しました。中身は書庫に残してあります。</p>
  <table class="delwiki-table">
    <tbody>
      <tr><th>残した書庫</th>
          <td><code>wikidata/{escape(name)}.{escape(stamp)}.7z</code></td></tr>
      <tr><th>大きさ</th><td>{escape(size)}</td></tr>
    </tbody>
  </table>
  <p class="delwiki-hint">戻すときは <code>wikidata/</code> で展開します。</p>
  <pre class="delwiki-restore">cd wikidata &amp;&amp; 7z x {escape(name)}.{escape(stamp)}.7z</pre>
  <p class="delwiki-hint">書庫を残したくない場合は、このファイルを消してください。
    <strong>消すと戻せません。</strong></p>
  <div class="delwiki-actions">
    <a class="delwiki-go" href="{base}/.allwiki">Wikiの一覧へ</a>
    <a class="delwiki-cancel" href="{base}/">トップページへ</a>
  </div>
</div>"""


def serve_delwiki_asset(name):
    """この画面が自前で持つCSS（/.delwiki.css）。"""
    return serve_asset(DELWIKI_DIR, "delwiki", name, kinds=("css",))
