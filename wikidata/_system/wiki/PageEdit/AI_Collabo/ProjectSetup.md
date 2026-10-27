# Gitリポジトリの作成とclone

#code()

[ssh経由のGitHubの準備](../GithubSetup) まで済んでいる前提で、**GitHub にリポジトリを作り、手元へ取得（clone）して AI の作業フォルダにします。**

ここでいう**リポジトリ**は、Gitがファイルと変更履歴をまとめて管理する場所です。
**clone（クローン）**は、GitHub上のリポジトリを変更履歴ごと自分のパソコンに複製し、
GitHubとの接続も設定する操作です。以降、作業フォルダでファイルを編集し、Gitを使って変更を記録・共有します。

## 1. リポジトリを作る

**このプロジェクト用のリポジトリがすでに GitHub にあれば、飛ばせます**（次の 2 の clone で、その URL を使います）。

GitHub の画面で **New repository**（右上の `+` → New repository）。

| 項目 | 入れるもの |
|---|---|
| Repository name | プロジェクトの名前（半角英数字と `-`。例: `hello-agent`） |
| Public / Private | 迷ったら **Private**。あとから変えられる |
| Add a README file | **チェックを入れる。**中身のあるリポジトリにしておくと、次の clone だけで始められる |
| .gitignore・License | 空でよい（あとで足せる） |

**Create repository** を押すと、リポジトリのページが開きます。緑の **Code** ボタン → **SSH** のタブに出る `git@github.com:<アカウント名>/<リポジトリ名>.git` が、clone で使う URL です。

## 2. リポジトリを clone（作業用に複製）する

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
| `Permission denied (publickey)` | ssh 鍵の登録が済んでいない。[ssh経由のGitHubの準備](../GithubSetup) の 3 へ |
| `Repository not found` | URL の打ち間違い、または Private のリポジトリを別のアカウントで開いている |

## 3. AI 用の作業フォルダにする

**済んでいるか:** `.gitignore` と `CLAUDE.md` がすでにあれば、足りないものだけ足します。

Claude Code は、起動したフォルダの `CLAUDE.md` を毎回読みます。**ここに、プロジェクトの決まりと Wiki の場所を書いておく**と、会話のたびに説明し直さずに済みます。

```bash
cd ~/work/<リポジトリ名>
printf '%s\n' '.claude/worktrees/' '.claude/settings.local.json' > .gitignore
```

`CLAUDE.md` の中身は [AI エージェントへの指示](../AgentPrompt) に雛形があります。ここでは、先に Wiki を用意します。

次は [wiki ページの準備](../WikiSetup) です。
