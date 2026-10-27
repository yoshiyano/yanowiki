# 公開版からの更新の仕組み

使いかたは [保守と運用](/AdminGuide/Maintenance#公開版から更新する) にあります。このページは仕組みの説明です。

公開版（GitHub の [yanowiki](https://github.com/yoshiyano/yanowiki)）に新しいバージョンが出ると、既定のWikiの
タイトル右端の info で知らせます。押すと `/.admin/update` が開き、いまのバージョン・最新のバージョン・その間の
[更新履歴](/ChangeLog) を見せます。「更新して再起動する」で公開版を取り込み、サービスを再起動します。
中身は `_sys/wikilib/sysupdate.py` です。

## 設計者の決定（2026-10-27）

info に update を出し、押したら現在・最新のバージョンと更新履歴を見せ、更新のボタンで最新版を取り込んで再起動する
（設計者の指示）。次の細部はクロコの案で、設計者が承認した（「A〜F すべてクロコ案で進めて」）。

| 項目 | 決めたこと |
|---|---|
| 知らせる相手 | Wiki名を含まないURLで開いた既定のWikiで、**管理者と、再起動を許された助手だけ**（`/.restart` と同じ範囲。権限は `site.restart`）。全員に出すと、古いバージョンのまま動いていることが外から分かる |
| 最新版の調べかた | yanowiki の main にある `wiki.py` の `VERSION` と `wikidata/_system/wiki/ChangeLog/index.md` を、そのまま取ってきて読む。問い合わせはサーバーが裏で行い、間隔を空ける（下の「最新版を調べる」）。つながらなければ何も知らせない |
| 更新のしかた | clone し直さず、[インストールの案内](/InstallGuide#更新する) と同じ `git fetch` → `git reset --hard` → `uv sync --inexact` → 再起動。途中で失敗したら、更新の前のコミットへ戻す |
| 更新できるとき | 作業ツリーが公開版のまま（origin が yanowiki・ブランチが main・`wikidata/_system/` の外に手元の変更が無い）のときだけ。`_system` のWikiの手直しは消えるので、画面で知らせる |
| 画面の場所 | `/.admin/update`（管理の道具は `/.admin` の下へつなぐ。2026-09-08） |
| 自動の更新 | 設定でオンにしたら勝手に更新する仕組みは作らない。再起動の失敗や `_system` の上書きを、誰も見ていないときに起こさないため |

あとから設計者が決めたこと（2026-10-27、更新の試験のため）:

- 確かめる間隔は、試験のあいだ暫定で10分にし、1.2.0 で1日に戻した（`CHECK_INTERVAL`）
- 見に行くブランチを `config/server.yaml` の `update.branch` で替えられる（既定 `main`）。試験は yanowiki の
  試験ブランチ `update-test` に置いた版で行う
- **先にブランチの最新のコミットを1つ聞き、そのコミットを指して読み、取り込む**（下の「最新版を調べる」）。
  ブランチ名で raw を読むと、ファイルごとに数分間古い内容が返り、「バージョンは新しく、更新履歴は古い」
  食い違いが起きたため（2026-10-27 の試験で起きた）

## 最新版を調べる

1. GitHub の API（`https://api.github.com/repos/yoshiyano/yanowiki/commits/<ブランチ>`、`Accept: application/vnd.github.sha`）に、
   ブランチの最新のコミット（40桁）を聞く（`latest_commit`）。認証なしで1時間に60回まで（1日1回と「今すぐ調べる」なら収まる）
2. そのコミットを指した raw（`https://raw.githubusercontent.com/yoshiyano/yanowiki/<コミット>/…`）から、`wiki.py` と
   更新履歴を読む。コミットを指した raw は中身が変わらないので、古い控えの影響を受けない
3. 覚えるのは、バージョン・更新履歴・コミット。更新の画面は、このコミットをボタンに持たせる


- 権限のある人が既定のWikiを開くと、info の知らせ（`pagenotice.update_notice`）が、覚えている最新版を見る。
  前に調べてから `CHECK_INTERVAL`（1日）たっていれば、裏のスレッドで調べ直す（`check_in_background`）。
  ページの表示は待たせない。調べ直した結果は、次に開いたときに出る
- 起動時に始める形にしていないのは、gunicorn などの WSGI で動かしたときに起動時の処理が通らないため
  （クロコの実装例）。更新の画面の「今すぐ調べる」でも調べ直せる
- いまのバージョンは、手元の `wiki.py` から公開版と同じ読みかた（`parse_version`）で読む（クロコの実装例。
  値を `wiki.py` の1か所に保つため）
- 更新履歴は、見出しが `## <バージョン>（日付）` の節のうち、いまより新しいものだけを、書いてある順に見せる
  （`changelog_sections`）。更新履歴が取れなくても、バージョンは知らせる（1.1.1 までの公開版には更新履歴のページが無い）

## 更新する

`POST /.admin/update`（`cmd=update`、`commit=<画面で見せたコミット>`）で、もう一度作業ツリーを確かめ、
最新のコミットを聞き直す。画面で見せたコミットと違えば（押すまでの間にもっと新しい版が出た・調べられなかった）、
見せていない版を取り込まないよう断り、画面を開き直してもらう。同じなら取り込む（`run_update`）。

1. `git rev-parse HEAD` で、いまのコミットを控える
2. `git fetch --depth 1 origin <コミット>`。失敗したら、何も変えずにやめる
3. `git reset --hard FETCH_HEAD`。手元のブランチは main のままで、中身を取ってきたものに合わせる
   （試験ブランチは main と履歴がつながっていなくてよい）
4. `uv sync --inexact`（`UV_PROJECT_ENVIRONMENT=_venv`）。`uv` は PATH のほか、インストールの案内が入れる
   `~/.local/bin` なども探す（`find_uv`）
5. 3・4 のどちらかが失敗したら、控えたコミットへ `git reset --hard` で戻し、`uv sync --inexact` をやり直す
6. 取り込めたら、助手の操作の記録に残し（種類 `update`）、`/.restart` と同じ方法で再起動する
   （[サービスの再起動の仕組み](/Tech/Restart)）。再起動の方法が分からない動かしかたでは、画面にそう出る

送信は POST だけで、入口で別のサイトからの送信を断る（[ログインの仕組み](/Tech/Accounts/Login#別のサイトから送られた-post-を断る)）。
関門は `/.restart` と同じ `sysui.require_on_default_farm`（権限 `site.restart`）。

## 試験

`tests/test_sysupdate.py`。GitHub への問い合わせと、git・uv の実行は差し替える。作業ツリーの確かめは、
一時的な git の作業ツリーを作って確かめる。
