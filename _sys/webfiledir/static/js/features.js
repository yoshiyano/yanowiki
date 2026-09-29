// 画面の機能の ON/OFF。組み込む側が createApp / createShell の features で切り替える（index.html は ?disable=）。
// 止めた機能は、ボタン・右クリックメニューに出さず、キー操作・ドラッグ＆ドロップも受け付けない。
// **画面で出さないだけで、API は止めない。**API で止めるのは組み込む側の仕事（設定の readonly、
// mount_access。Wiki「組み込みかた > 画面の機能を止める」）。

/** 機能の名前 → 何を止めるか。書かなかった機能は ON。 */
export const FEATURES = {
  newFolder: "新しいフォルダ（ツールバー・右クリック・Ctrl+Shift+N）",
  newFile: "新しいテキスト ドキュメント（ツールバー・右クリック）",
  rename: "名前の変更（ツールバー・右クリック・F2）",
  cut: "切り取り（ツールバー・右クリック・Ctrl+X）",
  copy: "コピー（ツールバー・右クリック・Ctrl+C）",
  paste: "貼り付け（ツールバー・右クリック・Ctrl+V）",
  delete: "削除（ツールバー・右クリックの「削除」・Delete・ごみ箱へのドロップ）。ごみ箱が無いマウントでは、項目は出すが実行できるかは purge で決まる",
  purge: "完全に削除（右クリックの「完全に削除」・Shift+Delete、ごみ箱が無いマウントでの削除、ごみ箱の中での完全に削除・空にする）。ごみ箱が無いマウントでは右クリックに「完全に削除」を出さない",
  trash: "ごみ箱（ツリーのごみ箱・元に戻す。削除の直後に出る［元に戻す］も）",
  dnd: "ドラッグ＆ドロップ（この画面から運ぶことも、この画面へ落とすことも）",
  dual: "二画面（ツールバーの［二画面］。createShell だけが見る）",
};

/**
 * features（{名前: true | false}）から、ON の機能の集合を作る。
 * 知らない名前・true / false 以外の値は Error（書き間違いで止めたつもりの機能が出たままにならないように）。
 */
export function parseFeatures(features = {}) {
  if (features == null || typeof features !== "object" || Array.isArray(features)) {
    throw new Error("features は {機能の名前: true | false} の形にしてください");
  }
  const on = new Set(Object.keys(FEATURES));
  for (const [name, value] of Object.entries(features)) {
    if (!(name in FEATURES)) {
      throw new Error(`features に知らない機能があります: ${name}（書けるもの: ${Object.keys(FEATURES).join(", ")}）`);
    }
    if (typeof value !== "boolean") throw new Error(`features.${name} は true か false にしてください`);
    if (!value) on.delete(name);
  }
  return on;
}

/** URL のクエリ（location.search）の disable=名前,名前 を features の形にする（index.html が使う）。 */
export function featuresFromQuery(search) {
  const disable = new URLSearchParams(search).get("disable");
  const features = {};
  for (const name of (disable || "").split(",").map((x) => x.trim()).filter(Boolean)) features[name] = false;
  return features;
}
