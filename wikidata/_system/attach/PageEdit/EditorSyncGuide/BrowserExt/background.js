/* background.js — 裏方。エディタのプラグインとの WebSocket を持ち、中身を見ずに受け渡す。
 *
 * 更新: 2026-10-07 23:20 +09:00
 *
 * ページから localhost へ直接つなげない場面（公開サイトの http の Wiki では Chrome が断る）の
 * ための予備。拡張機能のオリジンで通信するので、その制限を受けない。
 *
 * 保存やページの切り替えで編集画面が開き直されたときの引き継ぎは、エディタのプラグインが
 * 受け持つ（タブの合い言葉で見分ける。Tech/EditorSync「プロトコル v1」）。ここでは保たない。
 *
 * ## 使えるサイト
 * ツールバーのボタンを押したサイトだけ（閲覧者が許可したもの）。許可したオリジンは
 * storage に覚え、内容スクリプト（relay.js）をそこにだけ登録する。
 */
"use strict";

function safePost(port, m) {
  try { port.postMessage(m); } catch (e) { /* ページが先に離れた */ }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "wiki-editor-relay" || !port.sender || !port.sender.tab) return;
  let ws = null, opened = false;

  port.onMessage.addListener((m) => {
    if (!m || typeof m.type !== "string") return;
    if (m.type === "open" && !ws) {
      const wsPort = (m.port > 0 && m.port < 65536) ? m.port : 4100;
      ws = new WebSocket("ws://localhost:" + wsPort + "/");
      ws.onopen = () => { opened = true; safePost(port, { wikiEditorRelay: "opened" }); };
      ws.onmessage = (ev) => {
        let data;
        try { data = JSON.parse(ev.data); } catch (e) { return; }
        safePost(port, { wikiEditorRelay: "message", data });
      };
      ws.onclose = () => {
        safePost(port, { wikiEditorRelay: "closed", wasOpen: opened });
        ws = null;
      };
    } else if (m.type === "send" && ws && ws.readyState === WebSocket.OPEN) {
      if (m.data && typeof m.data === "object") ws.send(JSON.stringify(m.data));
    } else if (m.type === "close") {
      if (ws) ws.close();
      try { port.disconnect(); } catch (e) { /* もう切れている */ }
    }
  });

  port.onDisconnect.addListener(() => { if (ws) ws.close(); });
});

/* ---- 使えるサイトの登録 ---- */

async function allowedOrigins() {
  const { origins } = await chrome.storage.local.get("origins");
  return Array.isArray(origins) ? origins : [];
}

async function registerScripts() {
  const origins = await allowedOrigins();
  try { await chrome.scripting.unregisterContentScripts({ ids: ["relay"] }); } catch (e) { /* 無ければよい */ }
  if (!origins.length) return;
  await chrome.scripting.registerContentScripts([{
    id: "relay",
    js: ["relay.js"],
    matches: origins.map((o) => o + "/*"),
    runAt: "document_start",
    allFrames: false
  }]);
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab || !tab.url) return;
  let origin;
  try { origin = new URL(tab.url).origin; } catch (e) { return; }
  if (!/^https?:/.test(origin)) return;
  // 許可を求めるのは、ボタンを押したこの瞬間（閲覧者の操作）に限られる
  const granted = await chrome.permissions.request({ origins: [origin + "/*"] });
  if (!granted) return;
  const origins = await allowedOrigins();
  if (!origins.includes(origin)) {
    origins.push(origin);
    await chrome.storage.local.set({ origins });
  }
  await registerScripts();
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["relay.js"] });
  chrome.action.setBadgeText({ tabId: tab.id, text: "ON" });
});

chrome.runtime.onInstalled.addListener(registerScripts);
chrome.runtime.onStartup.addListener(registerScripts);
