// ステータスバー: 項目数、選択数、（選択がファイルだけなら）合計サイズ、クリップボードの中身、知らせ。

import { h, icon } from "./dom.js";
import { attributeValue, formatAttribute } from "./attributes.js";
import { attributesOf } from "./model.js";

export function createStatusBar(store, actions) {
  const counts = h("span", { class: "fd-status-counts" });
  const clip = h("span", { class: "fd-status-clip" });
  const message = h("span", { class: "fd-status-message", role: "status", "aria-live": "polite" });
  const el = h("div", { class: "fd-statusbar" }, [counts, clip, message]);

  // コピーは項目の見た目が変わらないので、ここに出さないと入っていることに気付けない
  function renderClip(c) {
    clip.replaceChildren();
    clip.hidden = !c;
    if (!c) return;
    const verb = c.mode === "cut" ? "切り取り中" : "コピー中";
    clip.title = `${c.mount}: ${c.paths.join("\n")}`;
    clip.append(
      icon(c.mode === "cut" ? "cut" : "copy"),
      `${c.paths.length} 個を${verb}`,
      h("button", { type: "button", class: "fd-status-clip-clear", title: "解除する（Esc）",
        "aria-label": `${verb}の項目を解除する`, onclick: () => actions.clearClipboard() }, [icon("close")]),
    );
  }

  function render(s) {
    const shown = s.visibleEntries;
    let text = s.loading ? "読み込み中…" : `${shown.length} 個の項目`;
    const selected = shown.filter((e) => s.selection.has(e.key));
    if (selected.length > 0) {
      text += `　${selected.length} 個の項目を選択`;
      // 合計は、このマウントが「バイト数」で見せる size 属性を持つときだけ（仮想構造では無いことがある）
      const size = attributesOf(s).find((a) => a.key === "size" && a.kind === "number" && a.format && a.format.type === "bytes");
      const values = size ? selected.map((e) => (e.kind === "file" ? attributeValue(size, e) : null)) : [];
      if (size && values.every((v) => v != null)) {
        text += `　${formatAttribute(size, values.reduce((sum, v) => sum + v, 0))}`;
      }
    }
    counts.textContent = text;
    message.replaceChildren();
    if (s.message) {
      message.append(s.message.text);
      if (s.message.action) {
        const { label, run } = s.message.action;
        message.append(" ", h("button", { type: "button", class: "fd-link-button", onclick: run }, label));
      }
    }
    message.className = `fd-status-message${s.message && s.message.kind === "error" ? " fd-error" : ""}`;
  }

  store.subscribe((s, changed) => {
    if (["visibleEntries", "selection", "loading", "message"].some((k) => changed.has(k))) render(s);
    if (changed.has("clipboard")) renderClip(s.clipboard);
  });
  render(store.get());
  renderClip(store.get().clipboard);
  return el;
}
