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
  選んで書ける。記法はページの拡張子（`.txt` / `.md`）で決まる
- 1つのサーバーで**複数のWiki**を動かせる（Wiki Farm）
- 見た目（テーマ）は[Jinja2](https://jinja.palletsprojects.com/)テンプレート
  で自由にデザインできる
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
- **ファイル一覧**で、ページとフォルダをエクスプローラーのように見て、名前の
  変更・移動・削除・新規作成ができる。名前や置き場所を変えても、指している側の
  リンクを自動で書き換える
- **アカウントとアクセス制限**。アカウント・グループ・承認制の登録、ページごとの
  閲覧・編集の制限、管理の画面（`/.admin`）
- コードブロックの**シンタックスハイライト**（Prism.js）
- 閲覧者が**テーマを選べる**（設定で有効にした場合）
- ブラウザから**新しいWikiを作れる・消せる**（Wiki Farmの追加・削除）
- PukiWikiのデータを移す道具（`./wiki.py convwiki`）
- Linux・Windowsどちらでも動く。インストールは数コマンドで完了する

導入や活用の詳しい説明、設計方針、開発方法は起動後にwikiページとして
閲覧できる（`/UsageGuide`、`/Tech` 以下）。

### インターネットへ公開するとき

**アクセス制限を置いていないWikiは、到達できる人なら誰でも編集できる。**
公開するWikiでは、アクセス制限（`/.admin/privileges`）で編集できる人を絞ること。
`./wiki.py` 単体は暗号化されていない http なので、前段のWebサーバー（リバース
プロキシ）で https にする（起動後の `/InstallGuide` の「サービスとして起動」）。

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
