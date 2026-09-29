// DOM を組み立てる小さな補助。文字列はすべて textContent で入れる（名前に < などがあっても安全）。

const SVG_NS = "http://www.w3.org/2000/svg";
const ICONS = new URL("../icons/icons.svg", import.meta.url).href;

/** h("button", {class: "x", onclick: fn, title: "..."}, [子...]) */
export function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    el.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return el;
}

/** スプライトのアイコン。name は "folder" など（"i-" は付けない）。 */
export function icon(name, cls = "fd-icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  // ページに埋め込んだスプライト（loadIcons）を参照する。埋め込む前に作ったアイコンも、埋め込まれた時点で描かれる
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

const SPRITE_ID = "fd-icon-sprite";
let loading = null;

/**
 * アイコンのスプライト（icons.svg）を読み、ページの中に埋め込む（何度呼んでも 1 回だけ）。
 *
 * 以前は <use href="icons.svg#i-folder"> と別ファイルを参照していたが、ブラウザは参照先のスプライトを
 * ページとは別に持ち続け、ふつうの再読み込みでは新しくならないことがあった（二画面のアイコンを足したとき、
 * 古いスプライトが使われて新しいアイコンだけが出なかった）。cache: "no-cache" で毎回サーバへ確かめて読み、
 * ページの中を参照する形にした。
 */
export function loadIcons() {
  if (document.getElementById(SPRITE_ID)) return Promise.resolve();
  if (!loading) {
    loading = (async () => {
      const res = await fetch(ICONS, { cache: "no-cache" });
      if (!res.ok) throw new Error(`icons.svg を読めません（${res.status}）`);
      const parsed = new DOMParser().parseFromString(await res.text(), "image/svg+xml");
      const sprite = parsed.documentElement;
      if (sprite.nodeName !== "svg") throw new Error("icons.svg が SVG として読めません");
      sprite.id = SPRITE_ID;
      sprite.setAttribute("aria-hidden", "true");
      // 見えない形で置く（display: none だと描けないブラウザがあるので、大きさを 0 にする）
      sprite.setAttribute("style", "position:absolute;width:0;height:0;overflow:hidden");
      if (!document.getElementById(SPRITE_ID)) document.body.prepend(document.importNode(sprite, true));
    })().catch((err) => {
      loading = null; // 次に呼ばれたら読み直す
      console.error(err);
    });
  }
  return loading;
}
