# 動作確認: Hello world

#code()

**AI エージェントに簡単なプログラムを作らせ、GitHub と Wiki の両方が更新されるのを見て、つながっていることを確かめます。**
[AI エージェントへの指示](/Tech/WikiPage_AIgenerate/AgentPrompt) の `CLAUDE.md` を置き、Claude Code を `--add-dir ~/wikiSystem` 付きで起動してあるところから始めます。

#note(type=info){{
このページの流れと出力は、**手順どおりの通し実行までは確かめていません**（2026-10-06 時点）。表示される文言は目安で、実際は AI の言い回しによって違います。
}}

## 1. 頼む

Claude Code に、次のように頼みます。

~~~
Python で「Hello, world!」と表示する hello.py を作って、実行して結果を確かめてください。
そのあと、やったことを Wiki の ChangeLog に書き、コミットしてください。
~~~

`CLAUDE.md` に決まりを書いてあるので、**Wiki に書く・`updatepage` を実行する・コミットする（push はしない）** が自動で付いてきます。途中で許可を聞かれたら、内容を見て許可します。

## 2. AI が行うこと（見てほしいところ）

| 順 | AI の操作 | 見るところ |
|---|---|---|
| 1 | `hello.py` を作る | 作業フォルダに `hello.py` ができる |
| 2 | `python3 hello.py` を実行する | `Hello, world!` と表示される |
| 3 | Wiki の `ChangeLog/<今日の日付>.md` を書く | `~/wikiSystem/wikidata/<Wiki名>/wiki/ChangeLog/` にファイルができる |
| 4 | `./wiki.py updatepage =<Wiki名>` を実行する | `追加: ChangeLog/…` と出る |
| 5 | `./checklinks.py <Wiki名>` を実行する | `リンク不良 0 件` |
| 6 | `git commit` する | `git log` に 1 件増える |

## 3. Wiki が更新されたことを見る

ブラウザで `http://127.0.0.1:8619/=<Wiki名>/ChangeLog` を開きます。**今日の日付のページが一覧に出て、開くと「何をしたか」が書かれていれば成功です。**

## 4. GitHub に反映して見る

`CLAUDE.md` で push を止めてあるので、**中身を確かめてから、自分で（または AI に頼んで）push します。**

```bash
cd ~/work/<リポジトリ名>
git log --oneline -3
git push
```

GitHub のリポジトリのページを開き直すと、`hello.py` と、コミットの一覧に今の変更が出ます。

| 場所 | 更新されたこと |
|---|---|
| GitHub | `hello.py`（と、あれば `CLAUDE.md`）のコミット |
| Wiki | `ChangeLog/<今日の日付>` ページ（と `index` の更新） |

**Wiki の更新は GitHub には上がりません**（[全体の形](/Tech/WikiPage_AIgenerate#全体の形)）。GitHub に出るのはコードの変更だけです。

## うまくいかないとき

| 症状 | 原因と対処 |
|---|---|
| Wiki の ChangeLog に出ない | `updatepage` を実行していない。AI に「updatepage をして」と頼む |
| AI が Wiki に書かずコードだけ作った | `CLAUDE.md` を読めていない。作業フォルダで起動したか、`CLAUDE.md` の場所を確かめる |
| `git push` が `Permission denied (publickey)` | [GitHub と ssh でつなぐ](/Tech/WikiPage_AIgenerate/GithubSetup) の 3 へ |
| `git push` が `rejected` | GitHub 側にも変更がある。`git pull --rebase` のあとで再度 push |
