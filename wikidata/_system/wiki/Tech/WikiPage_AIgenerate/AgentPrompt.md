# AI エージェントへの指示

#code()

**Claude Code を起動し、GitHub のリポジトリと Wiki の両方を管理させるための指示**です。
[作業フォルダと Wiki を用意する](/Tech/WikiPage_AIgenerate/ProjectSetup) まで済んでいる前提です。

## 1. 起動する

**済んでいるか:** `claude --version` で版が出れば、Claude Code は入っています。入っていなければ、Claude Code の案内に従って先に入れてください（ここでは扱いません）。

作業フォルダ（リポジトリ）で起動します。**Wiki のフォルダは作業フォルダの外にある**ので、`--add-dir` で書き込める場所に加えます。

```bash
cd ~/work/<リポジトリ名>
claude --add-dir ~/wikiSystem
```

起動したあとで足すこともできます（`/add-dir ~/wikiSystem`）。**最初は許可を聞かれる**ので、中身を見てから許可します。

## 2. 決まりを `CLAUDE.md` に置く

**すでに `CLAUDE.md` があるなら、作り直さず**、下の雛形のうち足りない項目（Wiki の場所・`updatepage`・push の決まり）だけを足します。

最初の 1 回、次の内容で作業フォルダに `CLAUDE.md` を作らせます。**Claude Code に「次の内容で CLAUDE.md を作って」と頼み、`<…>` を自分の値にしたものを渡す**のが簡単です。
作ったあとは、起動のたびに自動で読まれます。

~~~~markdown
# <プロジェクト名>

<このプロジェクトが何か、1〜2 行>

## 置き場所

| 何 | どこ |
|---|---|
| コード（GitHub のリポジトリ） | このフォルダ（`~/work/<リポジトリ名>`）。リモートは `origin` |
| 文書（Wiki） | `~/wikiSystem/wikidata/<Wiki名>/wiki/`。Wiki 名は `<Wiki名>` |
| Wiki システム | `~/wikiSystem`（`./wiki.py` はここで実行する） |

## 進めかた

- **コードは GitHub、文書は Wiki が正。**同じことを 2 か所に書かず、片方からリンクする
- Wiki ページを書くときは、先に `~/wikiSystem/wikidata/_system/wiki/Tech/WikiPage_AIgenerate/howto4ai.md` を読み、その規則（置き場所・記法・ChangeLog の書きかた）に従う
- **Wiki のファイルを書き換えたら、毎回 `cd ~/wikiSystem && ./wiki.py updatepage =<Wiki名>` を実行する**（目次・検索・一覧に出なくなるため）
- Wiki のリンクは、`~/wikiSystem` で `./checklinks.py <Wiki名>` を実行して 0 件を確かめる（`checklinks.py` の置きかたは [作業フォルダと Wiki を用意する](/Tech/WikiPage_AIgenerate/ProjectSetup) の 5）
- 作業のたびに、Wiki の `ChangeLog/YYYY-MM-DD.md` へ「何をしたか・なぜそうしたか・失敗」を書く（日付は今日の日付。既にあるファイルには追記する）
- 他の Wiki（`_system` など）と `~/wikiSystem` のプログラムは書き換えない

## git

- 作業ごとにコミットする。コミットメッセージは日本語で、何をしたかが分かるように
- **`git push` は、私が指示したときだけ行う**
- 秘密鍵・パスワード・`.env` はコミットしない
~~~~

#note(type=info){{
書き換えない範囲と push の決まりは、**AI に任せきりにしないための歯止め**です。慣れて任せてよいと思ったら、自分の判断で緩めます。
}}

## 3. 最初の指示の例

`CLAUDE.md` を置いたら、会話の最初に次のように頼みます。

~~~
このプロジェクトを始めます。次のことをしてください。

1. CLAUDE.md を読んで、置き場所と進めかたを確かめる
2. Wiki（<Wiki名>）の index.md に、プロジェクトの概要を書く（わからない点は私に聞く）
3. ChangeLog の最初のページを作り、今日やったことを書く
4. updatepage とリンク検査を行い、結果を報告する
5. コミットする（push はしない）
~~~

## うまくいかないとき

| 症状 | 原因と対処 |
|---|---|
| Wiki のファイルを書こうとして許可を求められ続ける | `--add-dir ~/wikiSystem` を付けずに起動した。付けて起動し直す |
| 書いたページが Wiki に出ない | `updatepage` を忘れている。`CLAUDE.md` の「進めかた」に書いてあるか確かめる |
| AI が `_system` の Wiki を書き換えた | `CLAUDE.md` の禁止が効いていない。履歴タブ（編集画面）から戻し、指示を足す |
| 指示を毎回忘れる | `CLAUDE.md` に書いていない。会話で言ったことは次の会話に残らない |
