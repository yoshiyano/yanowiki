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

  /**
   * コマンドを 1 つ行う（POST commands/<id>。Wiki「API 設計 > コマンド API」）。変更の操作・開く・独自のコマンドは
   * すべてここを通る。応答は {result?, results?, effects?}
   */
  command: (id, body) => post(`commands/${encodeURIComponent(id)}`, body),

  /** ジョブ（BackEnd が裏で行っているコマンド）の進み具合。終わったら result か error を持つ。 */
  job: (id) => get(`jobs/${encodeURIComponent(id)}`),
  /** ジョブを中止する（項目と項目の間で止まる）。 */
  cancelJob: (id) => post(`jobs/${encodeURIComponent(id)}/cancel`, {}),

  trash: (mount) => get("trash", { mount }),

  /** ファイルの中身（GET raw/<マウント>/<パス>。名前は 1 段ずつパーセント符号化）を ArrayBuffer で。 */
  async readFile(mount, path) {
    const segments = [mount, ...path.split("/").filter(Boolean)].map(encodeURIComponent).join("/");
    let res;
    try {
      res = await fetch(new URL(`raw/${segments}`, BASE), { cache: "no-store" });
    } catch {
      throw new ApiError({ code: "network", message: "サーバにつながりません" });
    }
    if (!res.ok) {
      let data = null;
      try {
        data = await res.json();
      } catch {
        // JSON でない応答
      }
      throw new ApiError((data && data.error) || { code: "internal", message: `サーバがエラーを返しました（${res.status}）` },
        res.status);
    }
    return res.arrayBuffer();
  },

  /**
   * ファイルを送るコマンド（宣言の request が upload）で、手元のファイル 1 つかフォルダ 1 つを置く
   * （POST commands/<id>/upload。Wiki「API 設計 > アップロード」）。params は {mount, dest, path, kind, mtime?,
   * onConflict?, check?, size?}、body は File（フォルダと確かめるだけのときは null）。onProgress(送ったバイト数)。
   * 送った量を知るため fetch ではなく XMLHttpRequest を使う。{promise, abort}。abort すると code "cancelled" で失敗する。
   */
  upload(id, params, body, onProgress = () => {}) {
    const url = new URL(`commands/${encodeURIComponent(id)}/upload`, BASE);
    for (const [k, v] of Object.entries(params)) if (v != null) url.searchParams.set(k, v);
    const xhr = new XMLHttpRequest();
    const promise = new Promise((resolve, reject) => {
      xhr.open("POST", url);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.setRequestHeader("X-WebFileDir", "1");
      xhr.upload.onprogress = (e) => onProgress(e.loaded);
      xhr.onload = () => {
        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          // JSON でない応答（プロキシの「大きすぎる」のページなど）
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else if (data && data.error) reject(new ApiError(data.error, xhr.status));
        else if (xhr.status === 413) {
          reject(new ApiError({ code: "too_large", message: "ファイルが大きすぎます（サーバの手前で断られました）" }, 413));
        } else reject(new ApiError({ code: "internal", message: `サーバがエラーを返しました（${xhr.status}）` }, xhr.status));
      };
      xhr.onerror = () => reject(new ApiError({ code: "network", message: "サーバにつながりません" }));
      xhr.onabort = () => reject(new ApiError({ code: "cancelled", message: "中止しました" }));
      xhr.send(body || new Blob([]));
    });
    return { promise, abort: () => xhr.abort() };
  },
};
