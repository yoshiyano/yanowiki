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
from ..exts import default_ext
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
    # 拡張子（"." を含まない。無ければ ""）。None なら既定の規則（server/exts.py）で名前から決める。
    # 画面は拡張子を切り出さず、これで「種類」・アイコン・名前の入力欄の選択範囲を決める
    ext: str | None = None
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
            "ext": self.ext if self.ext is not None else default_ext(self.name, self.kind),
            "moveauth": (self.auth >> 3) & 1,
            "readauth": (self.auth >> 2) & 1,
            "writeauth": (self.auth >> 1) & 1,
            "execauth": self.auth & 1,
            # 属性の値（キーはプロバイダの attributes）。size・mtime もここに入れる
            "attrs": {"size": self.size, "mtime": self.mtime, **self.attrs},
        }


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
    # {"mkdir", "touch", "rename", "delete", "copy", "move", "stream", "trash", "update_mtime"} の部分集合。
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

    def update_mtime(self, path: tuple[str, ...]) -> Entry:                 # "update_mtime"
        """path の更新日時を今の時刻にする（既定のコマンド touch）。中身は変えない。"""
        _unsupported()

    # --- 削除の前の問い返し（capabilities に "before_delete" があるときだけ） ---

    def before_delete(self, paths: list[tuple[str, ...]], answers: dict) -> "list[dict] | bool | None":
        """既定の削除（delete・purge）を行う前に、中身を見て問い返す。paths は削除する項目（名前の組）、
        answers はこれまでの答え（{名前: "yes" | "no"}。最初は空）。返り値:
        - 効果のリスト（server.commands.Modal(type="yesno", answer=…) など）… 削除せず、画面に見せる。
          はい・いいえの答えは answers.<answer> に付いて、同じ要求が届く（このメソッドをもう一度呼ぶ）
        - True … 確かめ済み。削除する（サーバの既定の確認も出さない）
        - False か空のリスト … 削除しない
        - None … 問い返さない。ごみ箱の無いマウントでは、サーバが既定の確認（はい・いいえ）を出して削除する
        capabilities に "before_delete" があると、削除・完全に削除の宣言から confirm を外す（二重に出さないため）。"""
        return None

    # --- 中身の読み書き（capabilities に "stream" があるときだけ） ---
    # マウントをまたぐコピー・移動（server/ops.py の transfer_across）が使う。中身はメモリに載せきらず流す

    def open_read(self, path: tuple[str, ...]):
        """ファイルの中身を読むファイルオブジェクト（read(n) を持ち、with で閉じられるもの）を返す。フォルダなら ApiError("bad_path")。"""
        _unsupported()

    def write_file(self, parent: tuple[str, ...], name: str, stream, mtime: float | None = None) -> Entry:
        """stream（read(n) を持つもの）の中身で、新しいファイルを作る。同じ名前があれば ApiError("exists")。
        途中で失敗したら（stream の read が例外を投げたときも）、書きかけのファイルを残さない。
        mtime（UNIX 時刻の秒）があれば、書き終えたファイルの更新日時をそれにする（アップロードで元の日時を継ぐ）。
        更新日時を持たない構造は無視してよい。"""
        _unsupported()

    # --- 中身の置き換え（capabilities に "replace" があるときだけ。テキストの編集） ---

    def replace_file(self, path: tuple[str, ...], stream) -> Entry:
        """今あるファイルの中身を、stream（read(n) を持つもの）の中身で置き換える。フォルダなら ApiError("bad_path")。
        途中で失敗したら、元の中身を残す（書きかけで置き換えない）。"""
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

    # --- コマンド（Wiki「サーバ側 > プロバイダ」） ---
    # 独自のコマンドの宣言（server.commands.Command の組）。request は常に "server"（POST commands/<id> を通り、
    # run_command が呼ばれる）。既定のコマンドと同じ id は使えない。使える部品は prompt・confirm まで（C7）
    commands: tuple = ()
    # 既定のコマンドのうち、このプロバイダでは出さないものの id
    disable_commands: frozenset = frozenset()
    # 既定のコマンドの見せかたを変える {id: {label・icon・places・group・order・key・texts のどれか}}
    # （2026-09-29 設計者の指示「C8 は変えられるに変更」。ファイル以外の構造でも言葉を合わせられるように）
    command_overrides: dict = {}

    def run_command(self, command_id: str, ctx) -> list[dict]:
        """独自のコマンドを行い、画面がすること（結果の語彙。server.commands の Navigate・Browse・Modal・
        Message・Reload で作る）のリストを返す。ctx は server.commands.CommandContext（パスは名前の組）。
        ctx.readonly なら、このマウントは今の要求にとって読み取り専用。変更するコマンドはそのとき拒むこと。
        誤りは ApiError で。知らない id は unsupported。"""
        raise ApiError("unsupported", "このマウントではできない操作です")

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
