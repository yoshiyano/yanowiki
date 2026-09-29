// ファイル表示: カレントフォルダ（またはごみ箱）の中身を 4 つの表示形式で出す。
// 並べ替えは main.js で済ませた visibleEntries をそのまま並べる。項目は key で指す
// （ふだんは名前、ごみ箱では ID。同じ名前のものを何度も消せるため）。
//
// 選択（Wiki「画面設計 > 選択」）: クリック・Ctrl・Shift・ラバーバンド・Ctrl+A・矢印キー。規則は selection.js。
// 名前の変更: 項目の上に入力欄を開く。**入力しているあいだは描き直さない**（位置が動かないように）。

import { h, icon } from "./dom.js";
import { splitExt } from "./filetypes.js";
import { attributeText } from "./attributes.js";
import { attributesOf, canPutInto, currentMount, enabled } from "./model.js";
import { entryIcon } from "./icons.js";
import { effectiveSort } from "./sort.js";
import { isCutPath } from "./clipboard.js";
import { parentPath, splitPath, joinPath } from "./location.js";
import {
  clickSelect, moveSelect, jumpSelect, selectAll, rectSelect, emptySelection,
} from "./selection.js";


export function createView(store, actions) {
  const content = h("div", { class: "fd-view-content" });
  const band = h("div", { class: "fd-band", hidden: true });
  const el = h("div", { class: "fd-view", tabindex: "0", "aria-label": "フォルダの中身" }, [content, band]);

  const selState = (s) => ({ selection: s.selection, anchor: s.anchor, focus: s.focus });
  const order = (s) => s.visibleEntries.map((e) => e.key);
  let scrollToFocus = false;

  function setSelection(next) {
    store.set({ selection: next.selection, anchor: next.anchor, focus: next.focus });
  }

  // --- 項目 ---

  function itemAttrs(entry, s) {
    const cls = ["fd-item"];
    const selected = s.selection.has(entry.key);
    if (selected) cls.push("fd-selected");
    if (s.focus === entry.key) cls.push("fd-focused");
    if (entry.extra && entry.extra.unreachable) cls.push("fd-unreachable");
    if (entry.extra && entry.extra.symlink) cls.push("fd-symlink");
    if (entry.name.startsWith(".")) cls.push("fd-hidden");
    const loc = s.location;
    const normal = loc && !loc.trash;
    const path = normal ? joinPath([...splitPath(loc.path), entry.name]) : null;
    if (normal && isCutPath(s.clipboard, loc.mount, path)) cls.push("fd-cut"); // 切り取り中は半透明
    // フォルダは落とし先になる（Wiki「画面設計 > ドラッグ＆ドロップ」）
    const droppable = normal && entry.kind === "dir" && !(entry.extra && entry.extra.unreachable);
    let title = entry.name;
    if (entry.extra && entry.extra.unreachable) {
      title += entry.extra.unreachable === "outside" ? "（マウントの外を指すリンク）" : "（壊れたリンク）";
    }
    if (entry.originalPath) title += `（元の場所: ${parentPath(entry.originalPath)}）`;
    return {
      class: cls.join(" "),
      title,
      dataset: {
        key: entry.key, name: entry.name,
        ...(droppable ? { dropMount: loc.mount, dropPath: path, dropDenied: canPutInto(entry) ? null : "1" } : {}),
      },
      // ごみ箱の中からは持ち出せない。名前の入力中も動かさない
      draggable: normal && s.editing !== entry.key && enabled(s, "dnd") ? "true" : null,
      "aria-selected": String(selected),
      role: "option",
      onclick: (e) => {
        e.stopPropagation();
        if (store.get().editing === entry.key) return;
        setSelection(clickSelect(selState(store.get()), order(store.get()), entry.key,
          { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }));
      },
      ondblclick: (e) => {
        // Shift を押しながらなら、その修飾キーの開く経路（Wiki「画面設計 > ファイルを開く」）
        if (store.get().editing !== entry.key) actions.open(entry, { modifier: e.shiftKey ? "shift" : null });
      },
    };
  }

  function iconFor(entry, big) {
    const name = entryIcon(entry, currentMount(store.get()));
    return h("span", { class: big ? "fd-item-icon fd-big" : "fd-item-icon" }, [icon(name)]);
  }

  function nameFor(entry, s) {
    if (s.editing === entry.key) return renameInput(entry);
    return h("span", { class: "fd-item-name" }, entry.name);
  }

  // --- 名前の変更 ---

  let editingRendered = null; // 入力欄を描いた項目の key

  function renameInput(entry) {
    editingRendered = entry.key;
    let busy = false;
    let finished = false;
    const input = h("input", {
      class: "fd-rename", type: "text", value: entry.name, spellcheck: "false", "aria-label": "新しい名前",
    });
    const selectStem = () => {
      // ファイルは拡張子の手前まで、フォルダは全部を選んだ状態で入る（エクスプローラーと同じ）
      const { stem } = splitExt(entry.name, entry.kind);
      input.setSelectionRange(0, entry.kind === "dir" ? entry.name.length : stem.length);
    };
    const commit = async () => {
      if (busy || finished) return;
      busy = true;
      const ok = await actions.commitRename(entry, input.value);
      busy = false;
      if (ok) {
        finished = true;
      } else if (input.isConnected) {
        input.focus(); // 失敗したら入力を続けてもらう
        input.select();
      }
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation(); // 入力中のキーを、表示や画面全体のキー操作に渡さない
      if (e.isComposing) return;
      if (e.key === "Enter") {
        e.preventDefault();
        commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        finished = true;
        actions.cancelRename();
      }
    });
    input.addEventListener("blur", () => {
      // 欄の外を押したら確定（エクスプローラーと同じ）
      if (!finished) commit();
    });
    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("dblclick", (e) => e.stopPropagation());
    input.addEventListener("mousedown", (e) => e.stopPropagation());
    requestAnimationFrame(() => {
      if (!input.isConnected) return;
      input.focus();
      selectStem();
    });
    return input;
  }

  // --- 描画 ---

  function renderGrid(s) {
    const big = s.view === "large";
    return h("div", { class: `fd-grid fd-mode-${s.view}`, role: "listbox", "aria-multiselectable": "true" },
      s.visibleEntries.map((e) => h("div", itemAttrs(e, s), [iconFor(e, big), nameFor(e, s)])));
  }

  // 詳細表示の列は、名前と、今の画面の属性（マウントごとにサーバが返す。Wiki「画面設計 > 詳細表示の列」）
  const attrClass = (a) => `fd-col-${a.key} fd-attr fd-align-${a.align === "end" ? "end" : "start"}`;

  // --- 列の幅（Wiki「画面設計 > 列の幅」）: 見出しの右端のつまみをドラッグ、ダブルクリックで中身に合わせる ---
  const MIN_WIDTH = 40;
  const MAX_WIDTH = 1000;
  const NAME_MIN = 200; // 名前の列が広がる形のとき、残す最低の幅
  const DEFAULT_ATTR_WIDTH = 130;
  const clampWidth = (w) => Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w)));
  let resizedAt = -Infinity; // ドラッグを終えた時刻。直後の見出しのクリック（並べ替え）を無視するため

  /** 列ごとの幅（px）。名前の列は、操作者が変えていなければ null（残りいっぱいに広がる）。 */
  function columnWidths(s, attributes) {
    const own = (s.location && s.columnWidths[s.location.mount]) || {};
    const widths = { name: own.name ?? null };
    for (const a of attributes) widths[a.key] = own[a.key] ?? a.width ?? DEFAULT_ATTR_WIDTH;
    return widths;
  }

  /** 中身に合わせた幅（見出しと、描かれている各行の文字が切れずに収まる幅）。 */
  function fitWidth(table, index) {
    let w = MIN_WIDTH;
    for (const row of table.rows) {
      const cell = row.cells[index];
      if (!cell) continue;
      const label = cell.querySelector(".fd-item-name, .fd-th-label");
      // 名前の列はアイコンと入力欄を含むので、名前の文字の幅にアイコンと余白の分を足す
      const extra = label ? cell.getBoundingClientRect().width - label.getBoundingClientRect().width : 0;
      w = Math.max(w, (label ? label.scrollWidth + extra : cell.scrollWidth) + 2);
    }
    return clampWidth(w);
  }

  function resizeHandle(key, th) {
    return h("span", {
      class: "fd-col-resize", title: "ドラッグで幅を変える（ダブルクリックで中身に合わせる）", "aria-hidden": "true",
      onclick: (e) => e.stopPropagation(), // 見出しの並べ替えにしない
      ondblclick: (e) => {
        e.stopPropagation();
        const table = th.closest("table");
        actions.setColumnWidth(key, fitWidth(table, th.cellIndex));
      },
      onpointerdown: (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const startX = e.clientX;
        const startW = th.getBoundingClientRect().width;
        let width = null;
        const move = (ev) => {
          width = clampWidth(startW + ev.clientX - startX);
          th.style.width = `${width}px`; // ドラッグ中は見出しだけを直す（描き直さない）
        };
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          resizedAt = performance.now();
          if (width != null) actions.setColumnWidth(key, width);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      },
    });
  }

  function renderDetails(s) {
    const trash = s.location && s.location.trash;
    const attributes = attributesOf(s);
    const sort = effectiveSort(trash ? s.trashSort : s.sort, attributes);
    const columns = [{ key: "name", label: "名前" }, ...attributes];
    const widths = columnWidths(s, attributes);
    const nameFixed = widths.name != null;
    const attrSum = attributes.reduce((sum, a) => sum + widths[a.key], 0);
    const head = h("tr", {}, [...columns.map((a) => {
      const sorted = sort.key === a.key;
      const th = h("th", {
        class: a.key === "name" ? "fd-col-name" : attrClass(a), scope: "col",
        style: widths[a.key] != null ? `width:${widths[a.key]}px` : null,
        "aria-sort": sorted ? (sort.desc ? "descending" : "ascending") : null,
        onclick: () => {
          if (performance.now() - resizedAt < 300) return; // 幅を変えた直後のクリックは並べ替えにしない
          actions.setSort({ key: a.key, desc: sorted ? !sort.desc : false });
        },
      }, [h("span", { class: "fd-th-label" }, a.label),
        sorted ? icon(sort.desc ? "sort-desc" : "sort-asc", "fd-icon fd-sort-mark") : null]);
      th.append(resizeHandle(a.key, th));
      return th;
    }),
    // 名前の列の幅を決めたら、余った幅は右端の空きの列に（エクスプローラーと同じ見え方）
    nameFixed ? h("th", { class: "fd-col-filler", "aria-hidden": "true" }) : null]);
    const rows = s.visibleEntries.map((e) => h("tr", itemAttrs(e, s), [
      h("td", { class: "fd-col-name" }, [iconFor(e, false), nameFor(e, s)]),
      ...attributes.map((a) => {
        const text = attributeText(a, e);
        return h("td", { class: attrClass(a), title: text || null }, text);
      }),
      nameFixed ? h("td", { class: "fd-col-filler" }) : null,
    ]));
    // 列の合計が表示より広ければ横にスクロールする（名前の列が広がる形なら、名前に NAME_MIN を残す）
    const minWidth = attrSum + (nameFixed ? widths.name : NAME_MIN);
    return h("table", { class: `fd-details${trash ? " fd-trash" : ""}`, role: "listbox",
      "aria-multiselectable": "true", style: `min-width:${minWidth}px` },
    [h("thead", {}, [head]), h("tbody", {}, rows)]);
  }

  function render(s) {
    // 名前の入力中は描き直さない（入力欄が消え、並べ替えで位置も動いてしまう）
    if (s.editing && s.editing === editingRendered && content.querySelector(".fd-rename")) return;
    editingRendered = null;
    const empty = s.location && s.location.trash ? "ごみ箱は空です" : "このフォルダは空です";
    let body;
    if (s.error) {
      body = h("div", { class: "fd-placeholder fd-error" }, s.error.message);
    } else if (s.loading && s.visibleEntries.length === 0) {
      body = h("div", { class: "fd-placeholder" }, "読み込み中…");
    } else if (s.view === "details") {
      body = renderDetails(s);
      if (s.visibleEntries.length === 0) body = [body, h("div", { class: "fd-placeholder" }, empty)];
    } else if (s.visibleEntries.length === 0) {
      body = h("div", { class: "fd-placeholder" }, empty);
    } else {
      body = renderGrid(s);
    }
    content.replaceChildren(...[].concat(body));
    el.setAttribute("aria-busy", String(s.loading));
    // 何も無いところ（＝カレントフォルダ）も落とし先にする。二画面モードで、隣の画面が開いているフォルダへ
    // 落とせるように（フォルダの項目の上に落とせばそのフォルダ、それ以外はここ）。ごみ箱の中には落とせない
    if (s.location && !s.location.trash && !s.error) {
      el.dataset.dropMount = s.location.mount;
      el.dataset.dropPath = s.location.path;
      if (canPutInto(s.dir)) delete el.dataset.dropDenied;
      else el.dataset.dropDenied = "1";
    } else {
      delete el.dataset.dropMount;
      delete el.dataset.dropPath;
      delete el.dataset.dropDenied;
    }
    if (scrollToFocus) {
      scrollToFocus = false;
      const f = content.querySelector(".fd-item.fd-focused");
      if (f) f.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  // --- キー操作（表示にフォーカスがあるとき） ---

  /** 矢印キーで何項目動くか。格子は 1 行の個数、一覧（縦に並べて折り返す）は 1 列の個数。 */
  function stride(mode) {
    const items = [...content.querySelectorAll(".fd-item")];
    if (items.length < 2) return 1;
    const first = items[0];
    const n = mode === "list"
      ? items.findIndex((it) => it.offsetLeft !== first.offsetLeft)
      : items.findIndex((it) => it.offsetTop !== first.offsetTop);
    return n < 0 ? items.length : n;
  }

  function arrowDelta(key, mode) {
    if (mode === "details") return { ArrowUp: -1, ArrowDown: 1 }[key];
    const n = stride(mode);
    if (mode === "list") return { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -n, ArrowRight: n }[key];
    return { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -n, ArrowDown: n }[key];
  }

  el.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select") || e.altKey) return;
    const s = store.get();
    const ord = order(s);
    const shift = e.shiftKey;
    if (e.key.startsWith("Arrow")) {
      const d = arrowDelta(e.key, s.view);
      if (d == null) return;
      e.preventDefault();
      scrollToFocus = true;
      setSelection(moveSelect(selState(s), ord, d, { shift }));
    } else if ((e.key === "Home" || e.key === "End") && ord.length) {
      e.preventDefault();
      scrollToFocus = true;
      setSelection(jumpSelect(selState(s), ord, e.key === "Home" ? ord[0] : ord[ord.length - 1], { shift }));
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
      e.preventDefault();
      setSelection(selectAll(selState(s), ord));
    } else if (e.key === "Enter") {
      const chosen = s.visibleEntries.filter((x) => s.selection.has(x.key));
      if (chosen.length === 1) actions.open(chosen[0], { modifier: shift ? "shift" : null });
    } else if (e.key === "Escape") {
      // 1 回目は選択を外し、選択が無ければコピー・切り取りを解除する
      if (s.selection.size > 0) setSelection(emptySelection());
      else actions.clearClipboard();
    } else if (e.key === "ContextMenu" || (shift && e.key === "F10")) {
      e.preventDefault();
      const f = content.querySelector(".fd-item.fd-focused") || content.querySelector(".fd-item.fd-selected");
      const r = (f || el).getBoundingClientRect();
      if (f) actions.openItemMenu(r.left + 16, r.bottom);
      else actions.openBackgroundMenu(r.left + 16, r.top + 16);
    }
  });

  // --- マウス: 何も無いところを押すと選択を外す、ラバーバンド、右クリック ---

  let suppressClick = false;

  el.addEventListener("click", (e) => {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (!e.target.closest(".fd-item, th")) setSelection(emptySelection());
  });

  el.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || e.target.closest(".fd-item, th, input")) return;
    const box = el.getBoundingClientRect();
    const toContent = (cx, cy) => ({ x: cx - box.left + el.scrollLeft, y: cy - box.top + el.scrollTop });
    const start = toContent(e.clientX, e.clientY);
    const before = selState(store.get());
    const ctrl = e.ctrlKey || e.metaKey;
    let dragging = false;
    e.preventDefault(); // 文字の選択を始めない
    el.focus();

    const move = (ev) => {
      const p = toContent(ev.clientX, ev.clientY);
      if (!dragging && Math.abs(p.x - start.x) + Math.abs(p.y - start.y) < 5) return;
      dragging = true;
      const r = { left: Math.min(start.x, p.x), top: Math.min(start.y, p.y),
        right: Math.max(start.x, p.x), bottom: Math.max(start.y, p.y) };
      Object.assign(band.style, { left: `${r.left}px`, top: `${r.top}px`,
        width: `${r.right - r.left}px`, height: `${r.bottom - r.top}px` });
      band.hidden = false;
      const hits = [...content.querySelectorAll(".fd-item")].filter((it) => {
        const b = it.getBoundingClientRect();
        const t = toContent(b.left, b.top);
        return t.x < r.right && t.x + b.width > r.left && t.y < r.bottom && t.y + b.height > r.top;
      }).map((it) => it.dataset.key);
      setSelection(rectSelect(before, hits, { ctrl }));
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      band.hidden = true;
      if (dragging) suppressClick = true; // 続く click で選択を外さない
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });

  el.addEventListener("contextmenu", (e) => {
    if (e.target.closest("input")) return;
    e.preventDefault();
    const s = store.get();
    const item = e.target.closest(".fd-item");
    if (item) {
      const key = item.dataset.key;
      // 選択の外の項目なら、それだけを選び直す（選択の中なら選択全部が対象）
      if (!s.selection.has(key)) setSelection(clickSelect(selState(s), order(s), key));
      actions.openItemMenu(e.clientX, e.clientY);
    } else {
      setSelection(emptySelection());
      actions.openBackgroundMenu(e.clientX, e.clientY);
    }
  });

  store.subscribe((s, changed) => {
    if (["visibleEntries", "selection", "focus", "view", "error", "loading", "sort", "trashSort", "editing", "clipboard", "columnWidths"]
      .some((k) => changed.has(k))) {
      render(s);
    }
  });
  render(store.get());
  return el;
}
