// 並べ替えの比べかた。画面の部品から切り離してテストページで確かめる
// （Wiki「画面設計 > 並べ替え」）。キーは "name" か、属性のキー（attributes.js）。

import { attributeValue } from "./attributes.js";

const collator = new Intl.Collator("ja", { numeric: true, sensitivity: "base" });

/** 名前の比較。自然順・大文字小文字を区別しない。同じと判定されたら符号順で決め、毎回同じ並びにする。 */
export function compareNames(a, b) {
  return collator.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0);
}

/** 並べ替えの設定として読めるか（localStorage から読んだ値の確かめ）。キーが今の属性にあるかは effectiveSort で見る。 */
export function isSort(v) {
  return !!v && typeof v.key === "string" && typeof v.desc === "boolean";
}

/** 今の属性で使える並べ替え。覚えていたキーがこのマウントの属性に無ければ名前の昇順（覚えている値は変えない）。 */
export function effectiveSort(sort, attributes) {
  if (sort && (sort.key === "name" || attributes.some((a) => a.key === sort.key))) return sort;
  return { key: "name", desc: false };
}

/**
 * 並べ替えた新しい配列を返す。
 * - フォルダが先。逆順でもフォルダが先のまま（逆になるのはそれぞれの組の中だけ）。
 *   foldersFirst: false なら分けない（ごみ箱の画面。削除日時で並べるときにフォルダだけ先に来ると見にくい）
 * - 値が null の項目は、属性の none が "first" なら昇順でも降順でも先頭（最優先）、"last" なら末尾（無効データ）
 * - 値が同じなら（null 同士も）名前の昇順
 * attributes は今の画面の属性の定義。key が名前でも属性でもなければ名前で並べる。
 */
export function sortEntries(entries, { key = "name", desc = false } = {}, { foldersFirst = true, attributes = [] } = {}) {
  const attr = key === "name" ? null : attributes.find((a) => a.key === key) || null;
  const sign = desc ? -1 : 1;
  return [...entries].sort((a, b) => {
    const da = a.kind === "dir";
    const db = b.kind === "dir";
    if (foldersFirst && da !== db) return da ? -1 : 1;
    if (!attr) return sign * compareNames(a.name, b.name);
    const va = attributeValue(attr, a);
    const vb = attributeValue(attr, b);
    if (va == null || vb == null) {
      if (va == null && vb == null) return compareNames(a.name, b.name);
      const first = attr.none === "first";
      return (va == null) === first ? -1 : 1; // 向き（desc）に関わらない
    }
    const c = attr.kind === "number" ? va - vb : collator.compare(va, vb);
    return sign * c || compareNames(a.name, b.name);
  });
}
