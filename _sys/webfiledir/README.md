# webFileDir

Windows のエクスプローラーのようなファイル操作を Web ブラウザから行うためのツールです。
別のプログラムから部品として使われることを想定しており、**認証は持ちません**（利用する側のシステムが行います）。

**開発中です（Phase 3: フォルダをまたいで整理できるところまで。作成・名前の変更・削除（ごみ箱）・コピー・移動（クリップボードとドラッグ＆ドロップ）ができます）。**
設計・経緯・計画は、このリポジトリではなくプロジェクトの Wiki（`=webfiledir`）にまとめています。

## 必要なもの

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)

## 導入

```bash
git clone git@github.com:yoshiyano/webFileDir.git webFileDirs
cd webFileDirs
uv sync
cp webfiledir.example.toml webfiledir.toml   # 必要に応じて直す
```

## 起動

```bash
uv run run.py                  # ./webfiledir.toml を読む
uv run run.py -c other.toml    # 設定ファイルを指定する
```

ブラウザで `http://<サーバのアドレス>:8616/` を開きます。

- マウントの根（見本では `/tmp/fdweb`）が無ければ権限 `0700` で作ります。
  あっても、シンボリックリンクだったり、起動したアカウントの持ち物でなかったりすると起動しません
- 見本の設定は LAN 内に `0.0.0.0` で公開します。**このサーバは誰が要求したかを確かめません。**
  利用する側のシステムを通らずに届く状態のまま、消えて困るフォルダを根にしないでください

`run.py` の shebang は `~/ClaudeWS/webFileDirs/.venv` の python を指しているので、その場所に置いたときは `./run.py` でも起動できます。

## 配布用のまとめを作る

組み込む人に渡すもの（`server/`・`static/`・`run.py`・設定の見本・組み込みの手引き `EMBED.md`・例 `examples/`）を、
`tar.gz` と `zip` にまとめます。

```bash
./tools/make_dist.py            # dist/ に webfiledir-<版>.tar.gz / .zip / .SHA256SUMS を作る
./tools/make_dist.py --no-docs  # Wiki を読めない環境では EMBED.md を入れずに作る
```

`EMBED.md` はプロジェクトの Wiki の「組み込みかた」から作ります（文書の正は Wiki）。

## テスト

```bash
uv run pytest
```

画面側のテスト（`static/tests/`）は、Chrome（`google-chrome` / `chromium`）があればヘッドレスで一緒に走ります。無ければ飛ばします。
関数のテストは、サーバを起動してブラウザで `http://<サーバのアドレス>:8616/static/tests/index.html` を開いても走ります。
