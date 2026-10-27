# Neovim のプラグイン

[外部エディタ連動の編集](..) で、**エディタ側**にインストールする Neovim のプラグイン（wikiedit）です。
ブラウザ側の拡張機能（[Chrome](../Chrome)・[Firefox](../Firefox)）もインストールしてください。

Neovim 0.9 以上で動きます（Vim では動きません）。ほかのプラグインは要りません。

## インストール
#attachls()

1. 上の一覧から `wikiedit.lua` をダウンロードする（一覧の日時が、更新した日時です）
2. `~/.config/nvim/lua/` に置く

   ```sh
   mkdir -p ~/.config/nvim/lua
   mv wikiedit.lua ~/.config/nvim/lua/
   ```

3. `init.lua` に書く（`init.vim` を使っているときは `lua require("wikiedit").setup()`）

   ```lua
   require("wikiedit").setup()
   ```

4. Neovim を起動し直す

### 動いているかを確かめる

`:WikiEditVersion` で、プラグインの更新日時と「（4100 で待ち受けています）」が出ます。
「（ほかのエディタが待ち受けています）」のときは、先に起動した Neovim（か、同じポート番号のほかの
エディタ）が待ち受けています。

## 使う

編集画面で「外部エディタにつなぐ」を押すと、`wikiedit://<Wiki のアドレス>/ページ名.txt`
（Markdown のページは `.md`）というバッファが、新しいタブページで開きます。

#img(つないだところ（xterm の中の Neovim）>/PageEdit/EditorSyncGuide/neovim.png)

初めての Wiki から接続したときは、「http://wiki.example.com からの接続を許しますか？」と
いちばん下の行で尋ねます。許可すると `~/.local/share/nvim/associated_wiki.txt` に覚え、次からは
尋ねません。許さなかった Wiki サイトは、その Neovim を閉じるまでつながりません。
`localhost` と `127.0.0.1` の Wiki は尋ねずにつなぎます。
覚えた Wiki の許可を取り消すときは、`associated_wiki.txt` からそのアドレスの行を消します。

#img(初めての Wiki から接続したとき>/PageEdit/EditorSyncGuide/neovim-ask.png)

| 操作 | |
|---|---|
| `:w` | 編集画面の保存を押す（変更が無ければ編集を終える。詳しくは [エディタから保存したとき](/PageEdit/EditorSyncGuide#エディタから保存したとき)） |
| `:bd` | バッファを閉じる（編集画面には「エディタ側で閉じました」と出る） |
| `:WikiEditAttach` | ページの添付ファイルを一覧から選び、本文での書きかた（`[[::a.zip]]` など）をカーソルの後ろに挿入する |
| `:WikiEditAttachCopy` | 選んだ添付ファイルの書きかたを、挿入せずにレジスタ（`"` と、使えれば `+`）にコピーする |

Wiki のバッファを出しているウィンドウの上の行（winbar）に、ページの添付ファイルの数が出ます
（例: `wikiedit: 添付 3件`。無ければ `添付 0件`）。数は `vim.b.wikiedit_attachments` にもあります。

キーに割り当てるときは、`init.lua` に次のように書きます（キーは一例です）。

```lua
vim.keymap.set("n", "<Leader>wa", "<Cmd>WikiEditAttach<CR>")
```

`:WikiEditStop` で待ち受けをやめ、Wiki のバッファを閉じます。`:WikiEditStart` で始め直します。

本文は打つたびに編集画面へ送るので、バッファに変更フラグ（`[+]`）は残りません。
ウィンドウを閉じてもバッファは残ります。つなぐのをやめるときは `:bd` で閉じます。

Neovim を同じパソコンで複数動かしているときは、最初に起動した Neovim が待ち受けます。ほかの
Neovim は5秒ごとに確かめ、待ち受けていた Neovim を閉じると、残っている Neovim のどれかが
引き継ぎます。

### 編集画面との通信が切れたとき

通信が切れても、Neovim での編集はそのまま続けられます。ウィンドウの上の行（winbar）の、添付ファイルの数のあとに状態が出ます（例: `wikiedit: 添付 3件 ｜ 切断（…）`）。

| winbar の添付ファイルの数のあと | 状態 |
|---|---|
| （出ない） | つながっている |
| `再読み込み中` | 保存などで、編集画面が再読み込みしている。すぐ戻る（10 秒たっても戻らなければ「切断」になる） |
| `応答なし` | つながっているが、編集画面から 45 秒応答がない。変更は送らずにため、応答が戻ったら送る |
| `切断` | 通信が切れている。同じタブの編集画面がつなぎ直したら送る |

まだ送っていない変更があるときは `・未送信あり` が付きます。状態は `vim.b.wikiedit_state`（`connected`・
`reloading`・`stale`・`disconnected`）にもあるので、自分のステータスラインに出すこともできます。
送っていない変更があるあいだは、閉じずに残します。

つなぎ直したときは、最後にそろえた本文を基準に、次のように合わせます。

| 切れているあいだに変わったもの | 合わせかた |
|---|---|
| Neovim だけ | Neovim の変更を編集画面に送る |
| 編集画面だけ | 編集画面の本文に合わせる |
| 両方 | 最後に変えたほうに合わせる。合わせなかったほうの本文は消さずに残す（Neovim は「控え」、編集画面はブラウザの中） |

## 設定

`setup()` に表で渡します。

```lua
require("wikiedit").setup({ port = 4100, display = "split" })
```

| 項目 | 既定 | |
|---|---|---|
| `port` | 4100 | 待ち受けるポート番号。編集画面の「設定」とそろえる |
| `autostart` | `true` | `setup()` で待ち受けを始める（`false` なら `:WikiEditStart` で始める） |
| `associated_file` | `~/.local/share/nvim/associated_wiki.txt` | 許した Wiki のアドレスを覚えておくファイル |
| `allow_extensions` | `true` | ブラウザ拡張機能を通した接続も受け付けるか（受け付けるときも、Wiki のアドレスで許すかを決める） |
| `display` | `"tab"` | バッファの表示方法（`"tab"` 新しいタブページ・`"split"` 分割したウィンドウ・`"current"` 今のウィンドウ・`"none"` 出さない） |
| `filetypes` | Markdown は `markdown`、PukiWiki は `text` | 書きかたごとの filetype |
| `takeover_interval` | 5 | ほかのエディタが待ち受けているとき、いなくなったかを確かめる間隔（秒） |
| `keep_seconds` | 10 | 保存などで編集画面が再読み込みされるあいだ、バッファを保つ秒数（タブを閉じたときは待たずに閉じる） |
| `stale_seconds` | 45 | 編集画面から何も届かないまま、この秒数がたったら「応答なし」とみなす |

## 新しいバージョンにするとき

新しい `wikiedit.lua` で置き換え、Neovim を起動し直します。
