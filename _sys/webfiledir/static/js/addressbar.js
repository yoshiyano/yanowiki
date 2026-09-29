// アドレスバー: パンくず表示。区切りを押すとそこへ移る。空いたところを押すとパスを打ち込める。

import { h, icon } from "./dom.js";
import { splitPath, joinPath, formatAddress, parseAddress } from "./location.js";
import { mountIcon } from "./icons.js";

export function createAddressBar(store, actions) {
  const crumbs = h("div", { class: "fd-crumbs" });
  const input = h("input", {
    class: "fd-address-input", type: "text", spellcheck: "false", "aria-label": "場所",
    hidden: true,
  });
  const el = h("div", { class: "fd-addressbar" }, [crumbs, input]);

  function startEditing() {
    const loc = store.get().location;
    input.value = loc ? formatAddress(loc.mount, loc.path) : "/";
    crumbs.hidden = true;
    input.hidden = false;
    input.focus();
    input.select();
  }

  function stopEditing() {
    input.hidden = true;
    crumbs.hidden = false;
  }

  // パンくずのボタン以外（空いたところ）を押したら打ち込みに入る
  crumbs.addEventListener("click", (e) => {
    if (e.target === crumbs) startEditing();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const loc = parseAddress(input.value);
      if (!loc) {
        actions.message("場所は /マウント名/フォルダ/… の形で入力してください", "error");
        return;
      }
      stopEditing();
      actions.go(loc.mount, loc.path);
    } else if (e.key === "Escape") {
      stopEditing();
    }
  });
  input.addEventListener("blur", stopEditing);

  function render(s) {
    crumbs.replaceChildren();
    if (!s.location) return;
    const { mount, path, trash } = s.location;
    const m = s.mounts.find((x) => x.id === mount);
    const parts = splitPath(path) || [];
    // [表示, 押したとき, アイコン, 落とし先の印]。区切りへ落とすと、その階層へ移せる（上の階層へすぐ移せるように）
    // 表示はマウントの label（id は URL・API の識別子で、表示には使わない）
    const items = [[m ? m.label : "不明なマウント", () => actions.go(mount, "/"), m ? mountIcon(m) : "mount", { dropMount: mount, dropPath: "/" }]];
    if (trash) items.push(["ごみ箱", () => actions.goTrash(mount), "trash", { dropMount: mount, dropTrash: "1" }]);
    else {
      parts.forEach((p, i) => {
        const path = joinPath(parts.slice(0, i + 1));
        items.push([p, () => actions.go(mount, path), null, { dropMount: mount, dropPath: path }]);
      });
    }
    items.forEach(([label, go, ic, drop], i) => {
      if (i > 0) crumbs.append(icon("chevron", "fd-icon fd-crumb-sep"));
      const last = i === items.length - 1;
      crumbs.append(h("button", {
        type: "button", class: "fd-crumb", "aria-current": last ? "location" : null, onclick: go, dataset: drop,
      }, ic ? [icon(ic), label] : label));
    });
  }

  store.subscribe((s, changed) => {
    if (changed.has("location") || changed.has("mounts")) render(s);
  });
  render(store.get());
  return el;
}
