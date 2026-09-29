"""Wikiの名前を変える（設定画面の「Wiki名」。Wiki設計者の指示、2026-09-18）。

やることは `wikidata/<旧名>/` を `wikidata/<新名>/` へ移すことだけだが、
**Wiki名はそのままURL**（`/=<Wiki名>/`）でもあるので、面倒を見るところが3つある。

    1. 実体の移動        wikidata/<旧名>/ → wikidata/<新名>/（`os.rename`）
    2. 既定Wikiの指定    server.yaml の farm.default が旧名なら付け替える
    3. 戻せない名前を断る 新規作成で**作れない名前**のWikiは、名前を変えない

## 中身は1文字も書き換えない

移すのはフォルダそのもので、ページも設定も添付もそのまま。**名前を元へ戻せば
元どおり**になるので、`/.delwiki` と違って書庫（`.7z`）は取らない。
消えるものが無いからで、「取り返しが付かないから確かめる」という段も
`/.delwiki` ほどには要らない（画面では、いまの名前を書き写してもらう1段だけ）。

## 消えないが、切れるものはある

URLが変わるので、次のものは切れる。画面でも同じことを断っている。

  外からのリンク・ブックマーク  `/=<旧名>/…` はどれも無いページになる
  パスワード                    **切れない。** 塩にWiki名が混ざるので、移す前に旧名を
                                `account.pw_salt` へ書いて固定する（`pin_pw_salt`）
  ログイン状態                  cookieのPathがWikiごとに分かれており
                                （`auth.remember_login`）、合言葉そのものにも
                                Wiki名が混ざる（`auth.session_token`）。
                                **そのWikiに入っている人は全員入り直し**になる
  テーマの選択                  同じくWikiごとのcookie（`wikilib.themes`）

名前を変えた本人だけは、続けて操作できるように新しいURLでcookieを置き直す
（`wikilib.configui._rename`）。他の人の入り直しは避けようがない——合言葉の
作りかたにWiki名が入っている以上、名前が変われば値が変わる。

## `_` で始まるWikiは名前を変えられない

`_system` のような名前は**新規作成では作れない**（`newwiki.WIKI_NAME_RE` と
接頭辞の断り）。作れない名前へは戻せないので、そこから出る道だけを開けて
おくと、間違えたときに引き返せなくなる。**片道の操作は用意しない。**

## 実体を移してから、指定を付け替える

既定Wiki（`farm.default`）の名前を変えるときは、**移してから** server.yaml を
書き換える。書き換えに失敗したら移動を戻す——「実体は新しい名前、指定は古い
名前」という組み合わせは、名前を付けずに開いたときの行き先が無くなり、
サービスの入口そのものが消えるため。
"""
import os

from wikilib import paths, userdb
from wikilib.newwiki import WIKI_NAME_RE
from wikilib.paths import FARM_PREFIX, SYSTEM_PREFIX, farm_config_path, farm_wiki_dir, safe_join
from wikilib.wikiconfig import (
    account_pw_salt, load_default_farm, load_wiki_config, read_yaml, save_farm_config,
    set_default_farm,
)


def wikidata_dir():
    """`wikidata/` の場所。**毎回 `paths` から読む。**

    テストが `paths.WIKIDATA_DIR` を仮置き場へ差し替えるため、読み込み時に
    自分の名前へ束ねてしまうと届かない（`wikilib.delwiki.wikidata_dir` と
    同じ理由）。"""
    return paths.WIKIDATA_DIR


def wiki_exists(name):
    found = safe_join(wikidata_dir(), name)
    return found is not None and os.path.isdir(found)


def renamable(name):
    """このWikiは名前を変えられるか。変えられない理由があれば文言、無ければ None。

    変えられないのは**新規作成では作れない名前のWiki**（冒頭参照）。見るのは
    新規作成と同じ決まり（`newwiki.WIKI_NAME_RE` と接頭辞）で、いまのところ
    `_system` が当たる——`_` 始まりは `WIKI_NAME_RE` が通さない。"""
    if not WIKI_NAME_RE.match(name) or name.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
        return (f"「{name}」は名前を変えられません。この形の名前は新しく作れない"
                "（先頭は半角英数字で、使えるのは半角英数字と - _ だけ）ので、"
                "変えてしまうと元の名前へ戻せなくなります。")
    return None


def rename_problem(old, new):
    """名前を変えられない理由。問題が無ければ None。

    新しい名前の決まりは**新規作成と同じ**（`newwiki.WIKI_NAME_RE` を共有）。
    URLの一部になり、フォルダ名にもなるので、そこだけ別の決まりにする理由が無い。"""
    if not wiki_exists(old):
        return f"「{old}」というWikiはありません。"
    problem = renamable(old)
    if problem:
        return problem
    if not new:
        return "新しい名前を入れてください。"
    if new == old:
        return "いまと同じ名前です。"
    if not WIKI_NAME_RE.match(new):
        return ("名前に使えるのは半角英数字と - _ で、先頭は英数字です"
                "（URLの一部になり、フォルダ名にもなるためです）。")
    if new.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
        return f"「{FARM_PREFIX}」「{SYSTEM_PREFIX}」で始まる名前は使えません。"
    if wiki_exists(new):
        return f"「{new}」はすでにあります。"
    if safe_join(wikidata_dir(), new) is None:
        return "その名前は使えません。"
    return None


def pin_pw_salt(old):
    """名前を変える前に、**旧名を `account.pw_salt` に固定する**。問題があれば理由を返す。

    パスワードのハッシュには塩（既定はWiki名）が混ざる（`wikilib.userdb` の冒頭）。
    塩を書いていないWikiは、名前が変わると**全員のパスワードが通らなくなる**——生の
    パスワードは持っていないので作り直せない。そこで、**移す前に**いまのWiki名を
    `account.pw_salt` へ書いておく（Wiki設計者の指示、2026-09-21）。

    すでに塩を書いてあるWiki（共通の設定に書いた場合を含む）、アカウントの記録が無い
    Wikiは、何もしない。**書けなかったときは名前を変えない**（変えると戻せない
    パスワードが出る）。"""
    wiki_dir = farm_wiki_dir(old)
    if wiki_dir is None or not userdb.exists(wiki_dir):
        return None
    if account_pw_salt(load_wiki_config(wiki_dir), ""):
        return None
    data = read_yaml(farm_config_path(wiki_dir))
    account = data.get("account")
    if not isinstance(account, dict):
        account = data["account"] = {}
    account["pw_salt"] = old
    ok, _saved, message = save_farm_config(wiki_dir, data)
    if not ok:
        return (f"パスワードの塩（account.pw_salt）を書けなかったので、名前は変えていません"
                f"（{message}）。")
    return None


def rename_farm(old, new, config):
    """Wikiの名前を変える。`(成否, 知らせる文言, 新しい既定Wiki名かNone)` を返す。

    3つめは、この操作で `farm.default` を付け替えたときだけ新しい名前を返す
    （呼ぶ側が、戻り先のURLを組み立てるのに要る）。付け替えていなければ None。"""
    problem = rename_problem(old, new)
    if problem:
        return False, problem, None

    source = safe_join(wikidata_dir(), old)
    dest = safe_join(wikidata_dir(), new)
    if source is None or dest is None:
        return False, "その名前では変えられません。", None
    problem = pin_pw_salt(old)
    if problem:
        return False, problem, None
    try:
        os.rename(source, dest)
    except OSError as e:
        return False, f"名前を変えられませんでした（{e}）。", None

    if load_default_farm(config) != old:
        return True, f"Wikiの名前を「{new}」に変えました。", None

    # 既定Wikiだった場合は、指定のほうも付け替える。**書けなければ移動を戻す**
    # （冒頭の「実体を移してから、指定を付け替える」を参照）
    if not set_default_farm(new):
        try:
            os.rename(dest, source)
        except OSError:
            return False, (f"既定のWikiの指定（config/server.yaml の farm.default）を"
                           f"書き換えられず、実体も「{old}」へ戻せませんでした。"
                           f"server.yaml の farm.default を手で「{new}」にしてください。"), None
        return False, ("既定のWikiの指定（config/server.yaml の farm.default）を"
                       "書き換えられなかったので、名前は変えていません。"), None
    return True, (f"Wikiの名前を「{new}」に変えました。"
                  "既定のWikiの指定も新しい名前に付け替えました。"), new
