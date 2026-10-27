// アップロードするもの（手元のファイル・フォルダ）を集める。
// 集めたものは [{rel, kind, file?}] の並び。rel は置く先のフォルダからの相対の名前の並び（"写真/2026/a.jpg"）、
// kind は "file" | "dir"。フォルダは、その中身より先に並ぶ（BackEnd へ送る順。親を先に作る）。

/** 項目の並びを、直下の項目（rel に / が無いもの）ごとにまとめる: [{top, children}]。 */
export function groupUploads(files) {
  const groups = new Map();
  for (const f of files) {
    const top = f.rel.split("/")[0];
    if (!groups.has(top)) groups.set(top, { top: null, children: [] });
    const g = groups.get(top);
    if (f.rel === top) g.top = f;
    else g.children.push(f);
  }
  // 中身だけがある（フォルダの項目が無い）ときは、フォルダの項目を足す
  return [...groups.entries()].map(([name, g]) => ({ top: g.top || { rel: name, kind: "dir" }, children: g.children }));
}

/** ファイルを選ぶ欄（<input type="file">）の FileList から。フォルダを選んだときは webkitRelativePath がある。 */
export function filesFromInput(fileList) {
  const out = [];
  const dirs = new Set();
  for (const file of fileList) {
    const rel = file.webkitRelativePath || file.name;
    const parts = rel.split("/");
    for (let i = 1; i < parts.length; i++) {
      const dir = parts.slice(0, i).join("/");
      if (!dirs.has(dir)) {
        dirs.add(dir);
        out.push({ rel: dir, kind: "dir" });
      }
    }
    out.push({ rel, kind: "file", file });
  }
  return out;
}

function readAll(reader) {
  // readEntries は一度に全部を返さないことがある（Chrome は 100 個ずつ）。空が返るまで読む
  return new Promise((resolve, reject) => {
    const all = [];
    const next = () => reader.readEntries((batch) => {
      if (!batch.length) resolve(all);
      else {
        all.push(...batch);
        next();
      }
    }, reject);
    next();
  });
}

async function walk(entry, rel, out) {
  if (entry.isDirectory) {
    out.push({ rel, kind: "dir" });
    for (const child of await readAll(entry.createReader())) await walk(child, `${rel}/${child.name}`, out);
  } else {
    const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
    out.push({ rel, kind: "file", file });
  }
}

/**
 * ドロップ（DataTransfer）から。folders が false ならフォルダは集めず、名前を skipped に返す。{files, skipped}。
 * **items から取り出すのは、drop の事象の中で await より先に行う**（あとでは DataTransfer が空になる）。
 */
export function filesFromDrop(dataTransfer, { folders = true } = {}) {
  const items = [...(dataTransfer.items || [])].filter((i) => i.kind === "file");
  const picked = items.map((i) => ({ entry: i.webkitGetAsEntry ? i.webkitGetAsEntry() : null, file: i.getAsFile() }));
  return (async () => {
    const files = [];
    const skipped = [];
    for (const { entry, file } of picked) {
      if (entry && entry.isDirectory) {
        if (folders) await walk(entry, entry.name, files);
        else skipped.push(entry.name);
      } else if (file) {
        files.push({ rel: file.name, kind: "file", file });
      }
    }
    return { files, skipped };
  })();
}

/** DataTransfer がほかのアプリのファイルを運んでいるか。 */
export const carriesFiles = (dataTransfer) => [...(dataTransfer.types || [])].includes("Files");
