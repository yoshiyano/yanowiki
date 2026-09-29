"""設定ファイルの読み込みと、そこから決まる値。

設定は役割で2つに分けている。

  config/server.yaml           サービスの起動に関わるもの（server / farm /
                               debug）。Wikiごとに変えようがないので、
                               全体で1つだけの実ファイル。
  config/default.example.yaml  個別Wikiの設定（page / markdown / theme）の
                               既定値。**実ファイル（config/default.yaml）は
                               用意しない**——雛形をそのまま既定値として
                               直接読む（Wiki設計者の指示、2026-09-04）。

個別Wikiの設定は、次の順に重ねて決まる。

  1. config/default.example.yaml を読む
  2. その上に wikidata/<Wiki名>/config/default.yaml があれば重ねて上書きする

**書かれていない項目は既定値がそのまま残る**ので、個別Wiki側には
変えたい項目だけを書けばよい（全部を写す必要はない）。farmを開いても
このexample.yamlの内容をfarm側へ複製することはしない——複製すると、
複製後にexample.yaml（や、かつて存在した実ファイル）を直しても
そのfarmには反映されなくなるという事故が起きるため（load_config参照）。
"""

import copy
import glob
import hashlib
import hmac
import os
import re
import shutil
import time

import yaml
from bottle import request

from wikilib.paths import (
    ALLWIKI_COMMAND, ALLWIKI_NAME_RE, CONFIG_PATH, DEFAULT_FARM_FALLBACK,
    DEFAULT_MARKUP, FARM_PREFIX, MARKUP_FORMATS, SERVER_CONFIG_PATH,
    farm_config_path,
)

_force_debug = False  # --debug 起動時に立つ。config の debug と OR で判定する
_version_label = ""   # 起動時に wiki.py から渡される（版と改訂の表示）


def set_force_debug(on):
    """--debug 起動を覚えておく。configのdebugと同じ意味で扱う。"""
    global _force_debug
    _force_debug = bool(on)


def set_version_label(label):
    """版と改訂の表示（"Ver 0.49 Rev 7.1"）を覚えておく。

    値そのものは wiki.py が持つ。ここは受け取って配るだけで、テーマが
    `{{ version }}` として使う。設定ファイルではなくコードが持つ値なので、
    config とは別に持たせてある。"""
    global _version_label
    _version_label = label or ""


def version_label():
    return _version_label


# 解析済みの設定の控え。path -> ((mtime_ns, 大きさ), 解析結果)
_yaml_cache = {}


def read_yaml(path):
    """設定ファイルを1つ読む。無ければ空として扱う。

    **解析した結果は、ファイルの更新時刻と大きさを鍵にして覚えておく。**
    YAMLの解析は1ファイルで数ミリ秒かかり、`load_wiki_config` は1回の表示で
    何度も呼ばれる（編集権限の設定を判定器から見るようにした2026-09-17に、
    1回あたり約8msと分かった）。ファイルが書き換われば mtime か大きさが
    変わるので、次に読むときに解析し直す。

    **控えは複製して返す。** 呼び出し側が受け取った辞書を書き換えても、
    次に読む人へ響かないようにするため。"""
    try:
        stat = os.stat(path)
        key = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = None
    if key is not None:
        kept = _yaml_cache.get(path)
        if kept is not None and kept[0] == key:
            return copy.deepcopy(kept[1])
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError:
        # 壊れた設定でサービス全体が止まらないよう、無かったものとして扱う
        return {}
    if key is not None:
        _yaml_cache[path] = (key, data)
    return copy.deepcopy(data)


def read_yaml_local_or_common(local_path, common_path):
    """個別Wiki側（local_path）があればそれだけを読み、無ければ共通側
    （common_path）を読む。**重ねる（merge_config）のではなく丸ごと
    読み替える。** PukiWiki記法の置換ルール・InterWiki登録表のように、
    配列まるごとの定義を個別Wikiで書き直す設定向け（項目単位で足し引き
    したいものは default.yaml のように merge_config を使う）。"""
    if os.path.exists(local_path):
        return read_yaml(local_path)
    return read_yaml(common_path)


def merge_config(base, over):
    """設定を重ねる。over にある項目だけが base を上書きする。

    値が両方とも辞書なら中に降りて重ねる（markdown.linkify だけを
    上書きしても markdown.toc_depth が消えないようにするため）。"""
    merged = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def example_of(path):
    """設定ファイルの実パスから、対になる雛形（*.example.yaml）のパスを作る。"""
    base, ext = os.path.splitext(path)
    return base + ".example" + ext


def _copy_if_missing(path, source):
    """path が無ければ source からコピーして作る。source も無ければ何もしない
    （雛形が無くても、設定ファイルが無いのは「空」として動くだけなので困らない）。"""
    if os.path.exists(path) or not os.path.exists(source):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile(source, path)


def ensure_root_config_files():
    """server.yaml が無ければ、雛形（server.example.yaml）から作る。

    起動のたびに呼ぶ想定（無ければ作るだけなので、既にあれば何もしない）。
    初めて動かす環境で「設定ファイルが無くて起動できない」を避けるための、
    サービス起動時の下ごしらえ。

    **default.yaml・pukiwiki.extrarules.yaml・pukiwiki.interwiki.yaml は
    対象外。** これらは`*.example.yaml`をそのまま既定値として直接読む
    （load_config・wikilib.extrarules・wikilib.interwiki参照）ため、
    config/に実ファイルを複製する必要がない。server.yamlだけは
    Wikiごとの上書き先（wikidata/<farm>/config/）を持たない、この
    インスタンス唯一の実体なので、従来どおり実ファイルとして用意する
    （Wiki設計者の指示、2026-09-04。「config/にはexampleのみ配置」の対象は
    farmごとに上書きできる設定に限る）。"""
    _copy_if_missing(SERVER_CONFIG_PATH, example_of(SERVER_CONFIG_PATH))


def load_config():
    """サービス全体の設定（起動に関わるもの＋Wiki設定の共通値）。

    どのWikiを開くか決まる前に要る値（server.prefix / farm.default / debug）が
    ここに含まれる。個別Wikiが決まったあとは load_wiki_config() を使う。

    Wiki設定の土台には config/default.example.yaml を直接読む
    （config/default.yaml という「実ファイル」は用意しない。Wiki設計者の指示、
    2026-09-04）。**farmが最初に開かれたときにこの値をfarm側へ複製する
    処理も廃止した**（旧ensure_farm_config_files）。以前は複製後、farm側が
    独立したファイルになり、この土台をあとから直しても複製済みのfarmには
    反映されないという事故があった（複製した瞬間の値で固定されてしまう
    ため、直した側は「効かなくなった」ことに気づけない）。土台は
    example.yamlそのものを毎回読むだけにし、farmは自分のconfig/に
    書いた項目**だけ**を持つ（無ければ何も書かず、この土台をそのまま
    使う）ようにして、この食い違いを構造的に無くした。

    server.yaml をあとから重ねているのは、分割前の default.yaml に
    server / farm / debug が残っていても動くようにするため。"""
    return merge_config(read_yaml(example_of(CONFIG_PATH)), read_yaml(SERVER_CONFIG_PATH))


def load_wiki_config(wiki_dir):
    """個別Wikiの設定。共通の設定に、そのWikiの default.yaml を重ねたもの。

    書かれていない項目は共通のものがそのまま使われる。
    なお server / farm / debug をここに書いても効かない。
    これらはどのWikiを開くか決まる前に要る値なので、server.yaml だけを見る。"""
    return merge_config(load_config(), read_yaml(farm_config_path(wiki_dir)))


# ---- 設定画面（/.admin/configwiki）が書くファイル ------------------------------

# 1行目に置く目印（Wiki設計者の指示、2026-09-06）。**このシステムが書いたままか**を
# 見分けるためのもので、秘密ではない（誰でも同じ値を作れる）。
CONFIG_MARKER_RE = re.compile(r"^#\s*wikiconfig\s+([0-9a-f]{40})\s*$")

# 控えを何世代まで残すか（Wiki設計者の指示、2026-09-06）
CONFIG_BACKUP_KEEP = 10
# 控えの名前（default.yaml.YYMMDD_HHMMSS）。この形のものだけを世代として数える
CONFIG_BACKUP_RE = re.compile(r"\.\d{6}_\d{6}$")


def config_body_hash(body):
    """目印に入れる値。**1行目を除いた中身**のSHA-1。"""
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def config_marker_line(body):
    return "# wikiconfig " + config_body_hash(body) + "\n"


def written_by_system(path):
    """このファイルは、設定画面が書いたそのままか（Wiki設計者の指示、2026-09-06）。

    1行目が目印で、そこに書かれた値が**残りの中身のハッシュと一致**すれば
    そのまま。人が1文字でも直せば合わなくなる。

    無いファイルは偽を返すが、**「人が直した」という意味ではない**——
    控えを取るかどうかは `needs_backup()` で見ること。"""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    head, sep, body = text.partition("\n")
    found = CONFIG_MARKER_RE.match(head.strip())
    if not sep or not found:
        return False
    return hmac.compare_digest(found.group(1), config_body_hash(body))


def needs_backup(path):
    """書き換える前に控えを取るべきか。

    **人が直したものだけ控える**（Wiki設計者の指示、2026-09-06）。設定画面が書いた
    ままのものは、控えても同じ内容が並ぶだけで、失うものが無い。
    まだ無いファイルも控えようがない。"""
    return os.path.isfile(path) and not written_by_system(path)


def config_backups(path):
    """控えの一覧を新しい順で返す（default.yaml.YYMMDD_HHMMSS）。"""
    found = [p for p in glob.glob(path + ".*") if CONFIG_BACKUP_RE.search(p)]
    return sorted(found, reverse=True)


def backup_config(path, now=None):
    """いまのファイルを `default.yaml.YYMMDD_HHMMSS` として控える。

    取れたら控えのパス、取らなかった／取れなかったら None。
    **古いものは `CONFIG_BACKUP_KEEP` 世代まで**（Wiki設計者の指示、2026-09-06）。
    名前が時刻そのものなので、名前の逆順が新しい順になる。"""
    stamp = time.strftime("%y%m%d_%H%M%S", time.localtime(now))
    dest = path + "." + stamp
    try:
        shutil.copy2(path, dest)
    except OSError:
        return None
    for old in config_backups(path)[CONFIG_BACKUP_KEEP:]:
        try:
            os.remove(old)
        except OSError:
            pass          # 消せなくても、控えが増えるだけで害は無い
    return dest


def dump_config(data):
    """設定を書き出す形にする。**目印の1行＋コメントの無いYAML。**

    Wiki設計者の指示（2026-09-06）により、コメントは残さない——**元のファイルに
    コメントが書いてあっても、この画面で保存すれば消える**。消えて困る
    ものがあれば、それは控え（`backup_config`）のほうに残る。"""
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    return config_marker_line(body) + body


def save_config_file(path, data, now=None):
    """設定ファイル1つを書き換える。(成否, 控えのパスかNone, 文言) を返す。

    **人が直したものだけ、先に控えを取る**（`needs_backup`）。書き込みは
    いったん別名に書いてから置き換える——途中で落ちても、読めない設定
    ファイルが残らないようにするため。個別Wikiの `default.yaml` と、
    定義ルール（`pukiwiki.extrarules.yaml`）の両方がこれを通る。"""
    saved = backup_config(path, now) if needs_backup(path) else None
    text = dump_config(data)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        return False, saved, f"設定を書けませんでした（{e}）。"
    if saved:
        return True, saved, ("設定を保存しました。"
                             f"直前のものは «{os.path.basename(saved)}» に控えました。")
    return True, None, "設定を保存しました。"


def save_farm_config(wiki_dir, data, now=None):
    """個別Wikiの設定（default.yaml）を書き換える。詳しくは `save_config_file`。"""
    return save_config_file(farm_config_path(wiki_dir), data, now)


def load_default_farm(config):
    return (config.get("farm") or {}).get("default", DEFAULT_FARM_FALLBACK)


def set_default_farm(name):
    """server.yaml の farm.default を書き換える。書けたら True。

    yaml.safe_load / yaml.dump は使わない。全体を読み直して書き出すと、
    Wiki設計者が付けたコメントや並びが失われるため、`farm:` セクション直下の
    `default:` 行だけを正規表現でその場置換する。"""
    try:
        with open(SERVER_CONFIG_PATH, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    pattern = re.compile(r"(^farm:\n(?:[ \t].*\n)*?[ \t]+default:[ \t]*)\S*", re.MULTILINE)
    new_text, count = pattern.subn(lambda m: m.group(1) + name, text, count=1)
    if not count:
        return False
    try:
        with open(SERVER_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(new_text)
    except OSError:
        return False
    return True


def allwiki_command(config):
    """全Wikiの一覧を出すページのURL名（設定 farm.allwiki、既定は "allwiki"）。

    返すのは `.` を付けない名前だけで、実際のURLは `/.allwiki` になる。
    **空にすると一覧のページを出さない**（そのURLはただの無いページになる）。
    外に見せたくない運用のための逃げ道で、名前を変えられるようにしてあるのも
    同じ理由（既定の名前で当てられたくない場合に付け替えられる）。

    名前として使えない文字が入っていたら、既定の名前に戻す。ここを通さずに
    URLへ入れると、`/` を含む値などで振り分けが壊れるため。"""
    raw = (config.get("farm") or {}).get("allwiki", ALLWIKI_COMMAND)
    if raw is None or raw is False:
        return ""
    name = str(raw).strip().strip("/")
    if not name:
        return ""
    if not ALLWIKI_NAME_RE.match(name):
        return ALLWIKI_COMMAND
    return name


def url_prefix(config):
    """リバースプロキシ配下などでサブパスに設置する場合のURL接頭辞。
    例: https://foo.bar.com/abcd/efgh/ 以下に置くなら prefix: /abcd/efgh
    未設定なら空文字列（サイトのルートに設置）。"""
    prefix = ((config.get("server") or {}).get("prefix") or "").strip("/")
    return "/" + prefix if prefix else ""


# プロキシが付ける接頭辞として受け付ける形。URLにそのまま埋めるので、
# 使える文字を絞る（`//` 始まり・`..`・引用符・`<>` などは通さない）
_FORWARDED_PREFIX_RE = re.compile(r"^/[A-Za-z0-9_~%.\-]+(?:/[A-Za-z0-9_~%.\-]+)*$")


def forwarded_prefix():
    """プロキシが「このWikiの入口は外向きにはここだ」と伝えてきた接頭辞。

    リクエストヘッダ `X-Forwarded-Prefix`（例: `/sandbox`）で受ける。
    **無い・形が不正・リクエストの外で呼ばれたときは None。**

    使いどころは、プロキシが外向きの `/sandbox/` を内側の `/=sandbox/` へ
    対応づけている場合。内側のURLは `/=sandbox/…` だが、外の閲覧者に
    見せるURLは `/sandbox/…` でなければならない。システムが作るリンク
    （CSS・ページ間リンク・リダイレクト・cookieのPath）を外向きの形で
    出すために、この接頭辞を「Wikiの入口」としてそのまま使う
    （`farm_base_url`）。`server.prefix` は設定ファイルで固定する
    接頭辞で、Wikiごとに外向きの名前を変えたい場合には足りない
    （全Wikiに同じ接頭辞が付くため）。

    ヘッダは直接つないだ相手にも付けられるが、影響は**その人自身に返る
    リンクの形**だけで、文字も上の正規表現で絞ってあるので害はない。"""
    try:
        raw = request.environ.get("HTTP_X_FORWARDED_PREFIX", "")
    except RuntimeError:  # リクエストの外（起動時・CLI）
        return None
    raw = (raw or "").strip().rstrip("/")
    if raw and _FORWARDED_PREFIX_RE.match(raw) and ".." not in raw.split("/"):
        return raw
    return None


def farm_base_url(config, farm, explicit_farm):
    """このWikiの入口のURL（末尾スラッシュなし。既定のWikiを接頭辞なしで
    使っているときは空文字列）。リンクの組み立ては、必ずここを通す。

    プロキシから `X-Forwarded-Prefix` が来ていればそれが入口（Wiki名の
    `/=名前` は付けない。プロキシが外向きの名前へ置き換えているため）。
    無ければ `server.prefix` に、既定以外のWiki（またはURLで明示された
    Wiki）なら `/=Wiki名` を足す。"""
    forwarded = forwarded_prefix()
    if forwarded is not None:
        return forwarded
    base_url = url_prefix(config)
    if explicit_farm or farm != load_default_farm(config):
        base_url += "/" + FARM_PREFIX + farm
    return base_url


def strip_url_prefix(urlpath, prefix):
    """リクエストパスから設定済みの接頭辞を取り除く。
    プロキシ側で既に取り除かれている場合もあるため、付いていなければそのまま返す。"""
    if not prefix:
        return urlpath
    prefix = prefix.strip("/")
    if urlpath == prefix:
        return ""
    if urlpath.startswith(prefix + "/"):
        return urlpath[len(prefix) + 1:]
    return urlpath

def is_debug(config):
    """プラグインのエラー詳細（トレースバック）まで表示するか。
    configの debug か、--debug 起動で有効。開発者向け。"""
    return _force_debug or bool((config or {}).get("debug"))


def default_markup(config):
    """新しく作るページをどの記法で書くか（`edit.defaultwiki`）。

    値は記法の名前（`pukiwiki` / `markdown`）。**書かれていない・知らない名前の
    ときは既定（`DEFAULT_MARKUP`＝pukiwiki）に戻す**——設定の書き損じで新しい
    ページが作れなくなるより、既定に戻って動き続けるほうが安全なため
    （`is_debug`など他の設定と同じ考えかた）。

    ここで決まるのは**新規ページの初期値**だけで、編集画面のツールバーから
    選び直せる。すでにあるページの記法は拡張子で決まっているので関係しない。"""
    name = ((config or {}).get("edit") or {}).get("defaultwiki")
    if isinstance(name, str) and name.strip().lower() in MARKUP_FORMATS:
        return name.strip().lower()
    return DEFAULT_MARKUP


LISTNAME_VALUES = ("fname", "title")


def listname_for(config, markup):
    """一覧（編集画面のページ一覧・`#ls` など）で、名前の代わりにファイル名
    （fname）とタイトル（title）のどちらを基準に出すか。

    設定 `markdown.listname` / `pukiwiki.listname`（Wiki設計者の指示、
    2026-09-18）。**PukiWiki記法はファイル名を基準に書く歴史的な流儀、
    Markdownは見出し（タイトル）を基準に書く流儀があり、統一のルールには
    できない**ため、記法ごとに既定を分けている（pukiwiki=fname、
    markdown=title）。

    `markup` は記法の名前（`"markdown"` / `"pukiwiki"`）。それ以外
    （`"plain"` など拡張子から記法が分からない場合）は常に fname を返す
    ——見出しを探す記法のルールが無いため。

    書き損じ・知らない値のときは、その記法の既定に戻す
    （`default_markup` など他の設定と同じ考えかた）。"""
    if markup not in ("markdown", "pukiwiki"):
        return "fname"
    section = (config or {}).get(markup) or {}
    value = section.get("listname")
    default = "title" if markup == "markdown" else "fname"
    if isinstance(value, str) and value.strip().lower() in LISTNAME_VALUES:
        return value.strip().lower()
    return default


# ユーザ登録の受け入れかた（設定 `account.policy`）の値。
ACCOUNT_POLICIES = ("open", "approval")
DEFAULT_ACCOUNT_POLICY = "open"


def account_policy(config):
    """このWikiが**ユーザ登録**（ログイン画面の「アカウント作成」）をどう受け入れるか
    （設定 `account.policy`。Wiki設計者の指示、2026-09-20）。

      open      誰でも自由にアカウントを作れる。**今の動きそのもの**（既定）
      approval  誰でも申請できるが、助手（staff）か管理者が承認するまで使えない

    **決めるのは登録だけ**（Wiki設計者の整理、2026-09-20）。誰が何を読めて書けるかは
    ページごとの権限（`config/privileges`）が決める。はじめは3つ目の値 `closed`
    （管理者だけが作る）も持っていたが、Wiki設計者の指示（2026-09-21）で外した。

    書き損じ・知らない値（`closed` を含む）のときは `open`（今の動き）に戻す——
    `default_markup` など他の設定と同じ考えかた。

    読んで動きを変えるのは `wikilib.auth.do_signup`（`approval` なら承認待ちで
    始まる）。承認は `wikilib.approvalsui`（`/.admin/approvals`）。値の意味は
    [ユーザ登録の受け入れかた](/Tech/Accounts/Policy)にある。"""
    value = ((config or {}).get("account") or {}).get("policy")
    if isinstance(value, str) and value.strip().lower() in ACCOUNT_POLICIES:
        return value.strip().lower()
    return DEFAULT_ACCOUNT_POLICY


def account_pw_salt(config, wikiname):
    """パスワードのハッシュに混ぜる塩（設定 `account.pw_salt`。Wiki設計者の指示、
    2026-09-21）。**書かなければ（空なら）Wiki名**。

    パスワードのハッシュは `pw_salt + uid + パスワード` から作る
    （`wikilib.userdb.hash_password`）。**この値を変えると、全アカウントのパスワードが
    通らなくなる**——生のパスワードは持っていないので、作り直せない。Wiki名を
    変えるときは、旧名をここへ固定してから移す（`wikilib.farmrename`）。

    文字列（と数）だけを受ける。前後の空白は落とす。"""
    value = ((config or {}).get("account") or {}).get("pw_salt")
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            return text
    return wikiname


def plugin_debug_enabled(config):
    """プラグインが実行できないとき、`_help()`（無ければモジュールのdocstring）を
    折りたたみで添えるか。config の plugin.debug で切り替える。

    is_debug（トレースバック）とは別の設定にしてある。あちらは実装の中身を
    追う開発者向けだが、こちらは「どう書けば動くか」を示す、プラグインの
    使い手・作り手向けのものだから。"""
    return bool(((config or {}).get("plugin") or {}).get("debug"))


# ブロックプラグイン: 行頭の #name(args) 。ATX見出しは "# " と空白が必須なので衝突しない。


def split_farm_and_page(urlpath, config):
    """URLパスを (farm名, ページパス, farmが明示されていたか) に分解する。
    "=Wiki名" で始まる場合はそのWikiを指定したアクセス、
    そうでない場合はデフォルトのWiki内のページパスとして扱う。"""
    if urlpath.startswith(FARM_PREFIX):
        farm_part, _, pagepath = urlpath.partition("/")
        return farm_part[len(FARM_PREFIX):], pagepath, True
    return load_default_farm(config), urlpath, False
