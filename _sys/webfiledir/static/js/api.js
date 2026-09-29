// API の呼び出し。エラーの形を {code, message, path} にそろえる。
// URL は index.html からの相対にする（利用する側がリバースプロキシで別のパスの下に置いても動くように）。

const BASE = new URL("api/v1/", document.baseURI);

export class ApiError extends Error {
  constructor({ code, message, path = null }, status = 0) {
    super(message);
    this.code = code;
    this.path = path;
    this.status = status;
  }
}

async function request(endpoint, { params = {}, body = undefined } = {}) {
  const url = new URL(endpoint, BASE);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const init = { headers: { Accept: "application/json" } };
  if (body !== undefined) {
    // 変更系は POST + JSON + X-WebFileDir（サーバが CSRF を防ぐために確かめる）
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.headers["X-WebFileDir"] = "1";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError({ code: "network", message: "サーバにつながりません" });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    // JSON でない応答（プロキシのエラーページなど）
  }
  if (!res.ok) {
    const err = data && data.error;
    throw new ApiError(err || { code: "internal", message: `サーバがエラーを返しました（${res.status}）` },
      res.status);
  }
  return data;
}

const get = (endpoint, params) => request(endpoint, { params });

/** 自動更新の接続先（EventSource に渡す）。targets は [{mount, path} | {mount, trash: true}] */
export function eventsUrl(targets) {
  const url = new URL("events", BASE);
  url.searchParams.set("targets", JSON.stringify(targets));
  return url.href;
}
const post = (endpoint, body) => request(endpoint, { body });

export const api = {
  mounts: () => get("mounts"),
  list: (mount, path) => get("list", { mount, path }),
  tree: (mount, path) => get("tree", { mount, path }),
  stat: (mount, path) => get("stat", { mount, path }),

  mkdir: (mount, parent, name = "") => post("mkdir", { mount, parent, name }),
  touch: (mount, parent, name = "") => post("touch", { mount, parent, name }),
  rename: (mount, path, newName) => post("rename", { mount, path, newName }),
  /** 一括の結果 {results: [{src, ok, trashId?, error?}]} */
  delete: (mount, paths, permanent = false) => post("delete", { mount, paths, permanent }),

  /** 一括の結果 {results: [{src, ok, entry?, skipped?, unchanged?, error?}]}。同じマウントの中だけ */
  // destMount を mount と違うマウントにすると、マウントをまたぐ（Phase 4）
  copy: (mount, srcs, dest, onConflict = "error", destMount = mount) =>
    post("copy", { mount, srcs, dest, onConflict, destMount }),
  move: (mount, srcs, dest, onConflict = "error", destMount = mount) =>
    post("move", { mount, srcs, dest, onConflict, destMount }),

  /** ファイルを開く。画面がすること {action: "navigate" | "modal", url, target, data} */
  // method は開く経路の id（省けば既定）
  open: (mount, path, method = undefined) => post("open", { mount, path, method }),

  trash: (mount) => get("trash", { mount }),
  restore: (mount, ids, onConflict = "error") => post("trash/restore", { mount, ids, onConflict }),
  purge: (mount, ids) => post("trash/purge", { mount, ids }),
  emptyTrash: (mount) => post("trash/empty", { mount }),
};
