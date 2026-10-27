<!-- この文書は Wiki の「組み込みかた」（how_to_embed）から 2026-10-06T22:04:45+09:00 に作った。版 1.2.0+g832d770。直すときは Wiki を直して作り直す -->
# 組み込みかた

**webFileDir（1.0.0）を別のシステム（利用する側のシステム）に組み込んで使う方法**をまとめたページです。配布物の `EMBED.md` は、このページから作ります。
webFileDir は **部品として使われることを前提にしていて、認証を持ちません**。組み込む前に、まず「[2.3 安全のために必ずすること](#23-安全のために必ずすること)」を読んでください。このページで使う用語は、下の「用語」ですべて説明します。


## 用語

| 用語 | 意味 |
|---|---|
| **利用する側のシステム** | webFileDir を組み込んで使う、あなたのシステム（ポータル・Wiki など）。ログインや利用者の管理は、こちらが持つ |
| **操作者** | ブラウザで webFileDir の画面を操作する人 |
| **FrontEnd** | webFileDir のうち、ブラウザで動く部分（`static/`）。一覧・ツリー・右クリックメニューなどを描き、操作を受け付ける |
| **BackEnd** | webFileDir のうち、サーバで動く部分（`server/`・`run.py`）。FrontEnd からの要求を受け、ファイルを読み書きする |
| **API** | FrontEnd（や利用する側のプログラム）が BackEnd に送る HTTP の要求の決まり。場所は `/api/v1/…` |
| **保存先** | ファイルやフォルダが実際に置かれている場所。OS のフォルダ（実ファイル）のほか、メモリ上の木やデータベースのような「仮想の構造」もある |
| **マウント** | 操作者に見せる保存先 1 つ分。設定ファイルの `[[mount]]` に 1 つずつ書く。`id` で指す |
| **マウントの根** | マウントのいちばん上のフォルダ。パスでは `/` |
| **パス** | マウントの中の場所を `/a/b.txt` の形で表した文字列。OS のパス（`/home/…`）は FrontEnd にも API にも出さない |
| **項目** | マウントの中のファイル 1 つ、またはフォルダ 1 つ |
| **権限** | 項目ごとの「読む」「書く」「動かす」（名前の変更・移動・削除）「実行」（フォルダに入る）の 4 つ |
| **コマンド** | 右クリックメニュー・ツールバー・キーから行う操作 1 つ（「名前の変更」「削除」「貼り付け」など）。`rename`・`delete` のような `id` を持つ |
| **宣言** | コマンドの定義。BackEnd が API で FrontEnd に渡す（名前・出す場所・出す条件・入力・終わったあとにすること） |
| **既定のコマンド** | BackEnd に組み込みのコマンド。マウントが持っている機能に応じて、BackEnd が自動で宣言する |
| **独自のコマンド** | 特定のプロバイダだけが持つコマンド |
| **コマンド API** | コマンドを行う API `POST /api/v1/commands/<id>`。変更の操作は、すべてここを通る |
| **プロバイダ** | BackEnd の中で、保存先の違いを受け持つ Python のクラス。マウントごとに 1 つあり、設定の `type` で選ぶ（`local` = 実ファイル、`memory` = メモリ上の木） |
| **プロバイダのメソッド** | BackEnd が保存先に働きかけるときに呼ぶ、プロバイダのメソッド（`stat()`・`listdir()`・`rename()` など）。FrontEnd からは見えない |
| **機能名**（`capabilities`） | プロバイダが「どの変更のメソッドを持っているか」の申告（`"rename"`・`"copy"`・`"trash"` など）。BackEnd はこれを見て、使えるコマンドだけを宣言する |
| **部品** | FrontEnd が持つ入力の道具（文字の入力 `prompt`・確認 `confirm` など）。宣言に書くと、FrontEnd がその部品で操作者に尋ねる |
| **結果の語彙** | コマンドが終わったあと FrontEnd がすることの、決まった一覧（読み直す・知らせる・ページへ移る・フォルダを表示する など） |
| **ごみ箱** | 削除した項目を元に戻せるように置いておく場所 |
| **自動更新** | ほかのタブやほかのプログラムで保存先が変わったとき、F5 を押さなくても FrontEnd の一覧が新しくなる仕組み |
| **オリジン** | URL の `https://host:port` の部分。ブラウザは、別のオリジンのページからの要求を区別する |
| **CSRF** | 別のサイトのページが、操作者のブラウザを使って勝手に要求を送る攻撃 |
| **配布物** | 組み込むのに要るファイルを 1 つにまとめたもの（`webfiledir-<版>.tar.gz`・`.zip`） |

## 1. 全体の考えかた

### 1.1 組み込みかたは 5 通り

| 組み込みかた | 利用する側がすること | 向いている場面 |
|---|---|---|
| **A. API だけを呼ぶ** | 自分の画面やプログラムから API を呼ぶ | 画面は自分で作り、ファイル操作だけを任せたい |
| **B. FrontEnd を `<iframe>` で埋め込む** | 自分のページに `<iframe>` を置き、webFileDir の FrontEnd を出す | FrontEnd ごと使いたい。いちばん手軽 |
| **C. FrontEnd を JS の部品として組み込む** | 自分のページで CSS と ES モジュールを読み、`createApp(要素)` を呼ぶ | 自分のページの一部として、見た目やフォーカスを混ぜたい |
| **D. BackEnd を Python（WSGI）のプログラムに組み込む** | 自分の Python のプログラムで `create_app(設定)`（WSGI アプリ）を動かす | BackEnd の起動・止めかたを自分のシステムでまとめたい |
| **E. bottle で作ったシステムに組み込む** | 自分の bottle のアプリに `mount_webfiledir(アプリ, "/files/", 設定)` で組み込み、自分の認証・認可をつなぐ | 利用する側のシステムが bottle で、ログインや利用者を持っている |

### 1.2 どれを選ぶか

1. 画面を自分で作るなら **A**
2. webFileDir の FrontEnd をそのまま使うなら、まず **B**（組み込む側とぶつかることが最も少ない）
3. B で足りない（ページの一部として混ぜたい）ときだけ **C**。**同じオリジンで配る必要がある** などの制約がある（[5.5](#55-いまの制約)）
4. A〜C のどれでも、BackEnd の動かしかたとして **D** を組み合わせられる
5. 利用する側のシステムが **bottle で作られているなら E**。同じプロセスの中に組み込むので、**利用する側の認証・認可を webFileDir の手前で効かせられる**

**どの組み込みかたでも、操作者ができる操作は BackEnd の設定で止める・変える**（[2.5](#25-操作を止める変える)）。FrontEnd の側だけで止める仕組みはありません。

### 1.3 配置の例

```
ブラウザ ──> 利用する側のシステム（認証・認可）──> webFileDir の BackEnd（127.0.0.1:8616）
                  │ リバースプロキシ /files/ → webFileDir
                  └─ 自分のページ（<iframe src="/files/"> など）
```

- webFileDir の BackEnd は **利用する側のシステムからしか届かない場所**で待ち受ける（例: `127.0.0.1`）
- ブラウザは利用する側のシステムを通して webFileDir に届く（リバースプロキシ）。こうすると **同じオリジンになり**、C の制約も CSRF の確認（[2.3.2](#232-コマンド-apiの確認origin-と-allowed_origins)）も素直に満たせる

## 2. BackEnd を用意する

### 2.1 導入と起動

#### 配布物から導入する（組み込む人向け）

配布物は、GitHub のリリース（[yoshiyano/webFileDir の Releases](https://github.com/yoshiyano/webFileDir/releases)）から入手できます。リポジトリは非公開なので、見られるのはリポジトリに招かれた人だけです。`gh` を使うなら `gh release download v<版> -R yoshiyano/webFileDir`。

```bash
tar xzf webfiledir-<版>.tar.gz                # zip なら unzip
cd webfiledir-<版>
sha256sum -c ../webfiledir-<版>.SHA256SUMS    # 配布物が壊れていないか（任意）
uv sync                                      # uv を使わないなら pip install -r requirements.txt
cp webfiledir.example.toml webfiledir.toml   # 直す（下の 2.2）
uv run run.py
```

| 配布物の中身 | 何か |
|---|---|
| `server/`・`run.py` | BackEnd |
| `static/` | FrontEnd（FrontEnd のテスト用のページは入れていない） |
| `webfiledir.example.toml` | 設定の見本 |
| `pyproject.toml`・`uv.lock`・`requirements.txt` | 依存（bottle だけ） |
| `EMBED.md` | このページを配布物の中で読めるようにしたもの |
| `examples/iframe.html`・`component.html` | 組み込みかた B・C の例 |
| `examples/nginx.conf` | リバースプロキシの例（2.4） |
| `examples/embed_server.py`・`bottle_host.py` | 組み込みかた D・E の例 |
| `examples/custom_commands.py` | 独自のコマンドを持つ仮想の構造の見本（[8 章](#8-自分のプロバイダを差し込む仮想ファイル構造)） |
| `VERSION` | 版・コミット・作った日時 |

- 配布物は、リポジトリで `./tools/make_dist.py` を動かすと `dist/` にできる（開発する人向け）

#### リポジトリから導入する（開発する人向け）

```bash
git clone git@github.com:yoshiyano/webFileDir.git webFileDirs
cd webFileDirs
uv sync
cp webfiledir.example.toml webfiledir.toml   # 直す（下の 2.2）
uv run run.py                  # ./webfiledir.toml を読む
uv run run.py -c other.toml    # 設定ファイルを指定する
```

- Python 3.12 以上と [uv](https://docs.astral.sh/uv/) が要る
- マウントの根が無ければ権限 `0700` で作る。**根がシンボリックリンク・フォルダ以外・起動したアカウント以外の持ち物なら起動しない**
- 設定に知らない項目があっても起動しない（打ち間違いを黙って無視しないため）。コマンドの宣言・止める・変える設定の誤り（予約のキー、知らないコマンドなど）も起動を止める
- **同じポートで webFileDir が先に動いていたら、それを止めてから起動する**（入れ替わる）。止めるのは、同じアカウントで動いている webFileDir の `run.py` だけ。**別のプログラムがポートを使っていれば止めずに**終わる
- 端末を閉じても動き続けるようにするなら: `setsid nohup ./run.py >> log/webfiledir.log 2>&1 < /dev/null &`

### 2.2 設定ファイル（TOML）

```toml
[server]
host = "127.0.0.1"
port = 8616
allowed_origins = ["https://portal.example.lan"]
# max_upload_size = 1073741824                # アップロードの 1 ファイルの上限（バイト）
# upload_deny_exts = ["php", "cgi"]           # アップロードを受け付けない拡張子

[[mount]]
id = "docs"
type = "local"
root = "/srv/share/docs"
label = "共有資料"
readonly = false
# trash = "/srv/share/docs/.fdweb-trash"
# disable = ["purge", "trash-empty"]          # 出さないコマンド（2.5）

# [mount.commands.rename]                     # コマンドの見せかたを変える（2.5）
# label = "名前を付け直す"
```

#### [server] の項目

| 項目 | 既定 | 意味 |
|---|---|---|
| `host` | `127.0.0.1` | 待ち受けるアドレス。**組み込むときは利用する側からしか届かないアドレスにする**（[2.3.1](#231-利用する側からしか届かないようにする)） |
| `port` | `8616` | 待ち受けるポート |
| `allowed_origins` | `[]` | コマンド APIを許す、利用する側のページのオリジン（`https://host:port` の形）。[2.3.2](#232-コマンド-apiの確認origin-と-allowed_origins) |
| `max_upload_size` | 無し（上限なし） | アップロードする 1 ファイルの大きさの上限（バイト、1 以上）。超えると `too_large`。リバースプロキシの上限は別に合わせる（[2.4](#24-リバースプロキシの下に置く)） |
| `upload_deny_exts` | `[]` | アップロードを受け付けない拡張子（`"php"`・`"tar.gz"` など。`.` は付けても付けなくてもよい）。名前の末尾で見て、大文字・小文字は区別しない。判定は BackEnd だけがする |

#### [[mount]] の項目（1 つ以上）

| 項目 | 既定 | 意味 |
|---|---|---|
| `id` | （必須） | URL・API での識別子（**操作者には見せない**。表示は `label`）。英数字・`_`・`-` の 1〜64 文字。重ならないこと |
| `type` | （必須） | プロバイダの種類。`local`（実ファイル）か `memory`（メモリ上の木。**BackEnd を止めると中身は消える**）か、差し込んだ種類（[8 章](#8-自分のプロバイダを差し込む仮想ファイル構造)） |
| `root` | `local` では必須 | マウントの根にする実フォルダ（絶対パス）。`memory` には書けない |
| `label` | `(root)` | FrontEnd に出す名前。`label` を書かないマウントが 2 つ以上あると見分けられないので、書いておく |
| `readonly` | `false` | `true` なら変更のコマンドを宣言しない（コマンド APIを直接呼んでも 403。ごみ箱の中を見ることはできる） |
| `trash` | 根の直下の `.fdweb-trash` | ごみ箱の置き場所（絶対パス）。根と同じファイルシステムに置く |
| `disable` | `[]` | 出さないコマンドの `id`（[2.5](#25-操作を止める変える)） |
| `commands` | — | `[mount.commands.<id>]` の表で、コマンドの見せかたを変える（[2.5](#25-操作を止める変える)） |
| `samples` | `[]` | 出す見本のコマンドの `id`（`duplicate`・`trim`・`touch`・`numbering`・`timer`）。標準では出さない、機能の作りかたの例（サーバ側実装例（Wiki: /ServerSample）） |

- 同じフォルダを、書き込めるマウントと読み取り専用のマウントの 2 つにしてもよい（利用する側が、人によってどちらを見せるか選べる）

### 2.3 安全のために必ずすること

**webFileDir は誰が要求したかを確かめません。**届いた要求は、BackEnd を動かしているアカウントの権限で実行します。

#### 2.3.1 利用する側からしか届かないようにする

- `host = "127.0.0.1"` にして同じ機械のリバースプロキシから通す、または利用する側からしか届かないネットワークで待ち受ける
- **この形にするまで、消えて困るフォルダをマウントしない**
- 共有の秘密をヘッダで確かめる仕組みのような、webFileDir の側で要求の出どころを確かめる仕組みは無い
- **利用する側のシステムが bottle で作られているなら、組み込みかた E で満たせる**（同じプロセスに組み込み、webFileDir 用のポートを開かない。[7 章](#7-bottle-で作ったシステムに組み込むe)）

#### 2.3.2 コマンド APIの確認（Origin と allowed_origins）

コマンド APIは、次を満たさないと拒否します（CSRF を防ぐため）。

| 確認 | 満たさないとき |
|---|---|
| ヘッダ `X-WebFileDir: 1` がある | 400 `bad_request` |
| `Content-Type: application/json` | 400 `bad_request` |
| `Origin` ヘッダがあるなら、**BackEnd から見た自分自身**（`http://` + 要求の `Host`）か `allowed_origins` のどれか | 403 `bad_origin` |

- **`Origin` の無い要求（ブラウザではないプログラム）は通す。**CSRF はブラウザでだけ起きるため
- リバースプロキシの外側が `https://` だと、ブラウザが付ける `Origin`（`https://…`）は、BackEnd から見た自分自身（`http://…`）と一致しない。**外から見えるオリジンを `allowed_origins` に書く**

#### 2.3.3 誰に何を見せるか（認可）は利用する側で

- **組み込みかた E なら、`mount_access` で人ごとにマウントを「読み書き・読み取りのみ・見せない」に分け、コマンドも止められる**（[7.3](#73-人ごとにマウントとコマンドを分けるmount_access)）。D でも `create_app` に同じ引数を渡せる
- A〜C（D を使わない）で人ごとに分けるには、人ごとに別の BackEnd を立てる、リバースプロキシで確かめる、などで分ける。webFileDir に認可の結果を渡す仕組みは、D・E の引数（`authorize`・`mount_access`）のほかには無い

#### 2.3.4 守りとして入っているもの

- 組み立てたパスを realpath で解決し、**マウントの根の外へは出ない**
- 名前の変更・削除・移動はシンボリックリンク（別の場所を指す参照の項目）を辿らない（リンクを消してもリンク先は残る）
- 削除は既定で**ごみ箱へ**
- **宣言したコマンドだけを受け付け、その条件（項目の権限など）も BackEnd で確かめる**
- ファイルの中身（`GET /api/v1/raw/…`）は `Content-Security-Policy: sandbox` を付けて返す（マウントの中の HTML のスクリプトを、webFileDir のオリジンで動かさない）

### 2.4 リバースプロキシの下に置く

FrontEnd と API の URL は **`index.html` からの相対** なので、`/files/` のような別のパスの下にそのまま置けます。

```nginx
location /files/ {
    proxy_pass http://127.0.0.1:8616/;   # 末尾の / で /files/ を取り除いて渡す
    proxy_set_header Host $host;
    # 自動更新（Server-Sent Events）の接続を溜めずに流し、開いたままにする
    proxy_buffering off;
    proxy_read_timeout 1h;
    # アップロード: 本文の上限（nginx の既定は 1MB）と、本文を溜めずに流すこと
    client_max_body_size 0;
    proxy_request_buffering off;
}
```

- **アップロードは、プロキシの本文の上限に当たる**（nginx の既定は 1MB）。送らせたい大きさに合わせる（`0` で上限なし。webFileDir の上限は `max_upload_size`）。プロキシが断ると、FrontEnd は「サーバの手前で断られました」と知らせる
- 本文を溜めずに流す（nginx は `proxy_request_buffering off`）と、FrontEnd の進み具合が実際の送り具合に合う

- 自動更新の応答には `X-Accel-Buffering: no` を付けているので nginx は溜めないが、ほかのプロキシでは **応答を溜めない設定** が要る
- 自動更新の接続には 20 秒ごとに空の行を送る。プロキシの無通信の制限は 20 秒より長くする
- 静的ファイルには `Cache-Control: no-cache` を付けている（更新した FrontEnd がすぐ届くように）。プロキシでキャッシュさせない

### 2.5 操作を止める・変える

**操作者ができる操作（コマンド）は、BackEnd の設定で止める・変える。**止めたコマンドは FrontEnd に出ず（ボタン・右クリック・キー・ドロップ）、コマンド APIを直接呼んでも受け付けません。コマンドの `id` は 既定のコマンド（Wiki: /Design/Command#既定のコマンド） の表にあります（`rename`・`delete`・`purge`・`paste`・`drop-move` など）。

```toml
[[mount]]
id = "docs"
type = "local"
root = "/srv/share/docs"
disable = ["purge", "trash-empty", "drop-move", "drop-copy"]   # 完全に削除とドラッグ＆ドロップを止める

[mount.commands.rename]
label = "名前を付け直す"
key = "F4"

[mount.commands.delete.texts]
done = "外しました"                  # 「3 個の項目を外しました」
```

| したいこと | 書きかた |
|---|---|
| マウントごとにコマンドを止める | `[[mount]]` の `disable` |
| 人ごとにコマンドを止める | `mount_access` が `{"access": "rw", "disable": [...]}` を返す（[7.3](#73-人ごとにマウントとコマンドを分けるmount_access)） |
| 見せかた（`label`・`icon`・`places`・`group`・`order`・`key`・`texts`）を変える、ジョブにする（`job = true`。BackEnd が裏で行い、FrontEnd が進み具合と［中止］を出す） | `[mount.commands.<id>]`。何をするか（条件・送るもの・終わったあとにすること）は変えられない |
| ごみ箱を使わせない | `restore`・`trash-purge`・`trash-empty` を止める（ツリーのごみ箱も出なくなる） |
| 二画面を使わせない | FrontEnd の設定 `createShell(要素, {dual: false})`（[5.3](#53-二画面の枠-createshell要素)） |

- 知らないコマンドの `id`・変えられない項目・予約のキー（F5・Enter など）・ブラウザが譲らないキー（Ctrl+W など）・キーの重なりは、起動時のエラーになる
- 切り取り・コピー・貼り付けは、API から見ればどれも同じ操作（移す・写す）を別の入口から呼ぶもの。止めるときは関わるコマンドを全部止める（例: 移動を止めるなら `cut`・`drop-move`）

## 3. 使いかた A: API だけを呼ぶ

API の細部は API 設計（Wiki: /Design/API） にあります。ここでは組み込むときに要ることだけを書きます。

### 3.1 共通の決まり

| 項目 | 決まり |
|---|---|
| 場所 | `/api/v1/…` |
| 対象の指定 | `mount`（マウントの `id`）と `path`・`paths`（パス。根は `/`）。**URL のパス部分には入れず**、クエリか JSON の本文で渡す（例外はファイルの中身の URL `GET /api/v1/raw/<マウント>/<パス>`） |
| 読み取り | `GET`。引数はクエリ |
| 操作 | コマンド API `POST /api/v1/commands/<id>`。本文は JSON。ヘッダ `X-WebFileDir: 1` と `Content-Type: application/json` が要る |
| パスの規則 | `..`・`.`・空の要素（`//` や末尾の `/`）・NUL を含むものは直さずに 400 `bad_path` |
| 日時 | UNIX 時刻（秒、小数あり） |
| エラー | `{"error": {"code", "message", "path"}}`。`code` は失敗の種類（`not_found`・`exists`・`forbidden` など）、`message` は操作者が読む文 |

### 3.2 API の一覧

| 分類 | API |
|---|---|
| 読み取り | `GET mounts`（マウントの一覧と、コマンドの宣言）・`list`（フォルダの中身）・`tree`（ツリーの 1 段）・`stat`（項目 1 つ）・`trash`（ごみ箱の中身） |
| 操作（作成・名前の変更・削除・コピー・移動・ごみ箱・開く・独自のコマンド） | コマンド API `POST commands/<id>` |
| アップロード | `POST commands/<id>/upload`（1 ファイル・1 フォルダずつ。本文はファイルの中身。API 設計の「アップロード」（Wiki: /Design/API#アップロード）） |
| ファイルの中身 | `GET raw/<マウント>/<パス>`（名前は 1 段ずつパーセント符号化。`?mode=download` で保存として） |
| 自動更新 | `GET events`（Server-Sent Events。[3.5](#35-変化を知らせてもらう自動更新)） |
| ジョブ（時間のかかるコマンドの進み具合） | `GET jobs/<番号>`・`POST jobs/<番号>/cancel`（[3.3](#33-例)） |

### 3.3 例

```bash
S=http://127.0.0.1:8616/api/v1
H=(-H 'X-WebFileDir: 1' -H 'Content-Type: application/json')

# マウントの一覧（できる操作は commands の宣言で分かる）
curl -s "$S/mounts"

# フォルダの中身
curl -s "$S/list?mount=docs&path=/2026"

# 新しいフォルダ（input を省くと「新しいフォルダ」「新しいフォルダ (2)」…）
curl -s -X POST "$S/commands/new-folder" "${H[@]}" -d '{"mount": "docs", "dir": "/2026", "input": "議事録"}'

# ごみ箱へ（完全に削除は commands/purge）
curl -s -X POST "$S/commands/delete" "${H[@]}" -d '{"mount": "docs", "paths": ["/2026/古い.txt"]}'

# 別のフォルダへ移動（コピーは mode を copy に）
curl -s -X POST "$S/commands/paste" "${H[@]}" \
     -d '{"mount": "docs", "source": {"mount": "docs", "paths": ["/2026/a.txt"], "mode": "cut"}, "dest": {"mount": "docs", "path": "/2027"}}'
```

- パスに日本語や空白を含めるときは、クエリでは URL の符号化をする（curl なら `--get --data-urlencode "path=/資料 2026"`）
- 宣言されていない（止めた・読み取り専用の）コマンドは 403 `forbidden`
- **宣言の `job` が `true` のコマンド（削除・貼り付けなど、項目をまとめて扱うもの）は、すぐに `{"job": 番号}` だけを返す。**結果は `GET jobs/<番号>` を `state` が `done` になるまで問い合わせて受け取る（`result` か `error`）。中止は `POST jobs/<番号>/cancel`
- コマンドが状態表示のダイアログの「はい・いいえ」（`effects` の `modal` で `type` が `yesno`）を返したら、答えを本文の `answers.<data.answer>` に `"yes"` か `"no"` で入れて、同じコマンドを送り直す
- 複数の項目を扱うコマンドは、`paths` に並べた順に処理する（FrontEnd は、操作者が見ている一覧の並び順で送る）

### 3.4 一括の結果と名前の衝突

- 削除・貼り付け・元に戻すなどは **1 件の失敗で止めず**、項目ごとの結果（一括の結果）を返す: `{"results": [{"src" | "id", "ok", "entry" | "error", …}]}`
- 名前の衝突（作る・変える名前の項目が既にあること）は、本文の `answers.onConflict` で扱いを決める: `"error"`（既定。`exists` で失敗にする）/ `"rename"`（「名前 (2)」にする）/ `"skip"` / `"overwrite"`（**ファイルだけ**。置き換えられるほうは消さずにごみ箱へ移す）
- FrontEnd と同じように尋ねたいときは、まず `answers` を省いて送り、`exists` になった項目だけを選ばれた値で送り直す
- ごみ箱へ移した項目の結果には `trashId` が付く（`commands/restore` の `ids` に渡すと元に戻せる）

### 3.5 変化を知らせてもらう（自動更新）

見張ってほしいフォルダを渡すと、変わったときに知らせます（Linux の inotify を使う。問い合わせの繰り返しはしない）。

```
GET /api/v1/events?targets=[{"mount":"docs","path":"/2026"},{"mount":"docs","trash":true}]
```

| 受け取るイベント | 中身 | 意味 |
|---|---|---|
| `ready` | `{"watching": [...]}` | 見張り始めた。実際に見張れた対象だけが入る |
| `change` | `{"mount", "path"}` か `{"mount", "trash": true}` | そのフォルダ（ごみ箱）が変わった。読み直す |
| `unavailable` | `{"message"}` | この環境では見張れない（Linux 以外など）。繋ぎ直さないこと |

- `targets` は JSON の配列で、1 つの接続で 256 個まで。短い間に続いた変化は 0.2 秒ごとにまとめて知らせる
- 切れたら 3 秒後に繋ぎ直すよう `retry: 3000` を送る。**繋ぎ直したら、切れていたあいだの変化は知らされないので、一度読み直す**
- 接続を開いたままにするので、BackEnd は要求ごとにスレッドを立てるサーバで動かす（`run.py` はそうしている）

## 4. 使いかた B: FrontEnd を iframe で埋め込む

### 4.1 埋め込みかた

```html
<iframe src="/files/#/docs/2026" title="ファイル" style="width: 100%; height: 600px; border: 0;"></iframe>
```

- FrontEnd の大きさは `<iframe>` の大きさに合わせる。二画面モードは幅が 1100px を超える横長なら左右、それ以外は上下に並ぶ
- キー操作（Delete・F2・Ctrl+C など）は、**FrontEnd の中にフォーカスがあるときだけ**効く
- 操作を止める・変えるのは BackEnd の設定（[2.5](#25-操作を止める変える)）

### 4.2 開く場所を URL で指定する

| URL のハッシュ | 開く場所 |
|---|---|
| （無し） | 最初のマウントの根 |
| `#/docs` | マウント `docs` の根 |
| `#/docs/2026/議事録` | マウント `docs` の `/2026/議事録`（各要素は URL の符号化をする） |
| `#trash/docs` | マウント `docs` のごみ箱 |

### 4.3 組み込む側とぶつかりうること

- **ブラウザの履歴**: FrontEnd の中で移動するたびに `<iframe>` の中のハッシュが変わり、ブラウザの履歴に入る。利用する側のページで［戻る］を押すと、先に `<iframe>` の中の移動が戻る
- **ブラウザに覚えるもの**: `localStorage` に `webfiledir.` で始まるキー（`view`・`sort`・`trashSort`・`showHidden`・`clipboard`・`dual`・`columnWidths`）、`sessionStorage` に `webfiledir.secondPane`。利用する側と同じオリジンで配ると、同じ場所に入る（名前が重ならなければ問題ない）
- **別のオリジンで配るとき**: FrontEnd の中の要求は webFileDir 自身のオリジンから送られるので確認は通る。ただし、利用する側と webFileDir の間で `localStorage` は共有されない

## 5. 使いかた C: FrontEnd を JS の部品として組み込む

### 5.1 読み込むもの

```html
<link rel="stylesheet" href="/files/static/css/app.css">
<div id="files" style="height: 600px"></div>
<script type="module">
  import { createApp } from "/files/static/js/main.js";
  const app = createApp(document.getElementById("files"), {
    router: "memory",                      // 利用する側のページのハッシュを使わない
    storageKey: "myportal.files.location", // 今の場所を覚える sessionStorage のキー
    paneId: "files",
  });
  // あとで外すとき: app.destroy()
</script>
```

- 置く要素には **高さを付ける**（FrontEnd は要素いっぱいに広がる）。ビルドは要らない（素の ES モジュール）

### 5.2 createApp(要素, 設定) の設定

| 設定 | 既定 | 意味 |
|---|---|---|
| `router` | `"hash"` | `"hash"` は URL のハッシュとブラウザの履歴を使う。**組み込むときは `"memory"`**（FrontEnd の中だけで戻る・進むを持つ） |
| `storageKey` | `"webfiledir.pane"` | `router: "memory"` のとき、今の場所を覚える `sessionStorage` のキー。1 つのページに複数置くなら別々にする |
| `fallbackLocation` | `() => null` | `router: "memory"` で覚えた場所が無いときの最初の場所（`{mount, path, trash}` を返す関数） |
| `paneId` | `"main"` | 画面 1 つ分の名前。1 つのページに複数置くなら別々にする |
| `dialogHost` | `true` | `false` なら確認のダイアログの置き場所にしない（あとで外すことのある画面） |
| `onToggleDual` | 無し | 渡すとツールバーに［二画面］を出し、押されたら呼ぶ |
| `onOpenInOther` | 無し | 「隣の画面で開く」のとき `(mount, path)` で呼ぶ。無ければ「隣の画面で開けません」と知らせる |
| `focus` | `true` | `false` なら作った直後に一覧へフォーカスを移さない |
| `folderUpload` | `true` | `false` ならフォルダごとのアップロードをさせない（[5.3](#53-二画面の枠-createshell要素)） |

戻り値は `{store, actions, destroy}`。`destroy()` は自動更新の接続とリスナーを外し、要素を空にする。操作を止めるのは BackEnd の設定（[2.5](#25-操作を止める変える)）。

### 5.3 二画面の枠 createShell(要素)

- `static/js/shell.js` の `createShell(要素, {dual, folderUpload})` は、`createApp` を 1 つか 2 つ並べる枠（`index.html` が使っているもの）。**`dual: false` で［二画面］を出さない**
- **`folderUpload: false` で、フォルダごとのアップロード（フォルダのドロップ・アップロードのダイアログの［フォルダを選ぶ］）をさせない**（ファイルだけ送れる。2026-10-03 設計者の指示「フォルダごとの可否は FrontEnd の設定オプションで変更できるように」）。見せかたの切り替えで、BackEnd の制限ではない（フォルダを作る・ファイルを送るを、それぞれ BackEnd が許していれば API からはできる）。`createApp` の設定にも同じ `folderUpload` がある
- **左の画面はハッシュを使う**ので、組み込むときはハッシュを使わない構成（`createApp` を 2 つ、どちらも `router: "memory"`）のほうが安全
- 同じページにある画面どうしは、ドラッグ＆ドロップ・クリップボード・変更の知らせを共有する

### 5.4 組み込んだページとぶつからないようにしてあること

| 対象 | どうしてあるか |
|---|---|
| CSS | すべて `.fd-` で始まるクラスの下に閉じている。色は `.fd-app` に付けた CSS 変数（`--fd-…`）で、上書きして変えられる |
| キー操作 | FrontEnd の中にフォーカスがあるときだけ受ける |
| URL | API・アイコン・CSS は相対 |
| 覚えるもの | `localStorage` のキーに `webfiledir.` を付ける。読み書きできなくても動く |
| ページ全体に触れるもの | アイコンのスプライトを `body` の先頭に 1 つ埋め込む（`id="fd-icon-sprite"`）。変更の知らせに `window` の `webfiledir:changed` イベントを使う。右クリックメニューを開いているあいだだけ `document` にリスナーを付ける |

### 5.5 いまの制約

- **API の場所は、利用する側のページの URL（`document.baseURI`）から相対で `api/v1/` と決まる。**利用する側のページを webFileDir と同じパスの下に置く（リバースプロキシで）か、`<base href="/files/">` を書く（`examples/component.html` はこの形）
- **同じオリジンで配る必要がある。**webFileDir は CORS のヘッダを返さない
- 自動更新の接続は、同じ接続先を開いているタブ全体で 1 本にまとめる（1 つのページに複数置いても、タブを増やしても 1 本）。見えていないタブは 30 秒たつと見張りから外れる。**ただし `http://` の LAN のアドレスのように、ブラウザが安全とみなさないオリジンではタブをまたいでまとめられず、見えているページごとに 1 本になる**（https か localhost で配れば 1 本）

## 6. BackEnd を Python（WSGI）のプログラムに組み込む（D）

```python
from server.app import create_app
from server.config import load_config, prepare_mounts

config = load_config("webfiledir.toml")
prepare_mounts(config)          # 根を用意し、安全に使えるか確かめる（使えなければ ConfigError）
files = create_app(config)      # WSGI アプリ

def app(environ, start_response):   # 自分の WSGI アプリ
    path = environ.get("PATH_INFO", "")
    if path.startswith("/files/"):
        # 前置きを SCRIPT_NAME へ移して渡す（WSGI の決まり）
        environ = dict(environ, SCRIPT_NAME=environ.get("SCRIPT_NAME", "") + "/files", PATH_INFO=path[6:])
        return files(environ, start_response)
    ...
```

- 全体は `examples/embed_server.py`（`/files` → `/files/` の転送と、スレッドを立てるサーバでの起動まで）
- **自動更新の接続を開いたままにするので、要求ごとにスレッドを立てる（か非同期の）サーバ** で動かす。`server/httpserver.py` の `ThreadingWSGIServer` が使える。そうできないなら `create_app(config, live_updates=False)`
- `prepare_mounts` を呼ばずに `create_app` だけを使うと、根の持ち主などの確かめを飛ばすことになる
- `create_app` にも、7 章の `authorize`・`mount_access`・`live_updates` と、8 章の `providers=` を渡せる

## 7. bottle で作ったシステムに組み込む（E）

利用する側のシステムが bottle で作られているときの方法です。**webFileDir を利用する側のアプリの中に組み込む**ので、webFileDir 用のポートを開かずに済み、要求は必ず利用する側のアプリを通ります。

### 7.1 最小の形

```python
import bottle
from server.embed import mount_webfiledir
from server.httpserver import ThreadingServer

app = bottle.Bottle()          # 利用する側のアプリ（既にあるもの）

mount_webfiledir(app, "/files/", "webfiledir.toml")

bottle.run(app, server=ThreadingServer, host="127.0.0.1", port=8080)
```

- FrontEnd は `/files/`、API は `/files/api/v1/…` になる。`/files` で来たら `/files/` へ転送する
- `mount_webfiledir` は根の持ち主などを確かめてから組み込む（使えなければ `ConfigError`）
- 設定ファイルの `[server]` の `host`・`port` は使わない（待ち受けは利用する側のもの）。`allowed_origins` は Origin の確認に使う
- 利用する側の bottle のプラグインやフックは、webFileDir のルートには効かないことがある（bottle の `mount` の決まり）。認証・認可は次の 2 つの引数で渡す

### 7.2 利用する側の認証をつなぐ（authorize）

```python
def authorize(request):
    if current_user(request) is not None:     # 利用する側のログインの仕組み
        return True
    if "/api/" in request.path:
        return False                           # API は 403（JSON のエラー）
    bottle.redirect("/login")                  # FrontEnd はログインへ

mount_webfiledir(app, "/files/", "webfiledir.toml", authorize=authorize)
```

| 返しかた | どうなるか |
|---|---|
| `True`（か `None`） | そのまま通す |
| `False` | 403。API なら `{"error": {"code": "forbidden", …}}`、FrontEnd・静的ファイルなら 403 のページ |
| `bottle.HTTPResponse` を投げる（`bottle.redirect(…)`・`bottle.abort(401)` など） | それを返す |

- **FrontEnd・静的ファイル・API・自動更新のすべての要求**で呼ぶ
- FrontEnd の中からの API の呼び出しと自動更新は、同じオリジンなのでクッキーが自動で付く

### 7.3 人ごとにマウントとコマンドを分ける（mount_access）

```python
def mount_access(request, mount_id):
    user = current_user(request)
    if user.is_admin:
        return "rw"                                          # 読み書き
    if mount_id == "docs":
        return {"access": "rw", "disable": ["purge", "trash-empty"]}   # 元に戻せない操作だけ止める
    return "ro" if mount_id == "pub" else None               # pub は読み取りのみ、ほかは見せない

mount_webfiledir(app, "/files/", "webfiledir.toml", authorize=authorize, mount_access=mount_access)
```

| 返す値 | 意味 |
|---|---|
| `"rw"` | 読み書き（設定で `readonly = true` のマウントは読み取りのみのまま） |
| `"ro"` | 読み取りのみ。変更のコマンドを宣言しない（FrontEnd に出ず、直接呼んでも 403） |
| `None` | 見せない。マウントの一覧に出さず、そのマウントへの要求は 404 `not_found`（あることも知らせない）。自動更新でも見張らない |
| `{"access": "rw" \| "ro", "disable": [コマンドの id…]}` | その人には、並べたコマンドを出さない（直接呼んでも 403）。見せかたを人ごとに変えることはできない |

- ほかの値・知らないコマンドの `id` を返すのは利用する側の誤りとして 500 にする（中身はログへ）
- 要求ごとに呼ぶので、重い処理（データベースの問い合わせなど）は利用する側でまとめる

### 7.4 ジョブの中では bottle.request を使えない

時間のかかるコマンド（ジョブ）は、BackEnd が別のスレッドで行います。**そのスレッドには、ジョブを始めた要求の `contextvars` が引き継がれますが、`bottle.request`（スレッドごとの値）は引き継がれません。**プロバイダのメソッドの中で、誰の操作か・操作の記録などの要求の情報が要るなら、`authorize` や `mount_access`（要求ごとに呼ばれる）の中で `contextvars` に入れておき、プロバイダはそこから読みます。

### 7.5 利用する側が 1 本ずつ処理するサーバで動いているとき

bottle の既定のサーバ（`bottle.run(app)` の wsgiref）は、要求を 1 本ずつ処理します。自動更新は接続を開いたままにするので、**そのあいだほかの要求が止まります。**要求ごとにスレッドを立てるサーバ（`server.httpserver.ThreadingServer` など）で動かすか、**`mount_webfiledir(…, live_updates=False)`** で自動更新を止めます（FrontEnd は F5 で読み直す）。

### 7.6 見本

`examples/bottle_host.py`: ログイン（見本なのでパスワードは確かめない）を持つ bottle のシステムに組み込み、`admin` は両方のマウントを読み書き、`guest` は `fdweb` を読み取りのみ・ほかは見せない。

```bash
uv run examples/bottle_host.py webfiledir.toml   # http://127.0.0.1:8080/
```

## 8. 自分のプロバイダを差し込む（仮想ファイル構造）

利用する側のシステムが持っている木（データベースのレコード、ネットワークの端末など）を、**webFileDir のコードを直さずに**フォルダとファイルとして見せる方法です。自分のプロバイダを書いて、BackEnd に差し込みます。**FrontEnd は変えません。**

```python
from server.app import create_app                 # bottle なら server.embed.mount_webfiledir も同じ引数
from server.config import ConfigError, load_config, prepare_mounts
from server.providers import Entry, Provider


class NotesProvider(Provider):
    capabilities = frozenset()                    # 読み取りだけ。書けるなら "mkdir" "touch" "rename" などを入れて実装する

    def __init__(self, db):
        self.db = db

    def stat(self, path):                         # path は名前の組（根は ()）。検査済み
        ...                                       # 無ければ raise ApiError("not_found", "見つかりません")

    def listdir(self, path):
        return [Entry(n.title + ".txt", "file", n.size, n.updated_at) for n in self.db.notes_in(path)]


def make_notes(m):                                # m は設定の [[mount]]（MountConfig）
    table = m.options.get("table")                # 共通の項目以外は options に入る
    if not isinstance(table, str):
        raise ConfigError("table は文字列で書いてください")   # 「マウント <id>: …」として起動を止める
    return NotesProvider(open_db(table))


config = load_config("webfiledir.toml")           # [[mount]] に type = "notes"、table = "…" と書く
prepare_mounts(config)
app = create_app(config, providers={"notes": make_notes})
```

| 決まり | 内容 |
|---|---|
| 作る関数 | `MountConfig`（設定の `[[mount]]` 1 つ分）を受け取り `Provider` を返す。設定の誤りは `ConfigError` で知らせる |
| 種類の名前 | 組み込みの `local`・`memory` は置き換えられない（`ValueError`）。知らない種類を `type` に書くと起動のときに `ConfigError` |
| 必ず書くプロバイダのメソッド | `stat`・`listdir`。ほかは機能名（`capabilities`）に入れたものだけ（入れた機能名に応じて、BackEnd が既定のコマンドを宣言する） |
| エラー | `ApiError("not_found" / "exists" / "bad_path" / …, 操作者が読む文)`。ほかの例外は 500 になり、中身はログにだけ出る |
| スレッド | 要求ごとにスレッドが立つので、共有している状態は錠で守る |
| 自動更新 | 変更がコマンド APIを通るなら何もしなくてよい。**API の外で変わったら `self.notify_changed()` を呼ぶ** |

- **構造に固有の操作は、独自のコマンドにする。**クラスの `commands` に `server.providers.Command` を並べ、`run_command(command_id, ctx)` で結果の語彙（`Navigate`・`Browse`・`Modal`・`Message`・`Reload`）を返す。`Modal` は状態表示のダイアログで、［OK］だけの型と［はい］［いいえ］の型（答えは `ctx.answers` に入って送り直される）がある。時間のかかるコマンドは `job=True` にすると、FrontEnd がプログレスバーを出す。使える部品は文字の入力（`prompt`）と確認（`confirm`）。**見本は `examples/custom_commands.py`**（`uv run examples/custom_commands.py` で 8617 番に立つ）
- **既定のコマンドを、構造の言葉にする・止める・ジョブにする**: `command_overrides`（ラベル・キー・出す場所・知らせの文・`job`）、`disable_commands`。名前の変更のように 1 件でも時間がかかる構造なら、`{"rename": {"job": True}}` でジョブにし、メソッドの中から `server.jobs` の `add_total`・`begin`・`advance` で段階を数え、`cancelled()` で中止を確かめる（中止したら `ApiError("cancelled", 文)`）。ジョブの中では `bottle.request` は使えない（[7.4](#74-ジョブの中では-bottlerequest-を使えない)）
- **項目ごとの権限**（`Entry.auth`: 8 = 動かす・4 = 読む・2 = 書く・1 = 実行）、**拡張子**（`Entry.ext`。名前の `.` が拡張子を意味しない構造なら `""`）、**アイコン**（`icons`・`Entry.icon`・`mount_icon`）、**詳細表示の列**（`attributes`）もプロバイダが決める
- **マウントをまたぐコピー・移動**（実ファイル ↔ 差し込んだ構造）と**アップロード**をさせるなら、機能名に `"stream"` を入れて `open_read`・`write_file` を実装する（`write_file` の `mtime` は、更新日時を持たない構造なら無視してよい）
- プロバイダのメソッドごとの引数・戻り値・投げるエラーは、配布物の `server/providers/base.py` の説明と、見本の `server/providers/memory.py` にある

## 9. まだできないこと

| できないこと | 今の形 |
|---|---|
| 検索 | 無い。独自のコマンドで足せる見込み（作って確かめてはいない） |
| 消えない仮想の構造（SQLite など）の組み込みの種類 | 組み込みの種類はメモリ上のものだけ。**利用する側の構造なら 8 章で差し込める** |
| 利用する側からの要求だけを受け付ける仕組み（共有の秘密など） | 無い。**E なら要らない** |
| FrontEnd に組み込みの文（「このフォルダは空です」など）を構造ごとに変える | コマンドのラベル・知らせの文は変えられるが、それ以外は無い |

## 10. 関連ページ

- 設計の全体像（Wiki: /Design） … 構成、コマンド、プロバイダ、安全対策、設定
- コマンドの宣言（Wiki: /Design/Command） … 既定のコマンドの `id` と宣言の形
- API 設計（Wiki: /Design/API） … API の細部、エラーの種類、一括の結果、名前の衝突
- 画面設計（Wiki: /Design/Frontend） … FrontEnd の振る舞い、二画面モード、JS の部品分け
- プロバイダの作りかた（Wiki: /Design/Provider） … 自分の仮想ファイル構造と独自のコマンド
- サーバ側実装例（Wiki: /ServerSample） … BackEnd だけで機能を足す方法と実装例
