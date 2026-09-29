# サーバとして公開する

[入れかた・動かしかた](/InstallGuide) で動かしたWikiを、サービスとして常に動かし、Webサーバの後ろで公開する手順です。

## サービスとして起動

`./wiki.py` は端末を閉じると止まる**お試し用**です。公開するなら次のどちらかにします。

| 方法 | 仕組み | gunicornの登録 |
|---|---|---|
| リバースプロキシ | gunicornを裏で動かし続け、nginx・Apacheが外からの通信を受けて中継する | 必要 |
| WSGI直結 | nginx・Apacheが直接Pythonアプリを読み込む | 不要（Apacheのみ対応） |

### gunicorn を入れる

```bash
uv pip install --python _venv/bin/python gunicorn
```

### gunicorn で動かす

```bash
cd ~/wikiSystem
_venv/bin/gunicorn --chdir ~/wikiSystem -b 127.0.0.1:8619 'wiki:app'
```

止めるのは `Ctrl` + `C` です。

指定するのは **`wiki:app`** です（`wiki.wsgi:application` では失敗します）。
待受アドレスとポートは `-b` で変えます。

```bash
_venv/bin/gunicorn --chdir ~/wikiSystem -b 0.0.0.0:8700 'wiki:app'   # 例: 他のパソコンからポート8700で
```

更新後の再起動は `/.restart` から行えます（既定のWikiの管理者・助手だけ。**サービスを止めずに**反映されます。
[サービスの再起動](/Tech/Restart)）。

### gunicorn をサービスとして登録する

**nginx・Apacheと組み合わせるなら、systemd への登録が要ります**（端末を閉じても動き続けるように）。

```bash
sudo tee /etc/systemd/system/wikisystem.service <<'UNIT'
[Unit]
Description=wikiSystem (gunicorn)
After=network.target

[Service]
User=<ユーザー名>
WorkingDirectory=/home/<ユーザー名>/wikiSystem
ExecStart=/home/<ユーザー名>/wikiSystem/_venv/bin/gunicorn --chdir /home/<ユーザー名>/wikiSystem -b 127.0.0.1:8619 wiki:app
Restart=always

[Install]
WantedBy=multi-user.target
UNIT
```

`<ユーザー名>` は自分のログイン名（`whoami`）に置き換え、登録して起動します。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wikisystem
```

`sudo systemctl status wikisystem` で確かめられます。更新後の反映は `/.restart` で行えます。

### nginx でリバースプロキシを構成する

nginx が入っている前提です（`wiki.example.com` は自分のドメインに）。

```nginx
server {
    listen 80;
    server_name wiki.example.com;

    location / {
        proxy_pass http://127.0.0.1:8619;
        proxy_set_header Host $host;
    }
}
```

書いたら `sudo nginx -t` で確かめ、`sudo systemctl reload nginx` で反映します。

### Apache でリバースプロキシを構成する

Apache が入っている前提です。`mod_proxy` を有効にしてから設定を書きます。

```bash
sudo a2enmod proxy proxy_http
```

```apache
<VirtualHost *:80>
    ServerName wiki.example.com
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8619/
    ProxyPassReverse / http://127.0.0.1:8619/
</VirtualHost>
```

書いたら `sudo apache2ctl configtest` で確かめ、`sudo systemctl reload apache2` で反映します。

### Wikiを外向きの別名で公開する（`/sandbox/` → `/=sandbox/`）

外向きの `http://wiki.example.com/sandbox/` を、内側の `/=sandbox/`（1つのWiki）へ中継する構成です。
**プロキシから `X-Forwarded-Prefix` ヘッダで外向きのパスを渡す**と、システムは `/=sandbox` の代わりに
その値でリンク（CSS・ページ間リンクなど）を作ります（渡さないとCSSが読めず崩れます）。

```bash
sudo a2enmod proxy proxy_http headers
```

```apache
<VirtualHost *:80>
    ServerName wiki.example.com

    # 「/sandbox」だけで来たときは、末尾スラッシュ付きへ寄せる
    RedirectMatch ^/sandbox$ /sandbox/

    <Location /sandbox/>
        ProxyPreserveHost On
        # 外向きの入口を伝える（末尾スラッシュなし）
        RequestHeader set X-Forwarded-Prefix "/sandbox"
    </Location>
    ProxyPass        /sandbox/ http://172.22.22.10:8619/=sandbox/
    ProxyPassReverse /sandbox/ http://172.22.22.10:8619/=sandbox/
</VirtualHost>
```

- 外向きの名前と内側のWiki名は違っていてもかまいません
  （`/wiki2/` → `/=sandbox/` など。`RequestHeader` の値を外向きの名前に合わせます）
- **`ProxyPass` の対象は1つのWikiの中に限られます。** `/sandbox/` の下から
  ほかのWiki（`/=wiki/` など）へは行けません。ページの本文に手書きした
  `/=wiki/…` のようなリンクはシステムが書き換えないので、公開するWikiの
  ページには使わないでください
- Wikiの新規作成・削除・全Wikiの一覧など、サイト全体を扱う管理画面は、
  この入口では使えません（内側のURLで直接開いてください）
- ヘッダが無い・形が正しくないときは、これまでどおり `/=Wiki名` でリンクを作ります。
  `server.prefix`（全Wikiに同じ接頭辞を付ける設定）と併用した場合は、ヘッダのほうが優先です
- 別のWikiも公開するなら、`<Location>`・`ProxyPass` の組をWikiごとに書き足します

## WSGIで直結する（gunicornを使わない）

**Apacheなら `mod_wsgi` で直接動かせます**（別のサービス登録は要りません）。nginxはPythonを実行
できないので、この方法は使えません（下の uWSGI を使います）。

### Apache（mod_wsgi）

```bash
sudo apt install -y libapache2-mod-wsgi-py3
sudo a2enmod wsgi
```

```apache
<VirtualHost *:80>
    ServerName wiki.example.com

    WSGIDaemonProcess wikisystem python-home=/home/<ユーザー名>/wikiSystem/_venv
    WSGIProcessGroup wikisystem
    WSGIScriptAlias / /home/<ユーザー名>/wikiSystem/wiki.wsgi

    <Directory /home/<ユーザー名>/wikiSystem>
        Require all granted
    </Directory>
</VirtualHost>
```

`python-home` で `_venv` を指します。`WSGIDaemonProcess` が無い「埋め込みモード」では `/.restart` が
効きません（[サービスの再起動](/Tech/Restart#apachemod_wsgiのとき)）。

書いたら `sudo apache2ctl configtest` で確かめ、`sudo systemctl reload apache2` で反映します。

#note(){{
`libapache2-mod-wsgi-py3` はシステムのPythonと**同じ版**でないと動きません。`_venv` と版がずれる
ときは gunicorn を使ってください。
}}

### nginx（uWSGIを使う場合）

gunicorn の代わりに **uWSGI** を使えます（サービスとしての登録は同じく要ります）。

```bash
uv pip install --python _venv/bin/python uwsgi
```

`/etc/systemd/system/wikisystem.service` を gunicorn と同じ要領で作り、`ExecStart` だけ差し替えます。

```
ExecStart=/home/<ユーザー名>/wikiSystem/_venv/bin/uwsgi --wsgi-file /home/<ユーザー名>/wikiSystem/wiki.wsgi --socket 127.0.0.1:8620
```

nginx側は `proxy_pass` ではなく `uwsgi_pass`（uWSGI独自の通信方式）を使います。

```nginx
server {
    listen 80;
    server_name wiki.example.com;

    location / {
        include uwsgi_params;
        uwsgi_pass 127.0.0.1:8620;
    }
}
```

## パスワードをかける（basic認証）

Wikiのログインとは別に、**サイト全体**へのパスワードを nginx・Apache でかけられます。
ページごとに分けるなら、Wikiのアクセス制限（[ページごとの権限](/Tech/PagePermissions)）を使います。

ユーザー名とパスワードを作ります。

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd taro
```

2人目からは `-c` を外します（付けると作り直しになります）。

### nginx の場合

`location` ブロックに2行を足します。

```nginx
location / {
    auth_basic "wiki";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:8619;
    proxy_set_header Host $host;
}
```

#note(){{
**編集だけに basic認証はかけられません**（編集はページ自身のURLへのPOSTなので）。
「編集はログインした人だけ」にするには、Wikiのアクセス制限で `*:W:g:all` と決めます。
}}

### Apache の場合

`<VirtualHost>` の中に足します。

```apache
<Location "/">
    AuthType Basic
    AuthName "wiki"
    AuthUserFile /etc/apache2/.htpasswd
    Require valid-user
</Location>
```

#note(type=warn){{
**http ではパスワードがそのまま流れます。** インターネットに出すなら https と一緒に使ってください。
}}
