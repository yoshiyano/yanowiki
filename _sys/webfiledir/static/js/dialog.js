// 確認と名前の衝突のダイアログ。<dialog> の showModal を使い、Promise で答えを返す。
// ダイアログは画面の根（.fd-app）の中に置き、見た目を閉じ込める。

import { h, icon } from "./dom.js";
import { attributeText, attributeValue, mountAttributes } from "./attributes.js";
import { entryIcon } from "./icons.js";

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
