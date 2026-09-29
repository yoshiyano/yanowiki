// 表示の書式（サイズ・日時）。

const UNITS = ["KB", "MB", "GB", "TB"];

/** バイト数を読みやすくする。1024 未満は「n バイト」、それ以上は 10 未満だけ小数 1 桁。 */
export function formatSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} バイト`;
  let n = bytes;
  let unit = -1;
  do {
    n /= 1024;
    unit++;
  } while (n >= 1024 && unit < UNITS.length - 1);
  const shown = n < 10 ? n.toFixed(1) : Math.round(n).toLocaleString("ja-JP");
  return `${shown} ${UNITS[unit]}`;
}

const dateFormat = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});

/** UNIX 時刻（秒）を「2026/09/25 23:58」の形にする（表示するブラウザの時間帯）。 */
export function formatTime(seconds) {
  if (seconds == null) return "";
  return dateFormat.format(new Date(seconds * 1000));
}

const dayFormat = new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit" });

/** UNIX 時刻（秒）を「2026/09/25」の形にする（表示するブラウザの時間帯）。 */
export function formatDate(seconds) {
  if (seconds == null) return "";
  return dayFormat.format(new Date(seconds * 1000));
}
