"""コマンド — 操作者ができる操作 1 つの宣言と、応答のあとに画面がすること（結果の語彙）。

画面の操作（右クリックメニュー・ツールバー・キー・開く・ドロップ）は、サーバが宣言したコマンドから組み立てる。
宣言の形は Wiki の「コマンドの宣言」、結果の語彙は「画面の部品と結果の語彙」を正とする。

**宣言は JSON にできる値だけで、関数・式・条件分岐は書けない。**値は "$名前" で差し込むだけ、文は "@名前" で
texts を指すだけ。どちらも決まった集合で、起動時に確かめる（check_command）。
"""

import re
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

COMMAND_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
TEXT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

PLACES = ("item", "background", "toolbar")
OPEN_VALUES = ("default", "shift")
DROP_TARGETS = ("folder", "trash")
DROP_MOUNTS = ("same", "other", "any")
DROP_MODIFIERS = (None, "ctrl", "shift")
# 落とすもの: items … この画面の項目（ドラッグで運ぶ）/ files … ほかのアプリ（OS のファイルブラウザ）のファイル・フォルダ
DROP_FROM = ("items", "files")
# 要求の送りかた: server … POST commands/<id>（JSON）/ upload … POST commands/<id>/upload（ファイルの中身。
# 1 ファイルに 1 要求）/ None … サーバに送らない
REQUESTS = ("server", "upload", None)
VIEWS = ("folder", "trash", "any")
KINDS = ("file", "dir")
SELECTS = ("none", "one", "some", "any")
AUTH_BITS = {"move": 8, "read": 4, "write": 2, "exec": 1}  # Entry.auth のビット（Wiki「API 設計 > 権限」）

# 部品。既定のコマンドはすべて、プロバイダの独自のコマンドは PROVIDER_PARTS だけ（2026-09-29 設計者決定、C7）
INPUT_PARTS = ("inlineEdit", "prompt", "uploadDialog", "textEdit")
ITEM_ERROR_PARTS = ("chooseConflict",)
PROVIDER_PARTS = ("prompt", "confirm")

# 結果の語彙 → 書ける項目。これ以外は宣言にも応答にも書けない
EFFECTS = {
    "reload": {"select", "edit"},
    "message": {"text", "kind"},
    "report": {"done", "fail"},
    "offer": {"label", "run", "items"},
    "clipboard": {"mode"},
    "clipboardClear": set(),
    "retryInput": set(),
    "navigate": {"url", "target", "method", "params"},
    "browse": {"mount", "path", "target"},
    "modal": {"data"},
}
# run_command（プロバイダの独自のコマンド）が返せる語彙。画面の中の状態（クリップボード・入力）に触るものは返せない
PROVIDER_EFFECTS = ("navigate", "browse", "modal", "message", "reload")
MESSAGE_KINDS = ("info", "error")
# 状態表示のダイアログ（結果の語彙 modal の data）
MODAL_TYPES = ("ok", "yesno")
MODAL_KEYS = {"type", "title", "message", "rows", "answer", "default"}
MAX_MODAL_ROWS = 100
# 答えの名前（answers のキー）。onConflict は名前の衝突の答えに使うので使えない
ANSWER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}")
ANSWER_VALUES = ("yes", "no")
NAVIGATE_TARGETS = ("_blank", "_self")
NAVIGATE_METHODS = ("GET", "POST")  # ブラウザでページを開く形で送れるのはこの 2 つだけ
BROWSE_TARGETS = ("_self", "_blank", "other")

CONFIRM_KEYS = {"title", "message", "detail", "okLabel", "danger"}
INPUT_KEYS = {"part", "value", "select", "title", "label", "detail", "maxSize"}
INLINE_SELECT = ("stem", "all")

# 差し込める値（Wiki「コマンドの宣言 > 差し込める値」）。$result・$done は then の中だけ
VARIABLES = {"$mount", "$dir", "$item.path", "$item.name", "$item.kind", "$items.names", "$items.count",
             "$items.label", "$input"}
RESULT_VARIABLES = {"$done.srcs", "$done.ids", "$done.trashIds", "$done.names", "$result"}
VARIABLE_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?")

# キー。修飾は Ctrl・Alt・Shift の順（Ctrl は Mac の Command も含む）
KEY_NAMES = ({f"F{i}" for i in range(1, 13)} | {chr(c) for c in range(ord("A"), ord("Z") + 1)}
             | {str(i) for i in range(10)}
             | {"Delete", "Insert", "Backspace", "Enter", "Escape", "Tab", "Space", "ArrowUp", "ArrowDown",
                "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"})
MODIFIERS = ("Ctrl", "Alt", "Shift")
# 画面の予約（閲覧の操作。画面に組み込みで実装する）
RESERVED_KEYS = {"Backspace", "Alt+ArrowLeft", "Alt+ArrowRight", "Alt+ArrowUp", "F5", "ArrowUp", "ArrowDown",
                 "ArrowLeft", "ArrowRight", "Shift+ArrowUp", "Shift+ArrowDown", "Shift+ArrowLeft",
                 "Shift+ArrowRight", "Enter", "Shift+Enter", "Escape", "Ctrl+A", "Tab", "Shift+Tab", "Home",
                 "End", "PageUp", "PageDown"}
# ブラウザが譲らないキー（ページが受け取れない、または受け取るとブラウザの操作を奪う）
BROWSER_KEYS = {"Ctrl+W", "Ctrl+T", "Ctrl+N", "Ctrl+Tab", "Ctrl+Shift+Tab", "Ctrl+L", "Ctrl+R",
                "Ctrl+Shift+R", "Ctrl+Shift+T", "Ctrl+Shift+W", "Ctrl+Q", "Alt+F4", "F11", "F12"}

# 既定のコマンドを変えるときに書ける項目（2026-09-29 設計者の指示で C8 を「変えられる」に。
# 見せかただけに限ったのはクロコの案: 条件・要求・結果を変えさせると、サーバが確かめる中身が崩れうる）
# 既定のコマンドを、プロバイダ（command_overrides）・設定（[mount.commands.<id>]）で変えられる項目。
# 見せかたと、BackEnd が裏で行うか（job。名前の変更のように 1 件でも時間がかかりうる構造のため）
OVERRIDABLE = ("label", "icon", "places", "group", "order", "key", "texts", "job")


class CommandError(ValueError):
    """宣言の誤り。起動時に「マウント <id>: コマンド 'x': …」として止める。"""


@dataclass(frozen=True)
class Command:
    """コマンドの宣言 1 つ。項目の意味は Wiki「コマンドの宣言 > 項目」。"""

    id: str
    label: str
    icon: str | None = None
    places: tuple[str, ...] = ()
    group: str | None = None
    order: int = 100
    key: str | None = None
    open: str | None = None
    drop: tuple[dict, ...] = ()
    when: dict = field(default_factory=dict)
    confirm: dict | None = None
    input: dict | None = None
    request: str | None = "server"   # REQUESTS のどれか（"server" なら POST commands/<id>、"upload" ならファイルを送る）
    job: bool = False                # True なら BackEnd が裏で行い（ジョブ）、FrontEnd は進み具合を見せる
    then: tuple[dict, ...] = ()
    on_error: dict = field(default_factory=dict)       # {エラーの code: [語彙…]}
    on_item_error: dict = field(default_factory=dict)  # {エラーの code: {"part": …} か [語彙…]}
    texts: dict = field(default_factory=dict)          # {名前: 文}。宣言の中から "@名前" で指す

    def __post_init__(self):
        # 並びは組（tuple）にそろえる（frozen なので object.__setattr__ で）
        object.__setattr__(self, "places", tuple(self.places))
        drop = self.drop
        object.__setattr__(self, "drop", (drop,) if isinstance(drop, dict) else tuple(drop or ()))
        object.__setattr__(self, "then", tuple(self.then))

    def to_json(self) -> dict:
        data = {"id": self.id, "label": self.label, "icon": self.icon, "places": list(self.places),
                "group": self.group, "order": self.order, "key": self.key, "open": self.open,
                "drop": [dict(d) for d in self.drop], "when": self.when, "confirm": self.confirm,
                "input": self.input, "request": self.request, "job": self.job, "then": list(self.then),
                "onError": self.on_error, "onItemError": self.on_item_error, "texts": self.texts}
        return data

    def overridden(self, changes: dict, where: str) -> "Command":
        """見せかたとジョブにするか（OVERRIDABLE）を変えた宣言。texts は名前ごとに重ねる（知らない名前は誤り）。"""
        if not isinstance(changes, dict):
            raise CommandError(f"{where}: 変える項目は {{項目: 値}} の形にしてください")
        unknown = set(changes) - set(OVERRIDABLE)
        if unknown:
            raise CommandError(f"{where}: 変えられない項目があります: {', '.join(sorted(unknown))}"
                               f"（変えられるのは {', '.join(OVERRIDABLE)}）")
        values = dict(changes)
        if "texts" in values:
            texts = values["texts"]
            if not isinstance(texts, dict):
                raise CommandError(f"{where}: texts は {{名前: 文}} にしてください")
            unknown = set(texts) - set(self.texts)
            if unknown:
                raise CommandError(f"{where}: 知らない文の名前があります: {', '.join(sorted(unknown))}"
                                   f"（書けるもの: {', '.join(sorted(self.texts)) or 'なし'}）")
            values["texts"] = {**self.texts, **texts}
        if "places" in values and isinstance(values["places"], list):
            values["places"] = tuple(values["places"])
        return replace(self, **values)


# --- 結果の語彙を組み立てる（プロバイダの run_command が返す） ---

def Navigate(url: str, target: str = "_blank", method: str = "GET", params: dict | None = None) -> dict:
    """ページへ移る。url は http・https か、画面（index.html）からの相対。"""
    return {"do": "navigate", "url": url, "target": target, "method": method, "params": dict(params or {})}


def Browse(mount: str, path: str, target: str = "_self") -> dict:
    """webFileDir の画面でフォルダを表示する。target は _self / _blank / other（二画面のもう片方）。"""
    return {"do": "browse", "mount": mount, "path": path, "target": target}


def Modal(title: str, message: str = "", rows=None, type: str = "ok", answer: str | None = None,
          default: str = "yes") -> dict:
    """状態表示のダイアログで見せる。type は "ok"（［OK］だけ）か "yesno"（［はい］［いいえ］）。
    rows は [(項目, 値), …] の表。文字だけで、HTML は書けない。
    yesno では answer に答えの名前を書く。FrontEnd は答え（"yes" / "no"）を answers.<answer> に付けて、
    同じコマンドを送り直す（Esc・閉じるは "no"）。default は最初にフォーカスするボタン（"yes" / "no"）。"""
    data = {"type": type, "title": title}
    if message:
        data["message"] = message
    if rows:
        data["rows"] = [[str(k), str(v)] for k, v in rows]
    if type == "yesno":
        data["answer"] = answer
        data["default"] = default
    return {"do": "modal", "data": data}


def Message(text: str, kind: str = "info") -> dict:
    """ステータスバーに知らせる。"""
    return {"do": "message", "text": text, "kind": kind}


def Reload(select: list[str] | None = None) -> dict:
    """一覧とツリーを読み直す。select の名前の項目を選ぶ。"""
    return {"do": "reload", **({"select": list(select)} if select else {})}


# --- 要求の中身（POST commands/<id> の本文を検査したもの） ---

@dataclass
class CommandContext:
    """コマンド API（POST commands/<id>）の本文（Wiki「API 設計 > コマンド API」）。パスは名前の組（根は ()）。"""

    mount: str
    dir: tuple[str, ...] | None = None
    paths: list[tuple[str, ...]] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)
    input: str | None = None
    source: dict | None = None   # {"mount", "paths": [名前の組…], "mode": "copy" | "cut"}
    dest: dict | None = None     # {"mount", "path": 名前の組}
    answers: dict = field(default_factory=dict)  # {"onConflict": …, <yesno の modal の answer>: "yes" | "no"}
    readonly: bool = False       # このマウントが今の要求にとって読み取り専用か（独自のコマンドが変更を拒むため）


# --- 確かめ ---

def check_key(key) -> str | None:
    """キーの書きかた。誤りなら理由。"""
    if not isinstance(key, str) or not key:
        return "key は \"F2\"・\"Ctrl+Shift+N\" のような文字列にしてください"
    parts = key.split("+")
    mods, name = parts[:-1], parts[-1]
    if name not in KEY_NAMES or len(set(mods)) != len(mods) or any(m not in MODIFIERS for m in mods) \
            or mods != sorted(mods, key=MODIFIERS.index):
        return f"key {key!r} は、修飾（{'・'.join(MODIFIERS)} の順）と、キーの名前（F1〜F12・A〜Z・0〜9・Delete など）を + で" \
               "つないでください"
    if key in RESERVED_KEYS:
        return f"key {key!r} は画面の予約（閲覧の操作）です"
    if key in BROWSER_KEYS:
        return f"key {key!r} はブラウザが譲らないキーです"
    return None


def _check_variables(value, allowed: set, where: str) -> None:
    """文字列の中の $名前 が、その場所で使える名前か。値は入れ子の dict・list もたどる。"""
    if isinstance(value, str):
        for name in VARIABLE_RE.findall(value):
            if name in allowed or (name.startswith("$result.") and "$result" in allowed):
                continue
            raise CommandError(f"{where}: 差し込めない名前です: {name}")
    elif isinstance(value, dict):
        for v in value.values():
            _check_variables(v, allowed, where)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _check_variables(v, allowed, where)


def _check_text_refs(value, texts: dict, where: str) -> None:
    """"@名前" が texts にあるか。"""
    if isinstance(value, str):
        if value.startswith("@") and value[1:] not in texts:
            raise CommandError(f"{where}: texts に無い文です: {value}")
    elif isinstance(value, dict):
        for v in value.values():
            _check_text_refs(v, texts, where)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _check_text_refs(v, texts, where)


def check_effects(effects, where: str, allowed_do=tuple(EFFECTS)) -> None:
    """結果の語彙の並び（宣言の then・onError と、run_command の応答）の形。"""
    if not isinstance(effects, (list, tuple)):
        raise CommandError(f"{where}: 結果の語彙の配列にしてください")
    for e in effects:
        if not isinstance(e, dict) or e.get("do") not in allowed_do:
            raise CommandError(f"{where}: do は {', '.join(allowed_do)} のどれかにしてください: {e!r}")
        unknown = set(e) - {"do"} - EFFECTS[e["do"]]
        if unknown:
            raise CommandError(f"{where}: {e['do']} に書けない項目があります: {', '.join(sorted(unknown))}")
        if e["do"] == "message" and e.get("kind", "info") not in MESSAGE_KINDS:
            raise CommandError(f"{where}: message の kind は {', '.join(MESSAGE_KINDS)} のどれかです")
        if e["do"] == "clipboard" and e.get("mode") not in ("copy", "cut"):
            raise CommandError(f"{where}: clipboard の mode は copy か cut です")


def check_effect_values(effects, where: str) -> None:
    """応答として返す語彙の値の安全の確かめ（0.x の開くの確かめを広げたもの）。javascript: などの URL、
    知らない target・method、文字列でない params を返させない。マウント・フォルダの確かめは呼ぶ側（app.py）。"""
    check_effects(effects, where, PROVIDER_EFFECTS)
    for e in effects:
        if e["do"] == "navigate":
            url = e.get("url")
            if not isinstance(url, str) or not url or urlsplit(url).scheme not in ("", "http", "https"):
                raise CommandError(f"{where}: navigate の url に使えない形です: {url!r}")
            if e.get("target", "_blank") not in NAVIGATE_TARGETS:
                raise CommandError(f"{where}: navigate の target は {' / '.join(NAVIGATE_TARGETS)} です")
            if e.get("method", "GET") not in NAVIGATE_METHODS:
                raise CommandError(f"{where}: navigate の method は {' / '.join(NAVIGATE_METHODS)} です")
            params = e.get("params", {})
            if not isinstance(params, dict) or not all(isinstance(k, str) and k and isinstance(v, str)
                                                       for k, v in params.items()):
                raise CommandError(f"{where}: navigate の params は {{名前: 文字列}} にしてください")
        elif e["do"] == "browse":
            if e.get("target", "_self") not in BROWSE_TARGETS:
                raise CommandError(f"{where}: browse の target は {' / '.join(BROWSE_TARGETS)} です")
            if not isinstance(e.get("mount"), str) or not isinstance(e.get("path"), str):
                raise CommandError(f"{where}: browse には mount と path（\"/a/b\"）が要ります")
        elif e["do"] == "message" and not isinstance(e.get("text"), str):
            raise CommandError(f"{where}: message の text は文字列にしてください")
        elif e["do"] == "modal":
            check_modal(e.get("data"), where)


def check_modal(data, where: str) -> None:
    """状態表示のダイアログの中身。文字だけ（HTML は FrontEnd が文字として描く）で、決まった項目だけ。"""
    if not isinstance(data, dict) or set(data) - MODAL_KEYS:
        raise CommandError(f"{where}: modal の data は {{{', '.join(sorted(MODAL_KEYS))}}} の形にしてください")
    if data.get("type") not in MODAL_TYPES:
        raise CommandError(f"{where}: modal の type は {' / '.join(MODAL_TYPES)} です")
    if not isinstance(data.get("title"), str) or not data["title"]:
        raise CommandError(f"{where}: modal には title（文字）が要ります")
    if not isinstance(data.get("message", ""), str):
        raise CommandError(f"{where}: modal の message は文字にしてください")
    rows = data.get("rows", [])
    if not isinstance(rows, list) or len(rows) > MAX_MODAL_ROWS or not all(
            isinstance(r, list) and len(r) == 2 and all(isinstance(x, str) for x in r) for r in rows):
        raise CommandError(f"{where}: modal の rows は [[項目, 値], …]（文字、{MAX_MODAL_ROWS} 行まで）にしてください")
    if data["type"] == "yesno":
        answer = data.get("answer")
        if not isinstance(answer, str) or not ANSWER_RE.fullmatch(answer) or answer == "onConflict":
            raise CommandError(f"{where}: yesno の modal には answer（英字で始まる英数字。onConflict 以外）が要ります")
        if data.get("default", "yes") not in ANSWER_VALUES:
            raise CommandError(f"{where}: modal の default は yes / no です")
    elif "answer" in data or "default" in data:
        raise CommandError(f"{where}: answer・default は yesno の modal だけに書けます")


def _check_when(when, where: str) -> None:
    if not isinstance(when, dict):
        raise CommandError(f"{where}: when は {{条件: 値}} にしてください")
    known = {"view", "kinds", "select", "items", "dir", "dest", "clipboard", "reachable"}
    unknown = set(when) - known
    if unknown:
        raise CommandError(f"{where}: when に知らない条件があります: {', '.join(sorted(unknown))}")
    if when.get("view", "folder") not in VIEWS:
        raise CommandError(f"{where}: when.view は {', '.join(VIEWS)} のどれかです")
    kinds = when.get("kinds", list(KINDS))
    if not isinstance(kinds, list) or not kinds or any(k not in KINDS for k in kinds):
        raise CommandError(f"{where}: when.kinds は [\"file\"]・[\"dir\"]・[\"file\", \"dir\"] のどれかです")
    if when.get("select", "any") not in SELECTS:
        raise CommandError(f"{where}: when.select は {', '.join(SELECTS)} のどれかです")
    items = when.get("items")
    if items is not None and (not isinstance(items, dict) or set(items) - {"auth", "partial"}
                              or items.get("auth") not in AUTH_BITS
                              or not isinstance(items.get("partial", False), bool)):
        raise CommandError(f"{where}: when.items は {{\"auth\": {'|'.join(AUTH_BITS)}, \"partial\": true|false}} です")
    for k in ("dir", "dest"):
        v = when.get(k)
        if v is not None and (not isinstance(v, dict) or set(v) != {"auth"} or v["auth"] not in AUTH_BITS):
            raise CommandError(f"{where}: when.{k} は {{\"auth\": {'|'.join(AUTH_BITS)}}} です")
    for k in ("clipboard", "reachable"):
        if k in when and when[k] is not True:
            raise CommandError(f"{where}: when.{k} は true だけ書けます")


def check_command(c, *, builtin: bool) -> None:
    """宣言 1 つの形。builtin でない（プロバイダの独自のコマンド）なら、使える部品を限る（C7）。"""
    if not isinstance(c, Command):
        raise CommandError(f"Command でないものがあります: {c!r}")
    where = f"コマンド {c.id!r}"
    if not isinstance(c.job, bool) or (c.job and c.request != "server"):
        raise CommandError(f"{where}: job は、BackEnd に送るコマンド（request が server）にだけ書けます")
    if not isinstance(c.id, str) or not COMMAND_ID_RE.match(c.id):
        raise CommandError(f"{where}: id は英小文字で始まる英小文字・数字・- の 32 文字までにしてください")
    if not isinstance(c.label, str) or not c.label:
        raise CommandError(f"{where}: label は空でない文字列にしてください")
    if any(p not in PLACES for p in c.places) or len(set(c.places)) != len(c.places):
        raise CommandError(f"{where}: places は {', '.join(PLACES)} から重ならずに選んでください")
    if c.icon is not None and (not isinstance(c.icon, str) or not c.icon):
        raise CommandError(f"{where}: icon は空でない文字列か None にしてください")
    if "toolbar" in c.places and not c.icon:
        raise CommandError(f"{where}: ツールバーに出すなら icon が要ります")
    if c.group is not None and (not isinstance(c.group, str) or not c.group):
        raise CommandError(f"{where}: group は空でない文字列か None にしてください")
    if isinstance(c.order, bool) or not isinstance(c.order, int):
        raise CommandError(f"{where}: order は整数にしてください")
    if c.key is not None and (err := check_key(c.key)):
        raise CommandError(f"{where}: {err}")
    if c.open not in (None, *OPEN_VALUES):
        raise CommandError(f"{where}: open は {', '.join(OPEN_VALUES)} か None です")
    for d in c.drop:
        if not isinstance(d, dict) or set(d) - {"target", "mounts", "modifier", "from"} \
                or d.get("target", "folder") not in DROP_TARGETS or d.get("mounts", "any") not in DROP_MOUNTS \
                or d.get("modifier") not in DROP_MODIFIERS or d.get("from", "items") not in DROP_FROM:
            raise CommandError(f"{where}: drop は {{from: items|files, target: folder|trash, mounts: same|other|any, "
                               f"modifier: null|ctrl|shift}} です: {d!r}")
        # ほかのアプリのファイルは、フォルダへ落とすだけ（マウント・押しているキーで分けない）。受け取るのはファイルを
        # 送るコマンドだけ
        if d.get("from", "items") == "files" and (d.get("target", "folder") != "folder" or "mounts" in d
                                                  or "modifier" in d or c.request != "upload"):
            raise CommandError(f"{where}: from: files のドロップは target: folder だけで、mounts・modifier は書けず、"
                               "request が upload のコマンドだけです")
        if d.get("from", "items") == "items" and c.request == "upload":
            raise CommandError(f"{where}: request が upload のコマンドが受け取れるドロップは from: files だけです")
    _check_when(c.when, where)
    if c.open is not None and c.when.get("select") != "one":
        raise CommandError(f"{where}: open を付けるコマンドは when.select を \"one\" にしてください")
    if c.open == "default" and c.when.get("kinds") != ["file"]:
        # フォルダの既定（ダブルクリック・Enter）は画面が中に入る（0.x の設計者の指示を引き継ぐ）
        raise CommandError(f"{where}: open: \"default\" はファイルのコマンドだけです（when.kinds を [\"file\"] に）")
    parts = set(INPUT_PARTS) | {"confirm"} | set(ITEM_ERROR_PARTS) if builtin else set(PROVIDER_PARTS)
    if c.confirm is not None:
        if "confirm" not in parts:
            raise CommandError(f"{where}: confirm は使えません")
        if not isinstance(c.confirm, dict) or set(c.confirm) - CONFIRM_KEYS or "message" not in c.confirm:
            raise CommandError(f"{where}: confirm は {{title, message, detail, okLabel, danger}} です（message は必ず）")
    if c.input is not None:
        if not isinstance(c.input, dict) or set(c.input) - INPUT_KEYS or c.input.get("part") not in INPUT_PARTS:
            raise CommandError(f"{where}: input は {{part: {'|'.join(INPUT_PARTS)}, …}} です")
        if c.input["part"] not in parts:
            raise CommandError(f"{where}: 部品 {c.input['part']} は、独自のコマンドでは使えません"
                               f"（使えるのは {', '.join(PROVIDER_PARTS)}）")
        if c.input["part"] == "inlineEdit" and (c.when.get("select") != "one"
                                                or c.input.get("select", "all") not in INLINE_SELECT):
            raise CommandError(f"{where}: inlineEdit は when.select が \"one\" のコマンドだけで、select は "
                               f"{' / '.join(INLINE_SELECT)} です")
    if c.input is not None and c.input.get("part") == "textEdit":
        # テキストの編集は、ファイル 1 つの中身を開いて、編集した全体を input で送る
        if c.when.get("select") != "one" or c.when.get("kinds") != ["file"] or c.request != "server":
            raise CommandError(f"{where}: textEdit は when.select が \"one\"・when.kinds が [\"file\"] の、"
                               "BackEnd に送るコマンドだけで使えます")
        size = c.input.get("maxSize")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise CommandError(f"{where}: textEdit には maxSize（開ける大きさの上限。バイト）が要ります")
    elif c.input is not None and "maxSize" in c.input:
        raise CommandError(f"{where}: maxSize は textEdit だけに書けます")
    if c.request not in REQUESTS:
        raise CommandError(f"{where}: request は \"server\"・\"upload\"・None のどれかです")
    # ファイルを送るコマンドは、送るファイルを部品 uploadDialog で選ばせるか、ドロップ（from: files）で受け取る
    uploads = c.input is not None and c.input.get("part") == "uploadDialog"
    if c.request == "upload" and not (uploads or (c.input is None and c.drop)):
        raise CommandError(f"{where}: request が upload のコマンドは、input に部品 uploadDialog を書くか、"
                           "from: files のドロップで受け取ってください")
    if uploads and c.request != "upload":
        raise CommandError(f"{where}: 部品 uploadDialog は request が upload のコマンドだけで使えます")
    if not builtin and c.request != "server":
        raise CommandError(f"{where}: 独自のコマンドの request は \"server\" だけです")
    check_effects(c.then, f"{where}: then")
    if not isinstance(c.on_error, dict):
        raise CommandError(f"{where}: onError は {{code: [語彙…]}} にしてください")
    for code, effects in c.on_error.items():
        check_effects(effects, f"{where}: onError.{code}")
    if not isinstance(c.on_item_error, dict):
        raise CommandError(f"{where}: onItemError は {{code: …}} にしてください")
    for code, handler in c.on_item_error.items():
        if isinstance(handler, dict):
            if set(handler) != {"part"} or handler["part"] not in ITEM_ERROR_PARTS or handler["part"] not in parts:
                raise CommandError(f"{where}: onItemError.{code} の部品は {', '.join(ITEM_ERROR_PARTS)} だけです"
                                   "（独自のコマンドでは使えません）")
        else:
            check_effects(handler, f"{where}: onItemError.{code}")
    if not isinstance(c.texts, dict) or not all(isinstance(k, str) and TEXT_NAME_RE.match(k) and isinstance(v, str)
                                                for k, v in c.texts.items()):
        raise CommandError(f"{where}: texts は {{名前（英字で始まる英数字・_）: 文}} にしてください")
    # 差し込み（$）と文（@）。$result・$done は then・onItemError の中だけ
    for value in (c.confirm, c.input, c.on_error):
        _check_variables(value, VARIABLES, where)
    _check_variables(list(c.then), VARIABLES | RESULT_VARIABLES, where)
    _check_variables(c.on_item_error, VARIABLES | RESULT_VARIABLES, where)
    _check_variables(list(c.texts.values()), VARIABLES | RESULT_VARIABLES, where)
    for value in (c.confirm, list(c.then), c.on_error, c.on_item_error, c.label):
        _check_text_refs(value, c.texts, where)


def check_command_set(commands, where_prefix: str = "") -> None:
    """1 つのマウントの宣言の組: id・キー・開く・ドロップの条件が重ならないこと。"""
    ids, keys, opens, drops = set(), {}, {}, {}
    for c in commands:
        where = f"{where_prefix}コマンド {c.id!r}"
        if c.id in ids:
            raise CommandError(f"{where}: id が重なっています")
        ids.add(c.id)
        view = c.when.get("view", "folder")
        if c.key is not None:
            # 同じキーは、ごみ箱の中とフォルダ（when.view が違う）でだけ許す
            for other_view, other in keys.get(c.key, []):
                if "any" in (view, other_view) or view == other_view:
                    raise CommandError(f"{where}: key {c.key} がコマンド {other!r} と重なっています")
            keys.setdefault(c.key, []).append((view, c.id))
        if c.open is not None:
            for kind in c.when.get("kinds", list(KINDS)):
                slot = (kind, c.open)
                if slot in opens:
                    raise CommandError(f"{where}: open: {c.open!r} が {kind} でコマンド {opens[slot]!r} と重なっています")
                opens[slot] = c.id
        for d in c.drop:
            for mounts in (("same", "other") if d.get("mounts", "any") == "any" else (d["mounts"],)):
                slot = (d.get("from", "items"), d.get("target", "folder"), mounts, d.get("modifier"))
                if slot in drops:
                    raise CommandError(f"{where}: drop の条件 {d!r} がコマンド {drops[slot]!r} と重なっています")
                drops[slot] = c.id
