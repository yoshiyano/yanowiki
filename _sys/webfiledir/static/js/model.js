// 状態から読み取る小さな関数（複数の部品が使うもの）。

import { mountAttributes, TRASH_ATTRIBUTES } from "./attributes.js";

/** 今いるマウントの情報（{id, label, readonly, capabilities, commands, trash, …}）。 */
export function currentMount(s) {
  return (s.location && s.mounts.find((m) => m.id === s.location.mount)) || null;
}

/** 選んでいる項目（表示の並び順）。 */
export function selectedEntries(s) {
  return s.visibleEntries.filter((e) => s.selection.has(e.key));
}

/** 今の画面の属性（詳細表示の列・並べ替えのキー）。ごみ箱ではごみ箱だけの属性を前に足す。 */
export function attributesOf(s) {
  const attrs = mountAttributes(currentMount(s));
  return s.location && s.location.trash ? [...TRASH_ATTRIBUTES, ...attrs] : attrs;
}

/** マウント id の情報（衝突のダイアログで、別のマウントの項目を見せるとき）。 */
export function mountOf(s, mountId) {
  return s.mounts.find((m) => m.id === mountId) || null;
}

/**
 * 項目の権限（サーバが返す moveauth・readauth・writeauth・execauth。それぞれ 0 か 1）で
 * what（"move" | "read" | "write" | "exec"）が許されているか。項目が無い（読み込み中・ごみ箱など）なら許さない。
 * コマンドの権限は宣言の when で決まる（runner.js の evaluate）。ここは画面に組み込みの操作が使う。
 */
export function allows(entry, what) {
  return !!entry && entry[`${what}auth`] === 1;
}

/** 開けるか・入れるか（画面に組み込みの「フォルダに入る」と、開く前の確かめ）: フォルダは「実行」、ファイルは「読む」。 */
export function canOpenEntry(entry) {
  return allows(entry, entry && entry.kind === "dir" ? "exec" : "read");
}

/** フォルダの中に作る・貼り付ける・落とせるか（移動先・コピー先としての権限。0.x の設計者の仕様）。 */
export function canPutInto(folderEntry) {
  return allows(folderEntry, "write");
}
