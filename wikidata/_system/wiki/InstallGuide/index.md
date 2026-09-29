# 入れかた・動かしかた

**入れたばかりの Ubuntu**（24.04 で確認）で動かすまでの手順です。`sudo` が使えれば始められ、
Pythonを先に入れる必要はありません。Windowsは [Windowsで動かす](/InstallGuide/Windows) をご覧ください。

## 1. git と curl を入れる

```bash
sudo apt update
sudo apt install -y git curl
```

## 2. uv を入れる

Pythonと部品をまとめて用意する道具です。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**端末を開き直してから**確かめます。

```bash
uv --version
```

#note(type=warn){{
`command not found` と出たら、開き直していないか `~/.local/bin` が見えていません。

```bash
export PATH="$HOME/.local/bin:$PATH"
```

毎回書かずに済ませるなら、同じ行を `~/.bashrc` の末尾に足します。
}}

## 3. Wikiシステム一式を取得する

```bash
cd ~
git clone --depth 1 https://github.com/yoshiyano/yanowiki.git wikiSystem
cd wikiSystem
```

公開しているリポジトリの名前は `yanowiki` ですが、取り出すフォルダの名前は `wikiSystem` に
しています（このあとの手順は、このフォルダ名で書いています）。
`--depth 1` は履歴を取らない指定です（開発に参加するなら外します）。`main` が最新の公開版で、
特定の版は `--branch v1.1` のように指定します。

## 4. サーバの実行に必要なモジュールをそろえる

```bash
UV_PROJECT_ENVIRONMENT=_venv uv sync
```

`_venv` に必要なものがそろいます。**`_venv` はそのパソコン専用**なので、別のパソコンへ移したら
消してから作り直してください。

## 5. 最初の1回は、下ごしらえも自動で済む

はじめて `./wiki.py` を動かしたとき、次の2つが自動で行われます。

### 設定ファイルを作る

`config/server.yaml` が無ければ、雛形（`config/server.example.yaml`）からコピーします
（待受ポートや最初に出すWikiはここに書きます。更新しても残ります）。
Wikiごとの設定は [設定を変える](#設定を変える) をご覧ください。

### 置いてあるページを全部登録する

一覧・検索が使う記録（`wikidata/<Wiki名>/pageinfo/wikiall.db`）は配布物に入っていないので、
最初の1回で、置いてあるページを全部登録します。

```
ページの取り込み: 追加139 (1 Wiki, 3.90秒)
  ※ 記録がまだ無かったので、置いてあるページを全部登録しました（_system）。次からは変わったぶんだけです。
```

この回だけ数秒かかります。記録は**いつ消しても構いません**（次に動かしたとき作り直されます）。

ファイルを直接足したり書き換えたりした場合は、動かしている間**1時間ごとに**取り込まれます。
すぐ反映するには `./wiki.py updatepage` を実行します。

## 6. 動かす

```bash
./wiki.py
```

ブラウザで **`http://127.0.0.1:8619/`** を開きます（既定では自分のパソコンからだけ開けます）。

- 止めるときは `Ctrl` + `C`。**端末を閉じても止まります**
- 前に動かしたサーバが残っていれば、止めてから動き始めます
- `source _venv/bin/activate` は要りません

待受アドレスとポートは次のように指定できます。

```bash
./wiki.py --host 0.0.0.0 --port 8700   # 例: 他のパソコンからポート8700で開くことができる
```

続きは [使ってみよう](/UsageGuide) をご覧ください。

## 7. 管理者のパスワードを決める

Wikiを増やす画面（`/.newwiki`）を使えるのは、**既定のWiki（はじめは `_system`）の管理者と助手だけ**です
（[既定のWikiの役割](/Tech/DesignPolicy/Farm#デフォルトのwikiの役割)）。
はじめはアカウントが無いので、管理者を用意します。

```bash
./wiki.py initusers
```

管理者（`admin`）のパスワードを2回聞かれます。そのあと「ログイン」から `admin` でログインし、
`/.newwiki` を開きます（[新しいWikiを作る](/NewWikiGuide)）。

パスワードを忘れたときは `./wiki.py resetpw` で入れ直せます。

## 更新する

最新版を使うだけの場合の手順です（履歴は残しません）。

```bash
cd ~/wikiSystem
git fetch --depth 1 origin main
git reset --hard origin/main
UV_PROJECT_ENVIRONMENT=_venv uv sync
```

- 更新で変わらないもの: `config/server.yaml`、`_venv/`、`wikidata/`（`_system` を除く。下の注意）。
  wikiSystem 自身の古いファイルは片づきます
- 動かしたまま更新してかまいません。反映するには再起動します（[サービスの再起動](/Tech/Restart)）

#note(type=warn){{
**サンプルの `_system` を編集していると、この手順で配布元の内容に置き換わります。**
自分のページは `/.newwiki` で**別のWikiを作って**書いてください。
}}

## つまずいたら

| エラー内容 | すること |
|---|---|
| `許可がありません` | `chmod +x wiki.py` |
| `依存パッケージが見つかりません` | 手順4をやり直す |
| 見た目が崩れる | `Ctrl` + `Shift` + `R` (フルリロード)で読み込み直す |

## 設定を変える

| ファイル | 何を書くか |
|---|---|
| `config/server.yaml` | 待受ポート、最初に出すWiki |
| `wikidata/<Wiki名>/config/default.yaml` | サイト名、見た目、添付の上限（**そのWikiだけ**） |

**書き換えたら動かし直してください。** 管理者と助手は、Wikiごとの設定を `/.admin/configwiki` からも
変えられます。全項目は [リファレンス](/Tech/Reference/Config) にあります。

- `config/server.yaml` は、初回起動のとき雛形から作られます
- 共通の既定値は `config/default.example.yaml` ですが、**システム側のファイルなので更新で元へ戻ります。**
  書き換えずに、Wikiごとの `default.yaml` に書いてください（書かなかった項目は既定値のまま）
- `/.newwiki` で「Wiki設定を独立させる」にチェックを入れて作ると、`default.yaml` が最初から入ります

## 書いたものの置き場所

**`wikidata/<Wiki名>/` の下**にあります。

```
wikidata/
  _system/        ← <Wiki名> の1つ（既定で入っているWiki。この技術ドキュメント自身）
    wiki/         ページ本体（.md のテキスト）
    attach/       添付ファイル
    config/       このWikiだけの設定（無くてもよい）
    pageinfo/     ページに付随する記録（システムが書きます）
      backup.db   保存時の差分（変更履歴）
      draft/      書きかけ
      upload/     分けて送られているファイルの、継ぎ足しの途中
      wikiall.db  ページ本文と、そこから取り出した情報のDB
  自分で作ったWiki名/   ← /.newwiki で増やすたびに、ここが増えます
    wiki/
    attach/
    ...
```

データベース（`*.db`）も `wikidata/` の中なので、**バックアップは `wikidata/` のコピーだけ**で済みます。
Wikiごとに持てるもの（プラグイン・テーマなど）は [新しいWikiを作る仕組み](/Tech/NewWiki) にあります。

## 他のパソコンから見せる

```bash
./wiki.py --host 0.0.0.0
```

`http://<このパソコンのIP>:8619/` で開けます（IPは `ip a` で確認）。

#note(type=warn){{
**アクセス制限を置いていないWikiは、見える範囲の人なら誰でも編集できます**
（`_system` もそうです）。編集をログインした人だけに絞るには、そのWikiの
アクセス制限（`/.admin/privileges`）で決めます（[ページごとの権限](/Tech/PagePermissions)）。
編集の入口（編集ボタンなど）は、その権限で出し分けられます。

`./wiki.py` のままでは暗号化されていない http なので、**インターネットに直接出さないでください。**
公開するなら次の「サービスとして起動」の方法を使います。
}}

## サーバとして公開する

サービスとして起動する（gunicorn・systemd）、nginx・Apache の後ろで公開する、WSGIで直結する、
basic認証をかける、の手順は [サーバとして公開する](/InstallGuide/Server) にあります。
