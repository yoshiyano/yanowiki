// ツールバー: 戻る・進む・上へ・更新（画面に組み込み）、操作のボタン（サーバが宣言したコマンドのうち places に
// toolbar があるもの。今の場所で使えなければ灰色、ごみ箱の中か種類が合わなければ出さない）、並べ替え、表示形式、
// 隠しファイル、二画面。

import { h, icon } from "./dom.js";
import { parentPath } from "./location.js";
import { attributesOf } from "./model.js";
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

  // 操作のボタン（宣言から作る。マウント・場所・宣言が変わったら作り直す）
  const ops = h("div", { class: "fd-group fd-commands" });
  let opsFor = null;
  let opButtons = []; // [{cmd, button}]

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

  const el = h("div", { class: "fd-toolbar", role: "toolbar" }, [
    h("div", { class: "fd-group" }, [back, forward, up, refresh]),
    ops,
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
    back.disabled = !s.canBack;
    forward.disabled = !s.canForward;
    up.disabled = !s.location || trash || parentPath(s.location.path) == null;
    refresh.disabled = !s.location;

    // 操作のボタン。ごみ箱の中のコマンドは、0.x と同じく文字も添える
    const ready = !!s.location && !s.error && !s.editing;
    const here = s.location ? actions.commandsHere("toolbar") : [];
    const opsSignature = JSON.stringify([s.location && s.location.mount, trash, here.map(({ cmd }) => cmd.id)]);
    if (opsSignature !== opsFor) {
      opsFor = opsSignature;
      opButtons = here.map(({ cmd }) => {
        const title = cmd.key ? `${cmd.label}（${cmd.key}）` : cmd.label;
        const withText = trash || (cmd.when && cmd.when.view === "trash");
        const b = button(cmd.icon, title, () => actions.run(cmd), withText ? cmd.label : null);
        b.dataset.command = cmd.id;
        return { cmd, button: b };
      });
      ops.replaceChildren(...opButtons.map((x) => x.button));
    }
    ops.hidden = !opButtons.length;
    const states = new Map(here.map(({ cmd, ev }) => [cmd.id, ev.state]));
    for (const { cmd, button: b } of opButtons) b.disabled = !ready || states.get(cmd.id) !== "enabled";

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
