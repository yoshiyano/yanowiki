// 場所（マウント + パス、またはマウントのごみ箱）と、URL のハッシュ・アドレスバーの文字列との行き来。
// 形は "#/<mount>/<path>"（例: "#/fdweb/資料/2026"）。各要素は encodeURIComponent で符号化する。
// ごみ箱は "#trash/<mount>"（パスの形と混ざらないよう、先頭を "/" にしない）。

/** パスの要素の組。根は []。規則はサーバの vpath と同じ（空・.・.. を含むものは null）。 */
export function splitPath(path) {
  if (typeof path !== "string" || !path.startsWith("/")) return null;
  if (path === "/") return [];
  const parts = path.slice(1).split("/");
  if (parts.some((p) => p === "" || p === "." || p === ".." || p.includes("\0"))) return null;
  return parts;
}

export function joinPath(parts) {
  return "/" + parts.join("/");
}

export function parentPath(path) {
  const parts = splitPath(path);
  if (!parts || parts.length === 0) return null;
  return joinPath(parts.slice(0, -1));
}

/** パスの最後の名前（根は ""）。 */
export function baseName(path) {
  const parts = splitPath(path);
  return parts && parts.length ? parts[parts.length - 1] : "";
}

function safeDecode(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return null; // 壊れた % 符号
  }
}

/** "#/fdweb/a/b" → {mount: "fdweb", path: "/a/b", trash: false}。"#trash/fdweb" はごみ箱。読めなければ null。 */
export function parseHash(hash) {
  const s = hash.startsWith("#") ? hash.slice(1) : hash;
  if (s.startsWith("trash/")) {
    const mount = safeDecode(s.slice("trash/".length));
    return mount && !mount.includes("/") ? { mount, path: "/", trash: true } : null;
  }
  if (!s.startsWith("/")) return null;
  const parts = s.slice(1).split("/").map(safeDecode);
  if (parts.includes(null)) return null;
  // 末尾の "/" は許す（"#/fdweb/" はマウントの根）
  if (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
  const [mount, ...rest] = parts;
  if (!mount) return null;
  const path = joinPath(rest);
  return splitPath(path) ? { mount, path, trash: false } : null;
}

export function formatHash(mount, path, trash = false) {
  if (trash) return `#trash/${encodeURIComponent(mount)}`;
  const parts = [mount, ...splitPath(path)];
  return "#/" + parts.map(encodeURIComponent).join("/");
}

/** アドレスバーに打ち込む形（"/fdweb/a/b"、符号化しない）。 */
export function formatAddress(mount, path) {
  return path === "/" ? `/${mount}` : `/${mount}${path}`;
}

/** アドレスバーの文字列を場所にする。読めなければ null。 */
export function parseAddress(text) {
  const s = text.trim();
  if (!s.startsWith("/")) return null;
  const parts = s.slice(1).split("/");
  if (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
  const [mount, ...rest] = parts;
  if (!mount) return null;
  const path = joinPath(rest);
  return splitPath(path) ? { mount, path, trash: false } : null;
}

/** 2 つの場所が同じか。 */
export function sameLocation(a, b) {
  return !!a && !!b && a.mount === b.mount && a.path === b.path && !!a.trash === !!b.trash;
}
