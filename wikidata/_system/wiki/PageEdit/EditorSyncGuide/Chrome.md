# Chrome

**ブラウザ側**にインストールする [ブラウザ拡張機能](../BrowserExt)（wikiedit）を、Chrome にインストールする方法です。

## インストール
#attachls()

1. 上の一覧から `wikiedit-chrome.zip` をダウンロードする（一覧の日時が、更新した日時です）
2. 置き場所のフォルダを作り、そこに展開する（zip の中にフォルダは無く、ファイルが直接入っています）

   ```sh
   mkdir -p ~/.local/chrome/wikiedit
   unzip wikiedit-chrome.zip -d ~/.local/chrome/wikiedit
   ```

3. `chrome://extensions` を開き、右上の「デベロッパー モード」をオンにする
4. 「パッケージ化されていない拡張機能を読み込む」で、展開したフォルダを選ぶ
5. 一覧に wikiedit が出て、有効になっていればインストールされています

#img(拡張機能の画面に wikiedit が出たところ（画面は Chrome と同じ作りの Chromium）>/PageEdit/EditorSyncGuide/chrome-extensions.png)

展開したフォルダは、拡張機能として使っているあいだ、消さずに残しておきます。

そのあと、Wiki のサイトで使えるように許します（[使うサイトを許す](../BrowserExt#使うサイトを許す)）。

## 新しいバージョンにするとき

新しい zip を、同じフォルダに展開し直して（上書き）、`chrome://extensions` の wikiedit の
「再読み込み」（丸い矢印）を押します。一覧の数字（0.3.2 など）がバージョンです。
