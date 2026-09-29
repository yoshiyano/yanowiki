// 項目のアイコンの決めかたと、プロバイダが持ち込んだアイコンの登録（Wiki「画面設計 > アイコン」）。
//
// - 項目の icon（プロバイダが決めた名前）があれば、そのマウントが持ち込んだアイコンか、組み込みのアイコンを使う
// - 無ければ、フォルダ・拡張子から決める（filetypes.js）
// 持ち込んだアイコンは GET mounts の icons（図形の並び）で届く。**要素を 1 つずつ作り、使ってよい図形と
// 属性だけを写す**（サーバも起動時に確かめているが、画面でも innerHTML は使わない）。

import { typeOf } from "./filetypes.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const CONTAINER_ID = "fd-mount-icons";

// プロバイダが Entry.icon に書ける組み込みのアイコン（icons.svg の項目用のもの。tests/test_static.py が突き合わせる）
export const ITEM_ICONS = new Set([
  "folder", "file", "text", "image", "audio", "video", "pdf", "archive", "code", "sheet", "doc", "link", "mount",
]);

const SHAPES = new Set(["g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon"]);
const SHAPE_ATTRS = new Set([
  "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points",
  "fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
  "stroke-dasharray", "stroke-opacity", "opacity", "transform",
]);

/** 持ち込んだアイコンの、スプライトの中での名前（icon() に渡す名前。"i-" は付けない）。 */
export function mountIconName(mountId, name) {
  return `m-${mountId}-${name}`;
}

function shape({ tag, attrs, children }) {
  if (!SHAPES.has(tag)) return null;
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (SHAPE_ATTRS.has(k) && !/url/i.test(v)) el.setAttribute(k, v);
  }
  for (const c of children) {
    const child = shape(c);
    if (child) el.append(child);
  }
  return el;
}

/** マウントが持ち込んだアイコンをページに登録する（同じ名前は置き換える。二画面で 2 回呼ばれてもよい）。 */
export function registerMountIcons(mounts) {
  let box = document.getElementById(CONTAINER_ID);
  if (!box) {
    box = document.createElementNS(SVG_NS, "svg");
    box.id = CONTAINER_ID;
    box.setAttribute("aria-hidden", "true");
    // 見えない形で置く（display: none だと描けないブラウザがあるので、大きさを 0 にする）
    box.setAttribute("style", "position:absolute;width:0;height:0;overflow:hidden");
    document.body.prepend(box);
  }
  for (const m of mounts) {
    for (const [name, def] of Object.entries(m.icons)) {
      const id = `i-${mountIconName(m.id, name)}`;
      const symbol = document.createElementNS(SVG_NS, "symbol");
      symbol.id = id;
      symbol.setAttribute("viewBox", def.viewBox);
      for (const s of def.shapes) {
        const el = shape(s);
        if (el) symbol.append(el);
      }
      const old = document.getElementById(id);
      if (old) old.replaceWith(symbol);
      else box.append(symbol);
    }
  }
}

function resolve(name, mount) {
  if (!name) return null;
  if (mount && Object.hasOwn(mount.icons, name)) return mountIconName(mount.id, name);
  return ITEM_ICONS.has(name) ? name : null;
}

/** 項目のアイコンの名前（icon() に渡す）。mount はその項目のマウント（GET mounts の 1 つ）。 */
export function entryIcon(entry, mount) {
  if (entry.extra && entry.extra.unreachable) return "link";
  return resolve(entry.icon, mount) || typeOf(entry).icon;
}

/** ツリーのマウントの行のアイコンの名前。 */
export function mountIcon(mount) {
  return resolve(mount.icon, mount) || "mount";
}
