// 自動更新: 画面に出ているフォルダ（カレントフォルダ・ツリーで開いている段・ごみ箱）が変わったら読み直す。
// 問い合わせを繰り返す（polling）のではなく、サーバが OS からの知らせ（inotify）を受けて
// Server-Sent Events で送ってくる（GET /api/v1/events）。
// 受けた知らせは store の externalChange に入れ、一覧（main.js）とツリー（tree.js）がそれぞれ読み直す。

import { eventsUrl } from "./api.js";

const MAX_TARGETS = 256; // サーバの上限と同じ

/** 見張る対象 [{mount, path} | {mount, trash: true}]。 */
export function liveTargets(s) {
  const seen = new Set();
  const list = [];
  const add = (t) => {
    const k = JSON.stringify(t);
    if (!seen.has(k)) {
      seen.add(k);
      list.push(t);
    }
  };
  const loc = s.location;
  if (loc) add(loc.trash ? { mount: loc.mount, trash: true } : { mount: loc.mount, path: loc.path });
  for (const k of s.treeOpened ? s.treeOpened.split("\0") : []) {
    const [mount, path] = k.split("\n");
    add({ mount, path });
  }
  return list.slice(0, MAX_TARGETS);
}

/**
 * root の data-live に状態を出す（"on" / "off" / "unavailable"）。data-live-watching は
 * 今の接続が見張っている対象（サーバが見張れたものだけ）の JSON。
 */
export function setupLiveUpdate(store, root) {
  if (typeof EventSource === "undefined") return () => {};
  let active = null;   // 知らせを受けている接続
  let current = null;  // いちばん新しく開いた接続（準備ができたら active になる）
  let currentUrl = null;
  let lost = false;    // 接続が切れていたか（繋ぎ直したら、そのあいだの変化を拾うため読み直す）
  let seq = 0;
  let timer = null;
  let stopped = false;

  const notify = (change) => store.set({ externalChange: { seq: ++seq, ...change } });

  function connect() {
    if (stopped) return;
    const targets = liveTargets(store.get());
    const url = targets.length ? eventsUrl(targets) : null;
    if (url === currentUrl) return;
    currentUrl = url;
    if (current && current !== active) current.close();
    current = null;
    if (!url) return;
    const es = new EventSource(url);
    current = es;
    es.addEventListener("ready", (e) => {
      if (es !== current) return;
      // 新しい接続の準備ができてから古い接続を閉じる（見張る対象を変えるあいだの変化を取りこぼさない）
      if (active && active !== es) active.close();
      active = es;
      root.dataset.live = "on";
      root.dataset.liveWatching = JSON.stringify(JSON.parse(e.data).watching);
      if (lost) {
        lost = false;
        notify({ all: true });
      }
    });
    es.addEventListener("change", (e) => {
      if (es === active || es === current) notify(JSON.parse(e.data));
    });
    es.addEventListener("unavailable", () => {
      // サーバの環境で見張れない。繋ぎ直しを繰り返さない（F5 で読み直す）
      stopped = true;
      es.close();
      root.dataset.live = "unavailable";
    });
    es.onerror = () => {
      // ブラウザが retry の間隔で自動で繋ぎ直す。繋がったら "ready" でまとめて読み直す
      if (es === active || es === current) {
        root.dataset.live = "off";
        lost = true;
      }
    };
  }

  const unsubscribe = store.subscribe((s, changed) => {
    if (changed.has("location") || changed.has("treeOpened")) {
      clearTimeout(timer);
      timer = setTimeout(connect, 150); // ツリーを続けて開いたときなどに繋ぎ直しを重ねない
    }
  });

  /** やめる（二画面モードを閉じて、その画面を片付けるとき）。接続を閉じ、繋ぎ直さない。 */
  return function stop() {
    stopped = true;
    clearTimeout(timer);
    unsubscribe();
    for (const es of new Set([active, current])) if (es) es.close();
  };
}
