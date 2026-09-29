// 属性（更新日時・サイズ・仮想構造に固有の属性）の定義・値・表現方法（Wiki「API 設計 > 属性」）。
// 属性は「値」と「表現方法」の 2 つの規則を持つ。定義はマウントごとにサーバが返す（GET mounts の attributes）。
//   値      … kind（"number" は数として、"text" は自然順で比べる）と none（値が null の項目の置き場所。
//             "first" は昇順でも降順でも先頭＝最優先、"last" は昇順でも降順でも末尾＝無効データ）
//   表現方法 … format（{type: "text" | "number" | "bytes" | "datetime" | "date" | "map", ...}）
// 画面の部品（詳細表示・並べ替え・ステータスバー・衝突のダイアログ）は、属性のキーを決め打ちせず、ここを通す。

import { typeOf } from "./filetypes.js";
import { formatSize, formatTime, formatDate } from "./format.js";
import { parentPath } from "./location.js";

// ごみ箱の画面だけの属性（マウントの属性の前に並べる）
export const TRASH_ATTRIBUTES = [
  { key: "originalPath", label: "元の場所", kind: "text", format: { type: "text" }, none: "last", align: "start", width: 240, source: "originalPath" },
  { key: "deletedAt", label: "削除日時", kind: "number", format: { type: "datetime" }, none: "last", align: "start", width: 150, source: "deletedAt" },
];

/** マウントの属性の定義（GET mounts の attributes）。 */
export function mountAttributes(mount) {
  return mount ? mount.attributes : [];
}

/** 項目の属性の値。無い・kind に合わないものは null（並べ替えでは「値なし」として none の規則に従う）。 */
export function attributeValue(attr, entry) {
  if (!entry) return null;
  let v;
  switch (attr.source) {
    case "filetype":
      return typeOf(entry).label;
    case "originalPath":
      return entry.originalPath ? parentPath(entry.originalPath) || "/" : null;
    case "deletedAt":
      v = entry.deletedAt;
      break;
    default:
      v = entry.attrs[attr.key];
  }
  if (attr.kind === "number") return typeof v === "number" && Number.isFinite(v) ? v : null;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return typeof v === "string" ? v : null;
}

const numberFormats = new Map();

function numberFormat(f) {
  const max = f.digits ?? 3;
  const min = Math.min(f.minDigits ?? 0, max);
  const k = `${min}/${max}/${f.grouping !== false}`;
  if (!numberFormats.has(k)) {
    numberFormats.set(k, new Intl.NumberFormat("ja-JP", {
      minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: f.grouping !== false,
    }));
  }
  return numberFormats.get(k);
}

/** 値を表現方法に従って文字にする。値が null なら format.none（既定は空）。 */
export function formatAttribute(attr, value) {
  const f = attr.format;
  if (value == null) return f.none ?? "";
  const wrap = (text) => `${f.prefix ?? ""}${text}${f.suffix ?? ""}`;
  switch (f.type) {
    case "bytes":
      return typeof value === "number" ? formatSize(value) : String(value);
    case "datetime":
      return typeof value === "number" ? formatTime(value) : String(value);
    case "date":
      return typeof value === "number" ? formatDate(value) : String(value);
    case "number":
      return typeof value === "number" ? wrap(numberFormat(f).format(value)) : wrap(String(value));
    case "map": {
      const labels = f.labels || {};
      const k = String(value);
      return Object.hasOwn(labels, k) ? labels[k] : k;
    }
    default:
      return wrap(String(value));
  }
}

// フォルダの行で値の無い欄は空欄（2026-09-28 設計者の指示）。表現方法の none より優先する
export const DIR_NO_VALUE = "";

/** 詳細表示などに出す文字（値を取り出して表現方法で文字にする）。フォルダで値が無ければ空欄。 */
export function attributeText(attr, entry) {
  const value = attributeValue(attr, entry);
  if (value == null && entry.kind === "dir") return DIR_NO_VALUE;
  return formatAttribute(attr, value);
}
