// 状態から読み取る小さな関数（複数の部品が使うもの）。

import { mountAttributes, TRASH_ATTRIBUTES } from "./attributes.js";

/** 今いるマウントの情報（{id, label, readonly, capabilities}）。 */
export function currentMount(s) {
  return (s.location && s.mounts.find((m) => m.id === s.location.mount)) || null;
}

/** 今いるマウントでできる操作の集合（読み取り専用なら空）。 */
export function capsOf(s) {
  const m = currentMount(s);
  return new Set(m ? m.capabilities : []);
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

/** 今いるマウントの、ファイルを開く経路（先頭が既定）。 */
export function openMethodsOf(s) {
  const m = currentMount(s);
  return m ? m.openMethods : [];
}

/** 今いるマウントの、フォルダを開く経路（既定の「中に入る」は画面が持ち、ここには入らない）。 */
export function dirOpenMethodsOf(s) {
  const m = currentMount(s);
  return m ? m.dirOpenMethods : [];
}

/** マウント id の情報（衝突のダイアログで、別のマウントの項目を見せるとき）。 */
export function mountOf(s, mountId) {
  return s.mounts.find((m) => m.id === mountId) || null;
}

/** 画面の機能（features.js）が ON か。組み込む側が止めた機能は、マウントでできても出さない。 */
export function enabled(s, feature) {
  return s.features.has(feature);
}

/**
 * 項目の権限（サーバが返す moveauth・readauth・writeauth・execauth。それぞれ 0 か 1）で
 * what（"move" | "read" | "write" | "exec"）が許されているか。項目が無い（読み込み中・ごみ箱など）なら許さない。操作ごとの決まりは下の can* を使う。
 */
export function allows(entry, what) {
  return !!entry && entry[`${what}auth`] === 1;
}

/** 渡した項目のすべてで what が許されているか（1 つも無ければ false）。 */
export function allAllow(entries, what) {
  return entries.length > 0 && entries.every((e) => allows(e, what));
}

// --- 操作ごとの権限（Wiki「画面設計 > 権限」）。権限の値は項目ごとにサーバが返すもので、Linux のアクセス権の
// 決まりには合わせない。名前の変更・移動・削除・移動先は設計者の仕様（2026-09-29）、それ以外はクロコの実装例 ---

/** 開けるか: フォルダは「実行」（中へ入る）、ファイルは「読む」。 */
export function canOpenEntry(entry) {
  return allows(entry, entry && entry.kind === "dir" ? "exec" : "read");
}

/**
 * 名前を変えられるか・動かせるか（切り取り・ドラッグで動かす）。**入っているフォルダではなく、項目それぞれの
 * 「動かす」で決める**（設計者の仕様）。移動先の可否は canPutInto（フォルダの「書く」）。
 * 複数を選んだときは、**1 つでも動かせれば操作できる。動かせない項目はその項目だけ失敗にし、残りは動かす**
 * （2026-09-29 設計者の指示「権限のないものだけ失敗させる形に」）。動かせない項目は unmovable で取り出す。
 */
export function canMoveEntries(entries) {
  return entries.some((e) => allows(e, "move"));
}

/**
 * 削除できるか（ごみ箱へ・完全に削除）。**項目それぞれの「動かす」で決める**（2026-09-29 設計者の仕様「MoveAuth に
 * 載せて下さい。ゴミ箱『移動』に準ずるべき」）。移動と同じく、1 つでも消せれば操作でき、消せない項目だけ失敗にする
 * （同じ日の設計者の指示「削除においても成功するものは動作させます」）。
 */
export function canDeleteEntries(entries) {
  return canMoveEntries(entries);
}

/** 動かせない（削除もできない）項目。操作のときにサーバへ送らず、その項目だけ失敗にする。 */
export function unmovable(entries) {
  return entries.filter((e) => !allows(e, "move"));
}

/** コピー元にできるか（中身を読む）。 */
export function canCopyFrom(entries) {
  return allAllow(entries, "read");
}

/** フォルダの中に作る・貼り付ける・落とせるか（移動先・コピー先としての権限。設計者の仕様）。 */
export function canPutInto(folderEntry) {
  return allows(folderEntry, "write");
}
