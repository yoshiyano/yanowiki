# サービスの再起動の仕組み

`/.restart` を開くと、このWikiサービスを再起動できます。ファイルを更新してから
再起動すれば、更新を反映した状態で再開します。実行できるのは既定Wikiの管理者と
助手だけです（[下記](#誰が実行できるか)）。

## 使いかた

| URL | 動き |
|---|---|
| `/.restart` | 確認の画面が出る。ボタンを押すと再起動する |
| `/.restart?now=1` | 画面を出さず、その場で再起動する（スクリプトなどから呼ぶ用） |

確認の画面を挟むのは、ブラウザの先読みやリンクの巡回など、意図しないGETで
サービスが落ちないようにするためです。画面は管理ページ共通の外枠（`sysui.page`）で
出ます（[管理ページ](/Tech/AdminPages)）。

## 誰が実行できるか

既定Wiki（`config/server.yaml` の `farm.default`）の管理者と助手だけです。
再起動はサービス全体に効くので、Wikiがいくつあっても判定は既定Wikiのアカウントで
行います（`wikilib.sysui.require_on_default_farm`）。

- **Wiki名を含むURL（`/=<Wiki名>/.restart`）は、既定Wikiのものでも403です。**
  ログイン状態のcookieはWikiごとの `Path` に置いてあるので、Wiki名付きのURLも
  通すと、どのWikiのcookieが読まれるかが状況次第になるためです
- `?now=1` も同じ判定を通ります（受け付ける関数は `serve_restart` 1つ）。
  cookieを持たないコマンド（素の `curl` など）からは通りません
- 同じ判定を通る画面: [`/.newwiki`](/Tech/NewWiki)・[`/.allwiki`](/Tech/Reference/Views#wikiの一覧)・
  [`/.delwiki`](/Tech/DelWiki)。既定Wikiが持つ役割のまとめは [設計方針](/Tech/DesignPolicy/Farm#デフォルトのwikiの役割)

権限の全体像は [ページごとの権限](/Tech/PagePermissions) にあります。

## 動かしかたによって方法が変わる

動作環境を見分け、それぞれに合った方法をとります（`wikilib.restart`）。

| 環境 | 見分けかた | 方法 |
|---|---|---|
| `wiki.py` の直接実行 | 起動した側が自分で記録する | 自分自身を `exec` し直す |
| gunicorn | `SERVER_SOFTWARE` | 親（master）に `SIGHUP` を送る |
| uWSGI | `uwsgi` モジュールの有無 | `uwsgi.reload()` を呼ぶ |
| Apache（mod_wsgi） | `mod_wsgi.process_group` | デーモンモードなら自分に `SIGINT` |
| 判別できないとき | — | 入口スクリプトの時刻だけ更新する |

nginx は Python を直接動かさないので、見分けるのは後ろのWSGIサーバです。

### 直接実行のとき

自分自身を `exec` し直します。プロセスIDが変わらないので、`.pid/<ポート>.pid` も
正しいままです。

### gunicorn のとき

親プロセスに `SIGHUP` を送ります。ワーカーが順に入れ替わるので、サービスを止めずに
コードの更新が反映されます。`--preload` を付けている場合は反映されないので、
gunicorn 自体を起動し直してください。

### Apache（mod_wsgi）のとき

デーモンモード（`WSGIDaemonProcess`）なら、自分に `SIGINT` を送ってデーモンプロセスを
起動し直させます。埋め込みモードでは自分を止められないので、入口スクリプトの時刻を
更新するだけです。反映されない場合はApacheの再読み込みが必要で、画面にもそう出します。

### 判別できないとき

入口スクリプト（`wiki.wsgi`）の更新時刻だけを新しくします。リロードを監視している
環境なら拾われますが、確実ではなく、画面にもそう出します。

## 応答を返しきってから実行する

どの方法でも、応答を返したあと `RESTART_DELAY`（1秒）待ってから別のスレッドで
実行します。すぐ実行すると、結果が届く前に接続が切れるためです。

`Connection: close` は付けません。WSGIサーバが扱うヘッダ（hop-by-hop）なので、
アプリから付けると `wsgiref` に弾かれて500になります。

## WSGIサーバから使う

入口は `wiki.wsgi` です。gunicorn だけはモジュール名で指定するので `wiki:app` を
渡します（`wiki.wsgi:application` では失敗します）。

```
uWSGI   : uwsgi --wsgi-file /path/to/wikiSystem/wiki.wsgi
Apache  : WSGIScriptAlias / /path/to/wikiSystem/wiki.wsgi
gunicorn: gunicorn --chdir /path/to/wikiSystem 'wiki:app'
```

### 依存パッケージの入ったPythonで起動する

`wiki.py` を直接実行したときは、`_venv` があればそちらのPythonで自分を起動し直します
（[設計方針](/Tech/DesignPolicy#ポータビリティ)）。import されたときはWSGIサーバごと
置き換えてしまうので起動し直しません。WSGIサーバは依存パッケージの入ったPythonで
起動してください。

```
/path/to/wikiSystem/_venv/bin/gunicorn 'wiki:app'
```
