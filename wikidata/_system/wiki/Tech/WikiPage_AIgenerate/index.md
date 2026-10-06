# AI をつかったプロジェクト管理方法

github と wiki を使ってコード管理とドキュメント管理を行う。

**コードは GitHub のリポジトリ、文書はこのシステムの Wiki** に置き、AI エージェント（Claude Code）に両方を更新させる準備を、
ここにまとめます。

## こんな人向けです

**Wiki システムを入れたばかりで、使いかたもまだよく分かっていない人**を想定しています。次のような状況を例に、
最初から順に説明します。

- Wiki システムを入れたばかり（[入れかた](/InstallGuide)）
- GitHub のアカウントはあるが、まだ使い込んでいない（ssh 鍵や自分のリポジトリは無い）
- Claude Code は入れてある

**これは条件ではありません。すでに済んでいることは、やり直さず飛ばしてください。**
各ページの冒頭に、「済んでいるか」の確かめかたを置いています（確かめて済んでいれば、その手順は不要です）。

| すでに済んでいること | 確かめかた | 飛ばしてよい手順 |
|---|---|---|
| GitHub に ssh でつながる | `ssh -T git@github.com` が `successfully authenticated` と答える | [GitHub と ssh でつなぐ](/Tech/WikiPage_AIgenerate/GithubSetup) の 1〜3 |
| git に名前を教えてある | `git config --global user.name` に名前が出る | 同 4 |
| プロジェクトの GitHub リポジトリがある | GitHub の画面に出ている | 同 5 |
| リポジトリを clone してある | 作業フォルダで `git remote -v` が GitHub の URL を出す | [作業フォルダと Wiki を用意する](/Tech/WikiPage_AIgenerate/ProjectSetup) の 1 |
| プロジェクトの Wiki がある | `ls ~/wikiSystem/wikidata/` に名前が並ぶ | 同 3 |
| Claude Code に `CLAUDE.md` がある | 作業フォルダに `CLAUDE.md` がある | [AI エージェントへの指示](/Tech/WikiPage_AIgenerate/AgentPrompt) の 2 |

たとえば**すでに自分の Wiki を作ってある人**は、`_system` 以外の Wiki があってもそのまま使えます。新しく作るのは、プロジェクト用の Wiki だけです。

## 進める順番

| 順 | ページ | することを 1 行で |
|---|---|---|
| 1 | [GitHub と ssh でつなぐ](/Tech/WikiPage_AIgenerate/GithubSetup) | 鍵を作って GitHub に登録し、最初のリポジトリを作る |
| 2 | [作業フォルダと Wiki を用意する](/Tech/WikiPage_AIgenerate/ProjectSetup) | リポジトリを clone して AI 用の置き場にし、プロジェクトの Wiki を作る |
| 3 | [AI エージェントへの指示](/Tech/WikiPage_AIgenerate/AgentPrompt) | Claude Code を起動し、GitHub と Wiki で管理させる指示を渡す |
| 4 | [動作確認: Hello world](/Tech/WikiPage_AIgenerate/HelloWorld) | 簡単なタスクを頼み、GitHub と Wiki が更新されるのを見る |
| 参考 | [AI エージェントに Wiki ページを書かせる](/Tech/WikiPage_AIgenerate/howto4ai) | Wiki ページの置き場所・記法・書きかたの原則。AI にも読ませる |

## 全体の形

```
~/wikiSystem/                 Wiki システム（git clone したもの）
  wikidata/<Wiki名>/            プロジェクトの Wiki（文書の正）
~/work/<リポジトリ名>/         GitHub のリポジトリを clone したもの（コードの正）。Claude Code はここで起動する
```

- **コードは GitHub、文書は Wiki が正。**どちらも AI が更新し、人が確かめる
- `wikidata/` の下は wikiSystem の git の対象外なので、**Wiki の中身は GitHub に上がらない**（上の形のとおり別の置き場所）

#note(type=warn){{
**Wiki の中身を GitHub にも残す方法は、まだ決めていません。**いまの手順では、Wiki のバックアップは
`wikidata/<Wiki名>/` を自分でコピーするしかありません。決まったらここに書きます。
}}

上の置き場所（`~/work/…`）は例で、好きな場所でよい。ここではこの形で説明します。
