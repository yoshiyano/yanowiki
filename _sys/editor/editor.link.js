/* editor.link.js — 編集画面の本文を、手元のエディタと同期する（エディタ連動の編集）。
 *
 * 仕組みとプロトコルは技術資料「エディタ連動の仕組み」（Tech/EditorSync）。使いかたは
 * 「エディタ連動の編集」（PageEdit/EditorSyncGuide）。エディタのプラグインもそこから配る。
 *
 * Wiki設計者の決定（2026-10-02〜10-06）: 一度つないだら切断するまで続け、編集画面を開くたびに
 * つなぐ。つながるまで再試行し続ける。エディタ側で閉じたら、その画面ではつなぎ直さない。
 * 変更は差分で送り、変更前後のハッシュを添え、合わなければ全文を求める。正は最後に更新が
 * あったほう。時刻は交わして仮想的にそろえる。ページから直接つなぐ（受け渡しの拡張機能は予備）。
 *
 * 1つの本文の欄をつなぐ中核は `WikiEditorLink.attach(o)`。編集画面（このファイルの末尾）と、
 * セクション編集（テーマの common.js。開いたときにこのファイルを読み込む。Wiki設計者の指示、
 * 2026-10-27）の両方が使う。
 *
 * ## 通信の部分（transport）
 *
 * `open(info, handlers)` で1本つなぎ、`{send, close}` を返す。handlers は onOpen() /
 * onMessage(obj) / onClose(wasOpen)。onClose の wasOpen が偽なら「つながらなかった」（再試行する）。
 * - 直接（directTransport）: `ws://localhost:<ポート番号>/` へつなぐ
 * - 拡張機能（relayTransport）: 拡張機能が `<html data-wiki-editor-relay>` を付けていれば、
 *   window.postMessage で拡張機能に頼む（公開サイトの http の Wiki では、Chrome がページから
 *   localhost への通信を断るため）
 */
(function () {
  "use strict";

  if (window.WikiEditorLink) return;   // セクション編集が後から読み込むので、2度目は何もしない

  var ON_KEY = "wikiEditorLink";              // "1" ならオン（ブラウザが覚える）
  var PORT_KEY = "wikiEditorLinkPort";
  var SESSION_KEY = "wikiEditorLinkSession";  // タブのセッション ID（sessionStorage）
  var BACKUP_KEY = "wikiEditorLinkBackup";    // 負けた側の本文の控え（ブラウザ）
  var HIDDEN_KEY = "wikiEditorLinkHidden";    // このタブで直前までつながっていたか（sessionStorage）
  var DEFAULT_PORT = 4100;
  var RETRY_STEPS = [2000, 4000, 8000];       // そのあとは RETRY_MAX ごと（期限なし）
  var RETRY_MAX = 10000;
  var SEND_DEBOUNCE = 150;
  var CURSOR_DEBOUNCE = 200;
  var PING_INTERVAL = 20000;

  function load(store, key, fallback) {
    try { var v = store.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; }
  }
  function save(store, key, value) {
    try { store.setItem(key, value); } catch (e) { /* この画面では効く */ }
  }
  function port() {
    var n = parseInt(load(window.localStorage, PORT_KEY, ""), 10);
    return (n > 0 && n < 65536) ? n : DEFAULT_PORT;
  }
  /* ---- SHA-256（ページが http でも使えるよう、crypto.subtle に頼らない） ---- */

  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];

  function sha256(text) {
    var bytes = new TextEncoder().encode(text);
    var n = bytes.length, total = ((n + 9 + 63) >> 6) << 6;
    var buf = new Uint8Array(total);
    buf.set(bytes);
    buf[n] = 0x80;
    var bits = n * 8;
    for (var i = 0; i < 8; i++) buf[total - 1 - i] = Math.floor(bits / Math.pow(2, 8 * i)) & 0xff;
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var w = new Int32Array(64);
    for (var off = 0; off < total; off += 64) {
      for (var j = 0; j < 16; j++) {
        w[j] = (buf[off + 4 * j] << 24) | (buf[off + 4 * j + 1] << 16) | (buf[off + 4 * j + 2] << 8) | buf[off + 4 * j + 3];
      }
      for (j = 16; j < 64; j++) {
        var x = w[j - 15], y = w[j - 2];
        var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        var s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        w[j] = (w[j - 16] + s0 + w[j - 7] + s1) | 0;
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
      for (j = 0; j < 64; j++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var t1 = (hh + S1 + ((e & f) ^ (~e & g)) + K[j] + w[j]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
      h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + hh) | 0;
    }
    return h.map(function (v) { return ("00000000" + (v >>> 0).toString(16)).slice(-8); }).join("");
  }

  /* ---- 送る中身 ---- */

  function normalize(text) { return text.replace(/\r\n?/g, "\n"); }

  // 前後で共通する部分を除いた1か所を、差分とする（位置は UTF-16 の単位）
  function diff(before, after) {
    var start = 0, max = Math.min(before.length, after.length);
    while (start < max && before.charCodeAt(start) === after.charCodeAt(start)) start++;
    var endB = before.length, endA = after.length;
    while (endB > start && endA > start && before.charCodeAt(endB - 1) === after.charCodeAt(endA - 1)) { endB--; endA--; }
    // サロゲートペアを割らない
    if (start > 0 && isHigh(before.charCodeAt(start - 1))) start--;
    if (endB < before.length && isLow(before.charCodeAt(endB))) { endB++; endA++; }
    return { start: start, end: endB, text: after.slice(start, endA) };
  }
  function isHigh(c) { return c >= 0xd800 && c <= 0xdbff; }
  function isLow(c) { return c >= 0xdc00 && c <= 0xdfff; }

  function applyChanges(text, changes) {
    for (var i = 0; i < changes.length; i++) {
      var ch = changes[i];
      var s = Math.max(0, Math.min(text.length, ch.start | 0));
      var e = Math.max(s, Math.min(text.length, ch.end | 0));
      text = text.slice(0, s) + String(ch.text || "") + text.slice(e);
    }
    return text;
  }

  /* ---- 通信の部分 ---- */

  function directTransport(info, handlers) {
    var ws, opened = false, closed = false;
    try { ws = new WebSocket("ws://localhost:" + info.port + "/"); }
    catch (e) {
      window.setTimeout(function () { handlers.onClose(false); }, 0);
      return { send: function () {}, close: function () {} };
    }
    ws.onopen = function () { opened = true; handlers.onOpen(); };
    ws.onmessage = function (ev) {
      var obj;
      try { obj = JSON.parse(ev.data); } catch (e) { return; }
      if (obj && typeof obj.type === "string") handlers.onMessage(obj);
    };
    ws.onclose = function () { if (!closed) { closed = true; handlers.onClose(opened); } };
    ws.onerror = function () { /* onclose が続けて来る */ };
    return {
      send: function (obj) { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj)); },
      close: function () { closed = true; try { ws.close(); } catch (e) { /* もう閉じている */ } }
    };
  }

  // 拡張機能との受け渡し（拡張機能の側と同じ形）:
  //   ページ → 拡張機能  {wikiEditorRelay: "open", id, port} / {.."send", id, data} / {.."close", id}
  //   拡張機能 → ページ  {wikiEditorRelay: "opened"|"message"|"closed", id, data?, wasOpen?}
  function relayTransport(info, handlers) {
    var id = "l" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    var closed = false;
    function onWindowMessage(ev) {
      var m = ev.data;
      if (ev.source !== window || !m || m.id !== id || m.from !== "relay") return;
      if (m.wikiEditorRelay === "opened") handlers.onOpen();
      else if (m.wikiEditorRelay === "message" && m.data && typeof m.data.type === "string") handlers.onMessage(m.data);
      else if (m.wikiEditorRelay === "closed" && !closed) {
        closed = true;
        window.removeEventListener("message", onWindowMessage);
        handlers.onClose(!!m.wasOpen);
      }
    }
    window.addEventListener("message", onWindowMessage);
    function post(m) { m.id = id; m.from = "page"; window.postMessage(m, location.origin); }
    post({ wikiEditorRelay: "open", port: info.port });
    return {
      send: function (obj) { post({ wikiEditorRelay: "send", data: obj }); },
      close: function () {
        closed = true;
        window.removeEventListener("message", onWindowMessage);
        post({ wikiEditorRelay: "close" });
      }
    };
  }

  function hasRelay() { return document.documentElement.hasAttribute("data-wiki-editor-relay"); }

  function newSessionId() { return "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10); }

  /* ---- 1つの本文の欄をエディタとつなぐ（attach） ----
   * 編集画面とセクション編集の両方が使う。o で受け取るもの:
   *   source       本文の欄（textarea）。値が基準
   *   box          つないでいるあいだ data-editor-link-hidden を付ける要素（見た目は CSS が決める）
   *   container    ボタンと状態の表示を置く要素
   *   page()       hello で送るページの情報 {path, title, markup, url}
   *   attachments() 添付ファイルの一覧（無ければ空）
   *   session      セッション ID（省略すると、つなぐ欄ごとに新しく作る）
   *   onSave()     エディタから保存が届いたとき
   *   leaveType()  ページを離れるときに送るもの（"reload" か "bye"。省略すると "bye"）
   *   resumeKey    再読み込みしても隠したまま始めるための sessionStorage のキー（編集画面だけ）
   *   onCaret()    隠しているあいだにカーソルが動いたとき（プレビューを合わせる。省略可）
   * 返すもの: {detach(sayBye)}。欄を片付けるときに呼ぶ（オン・オフの記録は変えない） */
  function attach(o) {
    var source = o.source;
    var session = o.session || newSessionId();
    var state = "off";
    var link = null;
    var retryTimer = null, retryCount = 0, pingTimer = null, sendTimer = null, cursorTimer = null;
    var shadow = null;          // 最後にエディタとそろえた本文
    // 本文を最後に変えた時刻（この画面の時計）。開いた時刻から始める。保存で再読み込みしたとき、
    // 保存した結果（&date; の展開などでサーバーが変えたもの）を正とするため
    var modified = Date.now();
    var offset = 0;             // エディタの時計 − この画面の時計（ミリ秒）
    var sentState = false;      // 食い違いの解決で、自分の state をもう送ったか
    var editorName = "";
    var lastSentSel = "";
    var detached = false;

    var ui = buildUi(o.container);

    /* ---- 本文の欄を隠す ----
     * つながっているあいだは、本文の欄を隠してプレビューを広げる（Wiki設計者の指示、2026-10-08。
     * セクション編集も同じ、2026-10-27）。待っているあいだ・エディタ側で閉じたとき・切断したときは
     * 出す（エディタが起動していないと書けなくなるため）。編集画面は、保存などで再読み込みするたびに
     * 出たり消えたりしないよう、このタブで直前までつながっていたら、隠したまま始める。つながらなかったら
     * 出す（クロコの実装例） */
    var resumeHidden = !!o.resumeKey && load(window.sessionStorage, o.resumeKey, "") === "1" &&
                       load(window.localStorage, ON_KEY, "0") === "1";
    function forgetHidden() {
      resumeHidden = false;
      if (!o.resumeKey) return;
      try { window.sessionStorage.removeItem(o.resumeKey); } catch (e) { /* 覚えられなくてもよい */ }
    }
    function applyHidden(next) {
      if (next === "connected") {
        resumeHidden = true;
        if (o.resumeKey) save(window.sessionStorage, o.resumeKey, "1");
      }
      var hide = next === "connected" || (resumeHidden && (next === "waiting" || next === "off"));
      if (o.box.hasAttribute("data-editor-link-hidden") === hide) return;
      if (hide) {
        o.box.setAttribute("data-editor-link-hidden", "");
        revealCaret();
      } else {
        o.box.removeAttribute("data-editor-link-hidden");
        scrollCaretIntoView();
      }
    }
    function sourceHidden() { return o.box.hasAttribute("data-editor-link-hidden"); }
    function revealCaret() { if (o.onCaret) o.onCaret(); }

    function setState(next, note) {
      state = next;
      applyHidden(next);
      ui.root.dataset.state = next;
      ui.toggle.textContent = next === "off" ? "外部エディタにつなぐ" : "切断";
      var text = {
        off: "",
        waiting: "エディタを待っています…",
        connected: "エディタとつながっています" + (editorName ? "（" + editorName + "）" : ""),
        closed: "エディタ側で閉じました"
      }[next];
      ui.status.textContent = note || text;
      ui.reopen.hidden = next !== "closed";
    }

    function send(obj) {
      if (!link) return;
      obj.t = Date.now();
      link.send(obj);
    }

    function connect() {
      if (detached) return;
      window.clearTimeout(retryTimer);
      if (link) { link.close(); link = null; }
      var current = (hasRelay() ? relayTransport : directTransport)({ port: port() }, {
        onOpen: function () {
          if (link !== current) return;
          retryCount = 0;
          sentState = false;
          shadow = normalize(source.value);
          send({ type: "hello", v: 1, session: session, page: o.page(),
                 text: shadow, hash: sha256(shadow), modified: modified,
                 attachments: o.attachments ? o.attachments() : [] });
        },
        onMessage: function (obj) { if (link === current) receive(obj); },
        onClose: function () {
          if (link !== current) return;
          link = null;
          forgetHidden();   // つながらなかった・切れた。本文の欄を出す
          window.clearInterval(pingTimer);
          if (state === "off" || state === "closed" || detached) return;
          scheduleRetry();   // つながらなかった・切れた（エディタが止まった）。つながるまで待つ
        }
      });
      link = current;
      if (state !== "connected") setState("waiting");
    }

    function scheduleRetry() {
      setState("waiting");
      var wait = retryCount < RETRY_STEPS.length ? RETRY_STEPS[retryCount] : RETRY_MAX;
      retryCount++;
      retryTimer = window.setTimeout(connect, wait);
    }

    function disconnect(sayBye) {
      forgetHidden();
      window.clearTimeout(retryTimer);
      window.clearTimeout(sendTimer);
      window.clearInterval(pingTimer);
      if (link) {
        if (sayBye) send({ type: "bye" });
        var l = link; link = null; l.close();
      }
      setState("off");
    }

    /* ---- 受け取ったもの ---- */

    function receive(m) {
      switch (m.type) {
        case "welcome":
          editorName = String(m.editor || "");
          setState("connected");
          ping();
          window.clearInterval(pingTimer);
          pingTimer = window.setInterval(ping, PING_INTERVAL);
          if (m.hash && m.hash !== sha256(shadow)) resolve(m);
          return;
        case "pong":
          var t3 = Date.now();
          offset = Math.round(((m.t1 - m.t0) + (m.t2 - t3)) / 2);
          send({ type: "clock", offset: offset });
          return;
        case "edit":
          flushLocal();
          if (m.from !== sha256(shadow)) { sendState(); return; }
          var next = applyChanges(shadow, m.changes || []);
          if (sha256(next) !== m.to) { sendState(); return; }
          setText(next);
          modified = toLocal(m.modified);
          return;
        case "state":
          resolve(m);
          return;
        case "full":
          flushLocal();
          var text = normalize(String(m.text || ""));
          if (text !== normalize(source.value)) keepBackup(source.value);
          setText(text);
          modified = toLocal(m.modified);
          sentState = false;
          return;
        case "cursor":
          setCursor(m.start, m.end);
          return;
        case "save":
          flushLocal();
          if (o.onSave) o.onSave();
          return;
        case "closed":
          forgetHidden();
          if (link) { var l = link; link = null; l.close(); }
          window.clearInterval(pingTimer);
          setState("closed");
          return;
      }
    }

    // エディタの時刻を、この画面の時計に直す
    function toLocal(t) { return typeof t === "number" ? t - offset : Date.now(); }

    // 食い違った。ハッシュが違えば、新しいほうが full を送る（同じ時刻ならエディタ側が正）
    function resolve(m) {
      if (m.hash === sha256(shadow)) { sentState = false; return; }
      if (modified > toLocal(m.modified)) {
        send({ type: "full", text: shadow, hash: sha256(shadow), modified: modified });
      } else if (!sentState) {
        sendState();
      }
    }
    function sendState() {
      sentState = true;
      send({ type: "state", hash: sha256(shadow), modified: modified });
    }

    function keepBackup(text) {
      try {
        window.localStorage.setItem(BACKUP_KEY, JSON.stringify({ page: o.page().path, at: Date.now(), text: text }));
      } catch (e) { /* 控えられなくても置き換えは進める */ }
      ui.status.textContent = "エディタ側の内容が新しかったので置き換えました（元の内容はブラウザに控えました）";
    }

    function ping() { send({ type: "ping" }); }

    /* ---- 本文の同期 ---- */

    // エディタから届いた本文を入れる。こちらのカーソルは、変わった位置に合わせてずらす
    function setText(text) {
      var before = source.value;
      shadow = text;
      if (text === before) return;
      var d = diff(before, text);
      var start = source.selectionStart, end = source.selectionEnd;
      var delta = d.text.length - (d.end - d.start);
      function move(p) { return p <= d.start ? p : (p >= d.end ? p + delta : d.start + d.text.length); }
      source.value = text;
      source.setSelectionRange(move(start), move(end));
      lastSentSel = selKey();
      // 下書き・プレビュー・保存ボタンの状態は input を見て動く（editor.js・セクション編集）
      source.dispatchEvent(new Event("input", { bubbles: true }));
    }

    // 手元の変更を、待たずに送る（届いたものを当てる前に、シャドウをそろえておく）
    function flushLocal() {
      window.clearTimeout(sendTimer);
      if (shadow === null || !link) return;
      var now = normalize(source.value);
      if (now === shadow) return;
      send({ type: "edit", from: sha256(shadow), to: sha256(now), changes: [diff(shadow, now)], modified: modified });
      shadow = now;
    }

    function onLocalChange() {
      if (state !== "connected" || shadow === null) return;
      if (normalize(source.value) === shadow) return;
      modified = Date.now();
      window.clearTimeout(sendTimer);
      sendTimer = window.setTimeout(function () {
        if (state === "connected") { flushLocal(); sendCursor(); }
      }, SEND_DEBOUNCE);
    }
    source.addEventListener("input", onLocalChange);
    // ツールバーなどが input を出さずに書き換えた場合に備えて、ときどき見に行く
    var watchTimer = window.setInterval(onLocalChange, 1000);

    /* ---- カーソル ---- */

    function selKey() { return source.selectionStart + ":" + source.selectionEnd; }

    function sendCursor() {
      if (state !== "connected" || selKey() === lastSentSel) return;
      lastSentSel = selKey();
      send({ type: "cursor", start: source.selectionStart, end: source.selectionEnd });
    }
    function onCaretMove() {
      if (state !== "connected" || document.activeElement !== source) return;
      window.clearTimeout(cursorTimer);
      cursorTimer = window.setTimeout(function () {
        if (normalize(source.value) !== shadow) return;   // 打った分は、本文と一緒に送る
        sendCursor();
      }, CURSOR_DEBOUNCE);
    }
    ["keyup", "mouseup", "select", "selectionchange"].forEach(function (name) {
      source.addEventListener(name, onCaretMove);
    });

    function setCursor(start, end) {
      var len = source.value.length;
      var a = Math.max(0, Math.min(len, start | 0)), b = Math.max(0, Math.min(len, end | 0));
      source.setSelectionRange(Math.min(a, b), Math.max(a, b));
      lastSentSel = selKey();
      if (sourceHidden()) revealCaret(); else scrollCaretIntoView();
    }

    function scrollCaretIntoView() {
      if (!source.clientHeight) return;   // 欄が見えていない
      var c = caretTop(source, source.selectionStart);
      var view = source.scrollTop, h = source.clientHeight;
      if (c.top >= view && c.top + c.height <= view + h) return;
      source.scrollTop = Math.max(0, c.top - h / 3);
    }

    /* ---- 画面 ---- */

    ui.toggle.addEventListener("click", function () {
      if (state === "off") {
        save(window.localStorage, ON_KEY, "1");
        retryCount = 0;
        connect();
      } else {
        save(window.localStorage, ON_KEY, "0");   // 切るのは、自分で切断したときだけ
        disconnect(true);
      }
    });
    ui.reopen.addEventListener("click", function () { retryCount = 0; connect(); });

    // ほかのタブ・ほかの欄でオン・オフを切り替えたら、この欄も合わせる
    function onStorage(ev) {
      if (ev.key !== ON_KEY) return;
      if (ev.newValue === "1" && state === "off") { retryCount = 0; connect(); }
      else if (ev.newValue !== "1" && state !== "off") disconnect(true);
    }
    window.addEventListener("storage", onStorage);

    setState("off");
    // 拡張機能は、ページより後に印を付けることがある。少し待ってから始める
    if (load(window.localStorage, ON_KEY, "0") === "1") window.setTimeout(connect, 150);

    // ページを離れるとき。何を送るかは使う側が決める（編集画面は再読み込みなら reload）
    function onPageHide() {
      flushLocal();
      if (!link) return;
      send({ type: o.leaveType ? o.leaveType() : "bye" });
      var l = link; link = null; l.close();
    }
    window.addEventListener("pagehide", onPageHide);

    return {
      // 欄を片付ける。sayBye なら bye を送り、エディタのバッファも閉じる
      detach: function (sayBye) {
        if (detached) return;
        flushLocal();
        disconnect(sayBye);
        detached = true;
        window.clearInterval(watchTimer);
        window.clearTimeout(cursorTimer);
        window.removeEventListener("storage", onStorage);
        window.removeEventListener("pagehide", onPageHide);
        if (ui.root.parentNode) ui.root.parentNode.removeChild(ui.root);
      }
    };
  }

  /* プログラムからカーソルを動かしても textarea はスクロールしない。プレビューの位置合わせは
   * 本文の欄のスクロールを見て動く（editor.js）ので、ここでスクロールさせる。カーソルの高さは、
   * textarea と同じ見た目の見えない要素に、カーソルまでの文字を入れて測る。 */
  var MIRROR_PROPS = ["boxSizing", "fontFamily", "fontSize", "fontWeight", "fontStyle",
    "letterSpacing", "lineHeight", "textTransform", "wordSpacing", "tabSize",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
    "borderTopStyle", "borderRightStyle", "borderBottomStyle", "borderLeftStyle"];

  function caretTop(source, pos) {
    var cs = window.getComputedStyle(source);
    var div = document.createElement("div");
    MIRROR_PROPS.forEach(function (p) { div.style[p] = cs[p]; });
    div.style.position = "absolute";
    div.style.visibility = "hidden";
    div.style.left = "-99999px";
    div.style.top = "0";
    div.style.whiteSpace = "pre-wrap";
    div.style.overflowWrap = "break-word";
    div.style.boxSizing = "border-box";
    div.style.width = (source.clientWidth + parseFloat(cs.borderLeftWidth) +
                       parseFloat(cs.borderRightWidth)) + "px";
    div.textContent = source.value.slice(0, pos);
    var mark = document.createElement("span");
    mark.textContent = "​";
    div.appendChild(mark);
    document.body.appendChild(div);
    var r = { top: mark.offsetTop, height: mark.offsetHeight };
    document.body.removeChild(div);
    return r;
  }

  function buildUi(container) {
    var root = document.createElement("span");
    root.className = "edit-link";
    root.innerHTML =
      '<button type="button" class="edit-link-toggle"></button>' +
      '<span class="edit-link-status" role="status" aria-live="polite"></span>' +
      '<button type="button" class="edit-link-reopen" hidden>もう一度つなぐ</button>' +
      '<details class="edit-link-settings"><summary title="ポート番号の設定">設定</summary>' +
      '<label>ポート番号 <input type="number" class="edit-link-port" min="1" max="65535"></label>' +
      '</details>';
    container.appendChild(root);
    var p = root.querySelector(".edit-link-port");
    p.value = port();
    p.addEventListener("change", function () { save(window.localStorage, PORT_KEY, p.value); });
    return {
      root: root,
      toggle: root.querySelector(".edit-link-toggle"),
      status: root.querySelector(".edit-link-status"),
      reopen: root.querySelector(".edit-link-reopen")
    };
  }

  window.WikiEditorLink = { attach: attach };
  // 試験から使うための入口（中身の確かめ用。画面からは使わない）
  window.__wikiEditorLink = { sha256: sha256, diff: diff, applyChanges: applyChanges };

  /* ---- 編集画面 ---- */

  (function () {
    var source = document.querySelector("textarea.edit-source");
    var editorBox = document.querySelector(".page-editor");
    var buttons = document.querySelector(".edit-buttons");
    if (!source || !editorBox || !buttons) return;

    function markup() {
      var checked = document.querySelector('input[name="markup"]:checked');
      return checked ? checked.value : "";
    }
    function markupExt() {
      var checked = document.querySelector('input[name="markup"]:checked');
      return (checked && checked.dataset.ext) || "";
    }
    function pageUrl() { return new URL(editorBox.dataset.action || location.href, location.href); }
    function pagePath() {
      var path = decodeURIComponent(pageUrl().pathname);
      return path.replace(/^\/=[^/]+/, "").replace(/^\/+/, "") || "index";
    }
    // 添付ファイルの一覧（編集画面の添付タブの行から集める）。ref は「本文での書きかた」で、
    // 添付タブに出ているものをそのまま使う（決まりを editor.py の attach_ref_text の1か所に保つため）。
    // エディタから選んで本文に入れられるようにする（設計者の指示、2026-10-06）。添付を操作すると
    // 編集画面が再読み込みされ、hello で送り直す
    function attachments() {
      return [].map.call(document.querySelectorAll(".attach-row"), function (row) {
        function text(sel) { var el = row.querySelector(sel); return el ? el.textContent.trim() : ""; }
        return { name: text(".attach-name"), kind: text(".attach-kind-label"), size: text(".attach-size"),
                 mtime: text(".attach-date"), ref: text(".attach-ref-code") };
      }).filter(function (a) { return a.name; });
    }

    // タブのセッション ID（sessionStorage）。同じタブなら、保存やページの切り替えで再読み込みしても
    // 同じ ID で、エディタは同じバッファを使い続ける
    var session = load(window.sessionStorage, SESSION_KEY, "");
    if (!session) { session = newSessionId(); save(window.sessionStorage, SESSION_KEY, session); }

    /* エディタから保存が届いた（Wiki設計者の指示、2026-10-13）。
     * - 変更が無い（保存が押せない）: 編集を終える。一時中断と同じく、ページの表示へ戻る
     * - 保存が押せて、連続編集がオン: 保存して、編集を続ける（再読み込みして戻る）
     * - 保存が押せて、連続編集がオフ: 保存して、編集を終える（ページの表示へ戻る）
     * 編集を終えるときは、離れる直前に reload ではなく bye を送り、エディタのバッファも閉じる */
    function saveFromEditor() {
      var saveBtn = document.querySelector(".edit-save");
      if (!saveBtn || saveBtn.disabled) {
        var pauseBtn = document.querySelector(".edit-pause");
        if (pauseBtn) pauseBtn.click();   // 一時中断として送信を見るほうで bye に決まる
        return;
      }
      saveBtn.click();   // 連続編集がオフなら、送信を見るほうで bye に決まる
    }

    /* ---- ページを離れるとき ----
     * 編集画面が自分で送信して再読み込みするとき（保存・サイドバーでのページの切り替え・添付の操作）は
     * bye を送らない。エディタはバッファをしばらく保ち、同じセッション ID の hello が来たら引き継ぐ
     * （ウィンドウを作り直さない）。それ以外で離れるとき（タブを閉じた・リンクでほかのページへ行った）は
     * bye を送り、エディタはすぐバッファを閉じる（設計者の指示、2026-10-07。タブを閉じても
     * エディタが残っていた）。bye が届かなくても、エディタは待つ時間のあとに閉じる。
     *
     * 送信は、ボタンによるもの（submit のイベント）と、プログラムからの form.submit()
     * （イベントが出ない）の両方を見る。送信してもページが移らない場合（裏で送るもの）に
     * 備えて、目印は LEAVE_BY_SUBMIT_MS で消す。 */
    var LEAVE_BY_SUBMIT_MS = 10000;
    var leavingBySubmit = false, leaveTimer = null;
    /* 送信のうち、編集を終えて通常表示に戻るもの（一時中断・連続編集がオフの保存と内容破棄）は、
     * 編集画面が戻ってこない。reload ではなく bye を送り、エディタのバッファもすぐ閉じる
     * （reload を送ると、エディタは戻りを待って 10 秒たってから閉じていた。設計者の報告、2026-10-13）。
     * どの送信かは、押されたボタン（submit の submitter）か、editor.js が詰める cmd で見る */
    var leavingForGood = false;
    function markLeavingForGood() {
      leavingForGood = true;
      // ページが移らなかったとき（保存の失敗など）に残らないよう、送信の目印と同じく消す
      window.setTimeout(function () { leavingForGood = false; }, LEAVE_BY_SUBMIT_MS);
    }
    function leavesEditing(cmd) {
      if (cmd === "pause") return true;
      if (cmd !== "save" && cmd !== "discard") return false;
      var box = document.querySelector(".edit-continuous-check");
      return !(box && box.checked);
    }
    function markSubmit(form, submitter) {
      leavingBySubmit = true;
      window.clearTimeout(leaveTimer);
      leaveTimer = window.setTimeout(function () { leavingBySubmit = false; }, LEAVE_BY_SUBMIT_MS);
      var cmdField = form && form.querySelector && form.querySelector('input[name="cmd"]');
      var cmd = (submitter && submitter.name === "cmd" && submitter.value) || (cmdField && cmdField.value) || "";
      if (leavesEditing(cmd)) markLeavingForGood();
    }
    document.addEventListener("submit", function (ev) { markSubmit(ev.target, ev.submitter); }, true);
    var formSubmit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function () {
      markSubmit(this, null);
      return formSubmit.apply(this, arguments);
    };

    attach({
      source: source,
      box: editorBox,
      container: buttons,
      session: session,
      resumeKey: HIDDEN_KEY,
      page: function () {
        return { path: pagePath(), title: pagePath() + markupExt(), markup: markup(), url: pageUrl().href };
      },
      attachments: attachments,
      onSave: saveFromEditor,
      // 自分で送信して離れる（再読み込みする）なら reload、それ以外は bye。エディタは reload のあとに
      // 切れても「通信が切れた」とは扱わず、同じセッション ID で戻るのを待つ
      leaveType: function () { return leavingBySubmit && !leavingForGood ? "reload" : "bye"; },
      // 欄を隠しているあいだ、プレビューをカーソルのある行に合わせてもらう（editor.js）
      onCaret: function () { source.dispatchEvent(new Event("wiki-editor-caret")); }
    });
  })();
})();
