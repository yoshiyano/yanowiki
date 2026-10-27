// extension.js — wikiSystem の編集画面と同期する（VS Code の拡張機能 wikiedit）
//
// 更新: 2026-10-14 21:43 +09:00
//
// 使いかたは wikiSystem の _system Wiki の「エディタ連動の編集」（PageEdit/EditorSyncGuide）。
// プロトコルは技術資料「エディタ連動の仕組み」（Tech/EditorSync）の「プロトコル v1」。
// ほかのパッケージは要らない（VS Code に組み込みの Node の http・crypto だけを使う）。
//
// - 起動すると ws://localhost:<ポート番号>/（既定 4100）で待ち受ける。ポートがふさがっていれば
//   （ほかのウィンドウが待ち受けている）、5 秒ごとに確かめ、いなくなったら引き継ぐ
// - 編集画面で「外部エディタにつなぐ」を押すと、ページごとにドキュメントが開く（wikiedit: のドキュメント）
// - 手動で保存（Ctrl+S）すると、編集画面の保存を押す。タブを閉じると、編集画面には
//   「エディタ側で閉じました」と出る
// - 「添付ファイルの書きかたを挿入」で、ページの添付ファイルを選んで本文での書きかたを挿入する

"use strict";

const vscode = require("vscode");
const http = require("http");
const crypto = require("crypto");

const UPDATED = "2026-10-14 21:43 +09:00";
const SCHEME = "wikiedit";
const WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
// 尋ねずに受けるオリジン（ポート番号は問わない）
const LOCAL_ORIGIN = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;
const EXTENSION_ORIGIN = /^(chrome|moz)-extension:\/\//;
const SEND_DEBOUNCE = 150;
const CURSOR_DEBOUNCE = 200;
const QUIET_SAVE_DEBOUNCE = 400;

let fsProvider = null;
let server = null;
let watchTimer = null;
let statusItem = null;
let linkItem = null;            // Wiki のドキュメントを開いているときの、編集画面とのつながり
let attachItem = null;          // Wiki のドキュメントを開いているときの、ページの添付ファイルの数
let staleTimer = null;
let log = null;
const sessions = new Map();     // セッション ID → Session
const byUri = new Map();        // ドキュメントの URI（文字列） → Session
const denied = new Set();       // このウィンドウを開いているあいだ、断ると答えたオリジン
const asking = new Map();       // 尋ねている最中のオリジン → 答えの Promise
const quietSaving = new Set();  // こちらで保存しているドキュメント（Wiki の保存を押さない）

function config() { return vscode.workspace.getConfiguration("wikiedit"); }
function now() { return Date.now(); }
function note(text) { if (log) log.appendLine(new Date().toISOString() + " " + text); }

/* ---- 本文・位置・ハッシュ ---- */

// 本文は改行を LF にそろえた文字列。位置は UTF-16 の単位（JS の文字列の位置と同じ）
function hash(text) { return crypto.createHash("sha256").update(text, "utf8").digest("hex"); }
function normalize(text) { return String(text).replace(/\r\n?/g, "\n"); }

function isHigh(c) { return c >= 0xd800 && c <= 0xdbff; }
function isLow(c) { return c >= 0xdc00 && c <= 0xdfff; }

// 前後で共通する部分を除いた1か所を、差分とする（編集画面の diff と同じ）
function diff(before, after) {
  let start = 0;
  const max = Math.min(before.length, after.length);
  while (start < max && before.charCodeAt(start) === after.charCodeAt(start)) start++;
  let endB = before.length, endA = after.length;
  while (endB > start && endA > start && before.charCodeAt(endB - 1) === after.charCodeAt(endA - 1)) { endB--; endA--; }
  // サロゲートペアを割らない
  if (start > 0 && isHigh(before.charCodeAt(start - 1))) start--;
  if (endB < before.length && isLow(before.charCodeAt(endB))) { endB++; endA++; }
  return { start, end: endB, text: after.slice(start, endA) };
}

function applyChanges(text, changes) {
  for (const ch of changes || []) {
    const s = Math.max(0, Math.min(text.length, ch.start | 0));
    const e = Math.max(s, Math.min(text.length, ch.end | 0));
    text = text.slice(0, s) + String(ch.text || "") + text.slice(e);
  }
  return text;
}

/* ---- ドキュメントの置き場所（wikiedit: のドキュメントを、メモリの中に持つ） ----
 * 名前の無いドキュメント（untitled）だと Ctrl+S が「名前を付けて保存」になり、閉じると保存を訊かれる。
 * 専用の置き場所にすると、保存（writeFile）はここに書くだけになり、手動で保存したことは
 * onWillSaveTextDocument で分かる。 */

class WikiFileSystem {
  constructor() {
    this.files = new Map();   // URI（文字列） → {data, mtime}
    this._emitter = new vscode.EventEmitter();
    this.onDidChangeFile = this._emitter.event;
  }
  set(uri, text) { this.files.set(uri.toString(), { data: Buffer.from(text, "utf8"), mtime: now() }); }
  drop(uri) { this.files.delete(uri.toString()); }
  watch() { return new vscode.Disposable(() => {}); }
  stat(uri) {
    const f = this.files.get(uri.toString());
    if (f) return { type: vscode.FileType.File, ctime: f.mtime, mtime: f.mtime, size: f.data.length };
    // ドキュメントの親のフォルダ（パンくずリストなどが尋ねる）
    const prefix = uri.toString().replace(/\/?$/, "/");
    for (const key of this.files.keys()) {
      if (key.startsWith(prefix)) return { type: vscode.FileType.Directory, ctime: 0, mtime: 0, size: 0 };
    }
    throw vscode.FileSystemError.FileNotFound(uri);
  }
  readDirectory() { return []; }
  createDirectory(uri) { throw vscode.FileSystemError.NoPermissions(uri); }
  readFile(uri) {
    const f = this.files.get(uri.toString());
    if (!f) throw vscode.FileSystemError.FileNotFound(uri);
    return f.data;
  }
  writeFile(uri, content) {
    // VS Code が保存したときに来る。Wiki に送るのは本文の変更のほうなので、覚えるだけ
    this.files.set(uri.toString(), { data: Buffer.from(content), mtime: now() });
  }
  delete(uri) { this.files.delete(uri.toString()); }
  rename(uri) { throw vscode.FileSystemError.NoPermissions(uri); }
}

/* ---- WebSocket（待ち受ける側を、標準の機能だけで持つ） ---- */

class Connection {
  constructor(socket, head) {
    this.socket = socket;
    this.buf = head && head.length ? Buffer.from(head) : Buffer.alloc(0);
    this.frag = [];
    this.session = null;
    this.viaExtension = false;
    this.bye = false;       // こちらから閉じた・bye を受けた（再読み込みを待たない）
    this.closed = false;
    socket.setNoDelay(true);
    socket.on("data", (d) => { this.buf = Buffer.concat([this.buf, d]); this.readFrames(); });
    socket.on("close", () => this.onClose());
    // 相手が送信を閉じた（FIN）。HTTP の待ち受けは半分だけ閉じた状態を許すので、自分からは閉じず、
    // 何か送って失敗するまで切れたことに気付かない（そのあいだに送った変更は失われる）。すぐ閉じる
    socket.on("end", () => { this.onClose(); socket.end(); });
    socket.on("error", () => {});
  }

  start() { if (this.buf.length) this.readFrames(); }

  sendFrame(opcode, payload) {
    if (this.closed) return;
    const n = payload.length;
    let head;
    if (n < 126) head = Buffer.from([0x80 | opcode, n]);
    else if (n < 65536) { head = Buffer.alloc(4); head[0] = 0x80 | opcode; head[1] = 126; head.writeUInt16BE(n, 2); }
    else { head = Buffer.alloc(10); head[0] = 0x80 | opcode; head[1] = 127; head.writeBigUInt64BE(BigInt(n), 2); }
    this.socket.write(Buffer.concat([head, payload]));
  }

  send(obj) {
    obj.t = now();
    this.sendFrame(1, Buffer.from(JSON.stringify(obj), "utf8"));
  }

  close() {
    if (this.closed) return;
    this.bye = true;
    try { this.sendFrame(8, Buffer.alloc(0)); } catch (e) { /* もう切れている */ }
    this.socket.end();
    this.socket.destroy();
  }

  readFrames() {
    let data = this.buf;
    while (data.length >= 2) {
      const b1 = data[0], b2 = data[1];
      const fin = (b1 & 0x80) !== 0, op = b1 & 0x0f, masked = (b2 & 0x80) !== 0;
      let n = b2 & 0x7f, pos = 2;
      if (n === 126) { if (data.length < 4) break; n = data.readUInt16BE(2); pos = 4; }
      else if (n === 127) { if (data.length < 10) break; n = Number(data.readBigUInt64BE(2)); pos = 10; }
      const mask = masked ? data.subarray(pos, pos + 4) : null;
      if (masked) pos += 4;
      if (data.length < pos + n) break;
      const payload = Buffer.from(data.subarray(pos, pos + n));
      if (mask) for (let i = 0; i < n; i++) payload[i] ^= mask[i % 4];
      data = data.subarray(pos + n);
      if (op === 1 || op === 0) {
        this.frag.push(payload);
        if (fin) {
          const text = Buffer.concat(this.frag).toString("utf8");
          this.frag = [];
          this.onText(text);
        }
      } else if (op === 8) {
        this.buf = Buffer.alloc(0);
        try { this.sendFrame(8, Buffer.alloc(0)); } catch (e) { /* もう切れている */ }
        this.socket.end();
        return;
      } else if (op === 9) {
        this.sendFrame(10, payload);
      }
    }
    this.buf = Buffer.from(data);
  }

  onText(text) {
    let m;
    try { m = JSON.parse(text); } catch (e) { return; }
    if (!m || typeof m.type !== "string") return;
    if (m.type === "ping") {
      const t1 = now();
      this.send({ type: "pong", t0: m.t, t1, t2: now() });
    } else if (m.type === "hello") {
      onHello(this, m);
    }
    if (this.session && this.session.conn === this) this.session.touch();
    if (m.type === "ping" || m.type === "hello") return;
    if (this.session && this.session.conn === this) this.session.enqueue(m);
  }

  onClose() {
    if (this.closed) return;
    this.closed = true;
    const s = this.session;
    if (s && s.conn === this) s.onDisconnect(this.bye);
  }
}

function acceptKey(key) {
  return crypto.createHash("sha1").update(key + WS_GUID).digest("base64");
}

function onUpgrade(req, socket, head) {
  const key = req.headers["sec-websocket-key"];
  const origin = req.headers.origin;
  if (!key) { socket.end("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"); return; }
  const accept = (viaExtension) => {
    socket.write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                 "Sec-WebSocket-Accept: " + acceptKey(key) + "\r\n\r\n");
    const conn = new Connection(socket, head);
    conn.viaExtension = viaExtension;
    conn.start();
  };
  if (config().get("allowExtensions") && origin && EXTENSION_ORIGIN.test(origin)) {
    // 拡張機能を通した接続。ページのオリジンは hello で確かめる
    accept(true);
    return;
  }
  if (originAllowed(origin)) { accept(false); return; }
  // 知らないオリジン。答えが出るまで応答を保留する（届いたものはソケットにためておく）
  socket.pause();
  socket.on("error", () => {});
  decide(origin).then((ok) => {
    if (socket.destroyed) return;
    if (ok) { accept(false); socket.resume(); }
    else {
      vscode.window.setStatusBarMessage("wikiedit: " + origin + " からの接続を断りました", 5000);
      socket.end("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n");
    }
  });
}

/* ---- 知らないオリジンからの接続を尋ねる ---- */

function originAllowed(origin) {
  if (!origin) return false;
  return LOCAL_ORIGIN.test(origin) || (config().get("allowedOrigins") || []).includes(origin);
}

// ORIGIN を許すかを決める。知らなければ尋ねる。同じオリジンの接続が重なっても1回だけ尋ねる
function decide(origin) {
  if (originAllowed(origin)) return Promise.resolve(true);
  if (!origin || denied.has(origin)) return Promise.resolve(false);
  if (asking.has(origin)) return asking.get(origin);
  const p = Promise.resolve(vscode.window.showWarningMessage(
    "wikiedit: " + origin + " からの接続を許しますか？",
    { modal: true, detail: "許すと設定（wikiedit.allowedOrigins）に覚え、次からは尋ねません。" +
      "知らないサイトなら断ってください。開いただけのページから、手元のエディタを読み書きされないようにするためです。" },
    "許す")).then(async (answer) => {
    asking.delete(origin);
    if (answer === "許す") {
      const list = (config().get("allowedOrigins") || []).filter((o) => o !== origin);
      list.push(origin);
      await config().update("allowedOrigins", list, vscode.ConfigurationTarget.Global);
      return true;
    }
    denied.add(origin);
    return false;
  }, () => { asking.delete(origin); return false; });
  asking.set(origin, p);
  return p;
}

function urlOrigin(url) {
  try { return new URL(url).origin; } catch (e) { return null; }
}

function onHello(conn, m) {
  if (!conn.viaExtension) { startSession(conn, m); return; }
  // 拡張機能を通した接続は、hello に書かれたページのオリジンで決める
  const origin = urlOrigin(m.page && m.page.url);
  decide(origin).then((ok) => {
    if (conn.closed) return;
    if (ok) startSession(conn, m);
    else {
      vscode.window.setStatusBarMessage("wikiedit: " + origin + " からの接続を断りました", 5000);
      conn.close();
    }
  });
}

/* ---- 1つの編集画面（タブのセッション ID ごと）と、それを映すドキュメント ---- */

function pageUri(page, sessionId) {
  let host = "wiki";
  try { host = new URL(page.url).host || host; } catch (e) { /* 既定の名前 */ }
  // 名前はページのパスと書きかたの拡張子（Tech/Foo.md）。拡張子で言語が決まる
  const title = String(page.title || page.path || "page").split("/")
    .filter((p) => p && p !== "." && p !== "..").join("/") || "page";
  let uri = vscode.Uri.from({ scheme: SCHEME, authority: host, path: "/" + title });
  const other = byUri.get(uri.toString());
  if (other && other.id !== sessionId) {
    // 同じページを別のタブでも開いている。別のドキュメントにする
    uri = uri.with({ query: sessionId });
  }
  return uri;
}

function startSession(conn, m) {
  const id = String(m.session || "");
  if (!id) { conn.close(); return; }
  let s = sessions.get(id);
  const resumed = !!s;
  if (!s) { s = new Session(id); sessions.set(id, s); }
  s.enqueue({ type: "__hello", conn, hello: m, resumed });
}

class Session {
  constructor(id) {
    this.id = id;
    this.conn = null;
    this.page = null;
    this.uri = null;
    this.shadow = null;         // 最後に編集画面とそろえた本文
    this.modified = now();      // 本文を最後に変えた時刻（この VS Code の時計）
    this.offset = 0;            // この VS Code の時計 − ページの時計（ミリ秒）
    this.sentState = false;
    this.attachments = [];
    this.applying = 0;          // 届いた変更をドキュメントに当てている最中
    this.sendTimer = null;
    this.cursorTimer = null;
    this.saveTimer = null;
    this.keepTimer = null;
    this.lastCursor = "";
    this.link = null;           // connected・reloading（再読み込み中）・stale（応答なし）・disconnected（切断）
    this.lastRecv = 0;          // 編集画面から最後に何か届いた時刻
    this.unsent = false;        // 送れないあいだに変えた分があるか
    this.expectReload = 0;      // 再読み込みを待っている印（reload を受けた・保存を送った時刻）
    this.disposed = false;
    this.queue = Promise.resolve();
  }

  // 届いたものは順に扱う（ドキュメントへの書き込みは待つので、重ならないように）
  enqueue(m) {
    this.queue = this.queue.then(() => this.handle(m)).catch((e) => note("error: " + (e && e.stack || e)));
  }

  send(obj) { if (this.conn) this.conn.send(obj); }

  document() {
    return this.uri && vscode.workspace.textDocuments.find((d) => d.uri.toString() === this.uri.toString());
  }

  docText() {
    const d = this.document();
    return d ? normalize(d.getText()) : this.shadow;
  }

  toLocal(t) { return typeof t === "number" ? t + this.offset : now(); }

  async handle(m) {
    if (this.disposed && m.type !== "__hello") return;
    switch (m.type) {
      case "__hello": return this.onHello(m.conn, m.hello, m.resumed && !this.disposed);
      case "clock": this.offset = Number(m.offset) || 0; return;
      case "attachments": this.attachments = Array.isArray(m.attachments) ? m.attachments : []; showLink(); return;
      case "edit": {
        this.flush();
        if (m.from !== hash(this.shadow)) { this.sendState(); return; }
        const next = applyChanges(this.shadow, m.changes);
        if (hash(next) !== m.to) { this.sendState(); return; }
        this.modified = this.toLocal(m.modified);
        await this.setText(next);
        return;
      }
      case "state": this.resolve(m); return;
      case "full": {
        // 置き換える前に手元の分を送らない（送ると、編集画面とエディタの本文がずれる）。手元の分は控える
        clearTimeout(this.sendTimer);
        const text = normalize(String(m.text || ""));
        const current = this.docText();
        if (text !== current) this.keepBackup(current);
        this.sentState = false;
        this.modified = this.toLocal(m.modified);
        await this.setText(text);
        return;
      }
      case "cursor": this.setCursor(m.start, m.end); return;
      case "reload":
        // 編集画面が再読み込みする。このあと切れても、同じセッション ID で戻るのを待つ
        this.expectReload = now();
        return;
      case "bye":
        if (this.conn) this.conn.bye = true;
        await this.dispose(false);
        return;
    }
  }

  async onHello(conn, m, resumed) {
    if (this.disposed) {   // 閉じたあとに同じセッション ID で来た。新しく始める
      this.disposed = false;
      this.uri = null;
      this.page = null;
      this.shadow = null;
    }
    clearTimeout(this.keepTimer);
    if (this.conn && this.conn !== conn) { const old = this.conn; this.conn = null; old.close(); }
    this.conn = conn;
    conn.session = this;
    const page = m.page || {};
    const text = normalize(String(m.text || ""));
    const samePage = resumed && this.page && this.page.path === page.path && this.document();
    const wasLink = this.link;
    const mine = this.document() ? this.docText() : null;
    const base = this.shadow;
    let follow = null;
    this.attachments = Array.isArray(m.attachments) ? m.attachments : [];
    this.sentState = false;
    if (resumed && !samePage && base !== null && mine !== null && mine !== base) {
      // 前のページの、まだ送っていない変更は消さずに控える
      this.keepBackup(mine, "別のページへ移る前の、送っていない変更を控えに残しました");
    }
    if (!samePage) {
      // 新しいページ（か初めて）: ページの本文で始める。前のページのドキュメントは閉じる
      const oldUri = this.uri;
      if (oldUri) byUri.delete(oldUri.toString());
      this.uri = pageUri(page, this.id);
      byUri.set(this.uri.toString(), this);
      fsProvider.set(this.uri, text);
      this.page = page;
      this.shadow = text;
      this.modified = now();
      await this.openDocument(oldUri);
      if (oldUri) await closeTabs(oldUri, true);
    } else {
      // 同じページを引き継いだ。最後にそろえた本文（シャドウ）を基準に、どちらが変わったかで決める
      this.page = page;
      if (base === null || mine === base) {
        await this.setText(text);               // エディタは変わっていない: 編集画面の本文にそろえる
      } else if (text === base) {
        follow = "edit";                        // 編集画面は変わっていない: welcome のあとに送る
      } else if (this.toLocal(m.modified) > this.modified) {
        this.keepBackup(mine);                  // 両方: 編集画面が新しい。エディタの分は控える
        await this.setText(text);
        this.modified = this.toLocal(m.modified);
      } else {
        follow = "full";                        // 両方: エディタが新しい。welcome のあとに全文を送る
      }
    }
    if (conn.closed || this.conn !== conn) {
      // ドキュメントを開くのを待っているあいだに切れた（か、別の接続に替わった）。
      // つながっている扱いにせず、切れたときの決まり（onDisconnect）に任せる
      return;
    }
    this.shadow = text;
    this.unsent = false;
    this.expectReload = 0;
    this.lastRecv = now();
    this.setLink("connected");
    showLink();                                 // 添付ファイルの数を出し直す
    // welcome の hash は、いつも編集画面から届いた本文のもの（編集画面に時刻で決めさせない）。
    // エディタの変更は、このあとの edit か full で送る
    conn.send({
      type: "welcome", v: 1,
      editor: "VS Code " + vscode.version + "・wikiedit " + UPDATED.slice(0, 16),
      resumed: !!resumed, t_recv: now(),
      hash: hash(text), modified: this.modified
    });
    if (follow === "edit") {
      this.flush();
      vscode.window.setStatusBarMessage("wikiedit: つなぎ直しました。切れているあいだの変更を編集画面に送りました", 8000);
    } else if (follow === "full") {
      this.sendFull();
      vscode.window.setStatusBarMessage("wikiedit: つなぎ直しました。両方で変更があり、エディタのほうが新しいので、エディタの本文にそろえました", 8000);
    } else if (samePage && (wasLink === "stale" || wasLink === "disconnected")) {
      vscode.window.setStatusBarMessage("wikiedit: つなぎ直しました", 5000);
    }
  }

  async openDocument(oldUri) {
    let doc = await vscode.workspace.openTextDocument(this.uri);
    const lang = (config().get("languages") || {})[this.page.markup];
    if (lang && lang !== doc.languageId) {
      try { doc = await vscode.languages.setTextDocumentLanguage(doc, lang); }
      catch (e) { note("言語 " + lang + " にできません: " + e); }
    }
    const display = config().get("display");
    if (display !== "none") {
      // 前のページのドキュメントがあった場所に開く
      const column = oldUri && tabColumn(oldUri);
      const editor = await vscode.window.showTextDocument(doc, {
        preview: false, viewColumn: column || undefined, preserveFocus: display === "background" });
      if (editor.document.eol !== vscode.EndOfLine.LF) {
        // 改行を CRLF にする設定（Windows の既定）でも、本文は LF で持つ
        this.applying++;
        try { await editor.edit((b) => b.setEndOfLine(vscode.EndOfLine.LF)); } finally { this.applying--; }
      }
    }
  }

  // 編集画面とつながりが切れた。bye でなければ、再読み込み（保存・ページの切り替え）を待つ
  onDisconnect(bye) {
    this.conn = null;
    clearTimeout(this.sendTimer);
    if (this.disposed) return;
    if (bye) { this.dispose(false); return; }
    this.setLink(this.reloadExpected() ? "reloading" : "disconnected");
    clearTimeout(this.keepTimer);
    this.keepTimer = setTimeout(() => {
      if (this.conn || this.disposed) return;
      if (this.document() && this.shadow !== null && this.docText() !== this.shadow) {
        // 送っていない変更がある: 閉じずに残し、同じタブの編集画面がつなぎ直すのを待つ
        this.setLink("disconnected");
        vscode.window.setStatusBarMessage("wikiedit: 編集画面との通信が切れたままです。送っていない変更があるので、閉じずに残します", 10000);
      } else {
        this.dispose(false);
      }
    }, (config().get("keepSeconds") || 10) * 1000);
  }

  /* -- 編集画面とのつながり（編集は止めない） -- */

  // 編集画面の再読み込みを待っているか（reload を受けた・保存を送ってから 15 秒以内）
  reloadExpected() { return now() - this.expectReload < 15000; }

  // いま編集画面へ送ってよいか。応答なしのあいだは送らない
  sendable() { return !!this.conn && !this.conn.closed && this.link === "connected"; }

  setLink(state) {
    if (state === this.link) return;
    const old = this.link;
    this.link = state;
    if (state === "disconnected") {
      vscode.window.setStatusBarMessage("wikiedit: 編集画面との通信が切れました。編集は続けられます（つながったら送ります）", 8000);
    } else if (state === "stale") {
      vscode.window.setStatusBarMessage("wikiedit: 編集画面から " + (config().get("staleSeconds") || 45) + " 秒応答がありません。編集は続けられます", 8000);
    } else if (state === "connected" && old === "stale") {
      vscode.window.setStatusBarMessage("wikiedit: 編集画面の応答が戻りました", 5000);
    }
    showLink();
  }

  // 編集画面から何か届いた。応答なしだったら、ためていた変更を送る
  touch() {
    this.lastRecv = now();
    if (this.link === "stale") {
      this.setLink("connected");
      this.unsent = false;
      showLink();
      setTimeout(() => { if (!this.disposed) { this.flush(); this.sendCursor(); } }, 0);
    }
  }

  // 終える。sayClosed なら、編集画面に「エディタ側で閉じました」と知らせる（タブを閉じたとき）
  async dispose(sayClosed) {
    if (this.disposed) return;
    this.disposed = true;
    clearTimeout(this.keepTimer);
    clearTimeout(this.sendTimer);
    clearTimeout(this.cursorTimer);
    clearTimeout(this.saveTimer);
    if (sessions.get(this.id) === this) sessions.delete(this.id);
    const uri = this.uri;
    if (uri) byUri.delete(uri.toString());
    if (this.conn) {
      const conn = this.conn;
      this.conn = null;
      conn.session = null;
      if (sayClosed) { this.flush(conn); conn.send({ type: "closed" }); }
      showLink();
      conn.close();
    }
    if (uri && !sayClosed) await closeTabs(uri, true);
    if (uri) fsProvider.drop(uri);
  }

  /* -- 本文 -- */

  // 届いた本文をドキュメントに反映する。シャドウは先に新しくし、当てた変更を送り返さないようにする
  async setText(next) {
    this.shadow = next;
    const doc = this.document();
    if (!doc) return;
    const current = normalize(doc.getText());
    if (current === next) return;
    const d = diff(current, next);
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(doc.positionAt(d.start), doc.positionAt(d.end)), d.text);
    this.applying++;
    try { await vscode.workspace.applyEdit(edit); } finally { this.applying--; }
    this.scheduleQuietSave();
    // 当てているあいだに打った分があれば送る
    if (this.docText() !== this.shadow) this.scheduleFlush();
  }

  onLocalChange() {
    if (this.shadow === null) return;
    if (this.docText() === this.shadow) return;   // 届いたものを当てた
    this.modified = now();
    if (!this.sendable() && !this.unsent) { this.unsent = true; showLink(); }
    this.scheduleFlush();
  }

  scheduleFlush() {
    clearTimeout(this.sendTimer);
    this.sendTimer = setTimeout(() => { this.flush(); this.sendCursor(); }, SEND_DEBOUNCE);
  }

  // 手元の変更を、待たずに送る（届いたものを当てる前に、シャドウをそろえておく）
  flush(conn) {
    clearTimeout(this.sendTimer);
    if (!conn && !this.sendable()) return;
    conn = conn || this.conn;
    if (!conn || this.shadow === null || this.applying) return;
    const text = this.docText();
    if (text === this.shadow) return;
    conn.send({ type: "edit", from: hash(this.shadow), to: hash(text),
                changes: [diff(this.shadow, text)], modified: this.modified });
    this.shadow = text;
    this.scheduleQuietSave();
  }

  // 食い違った。新しいほうが full を送る（同じ時刻ならエディタ側が正）
  resolve(m) {
    if (m.hash === hash(this.shadow)) { this.sentState = false; return; }
    if (this.modified >= this.toLocal(m.modified)) {
      this.sendFull();
    } else if (!this.sentState) {
      this.sendState();
    }
  }

  // いまのドキュメントの全文を full で送り、シャドウをそろえる
  sendFull() {
    clearTimeout(this.sendTimer);
    const text = this.docText();
    this.shadow = text;
    this.send({ type: "full", text, hash: hash(text), modified: this.modified });
  }

  sendState() {
    this.sentState = true;
    this.send({ type: "state", hash: hash(this.shadow), modified: this.modified });
  }

  // 置き換える前の本文を、控えのドキュメントに残す
  keepBackup(text, what) {
    const uri = this.uri.with({ path: this.uri.path.replace(/(\.[^./]*)?$/, " 控え$1") });
    fsProvider.set(uri, text);
    vscode.window.showWarningMessage(
      "wikiedit: " + (what || "編集画面の内容が新しかったので置き換えました（元の内容は控えに残しました）"), "控えを開く")
      .then((a) => { if (a) vscode.window.showTextDocument(uri, { preview: false }); });
  }

  /* -- 未保存のマーク --
   * 本文は打つたびに編集画面へ送っているので、ドキュメントの未保存のマークを消しておく
   * （閉じるときに保存を訊かれないように）。保存のときに本文を変える設定（保存時の整形など）が
   * あれば、勝手に変えないよう、マークは残す。 */
  scheduleQuietSave() {
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      const doc = this.document();
      if (doc && doc.isDirty && !savingChangesText(doc)) quietSave(doc);
    }, QUIET_SAVE_DEBOUNCE);
  }

  /* -- カーソル -- */

  cursorOf(editor) {
    const doc = editor.document, sel = editor.selection;
    const a = doc.offsetAt(sel.anchor), b = doc.offsetAt(sel.active);
    return { start: Math.min(a, b), end: Math.max(a, b) };
  }

  sendCursor() {
    const editor = vscode.window.visibleTextEditors.find((e) => this.uri && e.document.uri.toString() === this.uri.toString());
    if (!editor || !this.sendable()) return;
    const c = this.cursorOf(editor);
    const key = c.start + ":" + c.end;
    if (key === this.lastCursor) return;
    this.lastCursor = key;
    this.send({ type: "cursor", start: c.start, end: c.end });
  }

  onSelection() {
    clearTimeout(this.cursorTimer);
    this.cursorTimer = setTimeout(() => {
      if (this.docText() === this.shadow) this.sendCursor();   // 打った分は、本文と一緒に送る
    }, CURSOR_DEBOUNCE);
  }

  setCursor(start, end) {
    for (const editor of vscode.window.visibleTextEditors) {
      if (!this.uri || editor.document.uri.toString() !== this.uri.toString()) continue;
      const doc = editor.document, len = doc.getText().length;
      const a = doc.positionAt(Math.max(0, Math.min(len, start | 0)));
      const b = doc.positionAt(Math.max(0, Math.min(len, end | 0)));
      editor.selection = new vscode.Selection(a, b);
      editor.revealRange(new vscode.Range(a, b), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
      this.lastCursor = doc.offsetAt(a) + ":" + doc.offsetAt(b);
    }
  }
}

function sessionOf(doc) { return doc && byUri.get(doc.uri.toString()); }

// 保存のときに本文を変える設定があるか
function savingChangesText(doc) {
  const editor = vscode.workspace.getConfiguration("editor", doc);
  const files = vscode.workspace.getConfiguration("files", doc);
  const actions = editor.get("codeActionsOnSave");
  return !!(editor.get("formatOnSave") || files.get("trimTrailingWhitespace") ||
            files.get("insertFinalNewline") || files.get("trimFinalNewlines") ||
            (Array.isArray(actions) ? actions.length : actions && Object.values(actions).some((v) => v && v !== "never")));
}

async function quietSave(doc) {
  const key = doc.uri.toString();
  quietSaving.add(key);
  try { await doc.save(); } catch (e) { note("未保存のマークを消せません: " + e); }
  finally { quietSaving.delete(key); }
}

function tabsOf(uri) {
  const key = uri.toString(), found = [];
  for (const group of vscode.window.tabGroups.all) {
    for (const tab of group.tabs) {
      if (tab.input instanceof vscode.TabInputText && tab.input.uri.toString() === key) found.push(tab);
    }
  }
  return found;
}

function tabColumn(uri) {
  const tab = tabsOf(uri)[0];
  return tab && tab.group.viewColumn;
}

// ドキュメントのタブを閉じる。保存を訊かれないよう、先に未保存のマークを消す
async function closeTabs(uri, quiet) {
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
  if (quiet && doc && doc.isDirty) await quietSave(doc);
  const tabs = tabsOf(uri);
  if (tabs.length) await vscode.window.tabGroups.close(tabs, true);
}

/* ---- 待ち受け ---- */

function listen() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => { res.writeHead(426, { "Content-Length": 0 }); res.end(); });
    srv.on("upgrade", onUpgrade);
    srv.once("error", () => resolve(null));
    srv.listen(config().get("port"), "127.0.0.1", () => {
      srv.on("error", (e) => note("server error: " + e));
      resolve(srv);
    });
  });
}

async function start() {
  if (!staleTimer) staleTimer = setInterval(checkStale, 10000);
  if (server) return;
  server = await listen();
  if (server) {
    showStatus("listening");
    note(config().get("port") + " で待ち受けています");
    return;
  }
  showStatus("waiting");
  note(config().get("port") + " はほかのウィンドウが待ち受けています");
  if (!watchTimer) {
    watchTimer = setInterval(async () => {
      if (server) return;
      const srv = await listen();
      if (!srv) return;
      server = srv;
      clearInterval(watchTimer);
      watchTimer = null;
      showStatus("listening");
      vscode.window.setStatusBarMessage("wikiedit: 待ち受けていたウィンドウがいなくなったので、" +
                                        config().get("port") + " を引き継ぎました", 5000);
    }, (config().get("takeoverInterval") || 5) * 1000);
  }
}

async function stop() {
  clearInterval(watchTimer);
  watchTimer = null;
  clearInterval(staleTimer);
  staleTimer = null;
  if (server) { server.close(); server = null; }
  for (const s of [...sessions.values()]) await s.dispose(false);
  showStatus("off");
}

// 開いている Wiki のドキュメントの、編集画面とのつながりをステータスバーに出す（つながっていれば出さない）
function showLink() {
  if (!linkItem) return;
  const editor = vscode.window.activeTextEditor;
  const s = editor && sessionOf(editor.document);
  const labels = {
    reloading: ["$(sync~spin) Wiki 再読み込み中", "編集画面が再読み込みしています（保存など）。戻ったら続けます", null],
    stale: ["$(warning) Wiki 応答なし", "編集画面から応答がありません。編集は続けられ、応答があったら送ります", "statusBarItem.warningBackground"],
    disconnected: ["$(debug-disconnect) Wiki 切断", "編集画面との通信が切れています。編集は続けられ、同じタブの編集画面がつなぎ直したら送ります", "statusBarItem.errorBackground"],
  };
  showAttach(s && !s.disposed ? s : null);
  const l = s && !s.disposed && labels[s.link];
  if (!l) { linkItem.hide(); return; }
  linkItem.text = l[0] + (s.unsent ? "（未送信）" : "");
  linkItem.tooltip = "wikiedit: " + l[1];
  linkItem.backgroundColor = l[2] ? new vscode.ThemeColor(l[2]) : undefined;
  linkItem.show();
}

// 添付ファイルの数。0 も出す（ページに添付があるかを、一覧を開かずに分かるように）。押すと挿入の一覧を開く
function showAttach(s) {
  if (!attachItem) return;
  if (!s) { attachItem.hide(); return; }
  const list = s.attachments || [];
  attachItem.text = "$(file-media) 添付 " + list.length;
  attachItem.tooltip = list.length
    ? "wikiedit: 添付ファイル（押すと書きかたを挿入）\n" + list.map((a) => String(a.name || "")).join("\n")
    : "wikiedit: このページに添付ファイルはありません";
  attachItem.show();
}

function checkStale() {
  const limit = (config().get("staleSeconds") || 45) * 1000;
  for (const s of sessions.values()) {
    if (s.link === "connected" && s.conn && now() - s.lastRecv > limit) s.setLink("stale");
  }
}

function showStatus(state) {
  if (!statusItem) return;
  const port = config().get("port");
  if (state === "listening") {
    statusItem.text = "$(plug) Wiki";
    statusItem.tooltip = "wikiedit: " + port + " で待ち受けています";
  } else if (state === "waiting") {
    statusItem.text = "$(debug-disconnect) Wiki";
    statusItem.tooltip = "wikiedit: " + port + " はほかのウィンドウが待ち受けています。いなくなったら引き継ぎます";
  } else {
    statusItem.text = "$(circle-slash) Wiki";
    statusItem.tooltip = "wikiedit: 止めています";
  }
  statusItem.show();
}

/* ---- 命令 ---- */

function currentSession() {
  const editor = vscode.window.activeTextEditor;
  return editor && sessionOf(editor.document);
}

async function insertAttachment(copy) {
  const s = currentSession();
  if (!s) { vscode.window.showInformationMessage("wikiedit: Wiki のドキュメントで使ってください"); return; }
  const items = (s.attachments || []).map((a) => ({
    label: String(a.name || ""), description: [a.kind, a.size].filter(Boolean).join(" "),
    detail: String(a.ref || a.name || ""), ref: String(a.ref || a.name || "") }));
  if (!items.length) { vscode.window.showInformationMessage("wikiedit: このページに添付ファイルはありません"); return; }
  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: copy ? "コピーする添付ファイル" : "挿入する添付ファイル", matchOnDetail: true });
  if (!picked) return;
  if (copy) {
    await vscode.env.clipboard.writeText(picked.ref);
    vscode.window.setStatusBarMessage("wikiedit: " + picked.ref + " をコピーしました", 3000);
    return;
  }
  const editor = vscode.window.activeTextEditor;
  await editor.edit((b) => { for (const sel of editor.selections) b.replace(sel, picked.ref); });
}

function saveToWiki(s) {
  s.flush();
  if (s.conn) {
    s.send({ type: "save" });
    // 保存すると編集画面は再読み込みする。reload が届かなくても、通信の切断とは扱わない
    s.expectReload = now();
  }
  else vscode.window.setStatusBarMessage("wikiedit: 編集画面とつながっていません", 3000);
}

/* ---- 起動 ---- */

function activate(context) {
  log = vscode.window.createOutputChannel("wikiedit");
  fsProvider = new WikiFileSystem();
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 0);
  statusItem.command = "wikiedit.version";
  linkItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1);
  attachItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 2);
  attachItem.command = "wikiedit.insertAttachment";
  context.subscriptions.push(
    log, statusItem, linkItem, attachItem,
    vscode.window.onDidChangeActiveTextEditor(() => showLink()),
    vscode.workspace.registerFileSystemProvider(SCHEME, fsProvider, { isCaseSensitive: true }),
    vscode.commands.registerCommand("wikiedit.start", start),
    vscode.commands.registerCommand("wikiedit.stop", stop),
    vscode.commands.registerCommand("wikiedit.version", () =>
      vscode.window.showInformationMessage("wikiedit: " + UPDATED +
        (server ? "（" + config().get("port") + " で待ち受けています）" : watchTimer ? "（ほかのウィンドウが待ち受けています）" : "（止めています）"))),
    vscode.commands.registerCommand("wikiedit.save", () => { const s = currentSession(); if (s) saveToWiki(s); }),
    vscode.commands.registerCommand("wikiedit.insertAttachment", () => insertAttachment(false)),
    vscode.commands.registerCommand("wikiedit.copyAttachment", () => insertAttachment(true)),
    vscode.commands.registerCommand("wikiedit.close", async () => {
      const s = currentSession();
      if (s) { const uri = s.uri; await closeTabs(uri, true); }
    }),

    vscode.workspace.onDidChangeTextDocument((e) => {
      const s = sessionOf(e.document);
      if (s && !s.disposed && e.contentChanges.length) s.onLocalChange();
    }),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      const s = sessionOf(e.textEditor.document);
      if (s && !s.disposed) s.onSelection();
    }),
    // 手動で保存（Ctrl+S・メニュー）したら、編集画面の保存を押す
    vscode.workspace.onWillSaveTextDocument((e) => {
      const s = sessionOf(e.document);
      if (s && !s.disposed && e.reason === vscode.TextDocumentSaveReason.Manual &&
          !quietSaving.has(e.document.uri.toString())) saveToWiki(s);
    }),
    // タブを閉じたら、編集画面に「エディタ側で閉じました」と知らせる
    vscode.window.tabGroups.onDidChangeTabs((e) => {
      for (const tab of e.closed) {
        if (!(tab.input instanceof vscode.TabInputText)) continue;
        const s = byUri.get(tab.input.uri.toString());
        if (s && !s.disposed && !tabsOf(s.uri).length) s.dispose(true);
      }
    }),
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("wikiedit.port") && (server || watchTimer)) { await stop(); await start(); }
    }),
    { dispose: () => { stop(); } }
  );
  if (config().get("autoStart")) start(); else showStatus("off");
}

function deactivate() { return stop(); }

// _test は試験から中身を確かめるための入口（使う人は要らない）
module.exports = { activate, deactivate, _test: { vscode, hash, diff, applyChanges, sessions, byUri, linkItem: () => linkItem, attachItem: () => attachItem } };
