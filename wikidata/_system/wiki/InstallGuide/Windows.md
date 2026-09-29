# Windowsで動かす

**入れたばかりの Windows 11**（PowerShell）で動かすまでの手順です。管理者権限は基本的に不要で、
Pythonを先に入れる必要もありません。

#note(type=warn){{
**Windowsでは常時稼働の公開（gunicorn・uWSGI・mod_wsgi）はできません**（Unix系専用）。
試したり、自分だけ・社内だけで使う分には次の手順で足ります。公開するなら
[きちんと公開したいときは](#きちんと公開したいときは) をご覧ください。
}}

## 1. git を入れる

PowerShellで次を実行します（`winget` はWindows 10/11に標準で入っています）。

```powershell
winget install --id Git.Git -e --source winget
```

失敗する場合は [Git for Windows](https://git-scm.com/download/win) のインストーラーを使います
（選択肢はすべて既定のままで構いません）。

## 2. uv を入れる

Pythonと部品をまとめて用意する道具です（Python本体も uv が用意します）。

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

**PowerShellを開き直してから**確かめます。

```powershell
uv --version
```

#note(type=warn){{
`uv : 用語 'uv' は…認識されません` と出たら、開き直すか、サインアウト/再起動してから試してください。
}}

## 3. Wikiシステム一式を取得する

```powershell
cd ~
git clone --depth 1 https://github.com/yoshiyano/yanowiki.git wikiSystem
cd wikiSystem
```

公開しているリポジトリの名前は `yanowiki` ですが、取り出すフォルダの名前は `wikiSystem` に
しています（このあとの手順は、このフォルダ名で書いています）。
`--depth 1` は履歴を取らない指定です（開発に参加するなら外します）。`main` が最新の公開版で、
特定の版は `--branch v1.1` のように指定します。

## 4. サーバの実行に必要なモジュールをそろえる

PowerShellでは環境変数の指定を別の行にします。

```powershell
$env:UV_PROJECT_ENVIRONMENT = "_venv"
uv sync
```

**`_venv` はそのパソコン専用**なので、別のパソコンへ移したら消してから作り直してください。

## 5. 設定ファイルは自動で用意される

起動すると、`config\server.yaml` が無ければ雛形（`config\server.example.yaml`）からコピーします
（待受ポートや最初に出すWikiはここに書きます。更新しても残ります）。
Wikiごとの設定は [設定を変える](#設定を変える) をご覧ください。

## 6. 動かす

```powershell
_venv\Scripts\python.exe wiki.py
```

ブラウザで **`http://127.0.0.1:8619/`** を開きます（既定では自分のパソコンからだけ開けます）。

- 止めるときは `Ctrl` + `C`。**PowerShellの窓を閉じても止まります**
- 前に動かしたサーバが残っていれば、止めてから動き始めます
- Ubuntu向け手順の `./wiki.py` は使えません。`_venv\Scripts\python.exe wiki.py` を使います

待受アドレスとポートは次のように指定できます。

```powershell
_venv\Scripts\python.exe wiki.py --host 0.0.0.0 --port 8700   # 例: 他のパソコンからポート8700で開くことができる
```

続きは [使ってみよう](/UsageGuide) をご覧ください。

## 7. 管理者のパスワードを決める

Wikiを増やす画面（`/.newwiki`）を使えるのは、**既定のWiki（はじめは `_system`）の管理者と助手だけ**です。
はじめはアカウントが無いので、管理者を用意します。

```powershell
_venv\Scripts\python.exe wiki.py initusers
```

管理者（`admin`）のパスワードを2回聞かれます。そのあと「ログイン」から `admin` でログインし、
`/.newwiki` を開きます（[新しいWikiを作る](/NewWikiGuide)）。

パスワードを忘れたときは `_venv\Scripts\python.exe wiki.py resetpw` で入れ直せます。

## 更新する

最新版を使うだけの場合の手順です（履歴は残しません）。

```powershell
cd ~\wikiSystem
git fetch --depth 1 origin main
git reset --hard origin/main
$env:UV_PROJECT_ENVIRONMENT = "_venv"
uv sync
```

- 更新で変わらないもの: `config\server.yaml`、`_venv\`、`wikidata\`（`_system` を除く。下の注意）。
  wikiSystem 自身の古いファイルは片づきます
- 動かしたまま更新してかまいません。反映するには再起動します（[サービスの再起動](/Tech/Restart)）

#note(type=warn){{
**サンプルの `_system` を編集していると、この手順で配布元の内容に置き換わります。**
自分のページは `/.newwiki` で**別のWikiを作って**書いてください。
}}

## つまずいたら

| 症状 | すること |
|---|---|
| `uv`/`git` が「認識されません」と出る | PowerShellを開き直す。それでも直らなければ再起動する |
| `依存パッケージが見つかりません` | 手順4をやり直す |
| 見た目が崩れる | `Ctrl` + `Shift` + `R` (フルリロード)で読み込み直す |
| Windows Defender ファイアウォールの確認画面が出た | **プライベートネットワークのみ許可**で構いません（下の「他のパソコンから見せる」） |

## 設定を変える

| ファイル | 何を書くか |
|---|---|
| `config\server.yaml` | 待受ポート、最初に出すWiki |
| `wikidata\<Wiki名>\config\default.yaml` | サイト名、見た目、添付の上限（**そのWikiだけ**） |

**書き換えたら動かし直してください。** 管理者と助手は、Wikiごとの設定を `/.admin/configwiki` からも
変えられます。全項目は [リファレンス](/Tech/Reference/Config) にあります。

- `config\server.yaml` は、初回起動のとき雛形から作られます
- 共通の既定値は `config\default.example.yaml` ですが、**システム側のファイルなので更新で元へ戻ります。**
  書き換えずに、Wikiごとの `default.yaml` に書いてください（書かなかった項目は既定値のまま）
- `/.newwiki` で「Wiki設定を独立させる」にチェックを入れて作ると、`default.yaml` が最初から入ります

## 書いたものの置き場所

**`wikidata\<Wiki名>\` の下**にあります（構成は [Ubuntu向け手順](/InstallGuide#書いたものの置き場所) と同じ）。
データベース（`*.db`）も含め、**バックアップは `wikidata\` フォルダのコピーだけ**で済みます。

## 他のパソコンから見せる

```powershell
_venv\Scripts\python.exe wiki.py --host 0.0.0.0
```

`http://<このパソコンのIP>:8619/` で開けます（IPは `ipconfig` で確認）。はじめて外向けに待ち受けると
**Windows Defender ファイアウォールの許可画面**が出ることがあります。同じネットワーク内だけに
見せるなら「プライベートネットワーク」を許可してください。

#note(type=warn){{
**アクセス制限を置いていないWikiは、見える範囲の人なら誰でも編集できます**
（`_system` もそうです）。編集をログインした人だけに絞るには、そのWikiの
アクセス制限（`/.admin/privileges`）で決めます（[ページごとの権限](/Tech/PagePermissions)）。
編集の入口（編集ボタンなど）は、その権限で出し分けられます。

暗号化されていない http なので、**インターネットに直接出さないでください。**
}}

## きちんと公開したいときは

Windows単体では、PowerShellを閉じると止まる**お試し用の動かしかた**しかできません。
常時公開するなら **Linux環境**で [サービスとして起動](/InstallGuide/Server#サービスとして起動) してください。
同じWindowsパソコンの中なら、**WSL** でUbuntuを動かし、その中でUbuntu向け手順を行う方法もあります
（WSLの導入はMicrosoft公式の案内に沿ってください）。
