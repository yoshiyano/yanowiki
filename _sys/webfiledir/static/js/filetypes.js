// 拡張子 → アイコン・種類の対応と、名前の入力欄で選ぶ範囲。
// **拡張子はサーバが決めて項目の ext に載せる。画面は名前から切り出さない**（2026-09-30 設計者の指示。
// Wiki「画面設計 > 拡張子の切り出し」）。

/**
 * 名前の入力欄で「拡張子の手前まで」選ぶときの長さ。value が項目の拡張子（entry.ext）で終わっていれば、
 * その手前まで。フォルダ・拡張子の無い項目・拡張子を打ち変えた名前は、全体。
 */
export function stemLength(value, entry) {
  const ext = entry.kind === "dir" ? "" : entry.ext || "";
  const tail = `.${ext}`.toLowerCase();
  if (ext && value.toLowerCase().endsWith(tail) && value.length > tail.length) return value.length - tail.length;
  return value.length;
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
  // 複合拡張子（サーバの server/exts.py の COMPOUND_EXTS）
  "tar.gz": T("archive", "tar.gz 圧縮"),
  "tar.bz2": T("archive", "tar.bz2 圧縮"),
  "tar.xz": T("archive", "tar.xz 圧縮"),
  "tar.zst": T("archive", "tar.zst 圧縮"),
};


const FOLDER = T("folder", "フォルダ");
const UNREACHABLE = T("link", "リンク（開けません）");

/** エントリのアイコン名と「種類」の文字列。 */
export function typeOf(entry) {
  if (entry.extra && entry.extra.unreachable) return UNREACHABLE;
  if (entry.kind === "dir") return FOLDER;
  const ext = entry.ext || "";
  if (!ext) return T("file", "ファイル");
  return TABLE[ext.toLowerCase()] || T("file", `${ext.toUpperCase()} ファイル`);
}

/** 隠しファイルか（"." で始まる名前）。 */
export function isHidden(entry) {
  return entry.name.startsWith(".");
}
