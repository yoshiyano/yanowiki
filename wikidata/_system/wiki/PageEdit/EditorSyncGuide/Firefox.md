# Firefox

**ブラウザ側**にインストールする [ブラウザ拡張機能](../BrowserExt)（wikiedit）を、Firefox にインストールする方法です。

Firefox 用の zip は、そのままでは「一時的なアドオン」としてしか入らず、Firefox を閉じると
削除されます。インストールしたままにするには、Mozilla の署名が要ります（下の「常にインストールしておく」）。

## インストール（一時的・署名なし）
#attachls()

1. 上の一覧から `wikiedit-firefox.zip` をダウンロードする（展開は要りません。一覧の日時が、
   更新した日時です）
2. `about:debugging#/runtime/this-firefox` を開く（`about:debugging` の「この Firefox」）
3. 「一時的なアドオンを読み込む...」を押し、zip をそのまま選ぶ
4. 「一時的な拡張機能」に wikiedit が出ればインストールされています

#img(about:debugging の「この Firefox」。「一時的なアドオンを読み込む...」から zip を選ぶ>/PageEdit/EditorSyncGuide/firefox-debugging.png)

そのあと、Wiki のサイトで使えるように許します（[使うサイトを許す](../BrowserExt#使うサイトを許す)）。

Firefox を閉じると削除されます。試すだけならこれで足ります。

## 常にインストールしておく（署名を受ける）

署名は、Mozilla のアドオンのサイト（AMO）にユーザー登録すれば、**限定公開（AMO の一覧には出さない
自前の配布）**で無料で受けられます。

2026-10-06 時点の Mozilla の案内（[Extension Workshop](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)）に基づきます。

### 公開と限定公開

| | 公開（listed） | 限定公開（unlisted） |
|---|---|---|
| AMO の一覧 | 出る。誰でも検索してインストールできる | 出ない |
| 配布方法 | AMO から | 署名済みのファイル（`.xpi`）を自分で配布する |
| 更新 | Firefox が AMO から自動で取る | 新しいバージョンを自分で配布する |
| 審査 | 自動の検査のあと、人の審査もある | 自動の検査で署名される。人の審査は、あとから入ることがある |

この拡張機能は、限定公開で使います。

### 署名を受ける手順

1. [addons.mozilla.org](https://addons.mozilla.org/) の右上の **Register**（登録済みなら **Log in**）で、
   Mozilla アカウントを作ってログインする
2. [Developer Hub](https://addons.mozilla.org/developers/) で **Submit a New Add-on** を押す。
   初回は、アドオンの決まり（Add-on Policies）と開発者の同意書（Developer Agreement）に同意する
3. 配布方法で **On your own**（自分で配布する＝限定公開）を選ぶ
4. **Select a file** で `wikiedit-firefox.zip` を上げる。自動の検査が走る（エラーは直す必要が
   あり、警告なら進める）
5. 対応する環境を選ぶ
6. ソースコードの提出を訊かれたら「いいえ」を選ぶ（縮めたり難読化したりしていないので要らない）
7. **Continue** を押すと「Version Signature Pending」になる。署名が済むとメールが届く
   （ふつうは24時間以内）
8. **My Submissions** からそのバージョンのページを開き、署名済みの `.xpi` を保存する

### 署名済みのファイルをインストールする

`about:addons` の歯車のメニューの「ファイルからアドオンをインストール」で `.xpi` を選ぶか、
`.xpi` を Firefox のウィンドウにドラッグします。Firefox を閉じても削除されません。

### 新しいバージョンを出すとき

- `manifest.firefox.json` の `version` を上げる。**AMO は同じバージョン番号を二度受け付けない**
- `build_zip.py` で zip を作り直し、Developer Hub のそのアドオンのページから新しいバージョンとして登録する
- 署名済みの `.xpi` を配布し直す（限定公開では Firefox は自動で更新しない）

### 設定に要るもの

AMO に上げる Firefox 用の設定（`manifest.firefox.json`）には、次が含まれている必要があります。
どちらも記載してあります。

- `browser_specific_settings.gecko.id`: アドオンの ID。Manifest V3 では必須
- `browser_specific_settings.gecko.data_collection_permissions`: 集めるデータの申告。
  2025-11-03 から、新しいアドオンには必須（Firefox 140 以上が要る）。この拡張機能は
  本文を手元のエディタへ渡すだけで、外へは送らないので `{"required": ["none"]}`

### 署名なしで使う方法

Firefox の Developer Edition・Nightly・ESR なら、`about:config` で `xpinstall.signatures.required` を
`false` にすると、署名の無いものもインストールしたままにできます（ふつうの Firefox ではできません）。
