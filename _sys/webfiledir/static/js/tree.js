// フォルダツリー: マウントごとの木。▶ を押したときに 1 段ずつ読み込む。
// 移ったあとは、カレントフォルダまで開いて目立たせる。
// どこを開いたか・読み込んだ中身は、この部品だけが使う状態なのでここで持つ。

import { api } from "./api.js";
import { h, icon } from "./dom.js";
import { isHidden } from "./filetypes.js";
import { splitPath, joinPath } from "./location.js";
import { enabled } from "./model.js";
import { compareNames } from "./sort.js";
import { canPutInto } from "./model.js";
import { entryIcon, mountIcon } from "./icons.js";

const key = (mount, path) => `${mount}\n${path}`;
const HOVER_OPEN_MS = 700;

export function createTree(store, actions) {
  // key → {children: エントリの配列 | null, expanded, loading, hasChildren}
  const nodes = new Map();
  const el = h("nav", { class: "fd-tree", "aria-label": "フォルダ" });
  const list = h("ul", { class: "fd-tree-root", role: "tree" });
  el.append(list);

  function node(mount, path) {
    const k = key(mount, path);
    if (!nodes.has(k)) nodes.set(k, { children: null, expanded: false, loading: false, hasChildren: null });
    return nodes.get(k);
  }

  async function load(mount, path) {
    const n = node(mount, path);
    n.loading = true;
    render();
    try {
      const res = await api.tree(mount, path);
      n.children = res.entries;
      for (const e of res.entries) node(mount, joinPath([...splitPath(path), e.name])).hasChildren = e.hasChildren;
    } catch (err) {
      n.children = [];
      n.expanded = false;
      actions.message(`フォルダを読めません: ${err.message}`, "error");
    } finally {
      n.loading = false;
      render();
    }
  }

  async function expand(mount, path) {
    const n = node(mount, path);
    n.expanded = true;
    if (n.children == null && !n.loading) await load(mount, path);
    else render();
  }

  function toggle(mount, path) {
    const n = node(mount, path);
    if (n.expanded) {
      n.expanded = false;
      render();
    } else {
      expand(mount, path);
    }
  }

  /** カレントフォルダまでの各段を開く。 */
  async function reveal(loc) {
    if (!loc) return;
    if (loc.trash) {
      await expand(loc.mount, "/");
      return;
    }
    const parts = splitPath(loc.path) || [];
    for (let i = 0; i < parts.length; i++) {
      const p = joinPath(parts.slice(0, i));
      if (store.get().location !== loc) return; // 途中で別の場所へ移った
      await expand(loc.mount, p);
    }
    render();
    const current = list.querySelector(".fd-tree-item[aria-current]");
    if (current) current.scrollIntoView({ block: "nearest" });
  }

  function visibleChildren(n) {
    const showHidden = store.get().showHidden;
    return (n.children || [])
      .filter((e) => showHidden || !isHidden(e))
      .sort((a, b) => compareNames(a.name, b.name));
  }

  /** entry は、その段のフォルダの項目（権限を見る）。マウントの根は項目が無いので null。 */
  function item(mount, path, label, iconName, depth, entry = null) {
    const n = node(mount, path);
    const loc = store.get().location;
    const current = loc && !loc.trash && loc.mount === mount && loc.path === path;
    // ▶ を出すか: 読み込み済みなら見えるフォルダがあるか、未読みなら hasChildren（null は「不明」なので出す）
    const expandable = n.children != null ? visibleChildren(n).length > 0 : n.hasChildren !== false;
    const twisty = h("span", {
      class: `fd-twisty${n.expanded ? " fd-open" : ""}${n.loading ? " fd-loading" : ""}`,
      onclick: (e) => {
        e.stopPropagation();
        toggle(mount, path);
      },
    }, expandable ? [icon("chevron", "fd-icon fd-twisty-icon")] : []);
    const row = h("div", {
      class: "fd-tree-item", style: `--depth:${depth}`, title: label,
      "aria-current": current ? "true" : null,
      // 書けないフォルダには落とせない（Wiki「画面設計 > 権限」）
      dataset: { dropMount: mount, dropPath: path, dropDenied: entry && !canPutInto(entry) ? "1" : null },
      onclick: () => actions.go(mount, path),
    }, [twisty, icon(iconName), h("span", { class: "fd-tree-label" }, label)]);
    if (expandable && !n.expanded) hoverToOpen(row, mount, path);
    const li = h("li", { role: "treeitem", "aria-expanded": expandable ? String(n.expanded) : null }, [row]);
    if (n.expanded && n.children) {
      opened.push(key(mount, path));
      const ul = h("ul", { role: "group" });
      const m = store.get().mounts.find((x) => x.id === mount);
      for (const e of visibleChildren(n)) {
        ul.append(item(mount, joinPath([...(splitPath(path) || []), e.name]), e.name, entryIcon(e, m), depth + 1, e));
      }
      li.append(ul);
    }
    return li;
  }

  /**
   * ドラッグ中に閉じたフォルダの上で約 0.7 秒止めたら開く（深いところへ落とせるように）。
   * 開くと描き直されて row は消えるので、タイマーは row ごとに持てばよい。
   */
  function hoverToOpen(row, mount, path) {
    let timer = null;
    const stop = () => {
      clearTimeout(timer);
      timer = null;
    };
    row.addEventListener("dragover", () => {
      if (!timer) timer = setTimeout(() => expand(mount, path), HOVER_OPEN_MS);
    });
    row.addEventListener("dragleave", (e) => {
      if (!row.contains(e.relatedTarget)) stop();
    });
    row.addEventListener("drop", stop);
  }

  /** マウントの最後に置く「ごみ箱」（ごみ箱を持つマウントだけ）。 */
  function trashItem(m) {
    const loc = store.get().location;
    const current = loc && loc.trash && loc.mount === m.id;
    const row = h("div", {
      class: "fd-tree-item fd-tree-trash", style: "--depth:1", title: `${m.label} のごみ箱`,
      "aria-current": current ? "true" : null,
      dataset: { dropMount: m.id, dropTrash: "1" }, // ここへ落とすとごみ箱へ移す
      onclick: () => actions.goTrash(m.id),
    }, [h("span", { class: "fd-twisty" }), icon("trash"), h("span", { class: "fd-tree-label" }, "ごみ箱")]);
    return h("li", { role: "treeitem" }, [row]);
  }

  let opened = []; // render のあいだに集める、開いていて中身を出している段の key

  function render() {
    const s = store.get();
    opened = [];
    list.replaceChildren(...s.mounts.map((m) => {
      const li = item(m.id, "/", m.label, mountIcon(m), 0);
      if (m.capabilities.includes("trash") && enabled(s, "trash") && node(m.id, "/").expanded) {
        let ul = li.querySelector(":scope > ul");
        if (!ul) {
          ul = h("ul", { role: "group" });
          li.append(ul);
        }
        ul.append(trashItem(m));
      }
      return li;
    }));
    // 自動更新が見張る段（文字列にして、同じなら store が通知しないように）
    store.set({ treeOpened: opened.join("\0") });
  }

  /** 自動更新: 開いている段が変わったら、その段だけ読み直す。 */
  function onExternalChange(c) {
    if (c.all) {
      reload();
    } else if (!c.trash) {
      const n = nodes.get(key(c.mount, c.path));
      if (n && n.expanded && n.children != null && !n.loading) load(c.mount, c.path);
    }
  }

  /** 更新: 読み込み済みの段を読み直す（開いている段だけ）。 */
  async function reload() {
    const opened = [...nodes.entries()].filter(([, n]) => n.children != null);
    for (const [, n] of opened) n.children = null;
    await Promise.all(opened
      .filter(([, n]) => n.expanded)
      .map(([k]) => {
        const [mount, path] = k.split("\n");
        return load(mount, path);
      }));
  }

  store.subscribe((s, changed) => {
    if (changed.has("mounts")) {
      for (const m of s.mounts) node(m.id, "/").expanded = true;
      Promise.all(s.mounts.map((m) => load(m.id, "/")));
    }
    if (changed.has("refreshToken")) reload();
    if (changed.has("externalChange") && s.externalChange) onExternalChange(s.externalChange);
    if (changed.has("location")) reveal(s.location);
    else if (changed.has("showHidden")) render();
  });
  render();
  return el;
}
