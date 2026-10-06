# GitHub と ssh でつなぐ

#code()

**このパソコンから、パスワードなしで GitHub に push・pull できるようにします。**ssh 鍵を作り、公開鍵だけを GitHub に登録します。

**すでにできていれば、この手順は要りません。**次の 1 行を試してください。

```bash
ssh -T git@github.com
```

`Hi <アカウント名>! You've successfully authenticated` と出れば、鍵の作成・登録（1〜3）は済んでいます。4（git の名前）へ進んでください。
`Permission denied (publickey)` なら、これから作ります。

## 1. 鍵を作る

端末で作ります。`<メールアドレス>` は、鍵の持ち主を見分ける印（コメント）です。何でもよいので、どのパソコンの鍵か分かる文字にしておくと、
あとで GitHub の画面で見分けやすくなります。

```bash
ssh-keygen -t ed25519 -C "<メールアドレス または パソコンの名前>"
```

| 聞かれること | 答え |
|---|---|
| `Enter file in which to save the key` | そのまま Enter（`~/.ssh/id_ed25519` になる） |
| `Enter passphrase` | **決めることを勧める。**鍵ファイルを盗まれても使われない。空でも動く |

できるもの:

| ファイル | 何か | 扱い |
|---|---|---|
| `~/.ssh/id_ed25519` | **秘密鍵** | **誰にも渡さない。**GitHub にも貼らない |
| `~/.ssh/id_ed25519.pub` | **公開鍵** | これを GitHub に登録する |

`id_ed25519` の `ed25519` は鍵の種類の名前で、`-t rsa` で作った鍵なら `id_rsa.pub` になります。以降はお使いの名前に読み替えてください。
すでに `~/.ssh/id_*.pub` があれば、新しく作らずそれを使えます（`ls ~/.ssh/` で確かめる）。同じ名前の鍵を上書きすると、前の鍵は使えなくなります。

## 2. 公開鍵を GitHub に登録する

公開鍵を表示して、**1 行ぜんぶ**（`ssh-ed25519 …` で始まり、最後のコメントまで）をコピーします。

```bash
cat ~/.ssh/id_ed25519.pub
```

GitHub の画面で:

1. 右上のアイコン → **Settings**
2. 左の **SSH and GPG keys** → **New SSH key**
3. **Title**: パソコンの名前（例: `labo-pc`）。**Key type**: `Authentication Key`
4. **Key** に、コピーした 1 行を貼って **Add SSH key**（パスワードを聞かれたら入れる）

## 3. つながるか確かめる

```bash
ssh -T git@github.com
```

初めてのときは、接続先を信頼するか聞かれます。

```
The authenticity of host 'github.com (…)' can't be established.
ED25519 key fingerprint is SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

表示された指紋が、GitHub が公開している指紋（「GitHub's SSH key fingerprints」のページ）と同じことを確かめて `yes` と答えます。
**次のように出れば成功です**（`Hi` のあとは自分のアカウント名）。

```
Hi <アカウント名>! You've successfully authenticated, but GitHub does not provide shell access.
```

| 症状 | 原因と対処 |
|---|---|
| `Permission denied (publickey).` | 公開鍵が登録されていない、または別の鍵を使っている。登録した `.pub` と `ls ~/.ssh/` の鍵が合うか確かめる |
| `Host key verification failed.` | 指紋の確認で `yes` と答えていない、または `~/.ssh/known_hosts` が壊れている |
| `Bad owner or permissions on …` | `chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_ed25519` |

## 4. git に自分の名前を教える

**済んでいるか:** `git config --global user.name` と `git config --global user.email` に値が出れば、飛ばせます。

コミットに残る名前です。GitHub の公開メールを避けたいときは、GitHub の画面（Settings → Emails）に出る `…@users.noreply.github.com` を使えます。

```bash
git config --global user.name  "<名前>"
git config --global user.email "<メールアドレス>"
```

## 5. 最初のリポジトリを作る

**このプロジェクト用のリポジトリがすでに GitHub にあれば、飛ばせます**（次のページの clone で、その URL を使います）。

GitHub の画面で **New repository**（右上の `+` → New repository）。

| 項目 | 入れるもの |
|---|---|
| Repository name | プロジェクトの名前（半角英数字と `-`。例: `hello-agent`） |
| Public / Private | 迷ったら **Private**。あとから変えられる |
| Add a README file | **チェックを入れる。**中身のあるリポジトリにしておくと、次の clone だけで始められる |
| .gitignore・License | 空でよい（あとで足せる） |

**Create repository** を押すと、リポジトリのページが開きます。緑の **Code** ボタン → **SSH** のタブに出る `git@github.com:<アカウント名>/<リポジトリ名>.git` が、次のページで使う URL です。

次は [作業フォルダと Wiki を用意する](/Tech/WikiPage_AIgenerate/ProjectSetup) です。
