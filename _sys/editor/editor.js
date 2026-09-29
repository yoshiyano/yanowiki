/*
 * 編集画面のスクリプト。
 *
 * テーマの theme/ ではなく編集機能側が持ち、/.editor.js として配信される。
 * どのテーマを選んでいても編集画面が同じように動くようにするため。
 *
 * ツールバーの動きは、サーバーが渡す書式定義（MARKUP_FORMATS）だけを見て決める。
 * 記法そのもの（太字が ** なのか '' なのか等）はこのファイルには書かないので、
 * pukiwiki記法などを追加してもこのコードは変更不要。
 *
 * 定義で使える指定（いずれか1つ）:
 *   wrap          … 選択範囲の前後を囲む [開始, 終了]
 *   prefix        … 選択した各行の先頭に付ける（line=true）
 *   block         … 選択範囲を独立した行として前後で囲む [開始, 終了]
 *   template      … 定型文を挿入する（${text} が選択文字列に置き換わる）
 *   palette       … 色のポップオーバーを開く（"fg"/"bg"）。base_colors/
 *                   custom_colors（サーバーが config から差し込む）を選び、
 *                   &color(fg=/bg=){選択}; を挿入する
 *   size_percents … 文字サイズのポップオーバーを開く。プリセット・任意入力の
 *                   増減%から &size(割合%){選択}; を挿入する
 */
/* ---- 何回かに分けて送る（添付ファイルと、本文の一時保存で共用） ----
 * 1回のPOSTで送れる大きさには上限がある（受け取り側は一度メモリに置くため）。
 * **上限を上げてもらうのではなく、送る側で切って何回かに分ける。**
 * 上限を上げると1回ぶんに確保されるメモリがそのまま増え、同時にいくつか
 * 送ったときの合計にも効いてしまう。
 *
 * 1回ぶんの大きさは、サーバーが決めた値を data-chunk-bytes で受け取る。
 */
var wikiSend = (function () {
  function chunkBytesOf(form) {
    var n = parseInt(form.dataset.chunkBytes, 10);
    return n > 0 ? n : 1024 * 1024;
  }

  function newChunkId() {
    var chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    var out = "";
    for (var i = 0; i < 24; i += 1) {
      out += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return out;
  }

  // 送るのは fetch ではなく XMLHttpRequest。fetch では送信の進み具合を
  // 受け取れないので、進捗を出せない（大きなファイルほど、いま何が
  // 起きているのか分からない時間が長くなる）。
  function postForm(action, data, onUp) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", action);
      xhr.withCredentials = true;
      if (onUp && xhr.upload) {
        xhr.upload.addEventListener("progress", function (e) {
          if (e.lengthComputable) onUp(e.loaded, e.total);
        });
      }
      xhr.addEventListener("load", function () {
        resolve({
          ok: xhr.status >= 200 && xhr.status < 400,
          status: xhr.status,
          text: xhr.responseText,
        });
      });
      xhr.addEventListener("error", function () { reject(new Error("通信に失敗しました")); });
      xhr.addEventListener("abort", function () { reject(new Error("送信が止まりました")); });
      xhr.send(data);
    });
  }

  // fields を毎回添えて、blob を切って順に送る。最後の返事を返す。
  // 途中で断られたら、そこで止めてその返事を返す（残りは送らない）。
  function sendChunked(action, fields, blob, name, chunkBytes, onProgress) {
    var total = Math.max(1, Math.ceil(blob.size / chunkBytes));
    var id = newChunkId();
    var index = 0;

    function step() {
      var start = index * chunkBytes;
      var piece = blob.slice(start, Math.min(blob.size, start + chunkBytes));
      var data = new FormData();
      Object.keys(fields).forEach(function (k) { data.append(k, fields[k]); });
      data.append("chunk_id", id);
      data.append("chunk_index", String(index));
      data.append("chunk_total", String(total));
      data.append("chunk_name", name || "");
      data.append("part", piece, "part");
      return postForm(action, data, function (sent) {
        if (onProgress) onProgress(Math.min(blob.size, start + sent));
      }).then(function (res) {
        if (!res.ok) return res;
        index += 1;
        if (onProgress) onProgress(Math.min(blob.size, index * chunkBytes));
        if (index < total) return step();
        return res;
      });
    }
    return step();
  }

  return {
    chunkBytesOf: chunkBytesOf,
    postForm: postForm,
    sendChunked: sendChunked,
  };
})();

// ---- タブ（編集 / 添付ファイル） ----
// 編集フォームとは独立して動かす。新規ページなどフォームの状態に関係なく
// タブは常に切り替えられるようにしたいため。
(function () {
  var shell = document.querySelector(".edit-shell");
  if (!shell) return;

  var tabs = [].slice.call(shell.querySelectorAll(".edit-tab"));
  var panels = [].slice.call(shell.querySelectorAll(".edit-panel"));
  if (!tabs.length || !panels.length) return;

  // JSが動いたときだけ隠す。無効な環境では両方が縦に並んで読める
  shell.classList.add("is-tabbed");

  // 「履歴」タブは、バックアップ管理画面の右側（差分・復元）だけを埋め込んでいる
  // （wikilib.backupui）。ページの選択は、この画面のサイドバーの共通のページ一覧。
  // 履歴の一覧は、そのページ一覧の**下**に、履歴タブのときだけ出す。
  // 履歴が無いページでは、「変更履歴はありません」とだけ出す。
  // **最初に開かれたときに読み込む。** 編集を始めるたびに、履歴の取得を
  // 走らせないため。
  var historyFrame = shell.querySelector(".edit-history-frame");
  var historyEmpty = shell.querySelector(".edit-history-empty");
  var historyList = null;
  var historyLoaded = false;

  function prettyStamp(s) {
    if (!s || s.length !== 13) return s || "";
    return "20" + s.slice(0, 2) + "-" + s.slice(2, 4) + "-" + s.slice(4, 6)
      + " " + s.slice(7, 9) + ":" + s.slice(9, 11) + ":" + s.slice(11, 13);
  }

  function showHistoryList() {
    if (historyList) historyList.hidden = shell.dataset.activeTab !== "history";
  }

  function noHistory(message) {
    historyEmpty.textContent = message || "変更履歴はありません";
    historyEmpty.hidden = false;
  }

  // 履歴はページ自身のURLへ `?cmd=history` のPOSTで読み書きする（wikilib.backupui。
  // 以前は /.backup という別のURLだった。Wiki設計者の指示、2026-09-28）。
  // GETでは閲覧の画面が返るので、データの取得も埋め込みの表示もPOSTで行う
  function loadHistory() {
    if (!historyFrame || historyLoaded) return;
    historyLoaded = true;
    var url = historyFrame.dataset.src;
    var data = new FormData();
    data.append("data", "history");
    fetch(url, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.history || !res.history.length) { noHistory(); return; }
        buildHistoryList(res.page, res.history, url);
      })
      .catch(function () { historyLoaded = false; noHistory("履歴を読み込めませんでした。"); });
  }

  function buildHistoryList(page, history, url) {
    var side = document.querySelector(".edit-side");
    var frameReady = false;
    function pick(key, button) {
      [].forEach.call(historyList.querySelectorAll(".eh-item.is-selected"), function (b) {
        b.classList.remove("is-selected");
      });
      button.classList.add("is-selected");
      if (frameReady) {
        historyFrame.contentWindow.postMessage(
          { type: "wiki-backup-select", page: page, key: key }, window.location.origin);
      }
    }

    historyList = document.createElement("section");
    historyList.className = "eh-list";
    historyList.setAttribute("aria-label", "変更履歴");
    historyList.innerHTML = '<h2 class="panel-title">変更履歴</h2>';
    var first = null;
    history.forEach(function (h) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "eh-item";
      b.innerHTML = '<span class="eh-when">' + prettyStamp(h.stamp) + "</span>"
        + '<span class="eh-stat"><span class="eh-add">+' + h.added
        + '</span> <span class="eh-del">-' + h.removed + "</span></span>";
      b.addEventListener("click", function () { pick(h.key, b); });
      historyList.appendChild(b);
      if (!first) first = { key: h.key, button: b };
    });
    if (side) side.appendChild(historyList);
    showHistoryList();

    // 読み込めたら、いちばん新しい時点を選んだ状態にする
    historyFrame.addEventListener("load", function () {
      frameReady = true;
      pick(first.key, first.button);
    });
    historyFrame.hidden = false;
    // iframe を宛先にしたフォームをPOSTで送って開く（GETで開くと閲覧の画面になる）
    var opener = document.createElement("form");
    opener.method = "post";
    opener.action = url;
    opener.target = historyFrame.name;
    opener.style.display = "none";
    document.body.appendChild(opener);
    opener.submit();
    opener.remove();
  }

  // 編集画面・更新状況は同じ page-editor フォームの中の表示切り替え、
  // 添付ファイルはフォームの外の別セクション、と入れ物の深さが違う。
  // スクロール位置の保存など、中身側だけが知っていればよい後始末は
  // before/after イベントで知らせ、ここでは表示の出し分けに専念する。
  function activate(name, focus) {
    var from = shell.dataset.activeTab;
    shell.dispatchEvent(new CustomEvent("editor-tab-before", { detail: { from: from, to: name } }));
    tabs.forEach(function (tab) {
      tab.setAttribute("aria-selected", tab.dataset.tab === name ? "true" : "false");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.dataset.tab !== name;
    });
    shell.dataset.activeTab = name;
    if (name === "history") loadHistory();
    showHistoryList();
    if (focus) {
      var current = tabs.filter(function (t) { return t.dataset.tab === name; })[0];
      if (current) current.focus();
    }
    // 再読み込みしても同じタブが開くよう、URLにだけ残す（履歴は増やさない）
    try {
      var url = new URL(window.location.href);
      if (name !== "edit") url.searchParams.set("tab", name);
      else url.searchParams.delete("tab");
      url.searchParams.delete("msg");
      url.searchParams.delete("ok");
      window.history.replaceState(null, "", url.toString());
    } catch (e) { /* URLを扱えない環境では何もしない */ }
    shell.dispatchEvent(new CustomEvent("editor-tab-after", { detail: { from: from, to: name } }));
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () { activate(tab.dataset.tab, false); });
    tab.addEventListener("keydown", function (event) {
      var i = tabs.indexOf(tab);
      if (event.key === "ArrowRight") activate(tabs[(i + 1) % tabs.length].dataset.tab, true);
      else if (event.key === "ArrowLeft") activate(tabs[(i - 1 + tabs.length) % tabs.length].dataset.tab, true);
      else return;
      event.preventDefault();
    });
  });

  var initialTab = tabs.some(function (t) { return t.dataset.tab === shell.dataset.activeTab; })
    ? shell.dataset.activeTab : "edit";
  activate(initialTab, false);

  // 削除は取り消せないので、押したファイル名を見せて確認する
  var pendingDelete = null;
  shell.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".attach-delete");
    if (!button) return;
    if (!window.confirm("「" + button.dataset.name + "」を削除します。よろしいですか？")) {
      event.preventDefault();
      pendingDelete = null;
      return;
    }
    // どの削除ボタンを押したかは submitter からしか分からないので覚えておく
    pendingDelete = button;
  });

  // ---- ページ選択ダイアログ（TreeView） ----
  // 添付ファイルの移動先を選ぶのに使う。ページ一覧は開いたときに取りに行き、
  // 一度読んだら覚えておく（編集画面を出すたびに全ページを走査させないため）。
  var treeCache = null;

  function pickerEl() { return shell.querySelector(".page-picker"); }

  var tree = null;

  function openPicker(name) {
    var dlg = pickerEl();
    if (!dlg || !dlg.showModal || !window.WikiTreeView) return false;

    dlg.querySelector(".page-picker-target").textContent = "「" + name + "」の移動先";
    dlg.dataset.name = name;
    var chosen = dlg.querySelector(".page-picker-chosen");
    var ok = dlg.querySelector(".page-picker-ok");
    chosen.textContent = "選択なし";
    ok.disabled = true;
    delete dlg.dataset.chosen;

    var box = dlg.querySelector(".page-picker-tree");
    var filter = dlg.querySelector(".page-picker-filter input");
    filter.value = "";

    if (!tree) {
      // 木の作りかた・開閉・キーボードは共通の TreeView に任せる
      tree = new WikiTreeView(box, {
        prefix: "pp",
        showIndex: box.dataset.showIndex === "1",
        onSelect: function (info) {
          dlg.dataset.chosen = info.pagepath;
          chosen.textContent = "移動先: /" + info.pagepath + "（" + info.subpath + "）";
          ok.disabled = false;
        },
        onEnter: function () { if (!ok.disabled) ok.click(); }
      });
    }

    function render(data) {
      tree.render(data);
      dlg.showModal();
      filter.focus();
    }

    if (treeCache) { render(treeCache); return true; }
    box.textContent = "読み込み中…";
    dlg.showModal();
    fetch(dlg.dataset.treeUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { treeCache = data; render(data); })
      .catch(function () { box.textContent = "ページ一覧を読み込めませんでした。"; });
    return true;
  }

  // ---- 名前を変えるダイアログ ----
  // 添付ページの変更（別のページへ移す）とは違い、同じ場所のまま
  // 名前だけを変えるので、ページ一覧は要らずテキスト入力1つで済む。
  function renameDialogEl() { return shell.querySelector(".attach-rename-dialog"); }

  function openRenameDialog(name) {
    var dlg = renameDialogEl();
    if (!dlg || !dlg.showModal) return false;
    dlg.querySelector(".attach-rename-target").textContent = "「" + name + "」の新しい名前";
    dlg.dataset.name = name;
    var input = dlg.querySelector(".attach-rename-input");
    input.value = name;
    dlg.showModal();
    input.focus();
    input.select();
    return true;
  }

  shell.addEventListener("click", function (event) {
    // 「添付ページの変更」ボタン → ページ選択ダイアログを開く
    var moveBtn = event.target.closest && event.target.closest(".attach-move");
    if (moveBtn) {
      if (!openPicker(moveBtn.dataset.name)) {
        window.alert("この環境ではページ選択ダイアログを使えません。");
      }
      return;
    }

    // 「名前の変更」ボタン → 名前を変えるダイアログを開く
    var renameBtn = event.target.closest && event.target.closest(".attach-rename");
    if (renameBtn) {
      if (!openRenameDialog(renameBtn.dataset.name)) {
        window.alert("この環境では名前を変えるダイアログを使えません。");
      }
      return;
    }
  });

  // 絞り込みは TreeView に渡す（隠しかたの決まりを1か所にまとめるため）
  shell.addEventListener("input", function (event) {
    if (!tree || !event.target.closest(".page-picker-filter")) return;
    tree.filter(event.target.value);
  });

  // 決定されたら、隠しフィールドに詰めて通常の送信経路へ渡す
  shell.addEventListener("close", function (event) {
    var dlg = event.target;
    if (!dlg.classList) return;

    if (dlg.classList.contains("page-picker")) {
      if (dlg.returnValue !== "ok" || !dlg.dataset.chosen && dlg.dataset.chosen !== "") return;
      var form = shell.querySelector(".attach-manage");
      if (!form) return;
      form.querySelector('input[name="move"]').value = dlg.dataset.name || "";
      form.querySelector('input[name="move_to"]').value = dlg.dataset.chosen;
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
      return;
    }

    if (dlg.classList.contains("attach-rename-dialog")) {
      if (dlg.returnValue !== "ok") return;
      var newName = dlg.querySelector(".attach-rename-input").value.trim();
      if (!newName) return;
      var renameForm = shell.querySelector(".attach-manage");
      if (!renameForm) return;
      renameForm.querySelector('input[name="rename"]').value = dlg.dataset.name || "";
      renameForm.querySelector('input[name="rename_to"]').value = newName;
      if (renameForm.requestSubmit) renameForm.requestSubmit();
      else renameForm.submit();
    }
  }, true);

  // ---- ドラッグ&ドロップでの追加 ----
  // 一覧はAJAXで差し替わるため、ここでも shell 側で受ける（イベント委譲）。
  // 落とされたファイルは file 入力に移してから、通常の送信と同じ経路に流す。
  var dragDepth = 0;

  function dropZone(target) {
    return target.closest && target.closest(".attach-drop");
  }

  function hasFiles(event) {
    var dt = event.dataTransfer;
    if (!dt) return false;
    return [].indexOf.call(dt.types || [], "Files") !== -1;
  }

  shell.addEventListener("dragenter", function (event) {
    if (!hasFiles(event)) return;
    var zone = dropZone(event.target);
    if (!zone) return;
    event.preventDefault();
    dragDepth += 1;
    zone.classList.add("is-dragover");
  });

  shell.addEventListener("dragover", function (event) {
    if (!hasFiles(event) || !dropZone(event.target)) return;
    event.preventDefault();
    // 「コピーして追加する」であることをカーソルで示す
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });

  shell.addEventListener("dragleave", function (event) {
    var zone = dropZone(event.target);
    if (!zone) return;
    dragDepth -= 1;
    if (dragDepth <= 0) { dragDepth = 0; zone.classList.remove("is-dragover"); }
  });

  shell.addEventListener("drop", function (event) {
    var zone = dropZone(event.target);
    if (!zone || !hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    zone.classList.remove("is-dragover");

    var files = event.dataTransfer && event.dataTransfer.files;
    if (!files || !files.length) return;

    var form = zone.closest(".attach-manage");
    var input = form && form.querySelector('input[type="file"]');
    if (!form || !input) return;

    // 落とされたものを file 入力に移す。以降は「選んで追加」と同じ扱いになる
    if (window.DataTransfer) {
      var dt = new DataTransfer();
      [].forEach.call(files, function (f) { dt.items.add(f); });
      input.files = dt.files;
    }
    showPicked(form);
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  });

  /* ---- クリップボードの画像を貼り付けで追加 ----
   * クリップボードの画像はファイル名を持たない（getAsFile() の name が
   * 空、またはブラウザが適当に付けた汎用名）ため、ここでは拡張子だけ
   * 合わせた仮の名前を付けて送り、本当の名前（clipNNN、連番）はサーバー側
   * （handle_attach_post）に決めてもらう。Ctrl+V（paste イベント）・
   * 「クリップボードから貼り付け」ボタンのどちらから来ても同じ処理を通す。*/
  function applyPastedFiles(files) {
    if (!files.length || !window.DataTransfer) return;
    var form = attachPanel && attachPanel.querySelector(".attach-manage");
    var input = form && form.querySelector('input[type="file"]');
    if (!form || !input) return;

    var dt = new DataTransfer();
    files.forEach(function (f) {
      // MIMEタイプの後半（"image/png" → "png"）を拡張子にする。
      // "svg+xml" のような "+" 以降は落とす
      var ext = ((f.type || "").split("/")[1] || "png").split("+")[0];
      dt.items.add(new File([f], "clip." + ext, { type: f.type }));
    });
    input.files = dt.files;
    form.dataset.pasted = "1";
    showPicked(form);
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  }

  function imageFilesFromClipboardItems(items) {
    var files = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (it.kind === "file" && it.type && it.type.indexOf("image/") === 0) {
        var f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    return files;
  }

  // 添付タブを見ているときだけ拾う（本文タブでは、テキストの貼り付けを
  // 邪魔しないようにするため）。
  //
  // **聞くのは `document`。** paste は選択位置（無ければフォーカス）のある要素で
  // 起きるので、画面上部やページ一覧（`.edit-shell` の外）をクリックしたあとだと
  // shell には届かず、**黙って何も起きなかった**（2026-09-28に直した）。
  // ただし、添付欄の外の文字の入力欄（ダイアログの名前欄など）へ貼るときは
  // 横取りしない（画像と文字が一緒に入っていることがあるため）。
  function isOtherTextField(el) {
    if (!el || !el.closest) return false;
    if (attachPanel && attachPanel.contains(el)) return false;
    return !!el.closest("input, textarea, [contenteditable=\"true\"]");
  }

  document.addEventListener("paste", function (event) {
    if (shell.dataset.activeTab !== "attach") return;
    if (isOtherTextField(event.target)) return;
    var data = event.clipboardData;
    var items = data && data.items;
    var files = items ? imageFilesFromClipboardItems(items) : [];
    if (!files.length) {
      // 文字の入力欄（添付欄の中の名前の変更など）へ文字を貼るのはふつうの操作。
      // 貼り付け枠（スマートフォン向け）は <img> が差し込まれる道が残っている
      // （pasteBox の paste が拾う）。どちらも何も言わない
      if (event.target.closest &&
          event.target.closest("input, textarea, [contenteditable=\"true\"]")) return;
      // 黙って終わると、効かないのか画像が無いのか分からない。届いた形式を添えて知らせる
      var types = data ? [].slice.call(data.types || []) : [];
      showAttachProblem("クリップボードに画像がありません" +
        (types.length ? "（届いた形式: " + types.join(", ") + "）" : "") +
        "。画像そのものをコピーしてから貼り付けてください。");
      return;
    }
    event.preventDefault();
    applyPastedFiles(files);
  });

  // 添付欄に、貼り付けられなかった理由を出す（送るものがあれば showPicked が消す）
  function showAttachProblem(message) {
    var form = attachPanel && attachPanel.querySelector(".attach-manage");
    var refused = form && form.querySelector(".attach-refused");
    if (!refused) return;
    refused.textContent = message;
    refused.hidden = false;
  }

  /* ---- スマートフォン向けの貼り付け枠 ----
   * iOS・Androidでは、**編集できる欄にフォーカスが無いと「ペースト」の
   * メニューが出ない**（PCの Ctrl+V に当たる操作が無い）。押せる枠を1つ
   * 置いて、そこへ貼ってもらう（Wiki設計者の指示、2026-09-10）。
   *
   * 貼られかたが2通りあるので、両方を拾う。
   *
   *   1. clipboardData に画像ファイルが入ってくる（上の paste が拾う）
   *   2. **枠の中に <img> が差し込まれるだけ**（iOS Safari はこちらの
   *      ことがある）。この場合は差し込まれた画像を読み直してファイルに戻す
   *
   * どちらの道でも、最後は applyPastedFiles に合流する。 */
  // **`attachPanel` はこの下（貼り付けボタンのところ）で代入される。**
  // `var` は巻き上げられるので、ここで使うと undefined になり、リスナーが
  // 静かに付かない（実際にそう書いて踏んだ）。枠は shell から直に引く
  var pasteBox = shell.querySelector('.edit-panel[data-tab="attach"] .attach-pastebox');

  function filesFromPastedImages(box) {
    var imgs = [].slice.call(box.querySelectorAll("img"));
    if (!imgs.length) return Promise.resolve([]);
    return Promise.all(imgs.map(function (img) {
      // blob: も data: も fetch で読み直せる。読めないものは飛ばす
      return fetch(img.src).then(function (res) { return res.blob(); })
        .then(function (blob) {
          return new File([blob], "clip", { type: blob.type || "image/png" });
        }, function () { return null; });
    })).then(function (files) {
      return files.filter(function (f) { return f && f.type.indexOf("image/") === 0; });
    });
  }

  if (pasteBox) {
    // 枠に貼られたものは、上の paste ハンドラが拾えていればそこで終わる
    // （preventDefault 済み）。拾えなかったときだけ、差し込まれた画像を見る
    pasteBox.addEventListener("paste", function (event) {
      if (event.defaultPrevented) return;
      // 差し込みはこのイベントのあとに起きるので、次の番で見る
      setTimeout(function () {
        filesFromPastedImages(pasteBox).then(function (files) {
          pasteBox.textContent = "";      // 貼られた見た目は残さない
          if (files.length) applyPastedFiles(files);
        });
      }, 0);
    });

    // 文字だけ貼られた・打たれた場合に、枠に残しておかない
    pasteBox.addEventListener("blur", function () {
      if (!pasteBox.querySelector("img")) pasteBox.textContent = "";
    });
  }


  /* ---- 大きすぎるファイルは、送る前に断る ----
   * 送ってからサーバーに断られるのでは、上限を超えたぶんだけ回線と時間を
   * 無駄にする（大きなファイルほど待たされてから断られることになる）。
   * ブラウザは選ばれた時点で大きさを知っているので、その場で見て分けておく。
   * 上限そのものはサーバーが決めた値を data-max-bytes で受け取る。
   */
  function maxBytesOf(form) {
    var n = parseInt(form.dataset.maxBytes, 10);
    return n > 0 ? n : 0;
  }

  function sizeLabel(bytes) {
    var units = ["B", "KB", "MB", "GB"];
    var i = 0;
    var v = bytes;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? v : v.toFixed(1)) + " " + units[i];
  }

  // 選ばれたものを「送るぶん」と「大きすぎるぶん」に分ける
  function splitBySize(form) {
    var input = form.querySelector('input[type="file"]');
    var limit = maxBytesOf(form);
    var ok = [], over = [];
    [].forEach.call((input && input.files) || [], function (f) {
      if (limit && f.size > limit) over.push(f); else ok.push(f);
    });
    return { ok: ok, over: over, limit: limit };
  }

  // 選ばれたファイルを、送る前に名前で見せる（複数のとき何が入ったか分かるように）
  function showPicked(form) {
    var picked = form.querySelector(".attach-picked");
    var refused = form.querySelector(".attach-refused");
    if (!picked) return;
    var split = splitBySize(form);

    var names = split.ok.map(function (f) { return f.name; });
    picked.textContent = names.length ? names.length + "件: " + names.join(", ") : "";
    picked.hidden = !names.length;

    if (!refused) return;
    if (!split.over.length) {
      refused.textContent = "";
      refused.hidden = true;
      return;
    }
    // 大きさを添えて、なぜ送らないのかが分かるようにする
    refused.textContent = "大きすぎるので送りません（上限 " +
      (form.dataset.maxLabel || sizeLabel(split.limit)) + "）: " +
      split.over.map(function (f) {
        return f.name + "（" + sizeLabel(f.size) + "）";
      }).join(", ");
    refused.hidden = false;
  }

  // **選んだらそのまま送る**（Wiki設計者の指示、2026-09-28。「追加」を押す手間を
  // なくす）。ドラッグ&ドロップ・貼り付けと同じく requestSubmit で送信の経路に
  // 流す（大きさの確認・分割送信・進み具合は下の submit が受け持つ）。
  // 「同名を置き換える」は、選ぶ前に印を付けておく。
  // 「追加」ボタンは、スクリプトが動かないときのためにHTMLには残し、動くときは
  // 隠す（editor.css の .attach-auto）。
  document.documentElement.classList.add("attach-auto");
  shell.addEventListener("change", function (event) {
    if (event.target.type !== "file") return;
    var form = event.target.closest(".attach-manage");
    if (!form) return;
    showPicked(form);
    if (!event.target.files || !event.target.files.length) return;
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  });

  // 添付の追加・削除はページを再読み込みせずに行う。
  // 素直にフォームを送ると画面が入れ替わり、書きかけの本文が失われてしまうため。
  //
  // 送るのは fetch ではなく XMLHttpRequest。fetch では送信の進み具合を
  // 受け取れないので、進捗を出せない（大きなファイルほど、いま何が
  // 起きているのか分からない時間が長くなる）。
  var attachPanel = shell.querySelector('.edit-panel[data-tab="attach"]');

  /* ---- 「クリップ貼付」ボタン ----
   * Ctrl+V を知らない・使いづらい利用者のための、同じ機能への入口。
   * navigator.clipboard.read() は安全なコンテキスト（HTTPS・localhost）
   * でしか使えない仕様のため、http://<IPアドレス>: のような接続では
   * navigator.clipboard 自体が存在しない。押しても機能しないとだけ
   * 分かるボタンにはせず、条件を満たすときだけ表示する（Wiki設計者の指示）。
   * Ctrl+V（paste イベント）自体はこの制限を受けず常に使えるので、
   * その案内は .attach-hint 側に常時表示している
   * （build_attach_panel_html参照）。 */
  var pasteButton = attachPanel && attachPanel.querySelector(".attach-paste");
  if (pasteButton && navigator.clipboard && navigator.clipboard.read) {
    pasteButton.hidden = false;
    pasteButton.addEventListener("click", function () {
      var form = attachPanel.querySelector(".attach-manage");
      var refused = form && form.querySelector(".attach-refused");
      function fail(message) {
        if (!refused) return;
        refused.textContent = message;
        refused.hidden = false;
      }
      navigator.clipboard.read().then(function (clipItems) {
        var files = [];
        var reads = [];
        clipItems.forEach(function (item) {
          item.types.forEach(function (type) {
            if (type.indexOf("image/") !== 0) return;
            reads.push(item.getType(type).then(function (blob) {
              files.push(new File([blob], "clip", { type: type }));
            }));
          });
        });
        return Promise.all(reads).then(function () { return files; });
      }).then(function (files) {
        if (!files.length) {
          fail("クリップボードに画像が見つかりませんでした。");
          return;
        }
        if (refused) refused.hidden = true;
        applyPastedFiles(files);
      }, function () {
        fail("クリップボードを読み取れませんでした。この欄をクリックしてから Ctrl+V で貼り付けてください。");
      });
    });
  }

  function showProgress(form, sent, total) {
    var box = form.querySelector(".attach-progress");
    var bar = form.querySelector(".attach-progress-bar");
    var text = form.querySelector(".attach-progress-text");
    if (!box) return;
    if (sent === null) { box.hidden = true; return; }
    box.hidden = false;
    if (total) {
      var pct = Math.round(sent / total * 100);
      if (bar) bar.value = pct;
      if (text) text.textContent = sizeLabel(sent) + " / " + sizeLabel(total) +
        "（" + pct + "%）" + (sent >= total ? " 受け取り待ち…" : "");
    } else {
      // 大きさが分からない場合（削除・移動など）は、動いていることだけ見せる
      if (bar) bar.removeAttribute("value");
      if (text) text.textContent = "送信中…";
    }
  }

  shell.addEventListener("submit", function (event) {
    var form = event.target.closest && event.target.closest(".attach-manage");
    if (!form || !window.FormData || !window.DOMParser || !window.XMLHttpRequest) return;
    event.preventDefault();

    var split = splitBySize(form);
    var mv = form.querySelector('input[name="move"]');
    var mvTo = form.querySelector('input[name="move_to"]');
    var rn = form.querySelector('input[name="rename"]');
    var rnTo = form.querySelector('input[name="rename_to"]');
    var hasWork = !!(pendingDelete || (mv && mv.value) || (rn && rn.value));
    var isUpload = split.ok.length > 0;

    // 大きすぎるものは送らない。送るものが何も無いなら、そもそも通信しない。
    // ここで「ファイルが選ばれているか」ではなく「送るものがあるか」で見るのは、
    // 大きすぎるファイルが選ばれたままでも、削除・添付ページの変更・名前の
    // 変更は行えるようにするため。
    if (!isUpload && !hasWork) {
      showPicked(form);
      return;
    }

    // 毎回添える項目。ファイルと、その回だけの指示（削除・移動・名前の変更）は含めない
    var common = { "cmd": "attach" };
    var ow = form.querySelector('input[name="overwrite"]');
    if (ow && ow.checked) common.overwrite = ow.value;
    // クリップボードから貼り付けたファイルには、送った名前を使わず
    // サーバー側で clipNNN の連番を振ってもらう（handle_attach_post）
    if (form.dataset.pasted === "1") common.pasted = "1";

    // 送る手順を並べる。**追加は1ファイルずつ送る。** まとめて送ると1回の
    // POSTが全部の合計になり、1つ1つは収まっていても受け取り側の上限に届く
    var work = [];
    if (hasWork) {
      var once = { "cmd": "attach" };
      if (ow && ow.checked) once.overwrite = ow.value;
      if (pendingDelete) once["delete"] = pendingDelete.value;
      if (mv && mv.value) { once.move = mv.value; once.move_to = mvTo ? mvTo.value : ""; }
      if (rn && rn.value) { once.rename = rn.value; once.rename_to = rnTo ? rnTo.value : ""; }
      work.push({ kind: "plain", fields: once });
    }
    pendingDelete = null;
    // 添付ページの変更・名前の変更・クリップボード貼り付けの指定は1回きり。
    // 残したままだと、次の追加がそれとして送られてしまう
    if (mv) mv.value = "";
    if (mvTo) mvTo.value = "";
    if (rn) rn.value = "";
    if (rnTo) rnTo.value = "";
    delete form.dataset.pasted;

    var total = 0;
    split.ok.forEach(function (f) {
      total += f.size;
      work.push({ kind: "file", file: f });
    });

    var busy = form.querySelector(".attach-add");
    if (busy) busy.disabled = true;
    var skipped = split.over.slice();
    var chunkBytes = wikiSend.chunkBytesOf(form);
    var doneBytes = 0;

    showProgress(form, 0, isUpload ? total : 0);

    function runStep(i, lastText) {
      if (i >= work.length) return Promise.resolve(lastText);
      var step = work[i];
      if (step.kind === "plain") {
        var data = new FormData();
        Object.keys(step.fields).forEach(function (k) { data.append(k, step.fields[k]); });
        return wikiSend.postForm(form.action, data).then(function (res) {
          if (!res.ok) return Promise.reject(new Error(res.text || "送れませんでした"));
          return runStep(i + 1, res.text);
        });
      }
      return wikiSend.sendChunked(form.action, common, step.file, step.file.name,
        chunkBytes,
        function (sent) { showProgress(form, doneBytes + sent, total); }
      ).then(function (res) {
        if (!res.ok) return Promise.reject(new Error(res.text || "送れませんでした"));
        doneBytes += step.file.size;
        showProgress(form, doneBytes, total);
        return runStep(i + 1, res.text);
      });
    }

    runStep(0, "").then(function (lastText) {
      var doc = new DOMParser().parseFromString(lastText || "", "text/html");
      var fresh = doc.querySelector('.edit-panel[data-tab="attach"]');
      if (!fresh || !attachPanel) {
        if (busy) busy.disabled = false;
        showProgress(form, null);
        return;
      }
      attachPanel.innerHTML = fresh.innerHTML;
      // 送らなかったものは、差し替えた画面にも書き残しておく
      if (skipped.length) {
        var refused = attachPanel.querySelector(".attach-refused");
        if (refused) {
          refused.textContent = "大きすぎるので送りませんでした（上限 " +
            (form.dataset.maxLabel || "") + "）: " +
            skipped.map(function (f) {
              return f.name + "（" + sizeLabel(f.size) + "）";
            }).join(", ");
          refused.hidden = false;
        }
      }
    }, function (err) {
      // 途中で断られた・通信が切れた。素の送信に任せると全部を1回で送り直す
      // ことになり、大きいものほど確実に失敗するので、ここで理由を出して止める
      if (busy) busy.disabled = false;
      showProgress(form, null);
      var refused = form.querySelector(".attach-refused");
      if (refused) {
        refused.textContent = (err && err.message) || "送れませんでした。";
        refused.hidden = false;
      }
    });
  });

  // ---- 画像のサムネイル（マウスオーバー） ----
  // 一覧はAJAXで差し替わるので、行ではなく shell 側で受ける（イベント委譲）。
  // 実物を縮小して見せるだけなので、サーバー側でサムネイルを作る必要はない。
  // ただし読み込みは「最初にマウスを乗せたとき」まで遅らせる。
  var thumb = null;
  var thumbImg = null;
  var thumbFor = null;

  function ensureThumb() {
    if (thumb) return;
    thumb = document.createElement("div");
    thumb.className = "attach-thumb";
    thumb.hidden = true;
    thumbImg = document.createElement("img");
    thumbImg.alt = "";
    thumb.appendChild(thumbImg);
    var note = document.createElement("p");
    note.className = "attach-thumb-note";
    thumb.appendChild(note);
    thumb.note = note;
    document.body.appendChild(thumb);
  }

  function placeThumb(x, y) {
    if (!thumb) return;
    var pad = 16;
    var box = thumb.getBoundingClientRect();
    // 画面からはみ出す側には出さない（右端・下端で折り返す）
    var left = x + pad;
    var top = y + pad;
    if (left + box.width > document.documentElement.clientWidth - pad) {
      left = x - box.width - pad;
    }
    if (top + box.height > document.documentElement.clientHeight - pad) {
      top = y - box.height - pad;
    }
    thumb.style.left = Math.max(pad, left) + "px";
    thumb.style.top = Math.max(pad, top) + "px";
  }

  function hideThumb() {
    thumbFor = null;
    if (!thumb) return;
    thumb.classList.remove("is-shown");
    thumb.hidden = true;
  }

  shell.addEventListener("mouseover", function (event) {
    var row = event.target.closest && event.target.closest(".attach-row[data-thumb]");
    if (!row || row === thumbFor) return;
    thumbFor = row;
    ensureThumb();
    var link = row.querySelector(".attach-name a");
    thumb.note.textContent = link ? link.textContent : "";
    if (thumbImg.getAttribute("src") !== row.dataset.thumb) {
      thumbImg.removeAttribute("src");   // 前の画像を出したままにしない
      thumbImg.src = row.dataset.thumb;
    }
    thumb.hidden = false;
    placeThumb(event.clientX, event.clientY);
    // 画像の大きさが決まってから位置を決め直す（初回は読み込み後）
    if (thumbImg.complete) thumb.classList.add("is-shown");
    else thumbImg.onload = function () {
      if (thumbFor === row) { placeThumb(event.clientX, event.clientY); thumb.classList.add("is-shown"); }
    };
  });

  shell.addEventListener("mousemove", function (event) {
    if (thumbFor) placeThumb(event.clientX, event.clientY);
  });

  shell.addEventListener("mouseout", function (event) {
    var row = event.target.closest && event.target.closest(".attach-row[data-thumb]");
    if (!row) return;
    // 行の中で要素をまたいだだけなら消さない
    if (event.relatedTarget && row.contains(event.relatedTarget)) return;
    hideThumb();
  });

  // タブを切り替えたり一覧が入れ替わったら、出しっぱなしにしない
  shell.addEventListener("click", hideThumb);
  window.addEventListener("scroll", hideThumb, true);

  // 「コピー」を押すと、本文での書きかたをクリップボードへ入れる。
  // 書きかたそのものは data-ref に持たせてあるので、ボタンの表示を
  // 差し替えても写す中身は変わらない。
  shell.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".attach-copy");
    if (!button) return;
    copyRef(button);
  });

  function flash(button, label, cls) {
    if (button.dataset.busy) return;
    button.dataset.busy = "1";
    var original = button.textContent;
    button.classList.add(cls);
    button.textContent = label;
    setTimeout(function () {
      button.textContent = original;
      button.classList.remove(cls);
      delete button.dataset.busy;
    }, 1600);
  }

  // クリップボードに書けない場面がある（httpsでない場所からの利用、
  // 権限が下りていない場合など）。黙って何も起きないと壊れて見えるので、
  // 昔ながらのやりかたを試し、それも駄目なら書きかたを選択して知らせる。
  function legacyCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  function selectRef(button) {
    var code = button.parentElement && button.parentElement.querySelector(".attach-ref-code");
    if (!code || !window.getSelection) return;
    var range = document.createRange();
    range.selectNodeContents(code);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function copyRef(button) {
    var text = button.dataset.ref || "";
    if (!text) return;
    var ok = function () { flash(button, "コピーしました", "is-copied"); };
    var ng = function () {
      // 選択した状態にして、手で写せるようにしておく
      selectRef(button);
      flash(button, "Ctrl+Cで", "is-failed");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok, function () {
        if (legacyCopy(text)) ok(); else ng();
      });
      return;
    }
    if (legacyCopy(text)) ok(); else ng();
  }
})();

// ---- サイドバーのページ一覧（TreeView） ----
// 添付ファイルの移動先を選ぶダイアログ・名前を変える画面・バックアップ管理
// 画面と同じ共通のTreeView（WikiTreeView）で組み立てる。ただしこちらは
// ダイアログと違って常に見えているものなので、開くたびに `/.pagetree` を
// 取りに行くと編集画面を開くたび（＝行き来のたび）に待たされてしまう。
// 木のデータは編集画面のHTMLに埋め込んで届けてもらい（editor.pyの
// edit-pages-tree）、ここでは同期的に読んで組み立てるだけにする。
(function () {
  var nav = document.querySelector(".edit-pages");
  if (!nav) return;
  var box = nav.querySelector(".ep-tree");
  var dataEl = nav.querySelector(".edit-pages-tree");
  if (!box || !dataEl || !window.WikiTreeView) return;

  var editUrl = nav.dataset.editUrl;
  var currentSubpath = nav.dataset.currentSubpath;

  // pagepathは "/" 区切りのまま、区切りごとにエンコードする（"/" 自体は
  // 経路の区切りとして残す。encodeURIComponent をそのままかけると
  // "/" も %2F になってしまい、階層をたどるURLにならない）。
  function editUrlFor(pagepath) {
    return editUrl + "/" + pagepath.split("/").map(encodeURIComponent).join("/");
  }

  // 編集画面は '.edit' という別パスを持たず、そのページ自身の通常URLへ
  // POST + cmd=edit を送ることで開く（wiki.pyのdispatch参照）。GETでは
  // 塞がれておらず素通しなので、URLだけを見ても編集の入口があることは
  // 分からない。他の編集入口（テーマのcommand-form）と同じ形で遷移する
  // （サーバーはPOSTの応答としてそのまま編集画面のHTMLを返す。
  // リダイレクトは無いのでフォーム送信のままでよい）。
  //
  // **いま選んでいるタブ（編集 / 差分 / 添付ファイル）は移った先へも引き継ぐ。**
  // 送り先のURLに `?tab=` を付けると、サーバーがそのタブを開いた状態で
  // 返す（editor.py の initial_tab。再読み込みで同じタブが開くのと同じ
  // 仕組み）。付けないと、ページを移るたびに「編集」タブへ戻ってしまい、
  // 添付ファイルや差分を順に見て回る作業ができない。
  function navigate(info) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = editUrlFor(info.pagepath);
    var shell = document.querySelector(".edit-shell");
    var tab = shell && shell.dataset.activeTab;
    if (tab && tab !== "edit") form.action += "?tab=" + encodeURIComponent(tab);
    form.style.display = "none";
    var cmdField = document.createElement("input");
    cmdField.type = "hidden";
    cmdField.name = "cmd";
    cmdField.value = "edit";
    form.appendChild(cmdField);
    document.body.appendChild(form);
    // 書きかけがあれば、預けてから移る（下の「ページ一覧から別のページへ移る」。
    // 編集欄の側が持っている仕組みなので、そちらに任せる）
    if (window.wikiEditorLeave) {
      window.wikiEditorLeave(function () { form.submit(); });
    } else {
      form.submit();
    }
  }

  function focusSource() {
    var source = document.querySelector(".edit-source");
    if (source) source.focus();
  }

  // Enterはいま選んでいる行を開く決定キーだが、それが**いま編集している
  // ページそのもの**なら、同じページへ移り直す意味は無い。その場合は
  // 一覧から出て本文へ入る決定として扱う（TreeView自体の onEnter の意味は
  // 変えず、ここでの分岐だけで済ませる）。
  function openOrEnterBody(info) {
    if (info.subpath === currentSubpath) { focusSource(); return; }
    navigate(info);
  }

  var tree = new WikiTreeView(box, {
    prefix: "ep",
    showIndex: box.dataset.showIndex === "1",
    // 最初はいま開いているページの周りだけ開き、他は畳む（Wiki設計者の指示、2026-09-19）
    collapsed: true,
    // ファイル名とタイトルを並べて出すと幅を圧迫するので、タイトルだけ出す
    // （無いページはファイル名のまま。ファイル名はホバーで確かめられる）。
    // 他のTreeView利用箇所（ダイアログ・リネーム・バックアップ）は既定の
    // ままなので、この見た目はサイドバーだけの変化になる。
    titleOnly: true,
    // 長いタイトルの打ち切り幅（config/default.yaml の edit.title_length）。
    titleMaxWidth: parseInt(box.dataset.titleLength, 10) || 24,
    // 一時保存を預かっているページに印を付ける。**本保存されていないことを
    // 見落とすと困る**ので、他の行より強く目立たせる（editor.cssのep-draft）
    // **フォルダの行が index を兼ねているときは、index の書きかけを見る**（Wiki設計者の
    // 報告、2026-09-27。入口ページを書きかけにしてもフォルダ名が赤くならなかった）。
    // フォルダ自身の `draft` は常に偽（書きかけはページにしか無い）。TreeView が
    // 兼ねた行の実体の有無を index から取るのと同じ規則にそろえる
    decorate: function (node, parts) {
      var src = node;
      if (node.kind === "dir" && box.dataset.showIndex !== "1") {
        src = (node.children || []).filter(function (c) {
          return c.kind !== "dir" && c.name === "index";
        })[0] || node;
      }
      if (src.draft) parts.row.classList.add("ep-draft");
    },
    onEnter: openOrEnterBody
  });

  // クリックでの移動は自前で受ける。TreeViewの onSelect は矢印キーでの
  // 移動でも呼ばれるため、そちらに繋ぐと矢印を押しただけでページを
  // 離れてしまう（選ぶ＝即移動ではなく、選ぶのとEnter/クリックでの
  // 決定は分けたい）。開閉の三角は素通りさせる。
  box.addEventListener("click", function (event) {
    if (event.target.closest(".ep-twisty")) return;
    var row = event.target.closest(".tv-row");
    if (!row || !box.contains(row)) return;
    navigate(tree.infoOf(row));
  });

  // Tabは一覧から抜けて本文へ進む決定として扱う（TreeView共通の
  // _onKey は Tab を素通りさせるので、ここに足すだけで済み、他の
  // TreeView利用箇所には影響しない）。Shift+Tab（逆方向）は素通りのまま。
  box.addEventListener("keydown", function (event) {
    if (event.key !== "Tab" || event.shiftKey) return;
    event.preventDefault();
    focusSource();
  });

  /* いま開いているページの行を、一覧の**真ん中**に置く（Wiki設計者の指示、2026-09-06）。
   *
   * TreeView は選んだ行を scrollIntoView({block:"nearest"}) で見えるところへ
   * 出すが、"nearest" は「いちばん動かさずに済む位置」なので、下にある行は
   * **いちばん下に貼り付いた状態**で止まる。前後がまったく見えず、いまどのあたりを
   * 開いているのか分からない。
   *
   * TreeView 側の "nearest" は変えない。あちらは矢印キーで1行ずつ動かすときの
   * 動きでもあり、押すたびに真ん中へ跳ぶと目で追えなくなる。**開いた直後の
   * 1回だけ**、こちらで置き直す。
   *
   * 位置は getBoundingClientRect の差で測る。offsetTop は「いちばん近い
   * position 付きの祖先」からの距離なので、囲みの作りが変わると黙ってずれる。
   */
  function centerInScroller(el) {
    var box = el.parentElement;
    while (box && box !== document.body) {
      var oy = window.getComputedStyle(box).overflowY;
      if ((oy === "auto" || oy === "scroll") && box.scrollHeight > box.clientHeight) break;
      box = box.parentElement;
    }
    if (!box || box === document.body) return;   // 一覧が短くて、そもそも動かない
    var r = el.getBoundingClientRect(), c = box.getBoundingClientRect();
    box.scrollTop += (r.top - c.top) - (c.height - r.height) / 2;
  }

  try {
    tree.render(JSON.parse(dataEl.textContent));
    tree.selectSubpath(currentSubpath, false);
    // 開いた直後から矢印キーで一覧をたどれるよう、選んだ行にフォーカスして
    // おく（選ぶだけでは tabIndex が付くだけで、実際にフォーカスはしない）。
    // スクロールは自分で決めるので、フォーカスには任せない
    if (tree.selected) {
      tree.selected.focus({ preventScroll: true });
      centerInScroller(tree.selected);
    }
  } catch (e) {
    box.textContent = "ページ一覧を読み込めませんでした。";
  }
})();

// ---- 画面が低いとき、操作ボタンをタブの行へ入れ直す ----
// 足もとに1行を構えると、それだけで32pxほど取られる。タブの行はどうせ空いて
// いるので、そこへ寄せて1行まるごと空ける（Wiki設計者の指示、2026-09-06）。
//
// **CSSだけでは並べられない。** .edit-buttons は .page-editor の中にあり、
// タブとは兄弟ではないため。絶対配置で重ねる手もあるが、それだと幅が
// 足りないときにタブと重なってしまう。行の中へ入れ直せば、あとは flex が
// 面倒を見てくれる（足りなくなれば行ごと横へスクロールする）。
//
// 戻す先は覚えておく。画面を広げたときに元の足もとへ返すため。
(function () {
  var tabs = document.querySelector(".edit-tabs");
  var buttons = document.querySelector(".edit-buttons");
  if (!tabs || !buttons) return;

  var home = buttons.parentElement;
  var homeNext = buttons.nextElementSibling;   // 元の位置（この直前に戻す）
  var short = window.matchMedia("(max-height: 499px)");

  function place() {
    if (short.matches) {
      if (buttons.parentElement !== tabs) tabs.appendChild(buttons);
    } else if (buttons.parentElement !== home) {
      home.insertBefore(buttons, homeNext);
    }
  }

  place();
  // addEventListener を持たない古い実装のために、addListener も見る
  if (short.addEventListener) short.addEventListener("change", place);
  else if (short.addListener) short.addListener(place);
})();

// ---- 狭い画面で、ページ一覧を開閉できるようにする ----
// 縦に積むと一覧が本文の上に居座り、書く場所へ着くまで毎回スクロールが要る。
// 狭いときは流れから外して左に重ね（editor.css）、左上に固定したボタンで
// 出し入れする（Wiki設計者の指示、2026-09-06）。
//
// **開いているかどうかは .edit-layout のクラスだけで決まる。** 広い画面では
// そのクラスに効く指定が無いので、付いたまま広げても何も起きない。
(function () {
  var toggle = document.querySelector(".edit-side-toggle");
  var layout = document.querySelector(".edit-layout");
  var scrim = document.querySelector(".edit-side-scrim");
  if (!toggle || !layout) return;

  function setOpen(open) {
    layout.classList.toggle("is-side-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "ページ一覧を閉じる" : "ページ一覧を開く");
  }

  toggle.addEventListener("click", function () {
    setOpen(!layout.classList.contains("is-side-open"));
  });

  if (scrim) scrim.addEventListener("click", function () { setOpen(false); });

  // 一覧からページを選んだら閉じる。選んだ先へ移るので見た目には残らないが、
  // 同じページを選んだ場合（移動が起きない）に開いたままにならないように。
  // 一覧の行は <a> ではなく .tv-row（TreeViewが組み立てる）で、移動は
  // その click を受けて自前で行っている（下の「ページ一覧」参照）。
  // 開閉の三角（.ep-twisty）は移動しないので、こちらも閉じない。
  var side = document.querySelector(".edit-side");
  if (side) {
    side.addEventListener("click", function (event) {
      if (event.target.closest(".ep-twisty")) return;
      if (event.target.closest(".tv-row")) setOpen(false);
    });
  }

  // ESCで閉じる。**閉じたことを preventDefault で知らせる**——同じESCを
  // 「一時中断」も見ており（下の離脱まわり）、そちらは defaultPrevented を
  // 見て引き下がる。知らせないと、一覧を閉じたつもりが編集も中断される
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!layout.classList.contains("is-side-open")) return;
    setOpen(false);
    toggle.focus();
    event.preventDefault();
  });
})();

// ---- ページ一覧の幅をマウスでドラッグして変えられるようにする ----
// 編集画面はページを開くたびに丸ごと作り直される（JSの状態は残らない）ため、
// 選んだ幅は localStorage に控え、次に開いたときも同じ幅で始まるようにする。
(function () {
  var resizer = document.querySelector(".edit-side-resizer");
  var side = document.querySelector(".edit-side");
  if (!resizer || !side) return;

  var STORE_KEY = "wiki-edit-side-width";
  var MIN_W = 160, MAX_W = 560;

  function apply(px) {
    document.body.style.setProperty("--e-side-w", px + "px");
  }

  var saved = null;
  try { saved = window.localStorage.getItem(STORE_KEY); } catch (e) { /* 無くても既定幅で動く */ }
  if (saved) apply(saved);

  var startX = 0, startW = 0;

  function onMove(event) {
    var w = startW + (event.clientX - startX);
    apply(Math.max(MIN_W, Math.min(MAX_W, w)));
  }

  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    resizer.classList.remove("is-dragging");
    document.body.style.removeProperty("user-select");
    try {
      window.localStorage.setItem(STORE_KEY, Math.round(side.getBoundingClientRect().width));
    } catch (e) { /* 保存できなくても、この場では変わっているので困らない */ }
  }

  resizer.addEventListener("mousedown", function (event) {
    startX = event.clientX;
    startW = side.getBoundingClientRect().width;
    resizer.classList.add("is-dragging");
    document.body.style.userSelect = "none";  // ドラッグ中に本文などが選択されないように
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    event.preventDefault();
  });
})();

(function () {
  // 全体を <form> で囲むのをやめたので、これは囲みではなく**入れもの**
  // （.page-editor という <div>）。送り先と origin は data 属性で持たせてある
  var form = document.querySelector(".page-editor");
  if (!form) return;
  var postUrl = form.dataset.action || "";

  var source = form.querySelector(".edit-source");
  var preview = form.querySelector(".edit-preview");
  var previewUrl = form.dataset.previewUrl;
  // 書式定義のJSONはフォームの外に置いてあるので、文書全体から探す
  var formatsEl = document.querySelector(".edit-formats");
  var PREVIEW_DEBOUNCE = 400;

  var formats = {};
  if (formatsEl) {
    try {
      formats = JSON.parse(formatsEl.textContent);
    } catch (e) {
      // 定義が読めなくても、テキスト入力と保存は使えるようにしておく
    }
  }

  /* ---- 記法の切り替え（ツールバー・プレビュー・保存先の拡張子） ---- */
  // 記法はページの拡張子そのものなので、選び直すと保存先のファイル名も変わる。
  // 本文はいっさい書き換えない（記法を移すのは書き直す作業で、システムが
  // 勝手に変換すると、元のとおりに戻せなくなる）。
  var markupRadios = form.querySelectorAll('input[name="markup"]');
  var toolsBox = form.querySelector(".edit-tools");
  var noteExt = document.querySelector(".edit-note-ext");
  var actions = {};

  function currentMarkup() {
    for (var i = 0; i < markupRadios.length; i++) {
      if (markupRadios[i].checked) return markupRadios[i].value;
    }
    return "";
  }

  function useFormat(name) {
    var fmt = formats[name];
    actions = {};
    if (!fmt) return;
    (fmt.actions || []).forEach(function (a) { actions[a.name] = a; });
    if (toolsBox) {
      toolsBox.textContent = "";
      (fmt.actions || []).forEach(function (a) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "edit-tool";
        button.dataset.action = a.name;
        button.title = a.label;
        button.setAttribute("aria-label", a.label);
        button.textContent = a.icon || "";
        toolsBox.appendChild(button);
      });
    }
    // 新規作成のときの「保存すると作成されます（.md）」を選んだ記法に合わせる
    if (noteExt) noteExt.textContent = fmt.ext || "";
  }

  function previewEndpoint() {
    var name = currentMarkup();
    if (!previewUrl || !name) return previewUrl;
    return previewUrl + (previewUrl.indexOf("?") >= 0 ? "&" : "?") +
      "markup=" + encodeURIComponent(name);
  }

  /* ---- テキストの差し替え（取り消しが効く形で行う） ---- */
  function replaceSelection(text, selectStart, selectLength) {
    var start = source.selectionStart;
    var end = source.selectionEnd;
    var before = source.value;
    var expected = before.slice(0, start) + text + before.slice(end);

    source.focus();
    source.setSelectionRange(start, end);

    // execCommandは非推奨だが、ブラウザの取り消し履歴（Ctrl+Z）に残せる唯一の手段。
    // ただし「trueを返したのに何も起きない」環境があるため、戻り値ではなく
    // 実際に値が変わったかで判定し、変わっていなければ直接書き換える
    // （その場合は取り消しが効かなくなるが、ツールバーは確実に動く）。
    try {
      document.execCommand("insertText", false, text);
    } catch (e) {
      // 使えない環境。このあとの比較でフォールバックされる
    }
    if (source.value !== expected) {
      source.value = expected;
    }

    var caret = start + (selectStart === undefined ? text.length : selectStart);
    source.setSelectionRange(caret, caret + (selectLength || 0));
    source.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function selectedText() {
    return source.value.slice(source.selectionStart, source.selectionEnd);
  }

  // 選択範囲を行の境界まで広げる（行頭に印を付ける操作で使う）
  function expandToLines() {
    var value = source.value;
    var start = value.lastIndexOf("\n", source.selectionStart - 1) + 1;
    var end = value.indexOf("\n", source.selectionEnd);
    if (end === -1) end = value.length;
    source.setSelectionRange(start, end);
    return value.slice(start, end);
  }

  function applyAction(action) {
    if (!action) return;

    if (action.wrap) {
      var text = selectedText() || action.sample || "";
      var wrapped = action.wrap[0] + text + action.wrap[1];
      // 中身が空なら、あとで打ち替えられるよう中身を選択しておく
      replaceSelection(wrapped, action.wrap[0].length, text.length);
      return;
    }

    if (action.prefix) {
      var lines = expandToLines().split("\n");
      var allMarked = lines.every(function (l) { return l.indexOf(action.prefix) === 0; });
      var changed = lines.map(function (l) {
        return allMarked ? l.slice(action.prefix.length) : action.prefix + l;
      }).join("\n");
      replaceSelection(changed, changed.length, 0);
      return;
    }

    if (action.block) {
      var inner = selectedText() || action.sample || "";
      var body = action.block[0] + "\n" + inner + "\n" + action.block[1] + "\n";
      replaceSelection(body, action.block[0].length + 1, inner.length);
      return;
    }

    if (action.template) {
      var picked = selectedText() || action.sample || "";
      var filled = action.template.split("${text}").join(picked);
      var at = action.template.indexOf("${text}");
      if (at >= 0) {
        replaceSelection(filled, at, picked.length);
      } else {
        replaceSelection(filled);
      }
    }
  }

  /* ---- 色・文字サイズのポップオーバー（PukiWiki記法のみ。&color()/&size() を使う） ----
   * wrap を組み立てて applyAction にそのまま渡す（選択範囲の扱い・取り消し
   * 履歴への残しかたは wrap の処理を丸ごと再利用する）。 */
  // 位置引数の形（&color(fg,bg){…}; / &color(fg){…}; / &color(,bg){…};）で
  // 1回だけ適用する。文字色・背景色を別々のボタンで順に適用すると、2回目が
  // 1回目の &color(){…} の中に入れ子になってしまうため、1つのポップオーバーで
  // 両方選んでから1回で確定する
  function applyColorChoice(fg, bg) {
    if (!fg && !bg) return;
    var arg = fg && bg ? (fg + "," + bg) : (fg || ("," + bg));
    applyAction({ wrap: ["&color(" + arg + "){", "};"], sample: "文字" });
  }

  function applySizeChoice(percent) {
    applyAction({ wrap: ["&size(" + percent + "%){", "};"], sample: "サイズ" });
  }

  var activePopover = null;
  var activePopoverCleanup = null;

  function closePopover() {
    if (activePopover) { activePopover.remove(); activePopover = null; }
    if (activePopoverCleanup) { activePopoverCleanup(); activePopoverCleanup = null; }
  }

  // ボタンのすぐ下に出す。画面右端・下端をはみ出す場合は内側へ寄せる
  function positionPopover(pop, anchorEl) {
    var rect = anchorEl.getBoundingClientRect();
    pop.style.position = "fixed";
    var top = rect.bottom + 4;
    var left = rect.left;
    document.body.appendChild(pop); // 実寸を測るため、位置決め前に一度差し込む
    var popRect = pop.getBoundingClientRect();
    if (left + popRect.width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - popRect.width - 8);
    }
    if (top + popRect.height > window.innerHeight - 8) {
      top = Math.max(8, rect.top - popRect.height - 4);
    }
    pop.style.top = top + "px";
    pop.style.left = left + "px";
  }

  function watchOutside(pop, anchorEl, onClose) {
    function onOutside(e) {
      if (!pop.contains(e.target) && e.target !== anchorEl) onClose();
    }
    function onEscape(e) { if (e.key === "Escape") onClose(); }
    // 開いた瞬間のクリック（このボタン自身のclickバブリング）で即閉じないよう
    // 次のイベントループから外側クリック監視を始める
    setTimeout(function () {
      document.addEventListener("mousedown", onOutside, true);
      document.addEventListener("keydown", onEscape, true);
    }, 0);
    return function cleanup() {
      document.removeEventListener("mousedown", onOutside, true);
      document.removeEventListener("keydown", onEscape, true);
    };
  }

  // PowerPointの色選択に近い並び。「文字色」「背景色」の2区画を1つの
  // ポップオーバーに出し、それぞれ「標準の色」「wikiの色」を2段のグリッドで
  // 表示する。選ぶだけでは確定させず、「適用」で1回だけ &color() を挿入する
  // （文字色・背景色を同時に指定できるようにするため。詳しくは applyColorChoice）。
  function openColorPopover(button, action) {
    closePopover();
    var selectedFg = null;
    var selectedBg = null;

    var pop = document.createElement("div");
    pop.className = "edit-color-popover";

    function addSection(title, getSelected, setSelected) {
      var section = document.createElement("div");
      section.className = "edit-color-section";
      var heading = document.createElement("div");
      heading.className = "edit-color-section-label";
      heading.textContent = title;
      section.appendChild(heading);
      var swatches = [];

      function refresh() {
        var cur = getSelected();
        swatches.forEach(function (s) {
          s.classList.toggle("edit-color-swatch--selected", s.dataset.color === cur);
        });
      }

      function addRow(label, colors) {
        if (!colors || !colors.length) return;
        var row = document.createElement("div");
        row.className = "edit-color-row";
        var caption = document.createElement("div");
        caption.className = "edit-color-row-label";
        caption.textContent = label;
        row.appendChild(caption);
        var grid = document.createElement("div");
        grid.className = "edit-color-grid";
        colors.forEach(function (color) {
          var swatch = document.createElement("button");
          swatch.type = "button";
          swatch.className = "edit-color-swatch";
          swatch.style.backgroundColor = color;
          swatch.title = color;
          swatch.dataset.color = color;
          swatch.setAttribute("aria-label", color);
          swatch.addEventListener("click", function () {
            // 同じ色をもう一度押すと選択解除（この色を指定しない）
            setSelected(getSelected() === color ? null : color);
            refresh();
          });
          swatches.push(swatch);
          grid.appendChild(swatch);
        });
        row.appendChild(grid);
        section.appendChild(row);
      }
      addRow("標準の色", action.base_colors);
      addRow("wikiの色", action.custom_colors);
      pop.appendChild(section);
    }

    addSection("文字色", function () { return selectedFg; }, function (v) { selectedFg = v; });
    addSection("背景色", function () { return selectedBg; }, function (v) { selectedBg = v; });

    var actionsRow = document.createElement("div");
    actionsRow.className = "edit-color-actions";
    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "edit-color-cancel";
    cancelBtn.textContent = "キャンセル";
    cancelBtn.addEventListener("click", closePopover);
    var applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "edit-color-apply";
    applyBtn.textContent = "適用";
    applyBtn.addEventListener("click", function () {
      applyColorChoice(selectedFg, selectedBg);
      closePopover();
    });
    actionsRow.appendChild(cancelBtn);
    actionsRow.appendChild(applyBtn);
    pop.appendChild(actionsRow);

    positionPopover(pop, button);
    activePopover = pop;
    activePopoverCleanup = watchOutside(pop, button, closePopover);
  }

  // プリセット（元の大きさに対する増減%）のみ。任意の数値入力は持たない
  function openSizePopover(button, action) {
    closePopover();
    var pop = document.createElement("div");
    pop.className = "edit-size-popover";

    var presetRow = document.createElement("div");
    presetRow.className = "edit-size-presets";
    (action.size_percents || []).forEach(function (delta) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "edit-size-preset";
      btn.textContent = (delta > 0 ? "+" : "") + delta + "%";
      btn.addEventListener("click", function () {
        applySizeChoice(100 + delta);
        closePopover();
      });
      presetRow.appendChild(btn);
    });
    pop.appendChild(presetRow);

    positionPopover(pop, button);
    activePopover = pop;
    activePopoverCleanup = watchOutside(pop, button, closePopover);
  }

  // ボタンは記法を切り替えるたびに作り直すので、個々にではなく
  // ツールバー自体で受ける（作り直しのたびに登録し直さずに済む）
  var toolbar = form.querySelector(".edit-toolbar");
  if (toolbar) {
    toolbar.addEventListener("click", function (event) {
      var button = event.target.closest && event.target.closest(".edit-tool");
      if (!button) return;
      var action = actions[button.dataset.action];
      if (!action) return;
      if (action.palette) { openColorPopover(button, action); return; }
      if (action.size_percents) { openSizePopover(button, action); return; }
      closePopover();
      applyAction(action);
    });
  }

  /* ---- プレビュー（保存時と同じレンダラをサーバーで通す） ---- */
  var timer = null;
  var lastSent = null;
  var previewSeq = 0;   // 送った順と応答が届く順が入れ替わっても、最後に送ったものだけ反映する
  // **プレビューの要求を溜めない**（Wiki設計者の指示、2026-09-27）。応答を待って
  // いるあいだに本文が変わっても次は送らず、印（previewAgain）だけを付けておき、
  // 応答が届いたら最新の本文で1回だけ送り直す。`#pagediv` などで多くのページを
  // 差し込むページはプレビュー1回の描画が重く、打ち続けると重い描画がサーバーに
  // 積み重なって、CPUが張り付き他の画面の応答まで止まっていたため
  var previewInFlight = false;
  var previewAgain = false;

  function previewDone() {
    previewInFlight = false;
    if (previewAgain) {
      previewAgain = false;
      updatePreview();
    }
  }

  function updatePreview() {
    if (!preview || !previewUrl) return;
    if (previewInFlight) {
      previewAgain = true;
      return;
    }
    var text = source.value;
    if (text === lastSent) return;
    lastSent = text;
    var seq = ++previewSeq;
    previewInFlight = true;
    fetch(previewEndpoint(), { method: "POST", body: text })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) {
        if (seq !== previewSeq) return;  // 後から送った分の応答がまだ届いていない
        preview.innerHTML = html || '<p class="edit-preview-empty">プレビュー</p>';
        // **差し込んだ分を自分で拾い直させる。** ページ読み込み時に一度
        // 走るだけの仕組みを持つものは、innerHTMLで入れ替えたここでは
        // 動かない（Wiki設計者からの指摘: プレビューに色が付かない／数式が
        // 生のまま出る）。編集画面自体は登録済み全プラグインの資材を
        // 無条件で読み込んでいる（build_edit_page_html参照）ので、
        // 読み込まれてさえいれば必ず拾える。
        if (typeof Prism !== "undefined") Prism.highlightAllUnder(preview);
        if (window.KatexPlugin) window.KatexPlugin.renderAllUnder(preview);
        rebuildPreviewAnchors();
        syncPreviewScroll();
      })
      .catch(function () {
        // 失敗しても編集の妨げにしない。前回の表示を残す
      })
      .then(previewDone);
  }

  /* ---- プレビュー・オリジナル欄内のリンクはクリックしても遷移させない ----
   * どちらも「今の内容の確かめ」であって、そこから実際に別ページへ移る
   * 場面ではないため（オリジナル欄からうっかり遷移すると、書きかけの
   * 編集内容がその場に残ったまま画面だけ切り替わってしまう）。リンク先を
   * 確かめたいときのために、Shift+クリックだけは止めない（ブラウザ標準の、
   * 新しいウィンドウで開く動作がそのまま働く）。 */
  /* プレビューと「オリジナル」欄を、見るだけのものにする（Wiki設計者の指示、
     2026-09-01）。どちらもページをレンダリングした結果をそのまま埋め込む
     ので、放っておくと本文の中のリンクやフォームがそのまま働いてしまい、
     書きかけを残したまま編集画面から出て行ってしまう。

       フォームの送信   **一切通さない**
       リンク           Shift+クリックのときだけ通す（リンク先を確かめる
                        ための逃げ道。Wiki設計者の指示で残してある）

     サーバー側でも本文中の <form> は無害な <div> に付け替えてある
     （editor.disable_embedded_forms）。JSが動かない場合の備えなので、
     どちらか一方ではなく両方で止める。 */
  function makeInert(el) {
    if (!el) return;
    // 送信は capture で受けて、他のどのハンドラより先に止める
    el.addEventListener("submit", function (event) {
      event.preventDefault();
      event.stopPropagation();
    }, true);
    el.addEventListener("click", function (event) {
      var target = event.target.closest && event.target.closest("a, button, input, select");
      if (!target) return;
      // リンクだけは Shift+クリックで移動できる（それ以外は押しても何も起きない）
      if (target.tagName === "A" && event.shiftKey) return;
      event.preventDefault();
    });
    // キーボードでも同じ扱いにする（Enterでリンクをたどれてしまうため）
    el.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      var target = event.target.closest && event.target.closest("a, button, input, select");
      if (!target) return;
      if (target.tagName === "A" && event.shiftKey) return;
      event.preventDefault();
    });
  }
  makeInert(preview);
  makeInert(form.querySelector(".edit-origin"));

  /* ---- 本文とプレビューのスクロール位置を合わせる ----
   * 本文側（テキストエリア）が動いたときだけプレビュー側を追わせる（逆はしない。
   * ユーザーがプレビューだけ動かしても、次に本文が動くまでは邪魔しない）。
   *
   * サーバーが振った data-line（tag_source_lines、editor.pyのrender_preview）を
   * 手がかりに、本文の「今いちばん上に見えている行」に対応するプレビュー内の
   * 要素を探し、そこへ合わせる（アンカーの間は行番号の比率で補間するので、
   * data-line が無い行でもだいたいの位置に合う）。
   *
   * 本文はテキストエリアの折り返しがあるため、スクロール位置から「今何行目が
   * 見えているか」を単純な行の高さの掛け算では出せない（長い行が複数行に
   * 折り返されるため）。同じ見た目で隠しておいた <div>（mirror）に同じ文字列を
   * 流し込み、各行の先頭に置いた印（span）の実際の描画位置（offsetTop）を
   * 読むことで、折り返しを含めた正確な位置を得る。 */
  var mirror = null;
  var sourceLineTops = null;   // 行番号 → テキストエリア内でのY座標（折り返し込み）
  // 本文が変わって、sourceLineTops を測り直す必要があるか。**1字ごとには測らない**
  // （Wiki設計者の指示、2026-09-27）。全行を写した複製のレイアウトを伴うので、
  // 長いページでは1字ごとに数十ミリ秒かかり、打つたびに引っかかっていた。
  // 測るのは位置を合わせる直前（syncPreviewScroll）に、この印が立っていれば1回だけ
  var sourceLinesDirty = false;
  var previewAnchors = [];     // [{line, top}, ...]（data-lineを振られた要素、文書順）

  if (source && preview) {
    mirror = document.createElement("div");
    mirror.setAttribute("aria-hidden", "true");
    mirror.style.position = "fixed";
    mirror.style.top = "0";
    mirror.style.left = "-99999px";
    mirror.style.margin = "0";
    mirror.style.height = "auto";
    mirror.style.visibility = "hidden";
    mirror.style.pointerEvents = "none";
    mirror.style.whiteSpace = "pre-wrap";
    mirror.style.overflowWrap = "break-word";
    document.body.appendChild(mirror);
  }

  function syncMirrorStyle() {
    if (!mirror) return;
    var cs = window.getComputedStyle(source);
    ["fontFamily", "fontSize", "fontWeight", "fontStyle", "letterSpacing",
     "lineHeight", "textTransform", "wordSpacing", "wordBreak", "tabSize",
     "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
     "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
     "boxSizing"].forEach(function (prop) {
      mirror.style[prop] = cs[prop];
    });
    mirror.style.width = source.clientWidth + "px";
  }

  function rebuildSourceLineOffsets() {
    if (!mirror) return;
    var lines = source.value.split("\n");
    var frag = document.createDocumentFragment();
    var spans = [];
    lines.forEach(function (line, i) {
      if (i > 0) frag.appendChild(document.createTextNode("\n"));
      var span = document.createElement("span");
      frag.appendChild(span);
      spans.push(span);
      if (line) frag.appendChild(document.createTextNode(line));
    });
    mirror.textContent = "";
    mirror.appendChild(frag);
    // ここで初めてレイアウトが確定する。以降の offsetTop の読み出しは
    // 追加のレイアウト計算を発生させない（書き込みを挟まないため）
    sourceLineTops = spans.map(function (span) { return span.offsetTop; });
    sourceLinesDirty = false;
  }

  function topLineAtScrollTop(scrollTop) {
    var tops = sourceLineTops;
    if (!tops || !tops.length) return 0;
    var lo = 0, hi = tops.length - 1;
    while (lo < hi) {
      var mid = (lo + hi + 1) >> 1;
      if (tops[mid] <= scrollTop) lo = mid; else hi = mid - 1;
    }
    return lo;
  }

  function rebuildPreviewAnchors() {
    if (!preview) { previewAnchors = []; return; }
    // el.offsetTop は「直近の position 指定祖先」からの位置で、.edit-preview
    // 自身は position を指定していないため、そのままではページ上部からの
    // 位置になってしまう（ヘッダ等の高さぶんずれる）。getBoundingClientRect
    // どうしの差なら、position の指定に関係なく preview の中身の原点からの
    // 位置になる。
    var previewTop = preview.getBoundingClientRect().top - preview.scrollTop;
    previewAnchors = [].slice.call(preview.querySelectorAll("[data-line]")).map(function (el) {
      var top = el.getBoundingClientRect().top - previewTop;
      return { line: parseInt(el.getAttribute("data-line"), 10), top: top };
    });
  }

  function syncPreviewScroll() {
    if (!preview || !mirror) return;
    if (sourceLinesDirty) rebuildSourceLineOffsets();
    var maxPreviewScroll = preview.scrollHeight - preview.clientHeight;
    if (maxPreviewScroll <= 0) return;

    var lineIdx = topLineAtScrollTop(source.scrollTop);
    var targetY = null;
    var exact = false;

    var before = null, after = null;
    for (var i = 0; i < previewAnchors.length; i++) {
      var a = previewAnchors[i];
      if (a.line <= lineIdx) { before = a; }
      if (a.line > lineIdx) { after = a; break; }
    }
    if (before && after) {
      var ratio = (lineIdx - before.line) / (after.line - before.line);
      targetY = before.top + ratio * (after.top - before.top);
      exact = true;
    } else if (before || after) {
      targetY = (before || after).top;
      exact = true;
    }

    if (targetY === null) {
      // data-line を振られた要素が1つも見つからなかった（プラグイン出力だけの
      // ページ等）。文書全体に対する比率で合わせる
      var maxSourceScroll = source.scrollHeight - source.clientHeight;
      var ratio2 = maxSourceScroll > 0 ? source.scrollTop / maxSourceScroll : 0;
      targetY = ratio2 * preview.scrollHeight;
    } else if (exact) {
      // 厳密に対応が取れた場合は、対応位置がプレビューの上から1/3くらいに
      // 来るようにする（画面の最上段だと直前の文脈が見えない）
      targetY -= preview.clientHeight / 3;
    }

    preview.scrollTop = Math.max(0, Math.min(maxPreviewScroll, targetY));
  }

  var scrollSyncPending = false;
  function requestScrollSync() {
    if (scrollSyncPending) return;
    scrollSyncPending = true;
    window.requestAnimationFrame(function () {
      scrollSyncPending = false;
      syncPreviewScroll();
    });
  }

  if (mirror) {
    syncMirrorStyle();
    rebuildSourceLineOffsets();

    source.addEventListener("scroll", requestScrollSync);

    if (window.ResizeObserver) {
      new ResizeObserver(function () {
        syncMirrorStyle();
        rebuildSourceLineOffsets();
        requestScrollSync();
      }).observe(source);
    } else {
      window.addEventListener("resize", function () {
        syncMirrorStyle();
        rebuildSourceLineOffsets();
        requestScrollSync();
      });
    }
  }

  source.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(updatePreview, PREVIEW_DEBOUNCE);
    // 本文側の行位置は、ここでは測り直さず印だけを立てる（sourceLinesDirty）。
    // 以前はここで測り直して位置も合わせていたが、1字ごとに全行の複製の
    // レイアウトが走り、長いページで打つたびに引っかかっていた（2026-09-27）。
    // 位置はプレビューが届いたとき（updatePreview）と、本文をスクロールしたとき
    // （requestScrollSync）に、印が立っていれば測り直してから合わせる
    sourceLinesDirty = true;
  });

  markupRadios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      if (!radio.checked) return;
      useFormat(radio.value);
      // 本文が同じでも、記法が変われば見えかたは変わる
      lastSent = null;
      updatePreview();
    });
  });
  useFormat(currentMarkup());

  // GhostTextのような外部エディタ連携ツールは、textareaのvalueを直接書き換えて
  // inputイベントを発火させないことがある。プレビューが取り残されないよう、
  // 値の変化を控えめな間隔で見にいく（textareaを唯一の正とみなす作りにしてある
  // ので、外部から書き換えられてもそのまま保存できる）。
  var watched = source.value;
  window.setInterval(function () {
    if (source.value === watched) return;
    watched = source.value;
    window.clearTimeout(timer);
    timer = window.setTimeout(updatePreview, PREVIEW_DEBOUNCE);
  }, 500);

  /* ---- Tabで字下げ ---- */
  source.addEventListener("keydown", function (event) {
    if (event.key !== "Tab") return;
    event.preventDefault();
    replaceSelection("  ");
  });

  /* ---- Ctrl+S で保存 ----
   * **保存ボタンを押すのと同じ道を通す。** 実際に送るのはボタンだけの
   * 小さなフォーム（`.edit-actions`）で、書きかけを預けてから送る手順は
   * その submit ハンドラが持っている。
   *
   * ここは長く壊れていた。2026-09-01に編集画面の全体を `<form>` で囲むのを
   * やめたとき、`form`（`.page-editor`）が `<div>` になったのに
   * `form.requestSubmit()` を呼ぶままだったため、押すと例外が出て**何も
   * 起きなかった**（Wiki設計者の報告、2026-09-05）。
   *
   * 聞くのは `document`。本文欄から手が離れていても（プレビューや差分を
   * 見たあとでも）効かないと、押した人には壊れているのと区別が付かない。
   * ダイアログ（ページ選択など）が開いているあいだは横取りしない（ESCと同じ）。
   */
  document.addEventListener("keydown", function (event) {
    if (!event.ctrlKey && !event.metaKey || event.shiftKey || event.altKey) return;
    // CapsLockが入っていると key は "S" で届く（Shiftは押されていない）ので、
    // 大小は無視する。Ctrl+Shift+S は別の操作なので上の行で外してある
    if (!event.key || event.key.toLowerCase() !== "s") return;
    if (document.querySelector("dialog[open]")) return;
    event.preventDefault();
    // 送信中は保存ボタンが disabled になるので、二重に送られることはない。
    // **文書全体から探す。** 画面が低い（高さ500px未満）と、editor.js 自身が
    // `.edit-buttons` をタブの行へ移し、`.page-editor`（`form`）の外に出る。
    // `form.querySelector` で探していたため、そのとき Ctrl+S が黙って効かなく
    // なっていた（2026-09-20に直した。保存の送信の横取りと同じ不具合）
    var saveBtn = document.querySelector(".edit-save");
    if (saveBtn) saveBtn.click();
  });

  /* ---- 書きかけを預かる（一時保存） ----
   * 入力が DRAFT_IDLE のあいだ止まったら、そこまでの本文をサーバーに預ける。
   * 保存を押すまで手元にしか無い状態が続くと、閉じてしまったときや保存に
   * 失敗したときに、書いたものがそのまま消えてしまうため。
   *
   * **保存も、預けたものをファイルにするだけにしてある。** 本文をフォームで
   * 送り直さないので、長いページでも保存の送信は小さいまま済む
   * （フォームの送信は日本語で3倍に膨らみ、長いページだと上限に届く）。
   */
  var DRAFT_IDLE = 30000;
  var initial = source.value;
  var kept = initial;        // 最後に預かってもらえた内容
  var draftTimer = null;
  // 文書全体から探す（`.edit-buttons` の中にあり、画面が低いと `form` の外へ移る。
  // 上の Ctrl+S と同じ理由。探し損ねると、一時保存の表示が出なくなる）
  var draftState = document.querySelector(".edit-draft-state");

  function showDraftState(text, bad) {
    if (!draftState) return;
    draftState.textContent = text;
    draftState.classList.toggle("is-bad", !!bad);
  }

  function timeLabel() {
    var d = new Date();
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  function keepDraft() {
    if (source.value === kept) return Promise.resolve(true);
    if (!window.FormData || !window.Blob || !window.XMLHttpRequest) {
      return Promise.resolve(false);
    }
    var text = source.value;
    var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    var chunkBytes = wikiSend.chunkBytesOf(form);
    showDraftState("一時保存中…");

    // 開いたときの origin も一緒に送る。サーバー側がこの書きかけの
    // 「元になった本文」として覚えておき、あとで cmd=edit のたびに
    // 最新化するのではなく、この値をそのまま使い続ける（一時中断→再開の
    // 間に他の誰かがページを更新していた場合の競合検出に使うため）。
    var origin = form.dataset.origin || "";

    // 1回で収まらない長さなら、切って何回かに分けて送る。
    // 収まるなら、そのまま source として送る（受け取り側の道も分かれている）
    var sending;
    if (blob.size > chunkBytes) {
      sending = wikiSend.sendChunked(postUrl, { "cmd": "draft", "origin": origin }, blob, "",
                                     chunkBytes, null);
    } else {
      var data = new FormData();
      data.append("cmd", "draft");
      data.append("origin", origin);
      data.append("source", text);
      sending = wikiSend.postForm(postUrl, data);
    }

    return sending.then(function (res) {
      if (res.ok) {
        kept = text;
        showDraftState("一時保存しました " + timeLabel());
        return true;
      }
      // 預かれなかったことは必ず出す。黙って続けると、預かってもらえた
      // つもりで書き続けたぶんが保存のときに失われる
      showDraftState(res.text || "一時保存できませんでした", true);
      return false;
    }, function (err) {
      showDraftState("一時保存できませんでした（" +
                     ((err && err.message) || "原因不明") + "）", true);
      return false;
    });
  }

  source.addEventListener("input", function () {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(keepDraft, DRAFT_IDLE);
  });

  // 保存せずにページを離れようとしたら確認する。
  // ただしページ一覧から移る場合は、書きかけを預けてから黙って移る（下を参照）。
  var saving = false;
  var submitting = false;

  /* ---- 送信 ----
   * **囲んでいるのはボタンだけ**（.edit-actions）。本文・origin・記法は
   * その外にあるので、押された時点でここが集めて隠し項目へ詰める
   * （Wiki設計者の指示、2026-09-01）。編集画面の全体を <form> で囲むのをやめた
   * ことで、本文のプラグインが返す <form> と入れ子にならなくなった。
   *
   * 詰め終えたら、その小さなフォームをそのまま送る。応答（保存できたら
   * 303でページへ、競合したら編集画面を出し直す、大きすぎれば案内）の
   * 扱いはブラウザに任せたままにしてある。
   */
  // **文書全体から探す。** 画面が低いとき、editor.js 自身が `.edit-buttons`
  // （この <form> の入れもの）をタブの行へ移すことがあり、そのとき
  // `.page-editor` の外へ出る。`form.querySelector` で探していたため
  // null になり、**保存の横取りが黙って効かなくなっていた**
  // （Wiki設計者の報告、2026-09-10。iPhoneでページが消されかけた）。
  // **この変数を `actions` と呼ばない。** 上（記法の切り替え）に、ツールバーの操作の
  // 対応表として同じ関数の中に `var actions = {}` がある。同じ名前だと、どちらかを
  // 代入したとき他方が壊れる——2026-09-10にここを `actions` と書いたため、開いた
  // 直後にツールバーが効かず、記法を選び直すと今度は保存が黙って失敗していた
  // （2026-09-19に発見）。
  var actionForm = document.querySelector(".edit-actions");
  if (!actionForm) return;

  function fill(name, value) {
    var field = actionForm.querySelector('input[name="' + name + '"]');
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = name;
      actionForm.appendChild(field);
    }
    field.value = value;
    return field;
  }

  /* ---- 連続編集 ----
   * 入っていれば、保存と内容破棄のあとに元のページへ戻らず、この画面に留まる
   * （Wiki設計者の指示、2026-09-19）。値は押された瞬間に `continuous` として
   * 詰める（下の collect）。一時中断（ESC）と「ページを見る」は関わらない。
   *
   * **選び直しは覚えておく**（localStorage）。外した人が、ページを開くたびに
   * 入れ直されるのは困るため。何も覚えていなければ、入った状態から始まる
   * （既定）。localStorage が使えない環境では、毎回入った状態になるだけ。
   */
  var continuousBox = document.querySelector(".edit-continuous-check");
  var CONTINUOUS_KEY = "wikiEditContinuous";
  if (continuousBox) {
    try {
      if (window.localStorage.getItem(CONTINUOUS_KEY) === "0") continuousBox.checked = false;
    } catch (e) { /* 覚えていなければ、既定（入っている）のまま */ }
    continuousBox.addEventListener("change", function () {
      try {
        window.localStorage.setItem(CONTINUOUS_KEY, continuousBox.checked ? "1" : "0");
      } catch (e) { /* 覚えられなくても、この画面では効く */ }
    });
  }

  /* 連続編集で保存したあと、編集画面は開き直される。**カーソルとスクロールを
   * そのままにしておかないと、保存するたびに先頭へ戻される**（Ctrl+S を
   * 何度も押す使いかたが成り立たない）。保存の直前に位置を控え、開き直した
   * 画面で戻す。控えは1回きりで、古いもの（保存が別の画面へ回った場合など）は
   * 使わない。 */
  var POSITION_KEY = "wikiEditPosition";
  var POSITION_FRESH_MS = 60000;

  function rememberPosition() {
    try {
      window.sessionStorage.setItem(POSITION_KEY, JSON.stringify({
        action: form.dataset.action, start: source.selectionStart,
        end: source.selectionEnd, top: source.scrollTop, at: Date.now(),
      }));
    } catch (e) { /* 覚えられなければ、先頭から始まるだけ */ }
  }

  function restorePosition() {
    var saved = null;
    try {
      saved = JSON.parse(window.sessionStorage.getItem(POSITION_KEY) || "null");
      window.sessionStorage.removeItem(POSITION_KEY);
    } catch (e) { return; }
    if (!saved || saved.action !== form.dataset.action) return;
    if (Date.now() - saved.at > POSITION_FRESH_MS) return;
    var length = source.value.length;   // 保存時の置換（&date; など）で長さが変わりうる
    source.focus();
    source.setSelectionRange(Math.min(saved.start, length), Math.min(saved.end, length));
    source.scrollTop = saved.top;
  }

  // form.submit() はどのボタンで送信したかを運ばないため（.click() と違い
  // submitter が無い）、押したボタンの意味を hidden 項目に控えてから送る。
  // cmd は保存でも必ず要る（サーバー側の dispatch が cmd の有無で
  // 「編集に関わる送信かどうか」を見分けるため）。
  function collect(action, withSource) {
    fill("cmd", action);
    fill("origin", form.dataset.origin || "");
    var markup = form.querySelector('input[name="markup"]:checked');
    fill("markup", markup ? markup.value : "");
    // 本文は、書きかけを預けられたなら送らない（二重に運ばない）。
    // 預けられなかったときだけ、ここに入れて一緒に送る。
    //
    // **ただし本文が空のときは、必ずそのまま送る**（Wiki設計者の報告、2026-09-10）。
    // 空の保存は「このページを消す」という指示になるので、**預かってある
    // ファイル任せにしない**——預かるところで何かが失敗して空になっていた
    // 場合に、消すつもりのない削除が起きる。サーバー側も、この道で空が来たら
    // 断るようにしてある（editor.posted_source）
    var empty = !source.value.trim();
    var send = withSource || empty;
    fill("source", send ? source.value : "");
    fill("from_draft", send ? "" : "1");

    // 連続編集か、いま開いているタブは何か。連続編集で開き直すとき、
    // サーバーが同じタブで開けるように送る
    var continuous = !!(continuousBox && continuousBox.checked);
    fill("continuous", continuous ? "1" : "");
    var shellNow = document.querySelector(".edit-shell");
    fill("tab", (shellNow && shellNow.dataset.activeTab) || "edit");
    if (continuous && action === "save") rememberPosition();
  }

  /* ---- 保存・内容破棄を押せるか ----
   * **本文が、保存されている内容から変わっていないあいだは、どちらも押せない**
   * （Wiki設計者の指示、2026-09-19）。比べる相手は「更新状況」タブの差分と
   * 同じ（DB上の本文。サーバーが `.edit-saved` のJSONで渡してくる）。
   * 差分が空なら未変更、という1つの規則。
   *
   * **記法の選び直しも変更として数える。** 本文が同じでも、保存すると拡張子
   * （保存先のファイル）が変わるため。
   *
   * 開いた直後の状態はサーバーが決めて `disabled` を付けてある（付け外しの
   * ちらつきを避ける）。ここは入力に合わせて付け外すだけ。比べる本文が
   * 届いていなければ何もしない（押せるままにする）。送信中は触らない
   * （送信が始まると、保存は二重に送られないよう無効にされる）。
   */
  var savedEl = document.querySelector(".edit-saved");
  var savedText = null;
  try {
    savedText = savedEl ? JSON.parse(savedEl.textContent) : null;
  } catch (e) { /* 読めなければ、比べずに押せるままにする */ }
  var saveButton = actionForm.querySelector(".edit-save");
  var discardButton = actionForm.querySelector(".edit-discard");

  function markupNow() {
    var chosen = form.querySelector('input[name="markup"]:checked');
    return chosen ? chosen.value : "";
  }
  var savedMarkup = markupNow();

  /** ブラウザはtextareaの改行をCRLFで扱う場合があるので、LFにそろえて比べる。 */
  function lf(text) {
    return String(text).replace(/\r\n?/g, "\n");
  }

  function refreshButtons() {
    if (savedText === null || submitting) return;
    var unchanged = lf(source.value) === lf(savedText) && markupNow() === savedMarkup;
    [saveButton, discardButton].forEach(function (button) {
      if (!button) return;
      button.disabled = unchanged;
      if (unchanged) button.title = "変更がありません";
      else button.removeAttribute("title");
    });
  }
  source.addEventListener("input", refreshButtons);
  form.addEventListener("change", refreshButtons);   // 記法の選び直し
  refreshButtons();

  /* ---- 「履歴」タブで復元したとき ----
   * 履歴から戻すと、ページの保存内容が変わる。この画面の「保存されている内容」
   * （比べる相手・競合の基準）は古くなるので、**開き直す。** ただし書きかけを
   * 失わないよう、先に預ける（預けられなかったら開き直さない）。開き直した画面は、
   * 書きかけがあればそれを出し、保存すれば競合として統合の画面へ進む
   * （復元より前の内容を元に書いていたため）。受けるのは同じ出所の、履歴タブの
   * 埋め込みからのメッセージだけ。 */
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    var data = event.data;
    if (!data || data.type !== "wiki-backup-restored") return;
    var frame = document.querySelector(".edit-history-frame");
    if (!frame || event.source !== frame.contentWindow) return;

    saving = true;   // 離脱の確認は出さない
    window.clearTimeout(draftTimer);
    keepDraft().then(function (ok) {
      if (!ok) { saving = false; return; }
      var reopen = document.createElement("form");
      reopen.method = "post";
      reopen.action = postUrl + "?tab=history";
      reopen.style.display = "none";
      var field = document.createElement("input");
      field.type = "hidden";
      field.name = "cmd";
      field.value = "edit";
      reopen.appendChild(field);
      document.body.appendChild(reopen);
      reopen.submit();
    });
  });

  actionForm.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    var action = (submitter && submitter.name === "cmd") ? submitter.value : "save";

    if (action === "discard") {
      // 内容破棄は取り消せないので確認する（添付ファイルの削除と同じ扱い）。
      // 本文を送り直す必要は無く、サーバー側は書きかけを消すだけ
      if (!window.confirm("書きかけの内容を破棄します。よろしいですか？")) {
        event.preventDefault();
        return;
      }
      saving = true;   // 離脱の確認は出さない
      event.preventDefault();
      collect(action, false);
      actionForm.submit();
      return;
    }

    // **本文を空にしての保存は、ページを消す**という約束。押し間違い・
    // 画面の不調のどちらでも取り返しがつかないので、その場で確かめる
    // （Wiki設計者の報告、2026-09-10）
    if (action === "save" && !source.value.trim()) {
      if (!window.confirm("本文が空です。このまま保存すると、このページを削除します。よろしいですか？")) {
        event.preventDefault();
        return;
      }
    }

    saving = true;   // 離脱の確認は出さない
    // 預け終わるのを待つあいだに Ctrl+S を押されても、二重に送らない
    if (submitting) { event.preventDefault(); return; }
    event.preventDefault();

    if (!window.FormData || !window.Blob) {
      // 書きかけを預ける手段が無いときは、本文をそのまま添えて送る
      collect(action, true);
      actionForm.submit();
      return;
    }

    submitting = true;
    window.clearTimeout(draftTimer);
    // 預け終わるまで少し待つので、その間にもう一度押せないようにしておく
    var saveBtn = actionForm.querySelector(".edit-save");
    if (saveBtn) saveBtn.disabled = true;
    keepDraft().then(function (ok) {
      // 預けられたなら本文は送らず、預けてあるものを使ってもらう。
      // 預けられなかったときは、本文を添えて送る（書いたものを失わない）
      collect(action, !ok);
      actionForm.submit();
    });
  });

  // ---- 一時中断（ESC） ----
  // ダイアログ（ページ選択など）が開いているときは、そちらを閉じる
  // ブラウザ標準の動きを優先する（横取りしない）。
  // 狭い画面でページ一覧を開いているときも同じで、そちらが先に閉じて
  // preventDefault で知らせてくるので、ここは引き下がる（2026-09-06）。
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (event.defaultPrevented) return;
    if (document.querySelector("dialog[open]")) return;
    // 文書全体から探す（画面が低いと `form` の外へ移る。Ctrl+S と同じ理由）
    var pauseBtn = document.querySelector(".edit-pause");
    if (pauseBtn) pauseBtn.click();
  });

  window.addEventListener("beforeunload", function (event) {
    if (saving || source.value === initial) return;
    event.preventDefault();
    event.returnValue = "";
  });

  updatePreview();
  restorePosition();

  /* ---- 更新状況（差分）タブ ----
   * タブの切り替え自体は共通の editor-tab-before/after（上のIIFE）に任せ、
   * ここでは「更新状況」タブになったときだけ要る後始末（差分の取得・
   * スクロール位置の引き継ぎ）を、そのイベントを聞いて行う。
   */
  var shell = form.closest(".edit-shell");
  var diffPane = form.querySelector(".edit-diff");
  var originPane = form.querySelector(".edit-origin");
  var diffUrl = form.dataset.diffUrl;
  var DIFF_DEBOUNCE = 500;
  var diffTimer = null;
  var diffSent = null;
  var activeTab = shell ? shell.dataset.activeTab : "edit";
  var beforeTabPos = null;

  function colorFallback(text) {
    // サーバーから色付きで返るのが普通。取れなかったときの逃げ道として、
    // 素のテキストでも読める形にしておく
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function updateDiff(force) {
    if (!diffPane || !diffUrl) return;
    var text = source.value;
    if (!force && text === diffSent) return;
    diffSent = text;
    fetch(diffUrl, { method: "POST", body: text })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) {
        diffPane.innerHTML = html;
        // 中身が入れ替わったので、いまのオリジナルの位置に合わせ直す
        if (activeTab === "diff") syncFrom(originPane, [diffPane]);
      })
      .catch(function () {
        diffPane.innerHTML = '<span class="d-at">' +
          colorFallback("差分を取得できませんでした。") + "</span>";
      });
  }

  if (shell) {
    shell.addEventListener("editor-tab-before", function (event) {
      // 要素を隠すとスクロール位置は 0 に戻ってしまうため、隠す前に控える
      // （編集画面・更新状況どうしの行き来のときだけ意味がある）。
      var from = event.detail.from;
      if (from === "diff") beforeTabPos = capturePosition(originPane);
      else if (from === "edit") beforeTabPos = capturePosition(preview);
      else beforeTabPos = null;
    });
    shell.addEventListener("editor-tab-after", function (event) {
      activeTab = event.detail.to;
      if (activeTab === "diff") {
        applyPosition(originPane, beforeTabPos);
        // 差分はまだ取りに行っている最中。届いてから位置を合わせる（updateDiff内）
        updateDiff(true);
      } else if (activeTab === "edit") {
        applyPosition(preview, beforeTabPos);
      }
    });
  }

  source.addEventListener("input", function () {
    if (activeTab !== "diff") return;
    window.clearTimeout(diffTimer);
    diffTimer = window.setTimeout(updateDiff, DIFF_DEBOUNCE);
  });

  // 上のタブ切り替えIIFEはこのIIFEより先に動き、開いた時点のタブへの
  // 初回切り替えもそちらで既に済んでいる（editor-tab-after はそのときに
  // 発火済みで、このリスナーの登録には間に合わない）。開いた時点で
  // 既に「更新状況」タブなら、ここで一度だけ追いつかせる。
  if (activeTab === "diff") updateDiff(true);

  /* ---- 表示位置の同期 ----
   * 見出しを対応点（アンカー）にして揃える。左右で行数も高さも違うため、
   * 比率で合わせると本文が長いほどずれていく。見出しなら、増減しない限り
   * 同じ場所を指し続けるので、対応が崩れない。
   *
   * アンカーとアンカーの間は、その区間内での進み具合で内挿する
   * （見出しの直後で急に飛ばず、なめらかに追従させるため）。
   * 共通のアンカーが1つも無いページ（見出しが無い等）では、
   * 比率でのおおまかな追従に切り替える。
   */
  function anchorsIn(pane) {
    if (!pane) return [];
    var found = [];
    var seen = {};
    // 描画済みの見出し（id付き）と、差分の行に付けた data-anchor の両方を拾う
    pane.querySelectorAll("[id], [data-anchor]").forEach(function (el) {
      var key = el.dataset.anchor || el.id;
      if (!key || seen[key]) return;   // 同じ見出しの2つ目以降は最初の位置を使う
      seen[key] = true;
      found.push({ key: key, el: el });
    });
    return found;
  }

  function offsetIn(pane, el) {
    // pane を基準にした要素の上端。offsetParent を辿らずに済むよう矩形の差で取る
    return el.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  }

  function commonAnchors(from, to) {
    var a = anchorsIn(from);
    var b = {};
    anchorsIn(to).forEach(function (item) { b[item.key] = item.el; });
    var pairs = [];
    a.forEach(function (item) {
      if (!b[item.key]) return;
      pairs.push({ from: offsetIn(from, item.el), to: offsetIn(to, b[item.key]) });
    });
    pairs.sort(function (x, y) { return x.from - y.from; });
    return pairs;
  }

  function ratioScroll(from, to) {
    // 対応点が1つも無いときの逃げ道。全体に対する進み具合だけを合わせる
    var room = from.scrollHeight - from.clientHeight;
    var r = room > 0 ? from.scrollTop / room : 0;
    setScroll(to, r * Math.max(0, to.scrollHeight - to.clientHeight));
  }

  // こちらから動かした側は、その反動で返ってくるscrollイベントを聞き流す。
  // 聞いてしまうと相手を動かし返し、往復するたびに少しずつ行き過ぎてしまう。
  // 「動かされた側だけ」を黙らせるので、利用者が自分でスクロールしている側は
  // いつもどおり反応する。
  var quietUntil = new WeakMap();
  var QUIET_MS = 250;

  function setScroll(pane, value) {
    value = Math.max(0, Math.min(value, pane.scrollHeight - pane.clientHeight));
    if (Math.abs(pane.scrollTop - value) < 1) return;
    quietUntil.set(pane, Date.now() + QUIET_MS);
    pane.scrollTop = value;
  }

  function isQuiet(pane) {
    return Date.now() < (quietUntil.get(pane) || 0);
  }

  function syncPair(from, to) {
    if (!from || !to || from === to) return;
    var pairs = commonAnchors(from, to);
    if (pairs.length < 1) { ratioScroll(from, to); return; }

    var y = from.scrollTop;
    // いま画面の上端より上にある最後のアンカーと、その次のアンカーを探す
    var i = -1;
    for (var k = 0; k < pairs.length; k++) {
      if (pairs[k].from <= y + 1) i = k; else break;
    }
    if (i < 0) {
      // 最初のアンカーより手前。先頭からその点までを同じ割合で送る
      var head = pairs[0];
      var t = head.from > 0 ? y / head.from : 0;
      setScroll(to, t * head.to);
      return;
    }
    var cur = pairs[i];
    var next = pairs[i + 1];
    if (!next) {
      // 最後のアンカーより後ろ。残りの長さを同じ割合で送る
      var restFrom = Math.max(1, from.scrollHeight - cur.from);
      var restTo = Math.max(0, to.scrollHeight - cur.to);
      setScroll(to, cur.to + (y - cur.from) / restFrom * restTo);
      return;
    }
    var span = Math.max(1, next.from - cur.from);
    var t2 = (y - cur.from) / span;
    setScroll(to, cur.to + t2 * (next.to - cur.to));
  }

  function syncFrom(from, targets) {
    if (!from) return;
    targets.forEach(function (to) { if (to) syncPair(from, to); });
  }

  /* 表示を入れ替えるときは、上端にいちばん近い対応点と、そこからの距離を控えて
     持ち越す。左右を並べて見るときと違い、切り替えの前後で相手が隠れているため、
     その場で測って合わせることができないからである。 */
  function capturePosition(pane) {
    if (!pane) return null;
    var y = pane.scrollTop;
    var items = anchorsIn(pane);
    var best = null;
    items.forEach(function (item) {
      var top = offsetIn(pane, item.el);
      if (top <= y + 1) best = { key: item.key, delta: y - top };
    });
    if (!best && items.length) {
      // まだ最初の対応点より手前。そこまでの距離をそのまま持ち越す
      best = { key: items[0].key, delta: y - offsetIn(pane, items[0].el) };
    }
    if (best) return best;
    var room = pane.scrollHeight - pane.clientHeight;
    return { ratio: room > 0 ? y / room : 0 };
  }

  function findAnchor(pane, key) {
    if (!pane || !key) return null;
    var esc = window.CSS && CSS.escape ? CSS.escape(key) : key.replace(/"/g, '\\"');
    return pane.querySelector('[id="' + esc + '"]') ||
           pane.querySelector('[data-anchor="' + esc + '"]');
  }

  function applyPosition(pane, pos) {
    if (!pane || !pos) return;
    var el = findAnchor(pane, pos.key);
    if (el) { setScroll(pane, offsetIn(pane, el) + pos.delta); return; }
    if (typeof pos.ratio === "number") {
      setScroll(pane, pos.ratio * Math.max(0, pane.scrollHeight - pane.clientHeight));
    }
  }

  function watchScroll(pane, targets) {
    if (!pane) return;
    pane.addEventListener("scroll", function () {
      if (isQuiet(pane)) return;   // こちらから動かした反動なので何もしない
      syncFrom(pane, targets);
    });
  }

  watchScroll(diffPane, [originPane]);
  watchScroll(originPane, [diffPane]);

  /* ---- ページ一覧から別のページへ移る ----
   * 書きかけがあれば、確認を出さずに一時保存してから移る。
   * 「保存しますか？」と訊かれるより、預かっておいて戻ってきたときに
   * 続きから書けるほうが素直だと考えたため。
   *
   * 一覧（上の「サイドバーのページ一覧」）の `navigate` から呼ばれる。以前は一覧の
   * リンク（`.edit-pages-link`）のクリックをここで待ち受けていたが、一覧を共通の
   * TreeView に置き換えたとき（2026-08-20）にそのリンクが無くなり、**預けずに移る
   * うえ、離脱の確認が出る**状態になっていた（Wiki設計者の報告、2026-09-27）。
   * 待ち受けるのをやめ、一覧の側から呼んでもらう形にした。
   *
   * **預けられなかったら移らない。** 以前は失敗しても移っていたので、そのぶんの
   * 書きかけを失う余地があった。留まって、一時保存の欄に理由を出す（keepDraft）。
   */
  window.wikiEditorLeave = function (go) {
    saving = true;   // 確認ダイアログを出さずに移る
    window.clearTimeout(draftTimer);
    keepDraft().then(function (ok) {
      if (ok) { go(); return; }
      saving = false;
    }, function () { saving = false; });
  };
})();
