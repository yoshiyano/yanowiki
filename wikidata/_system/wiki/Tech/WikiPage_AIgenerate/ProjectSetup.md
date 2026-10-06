# 作業フォルダと Wiki を用意する

#code()

[GitHub と ssh でつなぐ](/Tech/WikiPage_AIgenerate/GithubSetup) まで済んでいる前提で、**リポジトリを手元に取得して AI の作業フォルダにし、プロジェクトの Wiki を作ります。**

## 1. リポジトリを clone する

**済んでいるか:** 作業フォルダがすでにあり、`git remote -v` が GitHub の URL を出すなら、飛ばせます。

GitHub のリポジトリの SSH の URL（`git@github.com:<アカウント名>/<リポジトリ名>.git`）を使います。

```bash
mkdir -p ~/work && cd ~/work
git clone git@github.com:<アカウント名>/<リポジトリ名>.git
cd <リポジトリ名>
git branch --show-current       # main と出る
```

`~/wikiSystem` とは別のフォルダにします。**wikiSystem の中に clone しない**（wikiSystem 自身の git と混ざります）。

| 症状 | 原因と対処 |
|---|---|
| `Permission denied (publickey)` | ssh 鍵の登録が済んでいない。[GitHub と ssh でつなぐ](/Tech/WikiPage_AIgenerate/GithubSetup) の 3 へ |
| `Repository not found` | URL の打ち間違い、または Private のリポジトリを別のアカウントで開いている |

## 2. AI 用の作業フォルダにする

**済んでいるか:** `.gitignore` と `CLAUDE.md` がすでにあれば、足りないものだけ足します。

Claude Code は、起動したフォルダの `CLAUDE.md` を毎回読みます。**ここに、プロジェクトの決まりと Wiki の場所を書いておく**と、会話のたびに説明し直さずに済みます。

```bash
cd ~/work/<リポジトリ名>
printf '%s\n' '.claude/worktrees/' '.claude/settings.local.json' > .gitignore
```

`CLAUDE.md` の中身は [AI エージェントへの指示](/Tech/WikiPage_AIgenerate/AgentPrompt) に雛形があります。ここでは、先に Wiki を作ります。

## 3. プロジェクトの Wiki を作る

**済んでいるか:** `ls ~/wikiSystem/wikidata/` にプロジェクト用の Wiki の名前があれば、作らずにその Wiki を使います（`<Wiki名>` をその名前にして、4 から続けます）。

**Wiki システムを動かし、管理者でログインして、[新しい Wiki を作る](/NewWikiGuide) 画面で作ります。**

1. サーバを動かす（動いていなければ）

   ```bash
   cd ~/wikiSystem
   ./wiki.py
   ```

2. ブラウザで管理者（`admin`）でログインし、管理の窓口（`/.admin`）の「新しいWikiを作る」を開く。管理者のパスワードをまだ決めていなければ、`./wiki.py initusers`（[入れかた](/InstallGuide) の 7）
3. 項目を入れて「作る」

| 項目 | 入れるもの |
|---|---|
| 名前 | **リポジトリ名に揃える**（例: `hello-agent`）と、どちらも同じプロジェクトだと分かる。半角英数字と `-` `_` |
| 記法 | **Markdown。**PukiWiki 記法の雛形が残らず、AI にも書かせやすい |
| 使いかた | 迷ったら一番上。**あとで変えられる** |

作ると、`~/wikiSystem/wikidata/<Wiki名>/` ができ、`http://127.0.0.1:8619/=<Wiki名>/` で開けます。

```bash
ls ~/wikiSystem/wikidata/               # <Wiki名> と _system が並ぶ
ls ~/wikiSystem/wikidata/<Wiki名>/wiki  # index.md と mainmenu.md がある
```

## 4. つながりを確かめる

AI に頼む前に、手で 1 回、書き込みと取り込みができることを確かめます。

```bash
cd ~/wikiSystem
echo '確認' >> wikidata/<Wiki名>/wiki/index.md
./wiki.py updatepage =<Wiki名>          # 「更新: index」と出る
```

ブラウザでトップページに「確認」が出たら、足した 1 行を消してもう一度 `updatepage` を実行します。

## 5. リンク検査の道具を置く

**済んでいるか:** `~/wikiSystem/checklinks.py` があれば、飛ばせます。

Wiki のリンク切れを調べる `checklinks.py` は、wikiSystem に同梱されています。AI が `./checklinks.py` で呼べるように、wikiSystem のルートへ写します。

```bash
cd ~/wikiSystem
cp wikidata/_system/attach/Tech/WikiPage_AIgenerate/howto4ai/checklinks.py .
chmod +x checklinks.py
./checklinks.py <Wiki名>               # 「リンク不良 0 件」と出る
```

次は [AI エージェントへの指示](/Tech/WikiPage_AIgenerate/AgentPrompt) です。
