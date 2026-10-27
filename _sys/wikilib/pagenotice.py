"""タイトル右端の info（テーマの変数 `page_info`）に出す知らせ。

テーマは `page_info`（`<a ...>...</a>` の `Markup`）を描くだけで、出すかどうかと
つなぐ先は本体が決める（`Tech/ThemeGuide/Blocks`）。知らせがなければ空を返す。
空のあいだ、テーマは幅も余白も取らない。

**本体から読み手に知らせる枠**として使う。誰に出すか（閲覧者全員・特定の人）も、
何件出すかも、本体が決める（数の制限は無い）。知らせが複数あれば、`<a>` を並べて返す。

いま知らせるのは次の3つ。

- **重複**: 同じページ名に `.txt` と `.md` が両方ある。運用では同時に存在させない
  約束だが、手でファイルを置くと起きる。ファイルを探す順（`paths.PAGE_EXTS`）は
  `.txt` が先で、取り込みも編集画面もそのファイルを読む。`.md` は読まれないまま、
  画面からは気づけない。
  **同じ名前のファイルとフォルダ**（`X.md` と `X/`）も重複として扱う。フォルダがあると
  `X/index` が読まれ（無ければ「まだありません」）、`X.md` は読まれない
  （`paths.shadowed_twin`）。整理は `X.拡張子` と `X/index.拡張子` の間で行う。

- **申請の受付の停止**: 承認制のWikiで、承認待ちの申請が `userdb.PENDING_MAX` 件に届き、
  申請を受け付けていない。**承認できる人（管理者と、承認か断るかの権限を持つ助手）にだけ**、
  ふつうのページと「まだありません」のページに出す。つなぐ先は承認の画面（`/.admin/approvals`）。Wiki設計者の指示、2026-10-19
  （ログインの画面ではなく info で「管理者・助手へ」状況を案内する）

- **新しいバージョン**: 公開版（GitHub の yanowiki）に新しいバージョンが出ている。Wiki名を含まない
  URLで開いた既定のWikiで、**管理者と、再起動を許された助手にだけ**出す。つなぐ先は更新の画面
  （`/.admin/update`。`wikilib.sysupdate`）。Wiki設計者の指示、2026-10-27

1つのページに重複が重なっているときは、**1段ずつ**整理してもらう（`duplicate_stage`）。

**画面に出ているファイルと、優先されるファイルは、取り込むまで食い違うことがある。**
画面に出るのは取り込んだ内容（DB）で、`.md` を公開したあとで `.txt` を置いたときは、
取り込む（updatepage・1時間ごとの走査・起動時）まで `.md` のままになる。そのため
知らせの文は、画面に出ているファイル（`shown_ext`）を見て言い分けている。

重複の知らせは**閲覧者全員に出す**（編集の権限では絞らない）。Wiki設計者の指示、2026-10-13
「閲覧者全員に出す案で進めて」。

つなぐ先は、そのWikiの整理の画面（`/.solveDupPage/<ページ名>`。`wikilib.solvedup`）。
詳しい説明のページ（`UsageGuide/Edit/Duplicate`）へは、その画面の先頭からつなぐ。

知らせを足すときは、条件とつなぐ先を返す関数を作り、`page_info_for` で並べる。
"""
import os
from urllib.parse import quote as urlquote

from markupsafe import Markup

from wikilib.paths import (
    APPROVALS_URLPATH, DEFAULT_FARM_FALLBACK, INDEX_NAME, SOLVEDUP_URLPATH, UPDATE_URLPATH, page_files,
    pagepath_of_subpath,
    shadowed_twin,
)
from wikilib.wikiconfig import account_policy, farm_base_url, load_wiki_config

# 案内ページは、配布している `_system` の Wiki にある。自分で作ったWikiには無いので、
# 別のWikiからは `/=_system/…` として開く
GUIDE_FARM = DEFAULT_FARM_FALLBACK
DUPLICATE_GUIDE_PAGE = "UsageGuide/Edit/Duplicate"

# 整理の段（`duplicate_stage` の答えの1つめ）。EXT=同じ名前の `.txt` と `.md`、
# FOLDER=同じ名前のファイル `X.拡張子` とフォルダ `X/`
STAGE_EXT, STAGE_FOLDER = "ext", "folder"

# 警告の三角形。色は意味（注意）を表すものなのでテーマには合わせず固定する。
# 大きさは common.css の `.page-info-slot svg`（高さ 1.4em・幅は自動）が揃える
_WARN_ICON = Markup(
    '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">'
    '<path d="M12 2.5 1.5 21h21z" fill="#d97706"/>'
    '<path d="M12 9v6" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>'
    '<circle cx="12" cy="18" r="1.3" fill="#fff"/>'
    '</svg>'
)

# 知らせ（注意ではない）の丸い i。重複の三角とは別の色にして、データの問題と見分ける
_INFO_ICON = Markup(
    '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="10.5" fill="#2563eb"/>'
    '<circle cx="12" cy="7" r="1.4" fill="#fff"/>'
    '<path d="M12 10.5v7" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>'
    '</svg>'
)


# 更新の知らせの、上向きの矢印。データの問題（橙の三角）とも、知らせ（青い i）とも見分ける
_UPDATE_ICON = Markup(
    '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="10.5" fill="#16a34a"/>'
    '<path d="M12 17.5V7.5M7.5 11.5 12 7l4.5 4.5" stroke="#fff" stroke-width="2.2" fill="none" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)


def guide_url(config, farm, base_url, page):
    """案内ページのURL。いま開いているのが案内のあるWikiなら、そのWikiの入口をそのまま
    使う（見えている景色を変えない）。それ以外のWikiからは `=_system` を明示する。"""
    if farm != GUIDE_FARM:
        base_url = farm_base_url(config, GUIDE_FARM, True)
    return base_url + "/" + urlquote(page, safe="/")


def solve_url(base_url, pagepath):
    """整理の画面のURL。**そのWikiの入口**（`base_url`）に付ける——整理するのはいま開いている
    Wikiのページなので、案内のように `_system` へは飛ばさない。トップページは名前を付けない。"""
    pagepath = (pagepath or "").strip("/")
    return base_url + "/" + SOLVEDUP_URLPATH + ("/" + urlquote(pagepath, safe="/") if pagepath else "")


def duplicate_stage(wiki_dir, subpath):
    """そのページ（実体パス `subpath`）で、次に整理する重複。`(段, 対象の実体パス)`。無ければ None。

    重なっているときは、この順に1段ずつ片付ける。

    1. `subpath` の `.txt` と `.md`（`X/index.txt` と `X/index.md` など）
    2. フォルダに隠れたファイル `X` の `.txt` と `.md`（`X.txt` と `X.md`）
    3. ファイル `X.拡張子` と、フォルダの入口 `X/index`（無くてもよい）

    2 は、ページ名 `X` で開くとフォルダの入口が開くため、ほかの道からは整理できない。"""
    if len(page_files(os.path.join(wiki_dir, subpath))) >= 2:
        return STAGE_EXT, subpath
    twin = shadowed_twin(wiki_dir, subpath)
    if twin is None:
        return None
    if len(page_files(os.path.join(wiki_dir, twin))) >= 2:
        return STAGE_EXT, twin
    return STAGE_FOLDER, twin


def _link(href, text, icon):
    return Markup('<a class="page-info" href="{}" title="{}" aria-label="{}">{}</a>').format(
        href, text, text, icon)


def _notice_link(base_url, pagepath, text):
    return _link(solve_url(base_url, pagepath), text, _WARN_ICON)


def signup_notice(base_url, wiki_dir, farm):
    """承認制のWikiで申請の受付を止めているあいだ、承認の画面へつなぐ `<a>`（Markup）。
    閲覧しているのが承認できる人でなければ、または受け付けているなら None。

    全ページで呼ばれるので、安い判定から順に見る（設定 → ログインと権限 → 承認待ちの件数）。"""
    if account_policy(load_wiki_config(wiki_dir)) != "approval":
        return None
    # auth は themes を通してこのモジュールを読むので、ここで読む
    from wikilib import auth, userdb
    if not auth.can(wiki_dir, farm, "approvals.approve", "approvals.reject"):
        return None
    if userdb.signup_open(wiki_dir):
        return None
    text = ("申請の受付を止めています（承認待ちの申請が{}件あるため）。"
            "承認の画面を開きます").format(userdb.PENDING_MAX)
    return _link(base_url + "/" + APPROVALS_URLPATH, text, _INFO_ICON)


def update_notice(config, farm, base_url, wiki_dir, explicit_farm=False):
    """公開版に新しいバージョンが出ていれば、更新の画面（`/.admin/update`）へつなぐ `<a>`（Markup）。
    Wiki名を含まないURLで開いた既定のWikiで、管理者か再起動を許された助手にだけ出す
    （`/.restart` と同じ範囲。Wiki設計者の指示、2026-10-27）。出さないときは None。

    最新版は `wikilib.sysupdate` が覚えているものを見るだけで、ここでは問い合わせない。
    覚えた内容が古ければ、裏で調べ直しを頼む（次に開いたときに知らせが出る）。"""
    from wikilib.wikiconfig import load_default_farm
    if explicit_farm or farm != load_default_farm(config):
        return None
    from wikilib import auth, sysupdate
    if not auth.can(wiki_dir, farm, "site.restart"):
        return None
    sysupdate.check_in_background()
    newer = sysupdate.available()
    if newer is None:
        return None
    text = "新しいバージョン {} があります（いまは {}）。更新の画面を開きます".format(
        newer, sysupdate.current_version() or "?")
    return _link(base_url + "/" + UPDATE_URLPATH, text, _UPDATE_ICON)


def folder_notice(base_url, wiki_dir, subpath, pagepath=None):
    """フォルダの入口 `subpath`（`X/index`）と同じ名前のファイル `X.拡張子` があれば、整理の画面へ
    つなぐ `<a>`（Markup）。なければ None。`X` に `.txt` と `.md` が両方あれば、そちらを先に
    知らせる（`duplicate_stage` の 2）。"""
    stage = duplicate_stage(wiki_dir, subpath)
    if stage is None or stage[1] == subpath:
        return None
    if pagepath is None:
        pagepath = pagepath_of_subpath(subpath)
    twin = stage[1]
    folder = os.path.basename(twin) + "/"
    names = [os.path.basename(path) for path in page_files(os.path.join(wiki_dir, twin))]
    if stage[0] == STAGE_EXT:
        text = ("同じ名前のファイルが複数あります（{}）。どれも、同じ名前のフォルダ {} があるため読まれません。"
                "整理の画面を開きます").format("・".join(names), folder)
    else:
        entry = page_files(os.path.join(wiki_dir, subpath))
        if entry:
            text = ("同じ名前のファイルとフォルダがあります（{} と {}）。{}{} が優先され、{} は読まれません。"
                    "整理の画面を開きます").format(
                names[0], folder, folder, os.path.basename(entry[0]), names[0])
        else:
            text = ("同じ名前のファイルとフォルダがあります（{} と {}）。フォルダに入口のページ（{}）が"
                    "無いので、このページは無いものとして扱われ、{} は読まれません。整理の画面を開きます"
                    ).format(names[0], folder, INDEX_NAME, names[0])
    return _notice_link(base_url, pagepath, text)


def duplicate_notice(config, farm, base_url, wiki_dir, subpath, shown_ext=None, pagepath=None):
    """同じページ名の `.txt` と `.md` が両方あれば、整理の画面へつなぐ `<a>`（Markup）。なければ None。

    shown_ext は、いま画面に出している内容の拡張子（取り込んだ行のもの）。
    優先されるファイルと食い違っているときは、そのことを title に書く。
    pagepath は、いま開いているページのURL上の名前（整理の画面のURLに使う）。"""
    files = page_files(os.path.join(wiki_dir, subpath))
    if len(files) < 2:
        return None
    if pagepath is None:
        pagepath = pagepath_of_subpath(subpath)
    names = [os.path.basename(path) for path in files]
    shown = os.path.basename(subpath) + shown_ext if shown_ext else names[0]
    if shown == names[0] or shown not in names:
        text = "同じ名前のファイルが複数あります（{}）。{} が優先され、{} は読まれません。整理の画面を開きます".format(
            "・".join(names), names[0], "・".join(names[1:]))
    else:
        text = ("同じ名前のファイルが複数あります（{}）。いま画面に出ているのは、取り込み済みの {} です。"
                "{} が優先されるので、取り込む（updatepage）と {} の内容に替わります。整理の画面を開きます").format(
            "・".join(names), shown, names[0], names[0])
    return _notice_link(base_url, pagepath, text)


def page_info_for(config, farm, base_url, wiki_dir, subpath, shown_ext=None, pagepath=None,
                  explicit_farm=False):
    """そのページの info に出す `<a>` を並べたもの（`Markup`）。知らせがなければ空の `Markup`。

    subpath は None でもよい（ページ名として正しくないURLなど）。そのときはページに
    付く知らせ（重複）を見ない。explicit_farm は、URLにWiki名が入っていたか（更新の知らせは、
    Wiki名を含まないURLで開いた既定のWikiにだけ出す）。"""
    notices = []
    if subpath is not None:
        notice = duplicate_notice(config, farm, base_url, wiki_dir, subpath, shown_ext, pagepath)
        if notice is None:
            notice = folder_notice(base_url, wiki_dir, subpath, pagepath)
        notices.append(notice)
    notices.append(signup_notice(base_url, wiki_dir, farm))
    notices.append(update_notice(config, farm, base_url, wiki_dir, explicit_farm))
    return Markup("").join(n for n in notices if n is not None)
