<!-- この文書は Wiki の「組み込みかた」（how_to_embed）から 2026-09-29T21:54:20+09:00 に作った。版 0.2.3+gfa1915d。直すときは Wiki を直して作り直す -->
# 組み込みかた

#note(type=warn,label="0.x の資料"){{
**これは 0.x（最後は 0.2.2）の資料です。**2026-09-29 に 1.0.0 の設計を始めるにあたり、ここ（`ver.0/`）へ移しました。以後は書き換えません。
1.0.0 の資料は トップ（Wiki: /） から辿ってください。
}}

**webFileDir を別のシステム（利用する側のシステム）に組み込んで使う方法**をまとめたページです。2026-09-26 時点の実装（`dev` ブランチ）に合わせて書いています。
このプログラムは **部品として使われることを前提にしていて、認証を持ちません**（認証と公開範囲（Wiki: /ver.0/Design#認証と公開範囲））。組み込む前に、まず「[2.3 安全のために必ずすること](#23-安全のために必ずすること)」を読んでください。


## 1. 全体の考えかた

### 1.1 組み込みかたは 5 通り

| 組み込みかた | 利用する側がすること | 向いている場面 |
|---|---|---|
| **A. API だけを呼ぶ** | 自分の画面やプログラムから JSON API を呼ぶ | 画面は自分で作り、ファイル操作だけを任せたい |
| **B. 画面を `<iframe>` で埋め込む** | 自分のページに `<iframe>` を置き、webFileDir の画面を出す | 画面ごと使いたい。いちばん手軽 |
| **C. 画面を JS の部品として組み込む** | 自分のページで CSS と ES モジュールを読み、`createApp(要素)` を呼ぶ | 自分のページの一部として、見た目やフォーカスを混ぜたい |
| **D. サーバを Python（WSGI）のプログラムに組み込む** | 自分の Python のプログラムで `create_app(設定)`（WSGI アプリ）を動かす | サーバの起動・止めかたを自分のシステムでまとめたい |
| **E. `bottle.py` で作ったシステムに組み込む** | 自分の bottle のアプリに `mount_webfiledir(アプリ, "/files/", 設定)` で組み込み、自分の認証・認可をつなぐ | 利用する側のシステムが bottle で、ログインや利用者を持っている |

どれを標準にするかは、まだ決めていません（ToDo の「決めていないこと」の 12（Wiki: /ver.0/ToDo#決めていないこと））。どれになっても直す範囲が小さくなるように作ってあります。

### 1.2 どれを選ぶか

1. 画面を自分で作るなら **A**
2. webFileDir の画面をそのまま使うなら、まず **B**（組み込む側とぶつかることが最も少ない）
3. B で足りない（ページの一部として混ぜたい）ときだけ **C**。今は **同じオリジンで配る必要がある** などの制約がある（[5.5 いまの制約](#55-いまの制約)）
4. A〜C のどれでも、サーバの動かしかたとして **D** を組み合わせられる
5. 利用する側のシステムが **`bottle.py` で作られているなら E**。同じプロセスの中に組み込むので、webFileDir への要求は必ず利用する側のアプリを通り、**利用する側の認証・認可を webFileDir の手前で効かせられる**（[2.3](#23-安全のために必ずすること) の 2.3.1・2.3.3 を、この形なら満たせる）

### 1.3 配置の例

```
ブラウザ ──> 利用する側のシステム（認証・認可）──> webFileDir（127.0.0.1:8616）
                  │ リバースプロキシ /files/ → webFileDir
                  └─ 自分のページ（<iframe src="/files/"> など）
```

- webFileDir は **利用する側のシステムからしか届かない場所**で待ち受ける（例: `127.0.0.1`）
- ブラウザは利用する側のシステムを通して webFileDir に届く（リバースプロキシ）。こうすると **同じオリジンになり**、C の制約も CSRF の確認（[2.3.2](#232-変更系の確認origin-と-allowed_origins)）も素直に満たせる

## 2. サーバを用意する

### 2.1 導入と起動

#### 配布物から導入する（組み込む人向け）

組み込むのに要るファイルを 1 つにまとめた配布物（`webfiledir-<版>.tar.gz` か `.zip`）があります。
GitHub のリリース（[yoshiyano/webFileDir の Releases](https://github.com/yoshiyano/webFileDir/releases)）から入手できます。リポジトリは非公開なので、見られるのはリポジトリに招かれた人だけです。`gh` を使うなら `gh release download v0.1.0 -R yoshiyano/webFileDir`。

```bash
tar xzf webfiledir-0.1.0+g1eb1c58.tar.gz     # zip なら unzip
cd webfiledir-0.1.0+g1eb1c58
sha256sum -c ../webfiledir-0.1.0+g1eb1c58.SHA256SUMS   # 配布物が壊れていないか（任意）
uv sync                                      # uv を使わないなら pip install -r requirements.txt
cp webfiledir.example.toml webfiledir.toml   # 直す（下の 2.2）
uv run run.py
```

| 配布物の中身 | 何か |
|---|---|
| `server/`・`static/`・`run.py` | サーバと画面（画面側のテスト用のページは入れていない） |
| `webfiledir.example.toml` | 設定の見本 |
| `pyproject.toml`・`uv.lock`・`requirements.txt` | 依存（bottle だけ） |
| `EMBED.md` | このページを配布物の中で読めるようにしたもの（作るたびにこのページから起こす） |
| `examples/iframe.html` | 組み込みかた B の例 |
| `examples/component.html` | 組み込みかた C の例（`<base>` で API の場所を合わせる形） |
| `examples/nginx.conf` | リバースプロキシの例（2.4） |
| `examples/embed_server.py` | 組み込みかた D の例（bottle を使わない WSGI のプログラムの `/files/` の下に置く） |
| `examples/bottle_host.py` | 組み込みかた E の例（ログインを持つ bottle のシステムに組み込み、人ごとに読み書き・読み取りのみ・見せないを分ける） |
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
- 設定に知らない項目があっても起動しない（打ち間違いを黙って無視しないため）
- **同じポートで webFileDir が先に動いていたら、それを止めてから起動する**（入れ替わる。「ポート 8616 で動いていた webFileDir（pid …）を止めました」と出る）。止めるのは、同じアカウントで動いている webFileDir の `run.py` だけ。**別のプログラムがポートを使っていれば止めずに**「webFileDir でないプログラムが使っています（pid …: コマンド）」で終わる。修正後の起動し直しは、もう一度 `run.py` を起動するだけでよい
- 端末を閉じても動き続けるようにするなら、端末から切り離して起動する: `setsid nohup ./run.py >> log/webfiledir.log 2>&1 < /dev/null &`（`log/` は git の対象外）

### 2.2 設定ファイル（TOML）

```toml
[server]
host = "127.0.0.1"
port = 8616
allowed_origins = ["https://portal.example.lan"]

[[mount]]
id = "docs"
type = "local"
root = "/srv/share/docs"
label = "共有資料"
readonly = false
# trash = "/srv/share/docs/.fdweb-trash"
```

#### [server] の項目

| 項目 | 既定 | 意味 |
|---|---|---|
| `host` | `127.0.0.1` | 待ち受けるアドレス。**組み込むときは利用する側からしか届かないアドレスにする**（[2.3.1](#231-利用する側からしか届かないようにする)） |
| `port` | `8616` | 待ち受けるポート |
| `allowed_origins` | `[]` | 変更系 API を許す、利用する側のページのオリジン（`https://host:port` の形）。[2.3.2](#232-変更系の確認origin-と-allowed_origins) |

#### [[mount]] の項目（1 つ以上。画面と API で選べる「根」）

| 項目 | 既定 | 意味 |
|---|---|---|
| `id` | （必須） | URL・API での識別子（**画面の表示には使わない**。表示は `label`）。英数字・`_`・`-` の 1〜64 文字。重ならないこと |
| `type` | （必須） | プロバイダの種類。`local`（実ファイル）か `memory`（メモリ上の仮想構造。**サーバを止めると中身は消える**） |
| `root` | `local` では必須 | 根にする実フォルダ（絶対パス）。`memory` には書けない |
| `label` | `(root)` | 画面に出す名前（ツリー・アドレスバーなど）。**`id` は画面の表示に使わない**（URL・API・アドレスバーに打ち込むときの識別子）。`label` を書かないマウントが 2 つ以上あると、どれも `(root)` と出て見分けられないので、書いておく |
| `readonly` | `false` | `true` なら変更系 API をすべて 403 にする（ごみ箱の中を見ることはできる） |
| `trash` | 根の直下の `.fdweb-trash` | ごみ箱の置き場所（絶対パス）。根と同じファイルシステムに置く（別だとごみ箱へ移せない） |

- 同じフォルダを、書き込めるマウントと読み取り専用のマウントの 2 つにしてもよい（利用する側が、人によってどちらを見せるか選べる）

### 2.3 安全のために必ずすること

**webFileDir は誰が要求したかを確かめません。**届いた要求は、サーバを動かしているアカウントの権限でそのまま実行します。

#### 2.3.1 利用する側からしか届かないようにする

- `host = "127.0.0.1"` にして同じ機械のリバースプロキシから通す、または利用する側からしか届かないネットワークで待ち受ける
- **この形にするまで、消えて困るフォルダをマウントしない**（検証中は `/tmp/fdweb` を使っている）
- 共有の秘密をヘッダで確かめる仕組みなど、ほかの方法はまだ作っていない（決めていないこと（Wiki: /ver.0/ToDo#決めていないこと） の 10）
- **利用する側のシステムが bottle で作られているなら、組み込みかた E で満たせる**（同じプロセスに組み込み、webFileDir 用のポートを開かない。[7 章](#7-bottle-で作ったシステムに組み込むe)）

#### 2.3.2 変更系の確認（Origin と allowed_origins）

変更系 API（`POST`）は次を満たさないと拒否します（別サイトのページから操作を送られる CSRF を防ぐため）。

| 確認 | 満たさないとき |
|---|---|
| ヘッダ `X-WebFileDir: 1` がある | 400 `bad_request` |
| `Content-Type: application/json` | 400 `bad_request` |
| `Origin` ヘッダがあるなら、**サーバから見た自分自身**（`http://` + 要求の `Host`）か `allowed_origins` のどれか | 403 `bad_origin` |

- **`Origin` の無い要求（ブラウザではないプログラム）は通す。**CSRF はブラウザでだけ起きるため
- リバースプロキシの外側が `https://` だと、ブラウザが付ける `Origin`（`https://…`）は、サーバから見た自分自身（`http://…`）と一致しない。**外から見えるオリジンを `allowed_origins` に書く**
- プロキシは `Host` ヘッダをそのまま渡すか、外から見えるオリジンを `allowed_origins` に書く

#### 2.3.3 誰に何を見せるか（認可）は利用する側で

- webFileDir はマウント単位でしか分けられない。**人ごとに見せるマウントを変えるのは利用する側の仕事**（例: プロキシで API の `mount` を確かめる、人ごとに別のサーバを立てる）
- 認可の結果を webFileDir へどう伝えるかは、まだ決めていない（決めていないこと（Wiki: /ver.0/ToDo#決めていないこと） の 11）
- **組み込みかた E なら、`mount_access` で人ごとにマウントを「読み書き・読み取りのみ・見せない」に分けられる**（[7.3](#73-人ごとにマウントを分けるmount_access)）

#### 2.3.4 守りとして入っているもの

- 組み立てたパスを realpath で解決し、**マウントの根の外へは出ない**（`..`、根の外を指すシンボリックリンク）
- 名前の変更・削除・移動はシンボリックリンクを辿らない（リンクを消してもリンク先は残る）
- 削除は既定で**ごみ箱へ**（完全に削除は `permanent: true` のときだけ）
- 詳しくは 設計の全体像の安全対策（Wiki: /ver.0/Design#安全対策）

### 2.4 リバースプロキシの下に置く

画面と API の URL は **`index.html` からの相対** なので、`/files/` のような別のパスの下にそのまま置けます。

```nginx
location /files/ {
    proxy_pass http://127.0.0.1:8616/;   # 末尾の / で /files/ を取り除いて渡す
    proxy_set_header Host $host;
    # 自動更新（Server-Sent Events）の接続を溜めずに流し、開いたままにする
    proxy_buffering off;
    proxy_read_timeout 1h;
}
```

- 自動更新の応答には `X-Accel-Buffering: no` を付けているので nginx は溜めないが、ほかのプロキシでは **応答を溜めない設定** が要る
- 自動更新の接続には 20 秒ごとに空の行を送る。プロキシの無通信の制限は 20 秒より長くする
- 静的ファイルには `Cache-Control: no-cache` を付けている（更新した画面がすぐ届くように）。プロキシでキャッシュさせない

## 3. 使いかた A: API だけを呼ぶ

API の一覧と細部は API 設計（Wiki: /ver.0/Design/API） が正です。ここでは組み込むときに要ることだけを書きます。

### 3.1 共通の決まり

| 項目 | 決まり |
|---|---|
| 場所 | `/api/v1/…` |
| 対象の指定 | `mount`（マウント名）と `path`（`/` で始まるパス。根は `/`）。**URL のパス部分には入れず**、クエリか JSON 本文で渡す（例外は中身の URL `GET raw/<マウント>/<パス>`） |
| 読み取り | `GET`。引数はクエリ |
| 変更 | `POST`。本文は JSON。ヘッダ `X-WebFileDir: 1` と `Content-Type: application/json` が要る |
| パスの規則 | `..`・`.`・空の要素（`//` や末尾の `/`）・NUL を含むものは直さずに 400 `bad_path` |
| 日時 | UNIX 時刻（秒、小数あり） |
| エラー | `{"error": {"code", "message", "path"}}`。種類は API 設計のエラーの形（Wiki: /ver.0/Design/API#エラーの形） |

### 3.2 API の一覧

| 分類 | API |
|---|---|
| 読み取り | `GET mounts`・`list`・`tree`・`stat` |
| 作成・名前の変更・削除 | `POST mkdir`・`touch`・`rename`・`delete` |
| コピー・移動 | `POST copy`・`move`（`destMount` を渡すとマウントをまたぐ） |
| ごみ箱 | `GET trash`、`POST trash/restore`・`trash/purge`・`trash/empty` |
| 自動更新 | `GET events`（Server-Sent Events。[3.5](#35-変化を知らせてもらう自動更新)） |
| 開く | `POST open`（開く経路を選び、画面がすること（ページへ移る / モーダル）を返す）、`GET raw/<マウント>/<パス>`（中身。名前は 1 段ずつパーセント符号化。`?mode=download` で保存として。sandbox 付き） |

### 3.3 例

```bash
S=http://127.0.0.1:8616/api/v1

# マウントの一覧（できる操作 capabilities も分かる）
curl -s "$S/mounts"

# フォルダの中身
curl -s "$S/list?mount=docs&path=/2026"

# 新しいフォルダ（name を省くと「新しいフォルダ」「新しいフォルダ (2)」…）
curl -s -X POST "$S/mkdir" -H 'X-WebFileDir: 1' -H 'Content-Type: application/json' \
     -d '{"mount": "docs", "parent": "/2026", "name": "議事録"}'

# ごみ箱へ（permanent: true なら完全に削除）
curl -s -X POST "$S/delete" -H 'X-WebFileDir: 1' -H 'Content-Type: application/json' \
     -d '{"mount": "docs", "paths": ["/2026/古い.txt"]}'
```

- パスに日本語や空白を含めるときは、クエリでは URL の符号化をする（curl なら `--get --data-urlencode "path=/資料 2026"`）

### 3.4 一括の結果と名前の衝突

- `delete`・`copy`・`move`・`trash/restore` などは **1 件の失敗で止めず**、項目ごとの結果を返す: `{"results": [{"src", "ok", "entry" | "error", …}]}`
- `copy`・`move`・`trash/restore` の `onConflict`: `"error"`（既定。`exists` で失敗にする）/ `"rename"`（「名前 (2)」にする）/ `"skip"` / `"overwrite"`（**ファイルだけ**。置き換えられるほうは消さずにごみ箱へ移す）
- 画面と同じように尋ねたいときは、まず `onConflict` を省いて送り、`exists` になった項目だけを選ばれた値で送り直す
- `delete` でごみ箱へ移した項目の結果には `trashId` が付く（`trash/restore` に渡すと元に戻せる）

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
- 切れたら 3 秒後に繋ぎ直すよう `retry: 3000` を送る（ブラウザの `EventSource` はこれに従う）。**繋ぎ直したら、切れていたあいだの変化は知らされないので、一度読み直す**
- 見張る対象を変えるときは、新しい接続の `ready` を受けてから古い接続を閉じると取りこぼさない（画面の `live.js` がそうしている）
- サーバは要求ごとにスレッドを立てるサーバで動かす（`run.py` はそうしている）。1 本ずつしか処理しないサーバだと、開いたままの接続でほかの要求が止まる

## 4. 使いかた B: 画面を iframe で埋め込む

### 4.1 埋め込みかた

```html
<iframe src="/files/#/docs/2026" title="ファイル" style="width: 100%; height: 600px; border: 0;"></iframe>
```

- 画面の大きさは `<iframe>` の大きさに合わせる。二画面モードは幅が 1100px を超える横長なら左右、それ以外は上下に並ぶ
- キー操作（Delete・F2・Ctrl+C など）は、**画面の中にフォーカスがあるときだけ**効く

### 4.2 開く場所を URL で指定する

| URL のハッシュ | 開く場所 |
|---|---|
| （無し） | 最初のマウントの根 |
| `#/docs` | マウント `docs` の根 |
| `#/docs/2026/議事録` | マウント `docs` の `/2026/議事録`（各要素は URL の符号化をする） |
| `#trash/docs` | マウント `docs` のごみ箱 |

### 4.3 画面の機能を止める（?disable=）

```html
<iframe src="/files/?disable=rename,delete,dnd#/docs/2026" title="ファイル" style="width: 100%; height: 600px; border: 0;"></iframe>
```

- `?disable=` に、止める機能の名前を `,` で区切って並べる（名前は [5.6](#56-画面の機能を止めるfeatures)）。クエリはハッシュ（`#…`）より前に書く
- 知らない名前を書くと、画面を出さずに誤りを見せる
- **画面で出さないだけで、API は止めない。**URL を書き換えれば元に戻せるので、アクセスの制限には使えない（[5.6](#56-画面の機能を止めるfeatures)）

### 4.4 組み込む側とぶつかりうること

- **ブラウザの履歴**: 画面の中で移動するたびに `<iframe>` の中のハッシュが変わり、ブラウザの履歴に入る。利用する側のページで［戻る］を押すと、先に `<iframe>` の中の移動が戻る
- **ブラウザに覚えるもの**: `localStorage` に `webfiledir.` で始まるキー（`view`・`sort`・`trashSort`・`showHidden`・`clipboard`・`dual`）、`sessionStorage` に `webfiledir.secondPane`。利用する側と同じオリジンで配ると、同じ場所に入る（名前が重ならなければ問題ない）
- **別のオリジンで配るとき**: 画面の中の変更系は webFileDir 自身のオリジンから送られるので確認は通る。ただし、利用する側と webFileDir の間で `localStorage` は共有されない

## 5. 使いかた C: 画面を JS の部品として組み込む

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

- 置く要素には **高さを付ける**（画面は要素いっぱいに広がる）
- ビルドは要らない。素の ES モジュール

### 5.2 createApp(要素, 設定) の設定

| 設定 | 既定 | 意味 |
|---|---|---|
| `router` | `"hash"` | `"hash"` は URL のハッシュとブラウザの履歴を使う。**組み込むときは `"memory"`**（画面の中だけで戻る・進むを持つ） |
| `storageKey` | `"webfiledir.pane"` | `router: "memory"` のとき、今の場所を覚える `sessionStorage` のキー。1 つのページに複数置くなら別々にする |
| `fallbackLocation` | `() => null` | `router: "memory"` で覚えた場所が無いときの最初の場所（`{mount, path, trash}` を返す関数）。`null` なら最初のマウントの根 |
| `paneId` | `"main"` | 画面の名前。1 つのページに複数置くなら別々にする |
| `dialogHost` | `true` | `false` なら確認のダイアログの置き場所にしない（あとで外すことのある画面） |
| `onToggleDual` | 無し | 渡すとツールバーに［二画面］を出し、押されたら呼ぶ |
| `focus` | `true` | `false` なら作った直後に表示へフォーカスを移さない |
| `features` | `{}`（すべて ON） | 画面の機能の ON/OFF `{機能の名前: false, …}`。[5.6](#56-画面の機能を止めるfeatures) |

戻り値は `{store, actions, destroy}`。`destroy()` は自動更新の接続とリスナーを外し、要素を空にする。

### 5.3 二画面の枠 createShell(要素)

- `static/js/shell.js` の `createShell(要素, {features})` は、`createApp` を 1 つか 2 つ並べる枠（`index.html` が使っているもの）。`features` はどちらの画面にも同じものを渡す。**左の画面はハッシュを使う**ので、組み込むときはハッシュを使わない構成（`createApp` を 2 つ、どちらも `router: "memory"`）のほうが安全
- 同じページにある画面どうしは、ドラッグ＆ドロップ・クリップボード・変更の知らせを共有する

### 5.4 組み込んだページとぶつからないようにしてあること

| 対象 | どうしてあるか |
|---|---|
| CSS | すべて `.fd-` で始まるクラスの下に閉じている。色は `.fd-app` に付けた CSS 変数（`--fd-…`）で、上書きして変えられる |
| キー操作 | 画面の中にフォーカスがあるときだけ受ける |
| URL | API・アイコン・CSS は相対（アイコンは読み込んだモジュールの場所から決める） |
| 覚えるもの | `localStorage` のキーに `webfiledir.` を付ける。読み書きできなくても動く |
| ページ全体に触れるもの | アイコンのスプライトを `body` の先頭に 1 つ埋め込む（`id="fd-icon-sprite"`、見えない）。変更の知らせに `window` の `webfiledir:changed` イベントを使う。右クリックメニューを開いているあいだだけ `document` にリスナーを付ける |

### 5.5 いまの制約

- **API の場所は、利用する側のページの URL（`document.baseURI`）から相対で `api/v1/` と決まる。**利用する側のページが webFileDir と同じ場所（例: `/files/`）に無いと、API を見つけられない。今は次のどちらかが要る
    - 利用する側のページを、webFileDir と同じパスの下に置く（リバースプロキシで）
    - ページに `<base href="/files/">` を書く（ページのほかの相対 URL もすべて変わるので注意）
- **同じオリジンで配る必要がある。**ES モジュールを別のオリジンから読むには CORS が要るが、webFileDir は CORS のヘッダを返さない
- 1 つのページに複数置くと、それぞれが自動更新の接続を 1 本ずつ持つ（ブラウザの同じサーバへの同時接続数に注意。HTTP/1.1 では 6 本ほど）

API の場所を設定で渡せるようにする（例: `createApp(要素, {apiBase: "/files/api/v1/"})`）と、上の 1 つめの制約は無くせる。必要になったら足す。

### 5.6 画面の機能を止める（features）

```js
createApp(要素, { features: { rename: false, delete: false, dnd: false } });
```

書かなかった機能は ON。止めた機能は**ボタン・右クリックメニューに出さず**（灰色にもしない）、キー操作・ドラッグ＆ドロップも受け付けない。知らない名前や `true` / `false` 以外の値は `Error`（書き間違いで、止めたつもりの機能が出たままにならないように）。

| 名前 | 止めるもの |
|---|---|
| `newFolder` | 新しいフォルダ（ツールバー・右クリック・Ctrl+Shift+N） |
| `newFile` | 新しいテキスト ドキュメント（ツールバー・右クリック） |
| `rename` | 名前の変更（ツールバー・右クリック・F2） |
| `cut` | 切り取り（ツールバー・右クリック・Ctrl+X） |
| `copy` | コピー（ツールバー・右クリック・Ctrl+C） |
| `paste` | 貼り付け（ツールバー・右クリック・Ctrl+V、フォルダの右クリックの「このフォルダに貼り付け」） |
| `delete` | 削除（ツールバー・右クリックの「削除」・Delete・ツリーのごみ箱へのドロップ）。ごみ箱のあるマウントではごみ箱へ移す。ごみ箱の無いマウントでも「削除」の項目・ボタンを出すかはこれで決まる（実行できるかは `purge`） |
| `purge` | 完全に削除。右クリックの「完全に削除」・Shift+Delete、**ごみ箱の無いマウントでの削除**、ごみ箱の中の「完全に削除」「ごみ箱を空にする」。元に戻せない操作はすべてこれで止まる。ごみ箱の無いマウントでは、右クリックに「完全に削除」を出さない（「削除」と同じ動きになるため。0.2.3 から） |
| `trash` | ごみ箱。ツリーのごみ箱、元に戻す、削除の直後に出る［元に戻す］。`#trash/…` で直接来ても中身を見せない |
| `dnd` | ドラッグ＆ドロップ。この画面から運び出すことも、この画面へ落とすこともできない（二画面で隣の画面から運んできても落とせない） |
| `dual` | ［二画面］のボタン。`createShell` だけが見る（覚えていた二画面の状態も使わない） |

- 機能は独立している。たとえば `cut` だけを止めても、ドラッグ＆ドロップでの移動はできる（止めるなら `dnd` も）
- マウントの `capabilities` に無い操作は、今までどおり灰色（機能を ON にしていても、サーバができない操作はできない）

#### API は止めない

**これは画面の見せかたの設定で、アクセスの制限ではない。**画面が出さないだけで、API は受け付けたまま。開発者ツールで API を直接呼べば、止めた操作もできる。

API でも止める必要があるなら、組み込む側がサーバで止める。今あるのは、マウントごとに変更系をすべて止める設定の `readonly = true` と、人ごとの `mount_access`（`"ro"`、[7.3](#73-人ごとにマウントを分けるmount_access)）。

#### 操作ごとにサーバでも止めるときの案（まだ作っていない）

API をどう絞るかは組み込み先しだいなので、作らずに案だけ置く。

1. **`mount_access` の戻り値を広げる**（おすすめ）。`"rw"` / `"ro"` / `None` に加え、止める操作の集合（例: `{"deny": ["rename", "delete"]}`）を返せるようにする。サーバは
    - `GET mounts` の `capabilities` からその操作を除く（画面は今までどおり灰色にする）
    - 変更系 API の入口（`server/app.py` の `writable_mount`。今は `capabilities` に無い操作を拒否している）で、同じ集合を見て `forbidden` を返す

    人ごと・要求ごとに変えられ、画面と API で食い違わない。
2. **設定の `[[mount]]` に `deny = ["rename", …]` を書く**。マウントごとに固定でよいときの簡単な形。中身は 1 と同じく `capabilities` から除く。

どちらの案も、サーバが止めるのは **API の操作**（`mkdir`・`touch`・`rename`・`delete`・`trash`・`copy`・`move`）で、画面の機能とは 1 対 1 ではない。切り取り・コピー・貼り付け・ドラッグ＆ドロップは、どれも API から見れば `copy` か `move` なので、サーバは区別できない。「コピーはさせるがドラッグはさせない」のような区別は、画面の `features` で行う。

## 6. サーバを Python（WSGI）のプログラムに組み込む（D）

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
- **自動更新の接続を開いたままにするので、要求ごとにスレッドを立てる（か非同期の）サーバ** で動かす。`server/httpserver.py` の `ThreadingWSGIServer` が使える。そうできないなら `create_app(config, live_updates=False)` で自動更新を止める
- 画面の URL は相対なので、`/files/` のような前置きの下でもそのまま動く
- `prepare_mounts` を呼ばずに `create_app` だけを使うと、根の持ち主などの確かめを飛ばすことになる
- `create_app` にも、7 章の `authorize`・`mount_access`・`live_updates` を渡せる（bottle 以外のシステムでも、要求ごとの判断を差し込める）
- 自分の仮想ファイル構造を `providers=` で差し込める（[8 章](#8-自分のプロバイダを差し込む仮想ファイル構造)）

## 7. bottle で作ったシステムに組み込む（E）

利用する側のシステムが `bottle.py` で作られているときの方法です。**webFileDir を利用する側のアプリの中に組み込む**ので、webFileDir 用のポートを開かずに済み、要求は必ず利用する側のアプリを通ります。

### 7.1 最小の形

```python
import bottle
from server.embed import mount_webfiledir
from server.httpserver import ThreadingServer

app = bottle.Bottle()          # 利用する側のアプリ（既にあるもの）

mount_webfiledir(app, "/files/", "webfiledir.toml")

bottle.run(app, server=ThreadingServer, host="127.0.0.1", port=8080)
```

- 画面は `/files/`、API は `/files/api/v1/…` になる。`/files` で来たら `/files/` へ転送する
- `mount_webfiledir` は根の持ち主などを確かめてから組み込む（使えなければ `ConfigError`。起動時と同じ）
- 設定ファイルの `[server]` の `host`・`port` は使わない（待ち受けは利用する側のもの）。`allowed_origins` は変更系の Origin の確認に使う
- 利用する側の bottle のプラグインやフック（`before_request` など）は、webFileDir のルートには効かないことがある（bottle の `mount` の決まり）。認証・認可は次の 2 つの口で渡す

### 7.2 利用する側の認証をつなぐ（authorize）

```python
def authorize(request):
    if current_user(request) is not None:     # 利用する側のログインの仕組み
        return True
    if "/api/" in request.path:
        return False                           # API は 403（JSON のエラー）
    bottle.redirect("/login")                  # 画面はログインへ

mount_webfiledir(app, "/files/", "webfiledir.toml", authorize=authorize)
```

| 返しかた | どうなるか |
|---|---|
| `True`（か `None`） | そのまま通す |
| `False` | 403。API なら `{"error": {"code": "forbidden", …}}`、画面・静的ファイルなら 403 のページ |
| `bottle.HTTPResponse` を投げる（`bottle.redirect(…)`・`bottle.abort(401)` など） | それを返す |

- **画面・静的ファイル・API・自動更新のすべての要求**で呼ぶ（webFileDir のアプリに bottle のプラグインとして入れる）
- `request` は bottle の要求そのもの。クッキー（`request.get_cookie(…, secret=…)`）やヘッダで利用者を見分ける
- 画面の中からの API の呼び出しと自動更新は、同じオリジンなのでクッキーが自動で付く

### 7.3 人ごとにマウントを分ける（mount_access）

```python
def mount_access(request, mount_id):
    user = current_user(request)
    if user.is_admin:
        return "rw"                    # 読み書き
    return "ro" if mount_id == "docs" else None   # docs は読み取りのみ、ほかは見せない

mount_webfiledir(app, "/files/", "webfiledir.toml", authorize=authorize, mount_access=mount_access)
```

| 返す値 | 意味 |
|---|---|
| `"rw"` | 読み書き（設定で `readonly = true` のマウントは読み取りのみのまま） |
| `"ro"` | 読み取りのみ。変更系は 403 `forbidden`。画面は操作ボタンを灰色にする |
| `None` | 見せない。マウントの一覧に出さず、そのマウントへの要求は 404 `not_found`（あることも知らせない）。自動更新でも見張らない |

- ほかの値を返すのは利用する側の誤りとして 500 にする（中身はログへ）
- 要求ごとに呼ぶので、重い処理（データベースの問い合わせなど）は利用する側でまとめる

### 7.4 利用する側が 1 本ずつ処理するサーバで動いているとき

bottle の既定のサーバ（`bottle.run(app)` の wsgiref）は、要求を 1 本ずつ処理します。自動更新は接続を開いたままにするので、**そのあいだほかの要求が止まります。**

- できれば、要求ごとにスレッドを立てるサーバで動かす（`server.httpserver.ThreadingServer`、gunicorn のスレッド、など）
- 変えられないなら **`mount_webfiledir(…, live_updates=False)`** で自動更新を止める。画面は自動更新を使わずに動く（F5 で読み直す）

### 7.5 見本

`examples/bottle_host.py`: ログイン（見本なのでパスワードは確かめない）を持つ bottle のシステムに組み込み、`admin` は両方のマウントを読み書き、`guest` は `fdweb` を読み取りのみ・ほかは見せない。

```bash
uv run examples/bottle_host.py webfiledir.toml   # http://127.0.0.1:8080/
```

## 8. 自分のプロバイダを差し込む（仮想ファイル構造）

利用する側のシステムが持っている木（データベースのレコード、別のサービスの中身など）を、**webFileDir のコードを直さずに**フォルダとファイルとして見せる方法です。**画面（`static/`）は変えません。**

```python
from server.app import create_app                 # bottle なら server.embed.mount_webfiledir も同じ引数
from server.config import ConfigError, load_config, prepare_mounts
from server.errors import ApiError
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
    table = m.options.get("table")                # 共通の項目（id・type・label・readonly）以外は options に入る
    if not isinstance(table, str):
        raise ConfigError("table は文字列で書いてください")   # 「マウント <id>: …」として起動を止める
    return NotesProvider(open_db(table))


config = load_config("webfiledir.toml")           # [[mount]] に type = "notes"、table = "…" と書く
prepare_mounts(config)
app = create_app(config, providers={"notes": make_notes})
```

| 決まり | 内容 |
|---|---|
| 作る関数 | `MountConfig` を受け取り `Provider` を返す。設定の誤りは `ConfigError` で知らせる |
| 種類の名前 | 組み込みの `local`・`memory` は置き換えられない（`ValueError`）。知らない種類を `type` に書くと起動のときに `ConfigError` |
| 必ず書くメソッド | `stat`・`listdir`。ほかは `capabilities` に入れたものだけ（入れない操作は画面で灰色になり、API も拒否する） |
| エラー | `ApiError("not_found" / "exists" / "bad_path" / …, 操作者が読む文)`。ほかの例外は 500 になり、中身はログにだけ出る |
| スレッド | 要求ごとにスレッドが立つので、共有している状態は錠で守る |
| 自動更新 | 変更がこの API を通るなら何もしなくてよい。**API の外で変わったら `self.notify_changed()` を呼ぶ**（どのスレッドからでもよい） |

- メソッドごとの引数・戻り値・投げるエラーは、配布物の `server/providers/base.py` の説明と、見本の `server/providers/memory.py`（メモリ上の構造。書き込み・ごみ箱・中身の読み書きまで持つ）にある。Wiki では プロバイダの作りかた（Wiki: /ver.0/Design/Provider）
- **開きかたもプロバイダが決める。**`open_methods` に開く経路（`OpenMethod(id, label, modifier)`。先頭が既定、`modifier="shift"` は Shift を押しながら）を並べ、`open(path, method)` で `OpenResult`（`navigate`: 新しいページへ移る / `modal`: モーダルで見せる。モーダルの画面は今後）を返す。規則の全体は配布物の `server/providers/base.py` の説明（Wiki では プロバイダの作りかたの「開く」（Wiki: /ver.0/Design/Provider#開く））
- **項目ごとの権限もプロバイダが決める。**`Entry.auth`（4 = 読む・2 = 書く・1 = 実行、既定 7）。画面は、ファイルを開く＝読む、フォルダに入る＝実行、中に作る・その中の項目の名前の変更・削除・移動＝そのフォルダの書く、で操作を止める。**API は権限を見て拒否しない**（止めたいなら `authorize`・`mount_access`）
- **アイコンもプロバイダが持ち込める。**クラスの `icons` に `{名前: server.icons.Icon(SVG の図形)}` を置き、`Entry.icon` で項目ごとに名前を選ぶ（`mount_icon` でマウントの行も）。使える図形は `path`・`circle`・`rect` などだけで、`script`・`on...`・`style`・`url(...)` は起動時に拒否する。規則の全体は配布物の `server/icons.py` の説明（Wiki では プロバイダの作りかたの「アイコン」（Wiki: /ver.0/Design/Provider#アイコン））
- **詳細表示の列（属性）もプロバイダが決める。**クラスの `attributes` に `server.attributes.Attribute` を並べる（既定は更新日時・種類・サイズ）。各属性は「値」（`kind`: `number` / `text`、`none`: 値なしを `first`＝最優先か `last`＝無効データに）と「表現方法」（`format`: `text`・`number`・`bytes`・`datetime`・`date`・`map`）を持つ。固有の属性の値は `Entry.attrs` に入れる。規則の全体は配布物の `server/attributes.py` の説明（Wiki では API 設計の「属性」（Wiki: /ver.0/Design/API#属性--値と表現方法））
- **マウントをまたぐコピー・移動**（実ファイル ↔ 差し込んだ構造）をさせるなら、`capabilities` に `"stream"` を入れて `open_read`・`write_file` を実装する

## 9. まだできないこと

| できないこと | 状況 |
|---|---|
| アップロード | 最初の依頼の範囲外（ToDo の「その後」（Wiki: /ver.0/ToDo））。ファイルを開く・ダウンロード・中身の表示は `POST open`・`GET raw` で作った（3.2） |
| モーダルで表示する形（開く API の `action: "modal"`） | 画面は今後。今は「まだ表示できません」と知らせるだけ |
| 消えない仮想ファイル構造（SQLite・ZIP の中・Wiki のページ階層など） | 組み込みの種類はメモリ上のものだけ。どれを組み込みにするかは決めていないことの 5。**利用する側の構造なら [8 章](#8-自分のプロバイダを差し込む仮想ファイル構造) で差し込める** |
| 利用する側からの要求だけを受け付ける仕組み（共有の秘密など） | 方法を決めていない（決めていないことの 10）。**bottle のシステムに組み込む（E）なら要らない** |
| 認可の結果を受け取る仕組み | 決めていない（決めていないことの 11）。**E なら `mount_access` で分けられる**。ほかの組み込みかたでも `create_app` に渡せる |
| 標準の組み込みかた | 決めていない（決めていないことの 12） |

## 10. 関連ページ

- 設計の全体像（Wiki: /ver.0/Design） … 構成、プロバイダ、安全対策、設定
- API 設計（Wiki: /ver.0/Design/API） … API の細部、エラーの種類、一括の結果、名前の衝突
- 画面設計（Wiki: /ver.0/Design/Frontend） … 画面の振る舞い、二画面モード、JS の部品分け
- プロバイダの作りかた（Wiki: /ver.0/Design/Provider） … 自分の仮想ファイル構造をつなぐとき（サーバ側だけの変更で済む）
- ToDo（Wiki: /ver.0/ToDo） … 決めていないことの一覧
