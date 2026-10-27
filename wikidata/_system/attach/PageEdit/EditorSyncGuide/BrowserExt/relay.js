/* relay.js — 内容スクリプト。編集画面（editor.link.js）と裏方（background.js）のあいだで
 * メッセージを受け渡すだけ。中身は見ない（形だけ確かめる）。
 *
 * 更新: 2026-10-07 23:20 +09:00
 *
 * 閲覧者がツールバーのボタンで許可したサイトにだけ差し込まれる（background.js）。
 * ページには `<html data-wiki-editor-relay>` の印を付け、editor.link.js はそれを見て
 * この中継を使う（公開サイトの http の Wiki では、ページから localhost へ直接つなげないため）。
 * 受け渡しの形は editor.link.js の relayTransport を参照。
 */
(function () {
  "use strict";
  if (window.__wikiEditorRelay) return;   // 二重に差し込まれたとき
  window.__wikiEditorRelay = true;
  document.documentElement.setAttribute("data-wiki-editor-relay", "1");

  var ports = {};   // id → 裏方への通り道（runtime.Port）

  // Chrome は拡張機能の裏方（service worker）を、出来事が無いとしばらくで止める。
  // 止まると持っている WebSocket も切れるので、つないでいるあいだは合図を送り続ける
  // （30秒より短い間隔）。裏方は受け取るだけで何もしない
  window.setInterval(function () {
    Object.keys(ports).forEach(function (id) {
      try { ports[id].postMessage({ type: "ping" }); } catch (e) { /* 切れていれば onDisconnect が来る */ }
    });
  }, 20000);

  function toPage(m) {
    m.from = "relay";
    window.postMessage(m, location.origin);
  }

  window.addEventListener("message", function (ev) {
    var m = ev.data;
    if (ev.source !== window || ev.origin !== location.origin) return;
    if (!m || m.from !== "page" || typeof m.id !== "string") return;
    if (m.wikiEditorRelay === "open") {
      var port = chrome.runtime.connect({ name: "wiki-editor-relay" });
      ports[m.id] = port;
      port.onMessage.addListener(function (r) {
        r.id = m.id;
        toPage(r);
        if (r.wikiEditorRelay === "closed") {
          delete ports[m.id];
          port.disconnect();
        }
      });
      port.onDisconnect.addListener(function () {
        if (ports[m.id] === port) {
          delete ports[m.id];
          toPage({ wikiEditorRelay: "closed", id: m.id, wasOpen: false });
        }
      });
      port.postMessage({ type: "open", port: m.port | 0 });
    } else if (m.wikiEditorRelay === "send" && ports[m.id]) {
      ports[m.id].postMessage({ type: "send", data: m.data });
    } else if (m.wikiEditorRelay === "close" && ports[m.id]) {
      ports[m.id].postMessage({ type: "close" });
      delete ports[m.id];
    }
  });
})();
