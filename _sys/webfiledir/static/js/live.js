// 自動更新: 画面に出ているフォルダ（カレントフォルダ・ツリーで開いている段・ごみ箱）が変わったら読み直す。
// 問い合わせを繰り返す（polling）のではなく、サーバが OS からの知らせ（inotify）を受けて
// Server-Sent Events で送ってくる（GET /api/v1/events）。
// 受けた知らせは store の externalChange に入れ、一覧（main.js）とツリー（tree.js）がそれぞれ読み直す。
//
// 開いたままの接続を増やさないため、サーバへの接続はブラウザ 1 つ（同じ接続先）につき 1 本にする。
// - ページの中の画面（二画面なら 2 つ）は、1 つの LiveHub を共有する
// - 同じ接続先を開いているタブ同士は、Web Locks で代表（leader）を 1 つ決め、代表だけがサーバと繋ぐ。
//   ほかのタブは見張ってほしい対象を BroadcastChannel で代表へ伝え、代表は受けた知らせを全タブへ流す
// - 見えなくなって HIDDEN_DELAY ミリ秒たったタブは、見張りから外れる（代表なら代表を降りる）。
//   見えるタブが無くなれば接続も閉じる。見えるようになったら加わり直し、そのあいだの変化は読み直して拾う
// Web Locks は安全なオリジン（https・localhost）でしか使えない。使えないときは、ページごとに 1 本で繋ぐ
// （見えなくなったら切るのは同じ）。

import { eventsUrl } from "./api.js";

const MAX_TARGETS = 256; // サーバの上限と同じ
const HIDDEN_DELAY = 30000; // 見えなくなってから見張りを外れるまで（タブを少し切り替えただけで繋ぎ直さない）
const CONNECT_DELAY = 150; // ツリーを続けて開いたときなどに繋ぎ直しを重ねない

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

/** いくつかの対象の列を 1 つにまとめる。上限を超えたら、どの列も先頭（今いる場所）から先に残す。 */
function mergeTargets(lists) {
  const seen = new Set();
  const out = [];
  for (let i = 0; out.length < MAX_TARGETS && lists.some((l) => i < l.length); i++) {
    for (const l of lists) {
      if (i >= l.length) continue;
      const k = JSON.stringify(l[i]);
      if (!seen.has(k) && out.length < MAX_TARGETS) {
        seen.add(k);
        out.push(l[i]);
      }
    }
  }
  return out;
}

/**
 * 接続先 1 つ分の見張り。ページに 1 つ（liveHub() で得る）。
 * 状態 status: "on"（見張っている）/ "off"（繋いでいない・繋ぎ直し中）/ "paused"（見えないので外れている）
 * / "unavailable"（サーバの環境で見張れない）。
 */
class LiveHub {
  constructor(base) {
    this.key = `webfiledir-live:${base}`;
    this.tab = Math.random().toString(36).slice(2) + Date.now().toString(36);
    this.hiddenDelay = HIDDEN_DELAY;
    this.clients = new Set(); // {targets(), notify(change), status(status, watching)}
    this.channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(this.key) : null;
    this.shared = !!(this.channel && typeof navigator !== "undefined" && navigator.locks);
    if (!this.shared && this.channel) {
      // 代表を決められないなら、どのタブも自分の分だけで繋ぐ（ほかのタブの対象を集めない）
      this.channel.close();
      this.channel = null;
    }
    this.active = false; // 見張りに加わっている（見えている）
    this.stopped = false; // サーバが "unavailable" と答えた。繋ぎ直さない
    this.status = "off";
    this.watching = [];
    this.sawLeader = false; // ほかのタブの代表から知らせを受けたことがある（代表を引き継いだら読み直す）
    // 代表のときだけ使う
    this.leader = false;
    this.peers = new Map(); // tab → そのタブの対象
    this.es = { active: null, current: null, url: null, lost: false, resync: false };
    this.connectTimer = null;
    this.hideTimer = null;
    this.lockAbort = null;
    this.releaseLock = null;

    if (this.channel) this.channel.onmessage = (e) => this.onMessage(e.data || {});
    this.onVisibility = () => this.visibilityChanged();
    document.addEventListener("visibilitychange", this.onVisibility);
    this.onPageHide = () => this.leave();
    window.addEventListener("pagehide", this.onPageHide);
    // 戻る・進むのキャッシュから戻ったとき
    this.onPageShow = (e) => {
      if (e.persisted && this.visible && !this.active && !this.stopped && this.clients.size) this.activate(true);
    };
    window.addEventListener("pageshow", this.onPageShow);
  }

  get visible() {
    return document.visibilityState !== "hidden";
  }

  add(client) {
    this.clients.add(client);
    client.status(this.status, this.watching);
    if (!this.active && !this.stopped && this.visible) this.activate(false);
    else if (!this.active && !this.stopped) this.setStatus("paused", []); // 裏で開かれた
    else this.announce();
  }

  remove(client) {
    this.clients.delete(client);
    if (this.clients.size === 0) this.leave();
    else this.announce();
  }

  /** このタブの画面が見張ってほしい対象（画面が場所を変えたら announce() で伝え直す）。 */
  ownTargets() {
    return this.active ? mergeTargets([...this.clients].map((c) => c.targets())) : [];
  }

  announce() {
    if (this.stopped) return;
    if (this.leader) this.scheduleConnect();
    else this.post({ type: "targets", tab: this.tab, targets: this.ownTargets() });
  }

  post(msg) {
    if (this.channel) this.channel.postMessage(msg);
  }

  setStatus(status, watching = this.watching) {
    this.status = status;
    this.watching = watching;
    for (const c of this.clients) c.status(status, watching);
  }

  deliver(change) {
    if (!this.active) return; // 外れているあいだの変化は、加わり直すときにまとめて読み直す
    for (const c of this.clients) c.notify(change);
  }

  // --- 見える・見えない ---

  visibilityChanged() {
    clearTimeout(this.hideTimer);
    this.hideTimer = null;
    if (this.visible) {
      if (!this.active && !this.stopped && this.clients.size) this.activate(true);
    } else if (this.active) {
      this.hideTimer = setTimeout(() => this.deactivate(), this.hiddenDelay);
    }
  }

  activate(resync) {
    this.active = true;
    if (this.status === "paused") this.setStatus("off", []);
    this.announce();
    if (this.shared) this.requestLeadership();
    else this.becomeLeader();
    if (resync) this.deliver({ all: true }); // 外れていたあいだの変化を拾う
  }

  deactivate() {
    this.active = false;
    this.post({ type: "targets", tab: this.tab, targets: [] });
    this.stopLeadership();
    if (!this.stopped) this.setStatus("paused", []);
  }

  /** ページを離れる・画面をすべて片付けた。 */
  leave() {
    if (this.active) this.deactivate();
    clearTimeout(this.hideTimer);
  }

  // --- 代表を決める ---

  requestLeadership() {
    if (this.lockAbort || this.leader) return;
    const abort = new AbortController();
    this.lockAbort = abort;
    navigator.locks.request(this.key, { signal: abort.signal }, () => new Promise((release) => {
      this.releaseLock = release;
      this.becomeLeader();
    })).catch(() => {}); // 取りやめた（AbortError）
  }

  stopLeadership() {
    if (this.lockAbort) this.lockAbort.abort();
    this.lockAbort = null;
    if (this.leader) this.resign();
    if (this.releaseLock) this.releaseLock();
    this.releaseLock = null;
  }

  becomeLeader() {
    this.leader = true;
    this.peers.clear();
    // 前の代表から引き継いだなら、代表がいなかったあいだの変化を、繋いだあとで全タブに読み直させる
    this.es.resync = this.sawLeader;
    this.post({ type: "hello", tab: this.tab }); // ほかのタブに対象を伝え直してもらう
    this.scheduleConnect();
  }

  resign() {
    this.leader = false;
    this.peers.clear();
    clearTimeout(this.connectTimer);
    this.closeAll();
    this.post({ type: "status", status: "off", watching: [] });
  }

  onMessage(msg) {
    switch (msg.type) {
      case "hello":
        if (this.active) this.announce();
        break;
      case "targets":
        if (!this.leader) break;
        if (msg.targets && msg.targets.length) this.peers.set(msg.tab, msg.targets);
        else this.peers.delete(msg.tab);
        this.scheduleConnect();
        break;
      case "change":
        this.sawLeader = true;
        this.deliver(msg.change);
        break;
      case "status":
        this.sawLeader = true;
        if (this.active && !this.leader) this.setStatus(msg.status, msg.watching);
        break;
      case "unavailable":
        this.unavailable();
        break;
    }
  }

  // --- 代表: サーバと繋ぐ ---

  scheduleConnect() {
    clearTimeout(this.connectTimer);
    this.connectTimer = setTimeout(() => this.connect(), CONNECT_DELAY);
  }

  closeAll() {
    const es = this.es;
    for (const x of new Set([es.active, es.current])) if (x) x.close();
    es.active = es.current = es.url = null;
    if (this.status === "on") this.setStatus("off", []);
  }

  connect() {
    if (!this.leader || this.stopped) return;
    const targets = mergeTargets([this.ownTargets(), ...this.peers.values()]);
    const url = targets.length ? eventsUrl(targets) : null;
    const es = this.es;
    if (url === es.url) {
      // 対象は同じ（あとから加わったタブの対象を、もう見張っていた）。そのタブにも今の状態を伝える
      if (this.status === "on") this.post({ type: "status", status: "on", watching: this.watching });
      return;
    }
    if (!url) {
      this.closeAll();
      this.post({ type: "status", status: "off", watching: [] });
      return;
    }
    es.url = url;
    if (es.current && es.current !== es.active) es.current.close();
    const source = new EventSource(url);
    es.current = source;
    source.addEventListener("ready", (e) => {
      if (source !== es.current) return;
      // 新しい接続の準備ができてから古い接続を閉じる（見張る対象を変えるあいだの変化を取りこぼさない）
      if (es.active && es.active !== source) es.active.close();
      es.active = source;
      const watching = JSON.parse(e.data).watching;
      this.setStatus("on", watching);
      this.post({ type: "status", status: "on", watching });
      if (es.lost || es.resync) {
        es.lost = es.resync = false;
        this.broadcast({ all: true });
      }
    });
    source.addEventListener("change", (e) => {
      if (source === es.active || source === es.current) this.broadcast(JSON.parse(e.data));
    });
    source.addEventListener("unavailable", () => {
      this.post({ type: "unavailable" });
      this.unavailable();
    });
    source.onerror = () => {
      // ブラウザが retry の間隔で自動で繋ぎ直す。繋がったら "ready" でまとめて読み直す
      if (source === es.active || source === es.current) {
        es.lost = true;
        this.setStatus("off", []);
        this.post({ type: "status", status: "off", watching: [] });
      }
    };
  }

  broadcast(change) {
    this.deliver(change);
    this.post({ type: "change", change });
  }

  unavailable() {
    // サーバの環境で見張れない。繋ぎ直しを繰り返さない（F5 で読み直す）
    this.stopped = true;
    this.stopLeadership();
    this.setStatus("unavailable", []);
  }
}

const hubs = new Map();

/** このページの、接続先ごとの見張り（テストが hiddenDelay を縮めるのにも使う）。 */
export function liveHub() {
  const base = eventsUrl([]).split("?")[0];
  if (!hubs.has(base)) hubs.set(base, new LiveHub(base));
  return hubs.get(base);
}

/**
 * 画面 1 つ分の自動更新を始める。root の data-live に状態（LiveHub の status）を出す。
 * data-live-watching は、今の接続が見張っている対象（サーバが見張れたもの。ほかのタブの分も含む）の JSON。
 * 戻り値は、やめる関数（二画面モードを閉じて、その画面を片付けるとき）。
 */
export function setupLiveUpdate(store, root) {
  if (typeof EventSource === "undefined") return () => {};
  const hub = liveHub();
  let seq = 0;
  let timer = null;
  const client = {
    targets: () => liveTargets(store.get()),
    notify: (change) => store.set({ externalChange: { seq: ++seq, ...change } }),
    status: (status, watching) => {
      root.dataset.live = status;
      root.dataset.liveWatching = JSON.stringify(watching);
    },
  };
  const unsubscribe = store.subscribe((s, changed) => {
    if (changed.has("location") || changed.has("treeOpened")) {
      clearTimeout(timer);
      timer = setTimeout(() => hub.announce(), CONNECT_DELAY);
    }
  });
  hub.add(client);

  return function stop() {
    clearTimeout(timer);
    unsubscribe();
    hub.remove(client);
  };
}
