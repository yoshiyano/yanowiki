"""プロバイダ — 「フォルダとファイルの木」を提供する部品の抽象クラス。

実ファイルか仮想構造かの違いはここで吸収し、API と画面は変えない（Wiki「設計の全体像 > プロバイダ」）。
パスは server.vpath.split で検査済みの要素の組（根は空の組）で受け取る。
名前は server.vpath.check_name で検査済みのものを受け取る。

**1 件ずつの操作だけを持たせる。**複数選択の一括処理・名前の衝突の扱い・既定の名前の番号付けは
API 層（server/ops.py）で共通に書く。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..attributes import DEFAULT_ATTRIBUTES, Attribute
from ..errors import ApiError
from ..icons import Icon


AUTH_ALL = 0o17  # Entry.auth の既定（動かす・読む・書く・実行のすべて）


@dataclass
class Entry:
    name: str            # 拡張子を含む完全な名前。項目を指す ID でもある
    kind: str            # "dir" か "file"
    size: int | None     # バイト数。フォルダや不明なら None
    mtime: float | None  # 更新日時（UNIX 時刻）。持たない構造なら None
    has_children: bool | None = None  # フォルダの中にフォルダがあるか。不明なら None
    extra: dict = field(default_factory=dict)  # プロバイダ固有の情報
    # size・mtime 以外の属性の値 {キー: 値}。キーはプロバイダの attributes の定義、値は数・文字列・None
    attrs: dict = field(default_factory=dict)
    # アイコンの名前（プロバイダの icons か、画面に元からあるもの）。None なら画面が決める（フォルダ・拡張子）
    icon: str | None = None
    # この項目への権限。4 ビット（8 = 動かす・4 = 読む・2 = 書く・1 = 実行）で、既定の 15 はすべて許す
    # （Wiki「API 設計 > 権限」）。画面での使いかた:
    #   動かす … この項目の名前の変更・移動（切り取り・ドラッグで動かす）・削除（ごみ箱へ入れるのは移動に準ずる）。
    #            **入っているフォルダではなく、項目自身の値で決める**（2026-09-29 設計者の仕様。MoveAuth を足してよい
    #            との指示で足した）
    #   読む … ファイル: 開く・コピー元にする / フォルダ: 中身を見る・コピー元にする
    #   書く … フォルダ: その中に作る・貼り付ける・落とす（移動先としての権限。同じ日の設計者の仕様）。
    #          ファイルの「書く」は画面では使わない
    #   実行 … フォルダ: 中へ入る
    # 画面が使う値で、API はこれを見て拒否しない（実ファイルでは OS が拒否する。API で止めるのは組み込む側の役目）
    auth: int = AUTH_ALL

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "hasChildren": self.has_children,
            "extra": self.extra,
            "icon": self.icon,
            "moveauth": (self.auth >> 3) & 1,
            "readauth": (self.auth >> 2) & 1,
            "writeauth": (self.auth >> 1) & 1,
            "execauth": self.auth & 1,
            # 属性の値（キーはプロバイダの attributes）。size・mtime もここに入れる
            "attrs": {"size": self.size, "mtime": self.mtime, **self.attrs},
        }


@dataclass(frozen=True)
class OpenMethod:
    """項目を開く経路（「ブラウザで表示」「ダウンロード」「新しいタブで開く」「別のコマンドで開く」など）。

    ファイルの経路は Provider.open_methods に並べる。先頭が既定（ダブルクリック・Enter）。
    フォルダの経路は Provider.dir_open_methods に並べる。既定（ダブルクリック・Enter）は画面が持つ
    「中に入る」で、並べた経路はそのあとに続く（先頭にも modifier を付けてよい）。
    modifier を付けた経路は、そのキーを押しながらのダブルクリック・Enter で使う。右クリックメニューにはすべてを並べる。"""

    id: str                     # open(path, method) に渡る名前。英小文字で始まる英小文字・数字・- の 32 文字まで
    label: str                  # 右クリックメニューに出す名前
    modifier: str | None = None  # "shift"（押しながら開くとこの経路）か None

    def to_json(self) -> dict:
        return {"id": self.id, "label": self.label, "modifier": self.modifier}


@dataclass
class OpenResult:
    """項目を開いたときに画面がすること（Provider.open が返す。Wiki「API 設計 > 開く」）。"""

    action: str                # "navigate"（ページへ移る）/ "modal"（モーダルで表示する。画面は今後）/
                               # "browse"（webFileDir の画面でフォルダを表示する）
    url: str | None = None     # navigate の行き先。http・https か、webFileDir の画面からの相対
    # navigate: "_blank"（新しいタブ）/ "_self"（この画面から移る）
    # browse: "_self"（この画面で）/ "_blank"（新しいタブの webFileDir で）/ "other"（二画面のもう片方で）
    target: str = "_blank"
    data: dict = field(default_factory=dict)  # modal に渡す情報（JSON にできるもの）
    mount: str | None = None   # browse で表示するフォルダのマウント（開いた項目と別のマウントでもよい）
    path: str | None = None    # browse で表示するフォルダのパス（"/a/b"）
    # navigate の送りかた: "GET"（url を開く）/ "POST"（画面がフォームを作って url へ送る）。ブラウザでページを開く
    # 形で送れるのはこの 2 つだけ（PUT・DELETE などはページを開く操作としては送れない）
    method: str = "GET"
    # navigate で送る値 {名前: 文字列}。GET なら url のクエリに足し、POST ならフォームの本文
    # （application/x-www-form-urlencoded）にする
    params: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"action": self.action, "url": self.url, "target": self.target, "data": self.data,
                "mount": self.mount, "path": self.path, "method": self.method, "params": self.params}


@dataclass
class TrashItem:
    id: str              # ごみ箱の中の項目を指す ID（同じパスのものを何度も消せるので、パスでは指さない）
    original_path: str   # 消す前のパス（"/a/b.txt"）
    deleted_at: float    # 消した日時（UNIX 時刻）
    entry: Entry

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "originalPath": self.original_path,
            "deletedAt": self.deleted_at,
            "entry": self.entry.to_json(),
        }


def _unsupported(*_args, **_kwargs):
    raise ApiError("unsupported", "このマウントではできない操作です")


class Provider(ABC):
    # {"mkdir", "touch", "rename", "delete", "copy", "move", "stream", "trash"} の部分集合。
    # 読み取り（stat / listdir）はどのプロバイダも持つので含めない
    capabilities: frozenset[str] = frozenset()
    # 詳細表示の列に並べる属性（並べる順）。名前は含めない。使わない属性は外し、固有の属性は足す
    # （server/attributes.py、Wiki「プロバイダの作りかた > 属性」）
    attributes: tuple[Attribute, ...] = DEFAULT_ATTRIBUTES
    # 持ち込むアイコン {名前: Icon}。Entry.icon で名前を選ぶ（server/icons.py、Wiki「プロバイダの作りかた > アイコン」）
    icons: dict[str, Icon] = {}
    # ツリーのマウントの行のアイコンの名前。None なら画面の既定（mount）
    mount_icon: str | None = None

    # --- 読み取り ---

    @abstractmethod
    def stat(self, path: tuple[str, ...]) -> Entry:
        """1 つの項目。無ければ ApiError("not_found")。シンボリックリンクは辿った先。"""

    @abstractmethod
    def listdir(self, path: tuple[str, ...]) -> list[Entry]:
        """フォルダの中身。並び順は決めない（並べ替えは画面側）。"""

    def has_children(self, path: tuple[str, ...]) -> bool | None:
        """フォルダの中にフォルダがあるか。調べるのが重いプロバイダは None（不明）でよい。"""
        return None

    def exists(self, path: tuple[str, ...]) -> bool:
        """その名前が使われているか（壊れたリンクなど、開けないものも「使われている」）。"""
        try:
            self.stat(path)
            return True
        except ApiError as e:
            if e.code == "not_found":
                return False
            raise

    # --- 変更（capabilities に名前があるものだけ実装する） ---
    # 同じ名前があれば ApiError("exists")。上書きはしない

    def mkdir(self, parent: tuple[str, ...], name: str) -> Entry:          # "mkdir"
        _unsupported()

    def create_file(self, parent: tuple[str, ...], name: str) -> Entry:    # "touch"（空ファイル）
        _unsupported()

    def rename(self, path: tuple[str, ...], new_name: str) -> Entry:       # "rename"
        _unsupported()

    def delete(self, path: tuple[str, ...]) -> None:                       # "delete"（完全に削除。フォルダは中身ごと）
        _unsupported()

    def copy(self, src: tuple[str, ...], dest_dir: tuple[str, ...], new_name: str | None = None) -> Entry:  # "copy"
        """src を dest_dir の中へ写す（名前は new_name か元の名前）。フォルダを自分の中へは ApiError("into_self")。"""
        _unsupported()

    def move(self, src: tuple[str, ...], dest_dir: tuple[str, ...], new_name: str | None = None) -> Entry:  # "move"
        """src を dest_dir の中へ移す。同じマウントの中だけ（マウントをまたぐときは API 層が open_read / write_file で行う）。"""
        _unsupported()

    # --- 中身の読み書き（capabilities に "stream" があるときだけ） ---
    # マウントをまたぐコピー・移動（server/ops.py の transfer_across）が使う。中身はメモリに載せきらず流す

    def open_read(self, path: tuple[str, ...]):
        """ファイルの中身を読む口（read(n) を持ち、with で閉じられるもの）。フォルダなら ApiError("bad_path")。"""
        _unsupported()

    def write_file(self, parent: tuple[str, ...], name: str, stream) -> Entry:
        """stream（read(n) を持つもの）の中身で、新しいファイルを作る。同じ名前があれば ApiError("exists")。
        途中で失敗したら、書きかけのファイルを残さない。"""
        _unsupported()

    # --- ごみ箱（capabilities に "trash" があるときだけ） ---

    def trash(self, path: tuple[str, ...]) -> TrashItem:
        _unsupported()

    def list_trash(self) -> list[TrashItem]:
        _unsupported()

    def trash_item(self, trash_id: str) -> TrashItem:
        """ごみ箱の項目 1 つ。無ければ ApiError("not_found")。"""
        _unsupported()

    def restore(self, trash_id: str, new_name: str | None = None) -> Entry:
        """元の場所へ戻す（元のフォルダが無ければ作り直す）。new_name を渡すと別名で戻す。"""
        _unsupported()

    def purge(self, trash_id: str) -> None:
        """ごみ箱から完全に削除する。"""
        _unsupported()

    # --- 自動更新（フォルダの変化を OS に見張らせられるプロバイダだけ） ---

    def watch_path(self, path: tuple[str, ...]) -> str | None:
        """フォルダ path の変化を見張るための OS のパス。見張れない構造は None（自動更新されない）。"""
        return None

    def watch_trash_path(self) -> str | None:
        """ごみ箱の中身の変化を見張るための OS のパス。"""
        return None

    # --- 開く ---
    # 開く経路。空なら自動で決める: open を上書きしていれば「開く」1 つ、中身を読める（"stream"）なら
    # 「ブラウザで表示」「ダウンロード（Shift）」、どちらでもなければ開けない（server/app.py の open_methods_of）
    open_methods: tuple[OpenMethod, ...] = ()
    # フォルダの開く経路（画面の既定の「中に入る」のあとに続くもの）。None なら自動で「新しいタブで開く（Shift）」
    # 「隣の画面で開く」（API 層だけで扱い、open は呼ばない）、() なら「中に入る」だけ
    # （server/app.py の dir_open_methods_of）
    dir_open_methods: tuple[OpenMethod, ...] | None = None

    def open(self, path: tuple[str, ...], method: str) -> "OpenResult | None":
        """項目を経路 method で開いたときに画面がすること。ファイルなら open_methods の、フォルダなら
        dir_open_methods の経路の id が来る（dir_open_methods が None のフォルダでは呼ばれない）。
        None なら既定の扱い（ファイル: "stream" の「view」「download」は API 層が GET /api/v1/raw へ移す。
        フォルダ: 「tab」「pane」は API 層がそのフォルダを新しいタブ・隣の画面で表示させる。それ以外は開けない）。"""
        return None

    def notify_changed(self) -> None:
        """このプロバイダの中身が API の外で変わったことを知らせる（どのスレッドから呼んでもよい）。

        watch_path を持たないプロバイダは、変更の API のあとならサーバが自動で知らせる。
        別のプログラムがデータベースを直接書き換えたときなど、API を通らない変化を知ったら、これを呼ぶ。
        このプロバイダを使うマウントを見ている画面が読み直す。
        """
        for notify in list(getattr(self, "_change_listeners", ())):
            notify()

    def _add_change_listener(self, notify) -> None:
        """サーバ（server/app.py）が、notify_changed の知らせ先をつなぐ。1 つのプロバイダを複数のマウントで使ってもよい。"""
        if "_change_listeners" not in self.__dict__:
            self._change_listeners = []
        self._change_listeners.append(notify)
