// 画面の中だけのクリップボード（Wiki「画面設計 > コピー・切り取り・貼り付け」）。
// OS のクリップボードは使わない（ブラウザは「ファイル」を書けず、パスの文字列を書いても他のアプリでは使えない）。
// 中身は {mount, paths, mode: "copy" | "cut", denied?}。denied は切り取った項目のうち動かす権限の無いもののパスで、
// 貼り付けたときにその項目だけ失敗にする（送らない）。別のタブとも共有できるよう localStorage にも置く
// （読み書きできなければ、この画面の中だけで動く）。

import { loadPref, savePref, prefKey } from "./prefs.js";

export function isClipboard(v) {
  return !!v && typeof v.mount === "string" && Array.isArray(v.paths) && v.paths.length > 0
    && v.paths.every((p) => typeof p === "string" && p.startsWith("/")) && (v.mode === "copy" || v.mode === "cut")
    && (v.denied === undefined || (Array.isArray(v.denied) && v.denied.every((p) => v.paths.includes(p))));
}

export function loadClipboard() {
  return loadPref("clipboard", null, isClipboard);
}

// 同じページの中の画面（二画面モードの左右）どうしで共有するための購読者。
// storage イベントは書いたページ自身には届かないので、別に知らせる
const localWatchers = new Set();

export function saveClipboard(clip) {
  savePref("clipboard", clip);
  for (const cb of localWatchers) cb(clip);
}

/** ほかの画面・別のタブでクリップボードが変わったら cb を呼ぶ。やめるときの関数を返す。 */
export function watchClipboard(cb) {
  const onStorage = (e) => {
    if (e.key === prefKey("clipboard")) cb(loadClipboard());
  };
  window.addEventListener("storage", onStorage);
  localWatchers.add(cb);
  return () => {
    window.removeEventListener("storage", onStorage);
    localWatchers.delete(cb);
  };
}

/** 切り取り中の項目か（半透明で見せる）。動かす権限の無い項目（denied）は、貼り付けても動かないので含めない。 */
export function isCutPath(clip, mount, path) {
  return !!clip && clip.mode === "cut" && clip.mount === mount && clip.paths.includes(path)
    && !(clip.denied || []).includes(path);
}
