# wikiSystem

Python + [bottle](https://bottlepy.org/) 製の軽量Wikiシステム。PukiWikiを
模範としつつ、Markdown記法にも対応する。サーバごとローカルで動かせば自前の
メモ・ドキュメント置き場として、外部公開可能なIPで動かせば情報公開用
サービスとして使える。

システム本体は約30MBの軽量設計。1台のサーバーで複数の個別Wikiを管理できる
（Wiki Farm）。

## 主な機能

### Wikiとして当たり前にできること

- Webブラウザから編集できる。誰でも編集できるWikiにも、ログインした人だけが
  編集できるWikiにもできる
- 画像やファイルを自由に添付できる
- サイト全体・ページ内を検索できる（AND/OR、対象の絞り込み、ワイルドカード）

### wikiSystem独自の特徴

- **PukiWiki記法とMarkdown記法**（GitHub Flavored Markdown）をページごとに
  選んで書ける。書きかたはページの拡張子（`.txt` / `.md`）で決まる
- 1つのサーバーで**複数のWiki**を動かせる（Wiki Farm）
- 見た目（テーマ）は[Jinja2](https://jinja.palletsprojects.com/)テンプレート
  で自由にデザインできる。HTML に差し込む場所を書くだけで作れる**スロット型のテーマ**もあり、
  管理の画面（「テーマのファイル」）からテーマのファイルを扱える
- **プラグイン**で機能を拡張できる（`note`・`contents`・`recent`・`ls`・
  `ref`・`img`・`color`・`size`・`include`・`pre`・`glossarytip` など多数を
  同梱。独自プラグインも追加できる）
- 複数の用語に色を付けて**ページをまたいで追いかけられるマーカー**機能。
  検索と違い、一度登録すれば開くどのページでも自動で光る
- 保存のたびに**差分で記録**され、編集画面の「履歴」タブで見比べたり戻したり
  できる（一部だけを戻すことも、消したページを戻すこともできる）
- **同じページを同時に編集しても、取り込みそこねない**。競合を検出し、
  3文書マージで統合する画面が開く
- **見出し単位で編集できる**（セクション編集）。長いページの一部を直すのに、
  全文を開かなくてよい
- **手元のエディタで書ける**（外部エディタ連動）。編集画面とセクション編集の本文を、
  VS Code・Emacs・Neovim と同期して書き、ブラウザでプレビューを見る。エディタのプラグインと
  ブラウザ拡張機能は、Wiki のページから配る
- **ファイル一覧**で、ページとフォルダをエクスプローラーのように見て、名前の
  変更・移動・コピー・削除・新規作成・フォルダ化ができる。名前や置き場所を変えても、
  指している側のリンクを自動で書き換える
- **アカウントとアクセス制限**。アカウント・グループ・承認制の登録、ページごとの
  閲覧・編集の制限、管理の画面（`/.admin`）。管理を手伝う助手に、操作ごとに権限を与えられる
- コードブロックの**シンタックスハイライト**（Prism.js）
- 閲覧者が**テーマを選べる**（設定で有効にした場合）
- ブラウザから**新しいWikiを作れる・消せる**（Wiki Farmの追加・削除）
- PukiWikiのデータを移す道具（`./wiki.py convwiki`）
- **公開版からの更新**。新しいバージョンが出ると管理者に知らせ、管理の画面から
  更新して再起動できる（1.2.0 から）
- Linux・Windowsどちらでも動く。インストールは数コマンドで完了する

導入や活用の詳しい説明、設計方針、開発方法は起動後にwikiページとして
閲覧できる（`/UsageGuide`、`/Tech` 以下）。

### インターネットへ公開するとき

**アクセス制限を置いていないWikiは、到達できる人なら誰でも編集できる。**
公開するWikiでは、アクセス制限（`/.admin/privileges`）で編集できる人を絞ること。
`./wiki.py` 単体は暗号化されていない http なので、前段のWebサーバー（リバース
プロキシ）で https にする（起動後の `/InstallGuide` の「サービスとして起動」）。

## クイックスタート

入れたあと、**`./wiki.py` の前に、必ず `uv sync` で部品をそろえる**（下の「セットアップ」）。
そろえずに動かすと、次のメッセージを出して止まる。

```
依存パッケージが見つかりません（No module named '…'）。`UV_PROJECT_ENVIRONMENT=_venv uv sync` を実行してインストールしてください。
```

Linux/macOS の流れは次のとおり（Windows は後ろの「起動」を参照）。

```bash
# 1. uv を入れる（入っていれば不要）。入れたら端末を開き直す
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 入手
git clone https://github.com/yoshiyano/yanowiki.git wikiSystem
cd wikiSystem

# 3. 部品をそろえる（_venv ができる。Pythonも uv が用意する）
UV_PROJECT_ENVIRONMENT=_venv uv sync

# 4. 起動
./wiki.py
```

**はじめての起動では、管理者（`admin`）のパスワードを端末で聞かれる。** 決めたら
ブラウザで `http://127.0.0.1:8619/` を開き、先頭の案内に従って初期設定
（自分のWikiをつくる）へ進む。**ダウンロードして起動しただけでは途中の状態**で、
同梱の `_system` は配布元が管理するサンプルなので、自分のページは別のWikiに書く。

## 入手

```bash
git clone https://github.com/yoshiyano/yanowiki.git wikiSystem
cd wikiSystem
```

リポジトリの名前は `yanowiki` だが、フォルダの名前は `wikiSystem` にしておく（起動後に読める
`/InstallGuide` の手順が、このフォルダ名で書いてあるため）。

## セットアップ

依存関係の管理には [uv](https://docs.astral.sh/uv/) を使う。未インストール
の場合、Linux/macOSは:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows（PowerShell）は:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

uv自体がPythonインタプリタのダウンロード・管理も行うため、対象PCにPython
3.12以上が事前に入っていなくてもよい（同梱のファイル一覧の部品 webFileDir が 3.12 以上を求める）。

```bash
UV_PROJECT_ENVIRONMENT=_venv uv sync
```

環境を作り直したい場合は `_venv/` を削除して同じコマンドを再実行すればよい
（`_venv/` はPCごとの実行環境であり、PC間でコピーしてはいけない）。

## 起動

Linux/macOS:

```bash
./wiki.py                              # config/server.yaml の設定で起動
./wiki.py --host 0.0.0.0 --port 80     # 外部公開用途（要権限）。引数がconfigより優先される
./wiki.py --debug                      # デバッグモード・自動リロード有効化
```

Windows:

```powershell
_venv\Scripts\python.exe wiki.py
```

同じホスト・ポートで前回起動した自分自身（`wiki.py`）がまだ動いていた場合は、
自動的に停止してから起動し直す（`.pid/` に前回のPIDを記録しており、起動
コマンドラインを照合できた場合のみ停止する。無関係なプロセスは誤って止めない）。

より詳しい手順（Ubuntu / Windowsそれぞれ）は、起動後に `/InstallGuide` として
も読める。

## 更新（1.1・1.1.1 などから）

新しいバージョンへは、入手したフォルダで次を実行し、そのあとサービスを再起動する
（動かしたまま実行してよい。反映は再起動のあと）。

Linux/macOS:

```bash
cd ~/wikiSystem
git fetch --depth 1 origin main
git reset --hard origin/main
UV_PROJECT_ENVIRONMENT=_venv uv sync --inexact
```

Windows（PowerShell）:

```powershell
cd ~\wikiSystem
git fetch --depth 1 origin main
git reset --hard origin/main
$env:UV_PROJECT_ENVIRONMENT = "_venv"
uv sync --inexact
```

- 更新で変わらないもの: `config/server.yaml`、`_venv/`、`wikidata/` の下の各Wiki（`_system` を除く）
- **同梱の `_system` を書き換えていると、配布元の内容に戻る。** 自分のページは別のWikiに書く
- `--inexact` は、あとから入れた部品（gunicorn・uWSGI など）を消さないための指定
- **1.2.0 からは、管理者が画面から更新できる。** 新しいバージョンが出ると、既定のWikiの管理者に
  タイトル右端の info で知らせ、管理の画面（`/.admin/update`）から更新して再起動できる。
  1.1・1.1.1 にはこの画面が無いので、1.2.0 へは上の手順で更新する

## 動作確認

```bash
curl http://127.0.0.1:8619/            # デフォルトのWikiのトップページ
curl http://127.0.0.1:8619/nosuchpage  # "no page" (HTTP 404)
```

ブラウザで `http://127.0.0.1:8619/UsageGuide` を開くと、使いかたの説明ページが
読める。

## トラブルシューティング

- `OSError: [Errno 98] Address already in use`: 指定ポートが他プロセスで
  使用中。`--port` オプションで別ポートを指定する。
- 依存関係を追加した場合は `pyproject.toml` の `dependencies` に追記し、
  `uv lock` でロックファイルを更新した上で
  `UV_PROJECT_ENVIRONMENT=_venv uv sync` を再実行する。

## ライセンス

[MIT License](LICENSE)。同梱している `_sys/bottle.py`（[bottle](https://bottlepy.org/)）
は第三者の著作物で、ファイル自身にMITライセンス表記を含む（Copyright (c)
2009-2024, Marcel Hellkamp）。同梱している `_sys/webfiledir/`（ファイル一覧の部品
webFileDir）も、wikiSystem と同じ MIT License で配布する。

---

フォルダ構成・URLルーティング仕様・設定ファイルの全項目・Git管理方針・
今後の予定などは、起動後にwikiページとして参照できる。

- `/InstallGuide` … 入れかた・動かしかた（Ubuntu / Windows）
- `/UsageGuide` … 使いかた
- `/Tech` … 技術ドキュメント（設計方針・テーマとプラグインの開発方法・
  リファレンス・ロードマップ）
