# wiki ページの準備

#code()

[Gitリポジトリの作成とclone](../ProjectSetup) まで済んでいる前提で、**プロジェクトの Wiki を作り、AI が書き込めることを確かめます。**

## 1. プロジェクトの Wiki を作る

**済んでいるか:** `ls ~/wikiSystem/wikidata/` にプロジェクト用の Wiki の名前があれば、作らずにその Wiki を使います（`<Wiki名>` をその名前にして、2 から続けます）。

**Wiki システムを動かし、管理者でログインして、[Wikiの新規作成](/AdminGuide/NewWiki) 画面で作ります。**

1. サーバを動かす（動いていなければ）

   ```bash
   cd ~/wikiSystem
   ./wiki.py
   ```

2. ブラウザで管理者（`admin`）でログインし、管理画面（`/.admin`）の「新しいWikiを作る」を開く。管理者のパスワードをまだ決めていなければ、`./wiki.py initusers`（[インストールと起動](/InstallGuide) の 7）
3. 項目を入れて「作る」

| 項目 | 入れるもの |
|---|---|
| 名前 | **リポジトリ名に揃える**（例: `hello-agent`）と、どちらも同じプロジェクトだと分かる。半角英数字と `-` `_` |
| 書きかた | **Markdown。**PukiWiki 記法の雛形が残らず、AI にも書かせやすい |
| 使いかた | 迷ったら一番上。**あとで変えられる** |

作ると、`~/wikiSystem/wikidata/<Wiki名>/` ができ、`http://127.0.0.1:8619/=<Wiki名>/` で開けます。

```bash
ls ~/wikiSystem/wikidata/               # <Wiki名> と _system が並ぶ
ls ~/wikiSystem/wikidata/<Wiki名>/wiki  # index.md と mainmenu.md がある
```

## 2. つながりを確かめる

AI に頼む前に、手で 1 回、書き込みと取り込みができることを確かめます。

```bash
cd ~/wikiSystem
echo '確認' >> wikidata/<Wiki名>/wiki/index.md
./wiki.py updatepage =<Wiki名>          # 「更新: index」と出る
```

ブラウザでトップページに「確認」が出たら、足した 1 行を消してもう一度 `updatepage` を実行します。

## 3. リンク検査のツールを置く

**済んでいるか:** `~/wikiSystem/checklinks.py` があれば、飛ばせます。

Wiki のリンク切れを調べる `checklinks.py` は、wikiSystem に同梱されています。AI が `./checklinks.py` で呼べるように、wikiSystem のルートへ写します。

```bash
cd ~/wikiSystem
cp wikidata/_system/attach/PageEdit/AI_Collabo/howto4ai/checklinks.py .
chmod +x checklinks.py
./checklinks.py <Wiki名>               # 「リンク不良 0 件」と出る
```

次は [AI エージェントへの指示](../AgentPrompt) です。
