// 拡張子の切り出しと、拡張子 → アイコン・種類の対応。
// **拡張子を切り出す関数はここの splitExt だけ。**アイコン・「種類」・F2 の選択範囲はすべてこれを使う
// （Wiki「画面設計 > 拡張子の切り出し」）。

/** 名前を拡張子の手前と拡張子に分ける。拡張子が無ければ ext は ""。 */
export function splitExt(name, kind = "file") {
  if (kind === "dir") return { stem: name, ext: "" };
  // 先頭の "."（いくつ続いても）は拡張子の区切りと見なさない（Python の os.path.splitext と同じ）
  let lead = 0;
  while (name[lead] === ".") lead++;
  const i = name.lastIndexOf(".");
  if (i < lead || i === name.length - 1) return { stem: name, ext: "" };
  return { stem: name.slice(0, i), ext: name.slice(i + 1) };
}

const T = (icon, label) => ({ icon, label });

// 拡張子（小文字）→ アイコンと種類
const TABLE = {
  txt: T("text", "テキスト ドキュメント"),
  md: T("text", "Markdown ドキュメント"),
  log: T("text", "ログ ファイル"),
  ini: T("text", "設定ファイル"),
  cfg: T("text", "設定ファイル"),
  conf: T("text", "設定ファイル"),

  jpg: T("image", "JPEG 画像"),
  jpeg: T("image", "JPEG 画像"),
  png: T("image", "PNG 画像"),
  gif: T("image", "GIF 画像"),
  webp: T("image", "WebP 画像"),
  svg: T("image", "SVG 画像"),
  bmp: T("image", "ビットマップ画像"),
  ico: T("image", "アイコン"),
  tif: T("image", "TIFF 画像"),
  tiff: T("image", "TIFF 画像"),
  heic: T("image", "HEIC 画像"),

  mp3: T("audio", "MP3 音声"),
  wav: T("audio", "WAV 音声"),
  flac: T("audio", "FLAC 音声"),
  ogg: T("audio", "Ogg 音声"),
  m4a: T("audio", "M4A 音声"),
  aac: T("audio", "AAC 音声"),

  mp4: T("video", "MP4 動画"),
  m4v: T("video", "MP4 動画"),
  mkv: T("video", "Matroska 動画"),
  webm: T("video", "WebM 動画"),
  mov: T("video", "QuickTime 動画"),
  avi: T("video", "AVI 動画"),
  m2ts: T("video", "M2TS 動画"), // ビデオカメラ（AVCHD）・Blu-ray の MPEG-2 TS（2026-09-26 設計者の指示で追加）

  pdf: T("pdf", "PDF ドキュメント"),

  zip: T("archive", "ZIP 圧縮"),
  gz: T("archive", "gzip 圧縮"),
  tgz: T("archive", "tar.gz 圧縮"),
  bz2: T("archive", "bzip2 圧縮"),
  xz: T("archive", "xz 圧縮"),
  zst: T("archive", "zstd 圧縮"),
  tar: T("archive", "tar アーカイブ"),
  "7z": T("archive", "7z 圧縮"),
  rar: T("archive", "RAR 圧縮"),

  py: T("code", "Python ソース"),
  js: T("code", "JavaScript ソース"),
  mjs: T("code", "JavaScript ソース"),
  ts: T("code", "TypeScript ソース"),
  html: T("code", "HTML ドキュメント"),
  htm: T("code", "HTML ドキュメント"),
  css: T("code", "CSS スタイルシート"),
  json: T("code", "JSON ファイル"),
  xml: T("code", "XML ファイル"),
  yaml: T("code", "YAML ファイル"),
  yml: T("code", "YAML ファイル"),
  toml: T("code", "TOML ファイル"),
  sh: T("code", "シェル スクリプト"),
  c: T("code", "C ソース"),
  h: T("code", "C ヘッダー"),
  cpp: T("code", "C++ ソース"),
  java: T("code", "Java ソース"),
  go: T("code", "Go ソース"),
  rs: T("code", "Rust ソース"),
  sql: T("code", "SQL ファイル"),

  csv: T("sheet", "CSV ファイル"),
  tsv: T("sheet", "TSV ファイル"),
  xlsx: T("sheet", "xlsx 表計算"),
  xls: T("sheet", "xls 表計算"),
  ods: T("sheet", "ods 表計算"),

  docx: T("doc", "docx 文書"),
  doc: T("doc", "doc 文書"),
  odt: T("doc", "odt 文書"),
  rtf: T("doc", "リッチ テキスト"),
  pptx: T("doc", "pptx プレゼンテーション"),
  odp: T("doc", "odp プレゼンテーション"),
};

// 最後の "." だけでは表せない組み合わせ。拡張子は "gz" のまま、「種類」だけまとめる
// （ToDo「決めていないこと」の 9 の案）
const COMPOUND = [
  [".tar.gz", T("archive", "tar.gz 圧縮")],
  [".tar.bz2", T("archive", "tar.bz2 圧縮")],
  [".tar.xz", T("archive", "tar.xz 圧縮")],
  [".tar.zst", T("archive", "tar.zst 圧縮")],
];

const FOLDER = T("folder", "フォルダ");
const UNREACHABLE = T("link", "リンク（開けません）");

/** エントリのアイコン名と「種類」の文字列。 */
export function typeOf(entry) {
  if (entry.extra && entry.extra.unreachable) return UNREACHABLE;
  if (entry.kind === "dir") return FOLDER;
  const lower = entry.name.toLowerCase();
  for (const [suffix, t] of COMPOUND) {
    // ".tar.gz" という名前そのもの（拡張子の手前が空）はまとめない
    if (lower.endsWith(suffix) && lower.length > suffix.length) return t;
  }
  const { ext } = splitExt(entry.name, entry.kind);
  if (!ext) return T("file", "ファイル");
  return TABLE[ext.toLowerCase()] || T("file", `${ext.toUpperCase()} ファイル`);
}

/** 隠しファイルか（"." で始まる名前）。 */
export function isHidden(entry) {
  return entry.name.startsWith(".");
}
