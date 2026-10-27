// 確認と名前の衝突のダイアログ。<dialog> の showModal を使い、Promise で答えを返す。
// ダイアログは画面の根（.fd-app）の中に置き、見た目を閉じ込める。

import { h, icon } from "./dom.js";
import { attributeText, attributeValue, mountAttributes } from "./attributes.js";
import { entryIcon } from "./icons.js";
import { formatSize } from "./format.js";
import { carriesFiles, filesFromDrop, filesFromInput, groupUploads } from "./upload.js";

let host = null;

export function setDialogHost(el) {
  host = el;
}

function open(content, { onCancel }) {
  const dlg = h("dialog", { class: "fd-dialog" }, content);
  dlg.returnFocus = document.activeElement; // 閉じたら元の場所へフォーカスを戻す（続けてキー操作できるように）
  (host || document.body).append(dlg);
  dlg.addEventListener("cancel", (e) => {
    e.preventDefault(); // Esc で閉じるときも、答え（取り消し）を返してから閉じる
    onCancel();
  });
  dlg.showModal();
  return dlg;
}

function close(dlg) {
  dlg.close();
  dlg.remove();
  if (dlg.returnFocus && dlg.returnFocus.isConnected) dlg.returnFocus.focus();
}

/**
 * 状態表示のダイアログ（結果の語彙 modal）。BackEnd が決めた中身を、文字として描く（HTML としては描かない）。
 * type "ok" は［OK］だけで "ok" を、"yesno" は［はい］［いいえ］で "yes" / "no" を返す（Esc・閉じるは "no"）。
 * rows は [[項目, 値], …] の表。def は最初にフォーカスするボタン（"yes" / "no"）。
 */
export function modalDialog({ type = "ok", title = "", message = "", rows = [], default: def = "yes" }) {
  return new Promise((resolve) => {
    let dlg;
    const done = (answer) => {
      close(dlg);
      resolve(answer);
    };
    const button = (label, answer, primary) =>
      h("button", { type: "button", class: `fd-button${primary ? " fd-primary" : ""}`, onclick: () => done(answer) },
        label);
    const yesno = type === "yesno";
    const buttons = yesno ? [button("はい", "yes", def !== "no"), button("いいえ", "no", def === "no")]
      : [button("OK", "ok", true)];
    dlg = open([
      h("h2", { class: "fd-dialog-title" }, title),
      message ? h("p", { class: "fd-dialog-message" }, message) : null,
      rows.length ? h("table", { class: "fd-dialog-table" },
        rows.map(([k, v]) => h("tr", {}, [h("th", { scope: "row" }, k), h("td", {}, v)]))) : null,
      h("div", { class: "fd-dialog-buttons" }, buttons),
    ], { onCancel: () => done(yesno ? "no" : "ok") });
    (yesno && def === "no" ? buttons[1] : buttons[0]).focus();
  });
}

/**
 * 進み具合のダイアログ（ジョブ）。update({done, total, item}) で進め、close() で閉じる。
 * ［中止］（と Esc）で onCancel を呼び、終わるまで「中止しています…」にする（閉じるのは呼ぶ側）。
 */
export function progressDialog({ title = "", onCancel = () => {} }) {
  const bar = h("progress", { class: "fd-progress", max: "1", value: "0" });
  const count = h("p", { class: "fd-dialog-message fd-progress-count" }, "準備しています…");
  const item = h("p", { class: "fd-dialog-detail fd-progress-item" }, "");
  let cancelling = false;
  const cancel = () => {
    if (cancelling) return;
    cancelling = true;
    stop.disabled = true;
    stop.textContent = "中止しています…";
    onCancel();
  };
  const stop = h("button", { type: "button", class: "fd-button", onclick: cancel }, "中止");
  const dlg = open([
    h("h2", { class: "fd-dialog-title" }, title),
    bar, count, item,
    h("div", { class: "fd-dialog-buttons" }, [stop]),
  ], { onCancel: cancel });
  dlg.classList.add("fd-progress-dialog");
  stop.focus();
  return {
    update({ done = 0, total = 0, item: path = "", text = null }) {
      if (total > 0) {
        bar.max = total;
        bar.value = done;
        // text … 数えかたが個数でないとき（アップロードのバイト数）の「（…）」の中身
        count.textContent = `${Math.floor((done / total) * 100)}%（${text ?? `${done} / ${total}`}）`;
      }
      item.textContent = path ? path.split("/").pop() : "";
    },
    close() {
      close(dlg);
    },
  };
}

/**
 * 確認。OK なら true。
 * danger: true なら OK のボタンを危険の色にし、既定のフォーカスを［キャンセル］に置く（Enter で消さないように）。
 */
export function confirmDialog({ title, message, detail = "", okLabel = "OK", danger = false }) {
  return new Promise((resolve) => {
    let dlg;
    const done = (answer) => {
      close(dlg);
      resolve(answer);
    };
    const ok = h("button", { type: "button", class: `fd-button${danger ? " fd-danger" : " fd-primary"}`,
      onclick: () => done(true) }, okLabel);
    const cancel = h("button", { type: "button", class: "fd-button", onclick: () => done(false) }, "キャンセル");
    dlg = open([
      h("h2", { class: "fd-dialog-title" }, title),
      h("p", { class: "fd-dialog-message" }, message),
      detail ? h("p", { class: "fd-dialog-detail" }, detail) : null,
      h("div", { class: "fd-dialog-buttons" }, [ok, cancel]),
    ], { onCancel: () => done(false) });
    (danger ? cancel : ok).focus();
  });
}

/**
 * 文字を 1 つ入力させる（部品 prompt。名前や開始値などを尋ねる）。OK なら入力した文字、取り消しなら null。
 * detail は入力欄の下の説明文、error は入力に戻ったときの誤りの理由（サーバの応答の message）。
 */
export function promptDialog({ title = "", label = "", value = "", detail = "", error = "" }) {
  return new Promise((resolve) => {
    let dlg;
    const input = h("input", { type: "text", class: "fd-prompt-input", value, spellcheck: "false",
      "aria-label": label || title });
    const done = (answer) => {
      close(dlg);
      resolve(answer);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        done(input.value);
      }
    });
    dlg = open([
      title ? h("h2", { class: "fd-dialog-title" }, title) : null,
      h("label", { class: "fd-dialog-message" }, [label ? h("span", {}, label) : null, input]),
      // 説明文（宣言の detail）と、サーバが入力を誤りとして返したときの理由（入力に戻ったとき）
      detail ? h("p", { class: "fd-dialog-detail" }, detail) : null,
      error ? h("p", { class: "fd-dialog-error", role: "alert" }, error) : null,
      h("div", { class: "fd-dialog-buttons" }, [
        h("button", { type: "button", class: "fd-button fd-primary", onclick: () => done(input.value) }, "OK"),
        h("button", { type: "button", class: "fd-button", onclick: () => done(null) }, "キャンセル"),
      ]),
    ], { onCancel: () => done(null) });
    input.focus();
    input.select();
  });
}

/**
 * 2 つの項目のどちらが新しいか・大きいか。{newer, larger} はそれぞれ "incoming" / "existing" / null（同じか分からない）。
 * フォルダのサイズは比べない（API はフォルダのサイズを返さない）。
 */
export function compareConflict(incoming, existing) {
  const pick = (a, b) => (a == null || b == null || a === b ? null : a > b ? "incoming" : "existing");
  if (!incoming || !existing) return { newer: null, larger: null };
  const [a, b] = [incoming.attrs, existing.attrs];
  return {
    // 更新日時は 1 秒未満の違いを同じとみなす（コピーで小数部が変わることがある）
    newer: a.mtime != null && b.mtime != null && Math.abs(a.mtime - b.mtime) >= 1 ? pick(a.mtime, b.mtime) : null,
    larger: incoming.kind === "file" && existing.kind === "file" ? pick(a.size, b.size) : null,
  };
}

/**
 * 衝突のダイアログに並べる 1 つの項目（アイコン・名前・場所と、そのマウントの属性）。
 * 「新しい」「大きい」の印は、属性に mtime・size があるときだけ付く。フォルダで値の無い属性（サイズ）は出さない。
 */
function conflictItem(title, entry, where, marks, mount) {
  const rows = [["場所", where || "—"]];
  if (entry) {
    for (const a of mountAttributes(mount)) {
      // フォルダで値の無い属性（サイズなど）は行ごと省く（詳細表示では空欄のもの）
      if (entry.kind === "dir" && attributeValue(a, entry) == null) continue;
      const text = attributeText(a, entry);
      const mark = a.key === "mtime" && marks.newer ? "新しい" : a.key === "size" && marks.larger ? "大きい" : null;
      rows.push([a.label, text || "—", mark]);
    }
  }
  return h("div", { class: "fd-conflict-item" }, [
    h("div", { class: "fd-conflict-heading" }, title),
    h("div", { class: "fd-conflict-body" }, [
      entry ? icon(entryIcon(entry, mount), "fd-icon fd-conflict-icon") : null,
      h("dl", { class: "fd-conflict-facts" }, [
        h("dt", {}, "名前"), h("dd", { class: "fd-conflict-name" }, entry ? entry.name : "（詳細を読めませんでした）"),
        ...rows.flatMap(([k, v, mark]) => [
          h("dt", {}, k),
          h("dd", {}, [v, mark ? h("span", { class: "fd-conflict-mark" }, mark) : null]),
        ]),
      ]),
    ]),
  ]);
}

/**
 * 名前の衝突。{choice: "overwrite" | "skip" | "rename", all: boolean} か、取り消しなら null。
 * all は「以降すべてに適用」。
 * incoming / existing は、写す（移す・戻す）項目と今ある項目のエントリ（読めなければ null）。
 * incomingTitle は incoming の見出し（「コピーする項目」「元に戻す項目」など）。
 */
export function conflictDialog({
  name, where, remaining = 0, incoming = null, existing = null, incomingWhere = "", incomingTitle = "コピーする項目",
  incomingMount = null, mount = null,
}) {
  return new Promise((resolve) => {
    let dlg;
    const all = h("input", { type: "checkbox", id: "fd-conflict-all" });
    const done = (choice) => {
      const answer = choice ? { choice, all: all.checked } : null;
      close(dlg);
      resolve(answer);
    };
    const choiceButton = (choice, label, cls = "") => h("button", { type: "button", class: `fd-button ${cls}`,
      onclick: () => done(choice) }, label);
    const rename = choiceButton("rename", "両方残す（別の名前にする）", "fd-primary");
    const cmp = compareConflict(incoming, existing);
    const mark = (side) => ({ newer: cmp.newer === side, larger: cmp.larger === side });
    dlg = open([
      h("h2", { class: "fd-dialog-title" }, "同じ名前の項目があります"),
      h("p", { class: "fd-dialog-message" }, `「${name}」は ${where} に既にあります。`),
      h("div", { class: "fd-conflict-items" }, [
        conflictItem(incomingTitle, incoming, incomingWhere, mark("incoming"), incomingMount),
        conflictItem("今ある項目", existing, where, mark("existing"), mount),
      ]),
      h("div", { class: "fd-dialog-choices" }, [
        rename,
        choiceButton("overwrite", "置き換える（今あるほうはごみ箱へ）"),
        choiceButton("skip", "スキップする"),
      ]),
      remaining > 0 ? h("label", { class: "fd-dialog-all" }, [all, ` 残りの ${remaining} 件にも同じようにする`]) : null,
      h("div", { class: "fd-dialog-buttons" }, [h("button", { type: "button", class: "fd-button",
        onclick: () => done(null) }, "キャンセル")]),
    ], { onCancel: () => done(null) });
    rename.focus();
  });
}

/**
 * テキストの中の位置 at の、行と列（どちらも 1 から）と全体の行数。列は文字（コードポイント）で数える。
 */
export function textPosition(text, at) {
  const before = text.slice(0, at);
  const lineStart = before.lastIndexOf("\n") + 1;
  return {
    line: before.split("\n").length,
    column: [...before.slice(lineStart)].length + 1,
    lines: text.split("\n").length,
  };
}

/**
 * テキストの編集（部品 textEdit）。value を入れたテキスト欄を出し、［保存］（Ctrl+S も）で編集した全体を、
 * ［キャンセル］・Esc で null を返す。変えたあとに閉じるときは、破棄してよいかを確かめる。
 * ボタンの横に、カーソルの位置（行 / 全体の行数・列）と、選んでいる文字数を出す。
 * error は保存に失敗して戻ったときの理由。改行は LF で返す（ブラウザのテキスト欄が LF にそろえる）。
 */
export function textEditDialog({ title = "", value = "", error = "" }) {
  return new Promise((resolve) => {
    let dlg;
    const area = h("textarea", { class: "fd-text-edit", spellcheck: "false", "aria-label": title || "テキスト" });
    area.value = value;
    const initial = area.value; // テキスト欄が改行をそろえたあとの値と比べる
    let asking = false;
    const finish = (answer) => {
      document.removeEventListener("selectionchange", onDocSelection);
      close(dlg);
      resolve(answer);
    };
    const save = () => finish(area.value);
    async function cancel() {
      if (asking) return;
      if (area.value !== initial) {
        asking = true;
        const ok = await confirmDialog({ title: "変更を破棄", message: "保存していない変更があります。破棄して閉じますか？",
          okLabel: "破棄する", danger: true });
        asking = false;
        if (!ok) {
          area.focus();
          return;
        }
      }
      finish(null);
    }
    const pos = h("span", { class: "fd-text-pos", "aria-live": "polite" });
    function showPosition() {
      const { line, column, lines } = textPosition(area.value, area.selectionEnd);
      const selected = [...area.value.slice(area.selectionStart, area.selectionEnd)].length;
      pos.textContent = `行 ${line} / ${lines}　列 ${column}${selected ? `（${selected} 文字を選択）` : ""}`;
    }
    // カーソルが動くのは、打つ・キー・クリック・ドラッグで選ぶ、のどれか。selectionchange はテキスト欄では
    // 文書に届くブラウザがあるので、両方で受ける
    for (const type of ["input", "keyup", "mouseup", "select", "selectionchange", "focus"]) {
      area.addEventListener(type, showPosition);
    }
    const onDocSelection = () => { if (document.activeElement === area) showPosition(); };
    document.addEventListener("selectionchange", onDocSelection);
    area.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s") {
        e.preventDefault(); // ブラウザの「ページを保存」にしない
        save();
      }
    });
    dlg = open([
      h("h2", { class: "fd-dialog-title" }, title),
      area,
      error ? h("p", { class: "fd-dialog-error", role: "alert" }, `保存できませんでした: ${error}`) : null,
      h("div", { class: "fd-dialog-buttons" }, [
        pos,
        h("button", { type: "button", class: "fd-button fd-primary", title: "Ctrl+S", onclick: save }, "保存"),
        h("button", { type: "button", class: "fd-button", onclick: cancel }, "キャンセル"),
      ]),
    ], { onCancel: cancel });
    dlg.classList.add("fd-text-dialog");
    area.focus();
    area.setSelectionRange(0, 0);
    showPosition();
  });
}

/**
 * アップロードするものを選ばせる（部品 uploadDialog）。［ファイルを選ぶ］［フォルダを選ぶ］か、ダイアログへのドロップで
 * 集め、［アップロード］で集めたもの（upload.js の [{rel, kind, file?}]）を、取り消しなら null を返す。
 * dest は送り先の表示（「マウント: /パス」）、folders が false ならフォルダを選ばせない（createShell の folderUpload）。
 */
export function uploadDialog({ title = "アップロード", dest = "", folders = true }) {
  return new Promise((resolve) => {
    let dlg;
    let chosen = []; // [{rel, kind, file?}]
    const note = h("p", { class: "fd-dialog-detail", role: "status" }, "");
    const list = h("ul", { class: "fd-upload-list" });
    const ok = h("button", { type: "button", class: "fd-button fd-primary", disabled: true,
      onclick: () => done(chosen) }, "アップロード");
    const done = (answer) => {
      close(dlg);
      resolve(answer);
    };

    /** 足す。同じ名前の直下の項目は、あとから選んだほうにする。 */
    function add(files) {
      const tops = new Set(files.filter((f) => !f.rel.includes("/")).map((f) => f.rel));
      chosen = [...chosen.filter((f) => !tops.has(f.rel.split("/")[0])), ...files];
      render();
    }

    function render() {
      list.replaceChildren(...groupUploads(chosen).map(({ top, children }) => {
        const files = top.kind === "file" ? [top] : children.filter((c) => c.kind === "file");
        const size = files.reduce((n, f) => n + f.file.size, 0);
        const what = top.kind === "dir" ? `フォルダ・${files.length} 個のファイル・${formatSize(size)}` : formatSize(size);
        return h("li", { class: "fd-upload-item" }, [
          icon(top.kind === "dir" ? "folder" : "file", "fd-icon"),
          h("span", { class: "fd-upload-name" }, top.rel),
          h("span", { class: "fd-upload-size" }, what),
          h("button", { type: "button", class: "fd-status-clip-clear", title: "外す", "aria-label": `「${top.rel}」を外す`,
            onclick: () => {
              chosen = chosen.filter((f) => f.rel.split("/")[0] !== top.rel);
              render();
            } }, [icon("close")]),
        ]);
      }));
      ok.disabled = !chosen.length;
      list.hidden = !chosen.length;
    }

    const picker = (directory) => {
      const input = h("input", { type: "file", multiple: true, hidden: true });
      if (directory) input.webkitdirectory = true;
      input.addEventListener("change", () => {
        add(filesFromInput(input.files));
        input.remove();
      });
      return input;
    };
    const choose = (directory) => {
      const input = picker(directory);
      dlg.append(input);
      input.click();
    };

    const zone = h("div", { class: "fd-upload-zone" }, [
      h("p", {}, folders ? "ここにファイル・フォルダをドロップできます" : "ここにファイルをドロップできます"),
      h("div", { class: "fd-upload-pick" }, [
        h("button", { type: "button", class: "fd-button", onclick: () => choose(false) }, "ファイルを選ぶ…"),
        folders ? h("button", { type: "button", class: "fd-button", onclick: () => choose(true) }, "フォルダを選ぶ…") : null,
      ]),
    ]);
    // ダイアログへのドロップは、ここで受ける（後ろの画面のドロップ＝すぐ送る、へ渡さない）
    zone.addEventListener("dragover", (e) => {
      e.stopPropagation();
      if (!carriesFiles(e.dataTransfer)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      zone.classList.add("fd-drop-target");
    });
    zone.addEventListener("dragleave", (e) => {
      if (!zone.contains(e.relatedTarget)) zone.classList.remove("fd-drop-target");
    });
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("fd-drop-target");
      const { files, skipped } = await filesFromDrop(e.dataTransfer, { folders });
      note.textContent = skipped.length ? `フォルダはアップロードできないので外しました（${skipped.join("、")}）` : "";
      add(files);
    });

    dlg = open([
      h("h2", { class: "fd-dialog-title" }, title),
      dest ? h("p", { class: "fd-dialog-message" }, `送り先: ${dest}`) : null,
      zone, list, note,
      h("div", { class: "fd-dialog-buttons" }, [
        ok,
        h("button", { type: "button", class: "fd-button", onclick: () => done(null) }, "キャンセル"),
      ]),
    ], { onCancel: () => done(null) });
    dlg.classList.add("fd-upload-dialog");
    // ダイアログの外（背景）に落としても、画面へは渡さない（ファイルを開いて画面を離れることもさせない）
    dlg.addEventListener("dragover", (e) => { e.stopPropagation(); e.preventDefault(); e.dataTransfer.dropEffect = "none"; });
    dlg.addEventListener("drop", (e) => { e.stopPropagation(); e.preventDefault(); });
    render();
    zone.querySelector("button").focus();
  });
}
