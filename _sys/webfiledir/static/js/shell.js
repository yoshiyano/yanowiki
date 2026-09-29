// 二画面モードの枠。画面（createApp）を 1 つか 2 つ並べ、ツールバーの［二画面］で切り替える。
// - 左（上）の画面は URL のハッシュとブラウザの履歴を使う。右（下）の画面は自分の中だけの履歴を持ち、
//   今の場所を sessionStorage に覚える（ハッシュは 1 つしかないので、2 つの画面で取り合わない）
// - 並べかた（左右か上下か）は CSS が画面の幅と向きで決める（app.css の .fd-shell）
// - 画面の間のドラッグ＆ドロップ・クリップボードの共有・変更の知らせは、それぞれ dnd.js・clipboard.js・
//   main.js が受け持つ（どちらの画面も同じページにあるので、そのまま共有できる）

import { setDialogHost } from "./dialog.js";
import { h } from "./dom.js";
import { parseFeatures } from "./features.js";
import { createApp } from "./main.js";
import { loadPref, savePref } from "./prefs.js";

const SECOND_PANE_KEY = "webfiledir.secondPane";

/**
 * options.features … 画面の機能の ON/OFF（features.js）。どちらの画面にも同じものを渡す。
 *                    dual を false にすると［二画面］を出さず、覚えている二画面の状態も使わない
 */
export function createShell(root, options = {}) {
  const { features = {} } = options;
  const dualEnabled = parseFeatures(features).has("dual"); // 知らない名前はここで Error
  root.classList.add("fd-shell");
  const firstEl = h("div", { class: "fd-pane" });
  root.replaceChildren(firstEl);

  let second = null;
  let secondEl = null;

  const first = createApp(firstEl, {
    paneId: "first", features, onToggleDual: dualEnabled ? () => setDual(!second) : null,
    // フォルダを「隣の画面で開く」。二画面でなければ、二画面にしてそこで開く
    onOpenInOther: dualEnabled ? (mount, path) => {
      if (second) second.actions.go(mount, path);
      else setDual(true, { mount, path, trash: false });
    } : null,
  });
  // ダイアログは、閉じることのない最初の画面に置く（見た目の変数が .fd-app に付いているため）
  setDialogHost(firstEl);

  /** 二画面を切り替える。initialLocation を渡すと、右（下）の画面をそこから始める。 */
  function setDual(on, initialLocation = null) {
    if (on && !second) {
      secondEl = h("div", { class: "fd-pane" });
      root.append(secondEl);
      second = createApp(secondEl, {
        paneId: "second",
        features,
        router: "memory",
        storageKey: SECOND_PANE_KEY,
        // 覚えた場所が無ければ、最初の画面と同じ場所から始める
        fallbackLocation: () => first.store.get().location,
        initialLocation,
        onOpenInOther: (mount, path) => first.actions.go(mount, path),
        onToggleDual: () => setDual(false),
        dialogHost: false,
        focus: false,
      });
      setDialogHost(firstEl);
    } else if (!on && second) {
      second.destroy();
      secondEl.remove();
      second = null;
      secondEl = null;
      firstEl.querySelector(".fd-view")?.focus();
    }
    root.classList.toggle("fd-dual", !!second);
    first.store.set({ dual: !!second });
    if (second) second.store.set({ dual: true });
    savePref("dual", !!second);
  }

  if (dualEnabled && loadPref("dual", false, (v) => typeof v === "boolean")) setDual(true);

  return { first, get second() { return second; }, setDual };
}
