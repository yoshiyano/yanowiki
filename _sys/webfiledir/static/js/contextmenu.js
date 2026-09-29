// 右クリックメニュー。項目は {label, shortcut?, disabled?, checked?, action} か、区切りの "-"。
// 外を押す・Esc・ウィンドウの大きさが変わる・スクロールで閉じる。↑↓ で選び Enter で実行する。

import { h } from "./dom.js";

let current = null;

export function closeMenu() {
  if (!current) return;
  current.cleanup();
  const { el, returnFocus } = current;
  const hadFocus = el.contains(document.activeElement);
  el.remove();
  current = null;
  // メニューの中にフォーカスがあったなら、開く前の場所へ戻す（続けてキー操作できるように）
  if (hadFocus && returnFocus && returnFocus.isConnected) returnFocus.focus();
}

export function openMenu(host, x, y, items) {
  closeMenu();
  const returnFocus = document.activeElement;
  const buttons = [];
  const list = h("div", { class: "fd-menu", role: "menu" }, items.map((it) => {
    if (it === "-") return h("div", { class: "fd-menu-sep", role: "separator" });
    const b = h("button", {
      type: "button", class: "fd-menu-item", role: it.checked == null ? "menuitem" : "menuitemradio",
      "aria-checked": it.checked == null ? null : String(!!it.checked),
      disabled: !!it.disabled,
      onclick: () => {
        closeMenu();
        it.action();
      },
    }, [
      h("span", { class: "fd-menu-check" }, it.checked ? "✓" : ""),
      h("span", { class: "fd-menu-label" }, it.label),
      h("span", { class: "fd-menu-shortcut" }, it.shortcut || ""),
    ]);
    if (!it.disabled) buttons.push(b);
    return b;
  }));
  host.append(list);

  // 画面からはみ出さないように位置を直す
  const rect = list.getBoundingClientRect();
  const left = Math.max(4, Math.min(x, window.innerWidth - rect.width - 4));
  const top = Math.max(4, Math.min(y, window.innerHeight - rect.height - 4));
  list.style.left = `${left}px`;
  list.style.top = `${top}px`;

  const onDown = (e) => {
    if (!list.contains(e.target)) closeMenu();
  };
  const onKey = (e) => {
    const i = buttons.indexOf(document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const d = e.key === "ArrowDown" ? 1 : -1;
      const next = buttons[(i + d + buttons.length) % buttons.length];
      if (next) next.focus();
    }
    e.stopPropagation(); // メニューを開いているあいだは、画面のキー操作に渡さない
  };
  const onClose = () => closeMenu();
  document.addEventListener("mousedown", onDown, true);
  list.addEventListener("keydown", onKey);
  window.addEventListener("resize", onClose);
  window.addEventListener("blur", onClose);
  document.addEventListener("scroll", onClose, true);
  current = {
    el: list,
    returnFocus,
    cleanup() {
      document.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("resize", onClose);
      window.removeEventListener("blur", onClose);
      document.removeEventListener("scroll", onClose, true);
    },
  };
  if (buttons[0]) buttons[0].focus();
  return list;
}
