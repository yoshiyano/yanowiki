# PukiWikiから移す

手元のPukiWikiのページと添付ファイルから、新しいWikiを作ります。サーバーで次のコマンドを実行します。

```bash
./wiki.py convwiki 1ev-c Prog1
```

`~/syncthing/pukiwiki/1ev-c/` をもとに `wikidata/Prog1/` ができ、`/=Prog1/` で開けます。
PukiWiki記法は、そのまま読めます（[PukiWiki記法](/Syntax/PukiWiki)）。

| 書きかた | 何をするか |
|---|---|
| `convwiki <元> <Wiki名>` | 写して新しいWikiを作る。管理者の最初のパスワードを聞かれます |
| `--dry-run` | 何も書かずに、何をどこへ写すかだけを出す |
| `--title` | トップページの見出し（省略するとWiki名） |
| `--password` | 管理者の最初のパスワード（省略すると聞かれます） |
| `--src-root` | 変換元の置き場所（既定は `~/syncthing/pukiwiki`） |
| `--include-system` | PukiWikiの設定ページ（`:config` など）も写す |
| `--include-stock` | PukiWiki付属のページも写す |
| `--toppage` | `index` にするページ（省略するとPukiWikiの `$defaultpage`） |
| `--theme` | 写したWikiで使うテーマ（既定は `pukiwiki_default`） |

変換元は、名前だけなら既定の置き場所の下、`/` を含むならパスとして読みます。
**まず `--dry-run` で確かめてから実行します。**

- **すでにあるWikiには書き込みません。** 入れ直すときは `wikidata/<Wiki名>/` を消してから実行します
- 変更の履歴・カウンタ・PukiWiki付属のページは写りません。元のPukiWikiを残しておけば、そちらで読めます
- このシステムに無いプラグインは、ページの中にエラーとして出ます。使われている数は、実行時の報告に出ます

写しかたの細かい決まりは [PukiWikiのデータを移す仕組み](/Tech/ConvWiki) にあります。
