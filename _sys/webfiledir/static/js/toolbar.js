// ツールバー: 戻る・進む・上へ・更新、作成・名前の変更・削除（ごみ箱では 元に戻す・完全に削除・空にする）、
// 並べ替え、表示形式、隠しファイル。マウントの capabilities に無い操作は灰色にする。
// 画面の機能（features.js）で止めた操作は、灰色にせずボタンごと出さない。

import { h, icon } from "./dom.js";
import { parentPath } from "./location.js";
import {
  attributesOf, canCopyFrom, canDeleteEntries, canMoveEntries, canPutInto, capsOf, enabled, selectedEntries,
} from "./model.js";
import { effectiveSort } from "./sort.js";

export const VIEW_MODES = [
  ["large", "view-large", "大アイコン"],
  ["small", "view-small", "小アイコン"],
  ["list", "view-list", "一覧"],
  ["details", "view-details", "詳細"],
];


function button(name, label, onclick, text = null) {
  return h("button", {
    type: "button", class: text ? "fd-tool fd-tool-text" : "fd-tool", title: label, "aria-label": label, onclick,
  }, text ? [icon(name), h("span", {}, text)] : [icon(name)]);
}

export function createToolbar(store, actions) {
  const back = button("back", "戻る（Alt+←）", actions.back);
  const forward = button("forward", "進む（Alt+→）", actions.forward);
  const up = button("up", "上のフォルダへ（Alt+↑）", actions.up);
  const refresh = button("refresh", "最新の情報に更新（F5）", actions.refresh);

  // ふだんの操作
  const newFolder = button("new-folder", "新しいフォルダ（Ctrl+Shift+N）", () => actions.newItem("dir"));
  const newFile = button("new-file", "新しいテキスト ドキュメント", () => actions.newItem("file"));
  const cut = button("cut", "切り取り（Ctrl+X）", actions.cutSelected);
  const copy = button("copy", "コピー（Ctrl+C）", actions.copySelected);
  const paste = button("paste", "貼り付け（Ctrl+V）", () => actions.paste());
  const rename = button("rename", "名前の変更（F2）", actions.startRename);
  const del = button("delete", "削除（Delete。Shift+Delete で完全に削除）", () => actions.deleteSelected());
  const normalOps = h("div", { class: "fd-group" }, [newFolder, newFile, cut, copy, paste, rename, del]);

  // ごみ箱の操作
  const restore = button("restore", "元に戻す", actions.restoreSelected, "元に戻す");
  const purge = button("delete", "完全に削除", actions.purgeSelected, "完全に削除");
  const empty = button("trash", "ごみ箱を空にする", actions.emptyTrash, "ごみ箱を空にする");
  const trashOps = h("div", { class: "fd-group" }, [restore, purge, empty]);

  const viewButtons = VIEW_MODES.map(([mode, ic, label]) => {
    const b = button(ic, label, () => actions.setView(mode));
    b.dataset.mode = mode;
    return b;
  });

  const sortKey = h("select", {
    class: "fd-select", title: "並べ替え", "aria-label": "並べ替えのキー",
    onchange: (e) => actions.setSort({ key: e.target.value, desc: currentSort().desc }),
  });
  const sortDir = h("button", {
    type: "button", class: "fd-tool",
    onclick: () => actions.setSort({ ...currentSort(), desc: !currentSort().desc }),
  });

  // 二画面モードの切り替え（二画面の枠が actions.toggleDual を渡したときだけ出す）
  const dual = actions.toggleDual
    ? h("button", {
      type: "button", class: "fd-tool fd-toggle", title: "二画面（左右か上下に 2 つ並べる）",
      "aria-label": "二画面", onclick: () => actions.toggleDual(),
    }, [icon("split")])
    : null;

  const hidden = h("button", {
    type: "button", class: "fd-tool fd-toggle", title: "隠しファイル（. で始まる名前）を表示",
    "aria-label": "隠しファイルを表示", onclick: () => actions.setShowHidden(!store.get().showHidden),
  }, [icon("hidden")]);

  // 止めた機能のボタンは出さない（作ったあとに features は変わらないので、ここで 1 回だけ決める）
  const byFeature = [[newFolder, "newFolder"], [newFile, "newFile"], [cut, "cut"], [copy, "copy"], [paste, "paste"],
    [rename, "rename"], [del, "delete"], [restore, "trash"], [purge, "purge"], [empty, "purge"]];
  for (const [b, feature] of byFeature) if (!enabled(store.get(), feature)) b.remove();

  const el = h("div", { class: "fd-toolbar", role: "toolbar" }, [
    h("div", { class: "fd-group" }, [back, forward, up, refresh]),
    normalOps,
    trashOps,
    h("div", { class: "fd-spacer" }),
    h("div", { class: "fd-group" }, [sortKey, sortDir]),
    h("div", { class: "fd-group", role: "group", "aria-label": "表示形式" }, viewButtons),
    h("div", { class: "fd-group" }, [hidden, dual]),
  ]);

  const inTrash = () => !!(store.get().location && store.get().location.trash);
  const currentSort = () => effectiveSort(inTrash() ? store.get().trashSort : store.get().sort, attributesOf(store.get()));
  let sortOptionsFor = null;

  function render(s) {
    const trash = !!(s.location && s.location.trash);
    const caps = capsOf(s);
    const selectedItems = selectedEntries(s);
    const selected = selectedItems.length;
    // 権限（Wiki「画面設計 > 権限」）: 作る＝今いるフォルダの「書く」、名前の変更・切り取り・削除＝選んだ項目の
    // 「動かす」、コピー＝選んだ項目の「読む」
    const canPut = canPutInto(s.dir);
    const canMove = canMoveEntries(selectedItems);
    const canDelete = canDeleteEntries(selectedItems);
    const ready = !!s.location && !s.error;

    back.disabled = !s.canBack;
    forward.disabled = !s.canForward;
    up.disabled = !s.location || trash || parentPath(s.location.path) == null;
    refresh.disabled = !s.location;

    normalOps.hidden = trash || !normalOps.childElementCount;
    trashOps.hidden = !trash;
    newFolder.disabled = !ready || !caps.has("mkdir") || !canPut;
    newFile.disabled = !ready || !caps.has("touch") || !canPut;
    cut.disabled = !ready || !caps.has("move") || selected === 0 || !canMove;
    copy.disabled = !ready || selected === 0 || !canCopyFrom(selectedItems);
    paste.disabled = !ready || !actions.canPaste();
    rename.disabled = !ready || !caps.has("rename") || selected !== 1 || !!s.editing || !canMove;
    del.disabled = !ready || selected === 0 || !(caps.has("trash") || caps.has("delete")) || !canDelete;
    restore.disabled = !caps.has("trash") || selected === 0;
    purge.disabled = !caps.has("trash") || selected === 0;
    empty.disabled = !caps.has("trash") || s.entries.length === 0;

    for (const b of viewButtons) b.setAttribute("aria-pressed", String(b.dataset.mode === s.view));
    // 並べ替えのキーは名前と、今の画面の属性（マウントごとに違う）
    const attributes = attributesOf(s);
    const keys = [{ key: "name", label: "名前" }, ...attributes];
    const signature = JSON.stringify(keys.map(({ key, label }) => [key, label]));
    if (sortOptionsFor !== signature) {
      sortOptionsFor = signature;
      sortKey.replaceChildren(...keys.map(({ key, label }) => h("option", { value: key }, `${label}順`)));
    }
    const sort = effectiveSort(trash ? s.trashSort : s.sort, attributes);
    sortKey.value = sort.key;
    const dirLabel = sort.desc ? "降順（押すと昇順）" : "昇順（押すと降順）";
    sortDir.replaceChildren(icon(sort.desc ? "sort-desc" : "sort-asc"));
    sortDir.title = dirLabel;
    sortDir.setAttribute("aria-label", dirLabel);
    hidden.setAttribute("aria-pressed", String(s.showHidden));
    if (dual) dual.setAttribute("aria-pressed", String(s.dual));
  }

  store.subscribe(render);
  render(store.get());
  return el;
}
