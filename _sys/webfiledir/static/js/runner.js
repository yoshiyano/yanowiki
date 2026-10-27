// 実行役: サーバが宣言したコマンド（GET mounts の commands）を読んで動かす（Wiki「画面の部品と結果の語彙」）。
// コマンドごとの手順は持たない。宣言の上から「条件（when）→ 確認（confirm）→ 入力（input）→ 要求（POST commands/<id>）
// → 結果（then・onError・onItemError・応答の effects）」と進めるだけ。
//
// 文脈（ctx）は、コマンドを動かす場所の情報:
//   {mount, view: "folder" | "trash", dir（今いるフォルダのパス）, dirEntry（そのフォルダ自身の項目）,
//    items（選んだ項目。path を足したもの）, source（運ぶ項目 {mount, paths, mode, denied, unreadable}）,
//    dest（移す先 {mount, path, denied}）, files（アップロードするもの。ほかのアプリからのドロップ。upload.js の形）}

import { formatSize } from "./format.js";
import { baseName, parentPath } from "./location.js";
import { groupUploads } from "./upload.js";

const AUTH_WORDS = { move: "動かす", read: "読む", write: "書く", exec: "実行する" };
const JOB_POLL_MS = 300;   // ジョブの進み具合を問い合わせる間隔
const JOB_DIALOG_MS = 500; // これより早く終われば、進み具合のダイアログは出さない（ちらつかないように）
const CHECK_FIRST = 1024 * 1024; // アップロードで、これより大きいファイルは、送る前に置けるか（大きさ・拡張子）を尋ねる

// --- 宣言を読む（副作用の無い関数。単体テストがある） ---

/** 項目が what（move | read | write | exec）を許しているか（サーバが返す moveauth などの値）。 */
const allows = (entry, what) => !!entry && entry[`${what}auth`] === 1;

/** 「report.txt」か「3 個の項目」。 */
export function describe(names) {
  return names.length === 1 ? `「${names[0]}」` : `${names.length} 個の項目`;
}

/** 権限を見る相手: 運ぶコマンド（source がある）は運ぶ項目、ほかは選んだ項目。 */
function authTargets(ctx) {
  return ctx.source ? ctx.source.paths : (ctx.items || []).map((e) => e.path);
}

/** 運ぶ項目・選んだ項目のうち、what の権限が無いもののパス。 */
function lacking(ctx, what) {
  if (ctx.source) {
    if (what === "move") return [...(ctx.source.denied || [])];
    if (what === "read") return [...(ctx.source.unreadable || [])];
    return [];
  }
  return (ctx.items || []).filter((e) => !allows(e, what)).map((e) => e.path);
}

/**
 * コマンドをこの文脈で使えるか。{state: "hidden" | "disabled" | "enabled", reason, denied}。
 * hidden … 出さない（ごみ箱の中か・項目の種類が合わない）。disabled … 灰色（数・権限・場所が合わない）。
 * reason … キーで呼ばれたときに知らせる理由（権限が無いとき）。denied … partial のコマンドで外す項目のパス。
 */
export function evaluate(cmd, ctx) {
  const when = cmd.when || {};
  const view = when.view || "folder";
  const hidden = { state: "hidden", reason: "", denied: [] };
  const disabled = (reason = "") => ({ state: "disabled", reason, denied: [] });
  if (view !== "any" && view !== ctx.view) return hidden;
  const items = ctx.items || [];
  const kinds = when.kinds || ["file", "dir"];
  if (items.some((e) => !kinds.includes(e.kind))) return hidden;
  const select = when.select || "any";
  const n = items.length;
  if ((select === "none" && n) || (select === "one" && n !== 1) || (select === "some" && !n)) return disabled();
  if (when.reachable && items.some((e) => e.extra && e.extra.unreachable)) return disabled();
  if (when.clipboard && !ctx.source) return disabled();
  if (when.dir && !allows(ctx.dirEntry, when.dir.auth)) return disabled("このフォルダに作る権限がありません");
  if (when.dest && (!ctx.dest || ctx.dest.denied)) return disabled("このフォルダに入れる権限がありません");
  let denied = [];
  // 切り取ったものの貼り付けでは、切り取ったときに動かす権限の無かった項目（クリップボードの denied）を送らず、
  // その項目だけ失敗にする（画面に組み込みのクリップボードの決まり。0.x と同じ）
  if (ctx.source && ctx.source.mode === "cut" && !when.items) {
    denied = [...(ctx.source.denied || [])];
    if (denied.length && denied.length === ctx.source.paths.length) {
      return { state: "disabled", reason: `動かす権限のある項目が無いので、「${cmd.label}」はできません`, denied: [] };
    }
  }
  if (when.items) {
    const targets = authTargets(ctx);
    denied = lacking(ctx, when.items.auth);
    const word = AUTH_WORDS[when.items.auth];
    if (!targets.length || denied.length === targets.length || (denied.length && !when.items.partial)) {
      const reason = targets.length === 1 && !ctx.source
        ? `「${baseName(targets[0])}」には${word}権限が無いので、「${cmd.label}」はできません`
        : `${word}権限のある項目が無いので、「${cmd.label}」はできません`;
      return { state: "disabled", reason, denied: [] };
    }
  }
  // 運ぶコマンドで、同じマウントの中のとき: 自分の中へは入れられない
  if (ctx.source && ctx.dest && ctx.source.mount === ctx.dest.mount) {
    for (const src of ctx.source.paths) {
      if (ctx.dest.path === src) return disabled("自分自身の上には置けません");
      if (ctx.dest.path.startsWith(src + "/")) return disabled("フォルダをそのフォルダ自身の中へは入れられません");
    }
  }
  return { state: "enabled", reason: "", denied };
}

/** 差し込める値（Wiki「コマンドの宣言 > 差し込める値」）。 */
export function variables(ctx, extra = {}) {
  const items = ctx.items || [];
  const one = items.length === 1 ? items[0] : null;
  const names = ctx.source && !items.length ? ctx.source.paths.map(baseName) : items.map((e) => e.name);
  return {
    $mount: ctx.mount, $dir: ctx.dir ?? null,
    "$item.path": one ? one.path : null, "$item.name": one ? one.name : null, "$item.kind": one ? one.kind : null,
    "$items.names": names, "$items.count": names.length, "$items.label": describe(names),
    ...extra,
  };
}

const VARIABLE_RE = /\$[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?/g;

function lookup(name, vars) {
  if (name in vars) return vars[name];
  if (name.startsWith("$result.") && vars.$result && typeof vars.$result === "object") {
    return vars.$result[name.slice("$result.".length)];
  }
  return undefined;
}

/**
 * 宣言の値に差し込む。"@名前" は texts の文にしてから差し込む。文字列が "$名前" そのものなら値（配列も）に、
 * 文の中の $名前 は文字にして埋める。dict・配列は中までたどる。
 */
export function fill(value, vars, texts = {}) {
  if (typeof value === "string") {
    let s = value;
    if (s.startsWith("@") && Object.hasOwn(texts, s.slice(1))) s = texts[s.slice(1)];
    const whole = s.match(/^\$[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?$/);
    if (whole) {
      const v = lookup(s, vars);
      return v === undefined ? s : v;
    }
    return s.replace(VARIABLE_RE, (m) => {
      const v = lookup(m, vars);
      return v === undefined || v === null ? "" : Array.isArray(v) ? v.join("、") : String(v);
    });
  }
  if (Array.isArray(value)) return value.map((v) => fill(v, vars, texts));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fill(v, vars, texts)]));
  }
  return value;
}

/** 数えるときの「済んだ」（スキップや、同じ場所への移動で何も変わらなかったものは数えない）。 */
const counted = (r) => r.ok && !r.skipped && !r.unchanged;

/** 一括の結果の知らせ: 「N 個の項目を〜しました。M 個の項目を〜できませんでした（名前: 理由 ほか）」。 */
export function reportText(results, done, fail) {
  const ok = results.filter(counted).length;
  const failures = results.filter((r) => !r.ok);
  const parts = [];
  if (ok) parts.push(`${ok} 個の項目を${done}`);
  if (failures.length) {
    const first = failures[0];
    const name = baseName(first.src || (first.error && first.error.path) || "") || "項目";
    const more = failures.length > 1 ? ` ほか ${failures.length - 1} 個` : "";
    parts.push(`${failures.length} 個の項目を${fail}ませんでした（${name}: ${first.error.message}${more}）`);
  }
  return { text: parts.join("。"), kind: failures.length ? "error" : "info" };
}

/** 一括の結果から、$done（成功した項目）を作る。 */
export function doneOf(results) {
  const ok = (results || []).filter((r) => r.ok && !r.skipped);
  return {
    "$done.srcs": ok.filter((r) => r.src).map((r) => r.src),
    "$done.ids": ok.filter((r) => r.id).map((r) => r.id),
    "$done.trashIds": ok.filter((r) => r.trashId).map((r) => r.trashId),
    "$done.names": ok.filter((r) => r.entry).map((r) => r.entry.name),
  };
}

const NAMED_KEYS = new Set(["Delete", "Insert", "Backspace", "Enter", "Escape", "Tab", "ArrowUp", "ArrowDown",
  "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"]);

/** キーボードの事象を、宣言のキーの書きかた（"Ctrl+Shift+N"）にする。修飾だけのときは null。 */
export function keyOf(e) {
  let name = e.key;
  if (name === " ") name = "Space";
  else if (name.length === 1) name = name.toUpperCase();
  else if (!NAMED_KEYS.has(name) && !/^F([1-9]|1[0-2])$/.test(name)) return null;
  const mods = [];
  if (e.ctrlKey || e.metaKey) mods.push("Ctrl");
  if (e.altKey) mods.push("Alt");
  if (e.shiftKey) mods.push("Shift");
  return [...mods, name].join("+");
}

// メニューの組の並び（ここに無い組は、あとに宣言の順で続く）
const GROUP_ORDER = ["open", "clipboard", "new", "edit", "delete", "trash"];

/** 宣言を、組の順・order の順に並べる（同じなら宣言の順）。 */
export function ordered(commands) {
  const rank = (c) => {
    const i = GROUP_ORDER.indexOf(c.group);
    return i < 0 ? GROUP_ORDER.length : i;
  };
  const firstSeen = new Map();
  commands.forEach((c, i) => { if (!firstSeen.has(c.group)) firstSeen.set(c.group, i); });
  return commands.map((c, i) => [c, i]).sort(([a, i], [b, j]) =>
    rank(a) - rank(b) || firstSeen.get(a.group) - firstSeen.get(b.group) || a.order - b.order || i - j,
  ).map(([c]) => c);
}

/**
 * ドロップの条件に合うコマンド（from: "items" | "files"、target: "folder" | "trash"、sameMount、
 * modifier: null | "ctrl" | "shift"）。ほかのアプリのファイル（files）は、マウント・押しているキーで分けない。
 */
export function dropCommand(commands, { from = "items", target, sameMount, modifier }) {
  return commands.find((c) => (c.drop || []).some((d) => (d.from || "items") === from
    && (d.target || "folder") === target
    && (from === "files" || (((d.mounts || "any") === "any" || d.mounts === (sameMount ? "same" : "other"))
      && (d.modifier ?? null) === modifier)))) || null;
}

// --- 動かす ---

/**
 * 実行役を作る。
 * io … FrontEnd の画面が渡す関数:
 *   command(id, body)        … POST commands/<id>（api.js）
 *   job(id) / cancelJob(id)  … ジョブの進み具合 GET jobs/<id> / 中止 POST jobs/<id>/cancel
 *   progress(p)              … ステータスバーのプログレスバー（{label, done, total, item} か null）
 *   stat(mount, path)        … 衝突のダイアログの詳細（読めなければ null を返す）
 *   trash(mount)             … ごみ箱の一覧（［元に戻す］から衝突を尋ねるときの詳細）
 *   upload(id, params, body, onProgress) … POST commands/<id>/upload（api.js）。{promise, abort}
 *   commandsOf(mount)        … そのマウントの宣言
 *   mountOf(mount)           … マウントの情報（属性・名前。衝突のダイアログ）
 *   message(text, kind, action)
 *   changed()                … 変更したあと（ツリー・先読み・隣の画面）
 *   reload({select, keepSelection}) … 一覧を読み直す（Promise）
 *   editItem(name)           … 一覧の項目を選び、その項目の文脈を返す（作ったあとに名前の変更へ入る）
 *   setClipboard(mode, ctx, denied) / clearClipboard()
 *   navigate(effect, name) / browse(effect, name)
 * parts … 部品: confirm(opts) / inlineEdit(ctx, {value, select}) / endInput(ok) / prompt(opts) / chooseConflict(opts)
 *          / modal(data)（状態表示のダイアログ。"ok" / "yes" / "no" を返す）/ progress({title, onCancel})（進み具合）
 *          / uploadDialog({title, dest})（アップロードするものを選ばせる。upload.js の形か、取り消しなら null）
 *          / textEdit(ctx, {title, maxSize, value, error})（選んだファイルの中身を編集させる。value が null なら
 *            中身を読んで始め、文字列なら（保存に失敗して戻ったとき）それを続ける。保存する全体か、取り消しなら null）
 */
export function createRunner(io, parts) {
  /** 要求の本文（Wiki「API 設計 > コマンド API」）。 */
  function bodyOf(ctx, input, answers) {
    const body = { mount: ctx.mount };
    if (ctx.view !== "trash" && ctx.dir != null) body.dir = ctx.dir;
    if (ctx.view === "trash") body.ids = (ctx.items || []).map((e) => e.trashId);
    else body.paths = (ctx.items || []).map((e) => e.path);
    if (ctx.ids) body.ids = ctx.ids;
    if (input != null) body.input = input;
    if (ctx.source) body.source = { mount: ctx.source.mount, paths: ctx.source.paths, mode: ctx.source.mode };
    if (ctx.dest) body.dest = { mount: ctx.dest.mount, path: ctx.dest.path };
    if (answers) body.answers = answers;
    return body;
  }

  /** partial で外す項目を、文脈から除く。 */
  function without(ctx, denied) {
    if (!denied.length) return ctx;
    const gone = new Set(denied);
    if (ctx.source) return { ...ctx, source: { ...ctx.source, paths: ctx.source.paths.filter((p) => !gone.has(p)) } };
    return { ...ctx, items: (ctx.items || []).filter((e) => !gone.has(e.path)) };
  }

  /** 衝突のダイアログに並べる 2 つの項目の詳細。 */
  async function conflictDetails(cmd, ctx, r) {
    const label = (id) => (io.mountOf(id) || { label: "(root)" }).label;
    if (ctx.view === "trash" || r.id) {
      let item = (ctx.items || []).find((e) => e.trashId === r.id);
      if (!item) {
        const listed = ((await io.trash(ctx.mount)) || { items: [] }).items.find((i) => i.id === r.id);
        item = listed ? { ...listed.entry, originalPath: listed.originalPath } : null;
      }
      return {
        incomingTitle: "元に戻す項目", incoming: item,
        incomingWhere: item ? `ごみ箱（元の場所: ${parentPath(item.originalPath) || "/"}）` : "ごみ箱",
        existing: await io.stat(ctx.mount, r.error.path),
        incomingMount: io.mountOf(ctx.mount), mount: io.mountOf(ctx.mount),
      };
    }
    const src = ctx.source || { mount: ctx.mount, mode: "copy" };
    const destMount = ctx.dest ? ctx.dest.mount : ctx.mount;
    const cross = src.mount !== destMount;
    const at = (id, path) => (cross ? `${label(id)}: ${path}` : path);
    const [incoming, existing] = await Promise.all([io.stat(src.mount, r.src), io.stat(destMount, r.error.path)]);
    return {
      incomingTitle: src.mode === "cut" ? "移動する項目" : "コピーする項目", incoming, existing,
      incomingWhere: at(src.mount, parentPath(r.src) || "/"),
      where: at(destMount, parentPath(r.error.path) || "/"),
      incomingMount: io.mountOf(src.mount), mount: io.mountOf(destMount),
    };
  }

  /** コマンドを BackEnd に送る（POST commands/<id>）。ジョブなら終わるまで待ち、ふつうの応答と同じ形で返す。 */
  async function sendCommand(cmd, body) {
    const res = await io.command(cmd.id, body);
    return res && res.job ? waitJob(cmd, res.job) : res;
  }

  /**
   * ジョブの進み具合を JOB_POLL_MS ごとに問い合わせ、ステータスバーに出す。JOB_DIALOG_MS を過ぎても終わらなければ、
   * 進み具合のダイアログ（［中止］付き）も出す。終わったら result を返す（誤りなら、ふつうの応答と同じに投げる）。
   */
  async function waitJob(cmd, id) {
    const started = Date.now();
    let dialog = null;
    try {
      for (;;) {
        const job = await io.job(id);
        io.progress({ label: cmd.label, done: job.done, total: job.total, item: job.item });
        if (job.state === "done") {
          if (job.error) {
            throw Object.assign(new Error(job.error.message), job.error, { status: job.status, fromJob: true });
          }
          return job.result;
        }
        if (!dialog && Date.now() - started >= JOB_DIALOG_MS) {
          dialog = parts.progress({ title: cmd.label, onCancel: () => io.cancelJob(id).catch(() => {}) });
        }
        if (dialog) dialog.update(job);
        await new Promise((r) => setTimeout(r, JOB_POLL_MS));
      }
    } finally {
      if (dialog) dialog.close();
      io.progress(null);
    }
  }

  /** onItemError: 失敗した項目の code ごとに。chooseConflict は、その項目だけを答え付きで送り直す。 */
  async function resolveItemErrors(cmd, ctx, results, answers = null) {
    const handlers = cmd.onItemError || {};
    const final = [];
    const pending = [];
    for (const r of results) {
      const h = !r.ok && r.error && handlers[r.error.code];
      if (h && !Array.isArray(h) && h.part === "chooseConflict") pending.push(r);
      else final.push(r);
    }
    let applyAll = null;
    for (let i = 0; i < pending.length; i++) {
      const c = pending[i];
      let choice = applyAll;
      if (!choice) {
        const answer = await parts.chooseConflict({
          name: baseName(c.error.path), where: parentPath(c.error.path) || "/", remaining: pending.length - i - 1,
          ...(await conflictDetails(cmd, ctx, c)),
        });
        if (!answer) {
          // 取り消し: 残りは何もしない（スキップと同じ）
          final.push(...pending.slice(i).map((x) => ({ ...x, ok: true, skipped: true })));
          break;
        }
        choice = answer.choice;
        if (answer.all) applyAll = choice;
      }
      const one = c.id ? { ...ctx, items: [], ids: [c.id] }
        : ctx.source ? { ...ctx, source: { ...ctx.source, paths: [c.src] } }
          : { ...ctx, items: (ctx.items || []).filter((e) => e.path === c.src) };
      try {
        const res = await sendCommand(cmd, bodyOf(one, null, { ...(answers || {}), onConflict: choice }));
        final.push(...(res.results || []));
      } catch (err) {
        final.push({ ...c, error: { code: err.code, message: err.message, path: c.error.path } });
      }
    }
    return final;
  }

  /**
   * 結果の語彙をする。retryInput があれば true を返す（入力に戻る）。
   * report の知らせに、続く offer（［元に戻す］）を付けて 1 つにする（0.x と同じ）。
   */
  async function doEffects(effects, vars, texts, { results = [], ctx, cmd, full = ctx, denied = [] }) {
    let retry = false;
    let pendingMessage = null;
    const flush = () => {
      if (pendingMessage) io.message(pendingMessage.text, pendingMessage.kind, pendingMessage.action);
      pendingMessage = null;
    };
    const name = vars["$items.names"] && vars["$items.names"].length === 1 ? vars["$items.names"][0] : cmd.label;
    for (const raw of effects) {
      const e = fill(raw, vars, texts);
      switch (e.do) {
        case "report": {
          flush();
          const r = reportText(results, e.done || "", e.fail || "");
          if (r.text) pendingMessage = { ...r, action: null };
          break;
        }
        case "offer": {
          const target = io.commandsOf(ctx.mount).find((c) => c.id === e.run);
          const items = Array.isArray(e.items) ? e.items : [];
          if (target && items.length && pendingMessage) {
            const offerCtx = { mount: ctx.mount, view: (target.when && target.when.view) || "folder", items: [],
              ...((target.when && target.when.view) === "trash" ? { ids: items } : {}) };
            pendingMessage.action = { label: e.label, run: () => run(target, offerCtx, { skipWhen: true }) };
          }
          break;
        }
        case "message":
          flush();
          io.message(e.text || "", e.kind || "info");
          break;
        case "reload": {
          // 知らせは出し切らない（続く offer が［元に戻す］を付けるため）
          const select = Array.isArray(e.select) ? e.select.filter((x) => typeof x === "string") : null;
          await io.reload({ keepSelection: !select || !select.length, select: select && select.length ? select : null });
          if (typeof e.edit === "string" && e.edit) {
            // 作ったあとすぐ名前の変更へ（エクスプローラーと同じ）: 入力欄を使うコマンドを、その項目で動かす
            const itemCtx = io.editItem(e.edit);
            const editor = itemCtx && io.commandsOf(itemCtx.mount).find((c) => c.input && c.input.part === "inlineEdit"
              && evaluate(c, itemCtx).state === "enabled");
            if (editor) setTimeout(() => run(editor, itemCtx), 0);
          }
          break;
        }
        case "clipboard":
          // 切り取りは、動かす権限の無い項目も覚え、貼り付けたときにその項目だけ失敗にする（0.x と同じ）
          io.setClipboard(e.mode, full, denied);
          break;
        case "clipboardClear":
          io.clearClipboard();
          break;
        case "retryInput":
          retry = true;
          break;
        case "navigate":
          flush();
          io.navigate(e, name);
          break;
        case "browse":
          flush();
          io.browse(e, name);
          break;
        case "modal":
          // 状態表示のダイアログ（OK の型）。はい・いいえの型は runEnabled が先に扱う
          flush();
          await parts.modal(e.data || {});
          break;
        default:
          // 知らない語彙はしない（サーバも確かめているので、ふつうは来ない）
          console.warn("webFileDir: 知らない結果の語彙", e);
      }
    }
    flush();
    return retry;
  }

  /**
   * ファイルを送るコマンド（宣言の request が upload）: files（upload.js の形）を、ctx.dest へ 1 つずつ送る。
   * 直下の項目は、送る前に置けるかを尋ね（check）、同じ名前があれば onItemError の chooseConflict で尋ねる。
   * フォルダは先に作り、その中身を続けて送る（中の段は新しく作ったフォルダなので、衝突は尋ねない）。
   * 進み具合（バイト数）はブラウザで数え、ステータスバーと、JOB_DIALOG_MS を過ぎたら進み具合のダイアログに出す。
   * 結果は直下の項目ごと（と、フォルダの中で失敗したもの）の一括の結果にして、then に渡す。
   */
  async function runUpload(cmd, ctx, files, vars, texts) {
    const dest = ctx.dest;
    const groups = groupUploads(files);
    const sizeOf = (list) => list.reduce((n, f) => n + (f.kind === "file" ? f.file.size : 0), 0);
    const total = sizeOf(files);
    const handler = (cmd.onItemError || {}).exists;
    const asks = !!handler && !Array.isArray(handler) && handler.part === "chooseConflict";
    const results = [];
    const started = Date.now();
    let sent = 0; // 送り終えた（か、送らないと決めた）バイト数
    let cancelled = false;
    let current = null; // 今の送信 {promise, abort}
    let dialog = null;
    let applyAll = null;

    const show = (loaded, item) => {
      const done = Math.min(sent + loaded, total);
      const p = { label: cmd.label, done, total, item, text: `${formatSize(done)} / ${formatSize(total)}` };
      io.progress(p);
      if (!dialog && Date.now() - started >= JOB_DIALOG_MS) {
        dialog = parts.progress({ title: cmd.label, onCancel: () => {
          cancelled = true;
          if (current) current.abort();
        } });
      }
      if (dialog) dialog.update(p);
    };

    async function put(f, rel, extra = {}) {
      const check = !!extra.check;
      const params = { mount: dest.mount, dest: dest.path, path: rel, kind: f.kind, ...extra,
        check: check ? "1" : null,
        // 元の更新日時を継ぐ（ファイルだけ。フォルダの日時はブラウザから分からない）
        mtime: f.kind === "file" && !check && f.file.lastModified ? f.file.lastModified / 1000 : null };
      current = io.upload(cmd.id, params, f.kind === "file" && !check ? f.file : null, (n) => show(n, rel));
      try {
        return await current.promise;
      } finally {
        current = null;
      }
    }

    /** 同じ名前の項目があったときの答え（"overwrite" | "skip" | "rename"）。取り消しなら null。 */
    async function choose(f, err, remaining) {
      if (applyAll) return applyAll;
      const existing = await io.stat(dest.mount, err.path);
      const mount = io.mountOf(dest.mount);
      // 手元の項目の拡張子は BackEnd が決めるものなので、名前が同じ今ある項目のものを借りる
      const incoming = { name: baseName(f.rel), kind: f.kind, ext: existing ? existing.ext : "",
        attrs: f.kind === "file" ? { size: f.file.size, mtime: f.file.lastModified / 1000 } : {} };
      const answer = await parts.chooseConflict({
        name: baseName(err.path), where: parentPath(err.path) || "/", remaining, incomingTitle: "アップロードする項目",
        incoming, incomingWhere: "このコンピューター", existing, incomingMount: mount, mount,
      });
      if (!answer) return null;
      if (answer.all) applyAll = answer.choice;
      return answer.choice;
    }

    // 結果の src は、ほかのコマンドと同じくマウントの中のパスにする（知らせに名前を出す）
    const at = (rel) => `${dest.path === "/" ? "" : dest.path}/${rel}`;
    const failure = (rel, err) => ({ src: at(rel), ok: false,
      error: { code: err.code || "internal", message: err.message, path: err.path || at(rel) } });

    try {
      for (let i = 0; i < groups.length; i++) {
        const { top, children } = groups[i];
        const groupSize = sizeOf([top, ...children]);
        const base = sent;
        if (cancelled) {
          results.push(failure(top.rel, { code: "cancelled", message: "中止しました" }));
          continue;
        }
        let res = null;
        let choice = null;
        try {
          for (;;) {
            const onConflict = choice || null;
            try {
              if (top.kind === "file") {
                // 送る前に、置けるか（同じ名前・大きさ・拡張子）を尋ねる。大きなファイルを送ってから断られないように
                const c = await put(top, top.rel, { check: true, size: top.file.size, onConflict });
                res = c.skipped ? c : await put(top, top.rel, { onConflict });
              } else {
                res = await put(top, top.rel, { onConflict });
              }
              break;
            } catch (err) {
              if (err.code !== "exists" || !asks || choice) throw err;
              choice = await choose(top, err, groups.length - i - 1);
              if (!choice) {
                // 取り消し: これと残りは送らない（スキップと同じ。貼り付けの衝突と同じ）
                results.push(...groups.slice(i).map((g) => ({ src: at(g.top.rel), ok: true, skipped: true })));
                return results;
              }
            }
          }
        } catch (err) {
          if (err.code === "cancelled") cancelled = true;
          results.push(failure(top.rel, err));
          sent = base + groupSize;
          continue;
        }
        if (res.skipped) {
          results.push({ src: at(top.rel), ok: true, skipped: true });
          sent = base + groupSize;
          continue;
        }
        if (top.kind === "file") sent += top.file.size;
        results.push({ src: at(res.entry.name), ok: true, entry: res.entry });
        // フォルダの中身。直下のフォルダを別の名前で作ったら（両方残す）、その名前の下へ送る
        const failedDirs = [];
        for (const c of children) {
          const rel = res.entry.name + c.rel.slice(top.rel.length);
          const size = c.kind === "file" ? c.file.size : 0;
          if (cancelled) {
            results.push(failure(rel, { code: "cancelled", message: "中止しました" }));
            break;
          }
          if (failedDirs.some((d) => rel.startsWith(`${d}/`))) {
            sent += size; // 親を作れなかったので送らない（親の失敗として知らせてある）
            continue;
          }
          try {
            if (c.kind === "file" && size > CHECK_FIRST) await put(c, rel, { check: true, size });
            await put(c, rel);
          } catch (err) {
            if (err.code === "cancelled") cancelled = true;
            results.push(failure(rel, err));
            if (c.kind === "dir") failedDirs.push(rel);
          }
          sent += size;
        }
        sent = base + groupSize;
      }
      return results;
    } finally {
      if (dialog) dialog.close();
      io.progress(null);
    }
  }

  /** 応答が、ページへ移る・表示するだけか（そのときは変更の知らせを出さない）。 */
  const onlyNavigation = (res) => res.result === undefined && res.results === undefined
    && (res.effects || []).every((e) => ["navigate", "browse", "modal"].includes(e.do));

  /**
   * コマンドを動かす。skipWhen … 条件を確かめない（［元に戻す］から。サーバは確かめる）。
   * 入力・確認の途中に別のコマンドが動かないことは、画面が守る（名前の入力欄・ダイアログの中のキーは受けない、
   * ダイアログはモーダル）。ここで鍵をかけると、入力をやめた直後の操作が、実行役の続きが動くまで捨てられる。
   */
  async function run(cmd, ctx, { skipWhen = false } = {}) {
    const ev = skipWhen ? { state: "enabled", reason: "", denied: [] } : evaluate(cmd, ctx);
    if (ev.state !== "enabled") {
      if (ev.reason) io.message(ev.reason, "error");
      return;
    }
    await runEnabled(cmd, ctx, ev.denied);
  }

  async function runEnabled(cmd, ctx, denied) {
    const texts = cmd.texts || {};
    const send = without(ctx, denied);
    const deniedWord = cmd.when && cmd.when.items ? AUTH_WORDS[cmd.when.items.auth] : AUTH_WORDS.move;
    const deniedResults = denied.map((src) => ({
      src, ok: false, error: { code: "forbidden", message: `${deniedWord}権限がありません`, path: src } }));
    const vars = variables(send);
    if (cmd.confirm) {
      const c = fill(cmd.confirm, vars, texts);
      if (denied.length) c.detail = `${c.detail || ""}${deniedWord}権限の無い ${denied.length} 個の項目は含めません。`;
      if (!(await parts.confirm(c))) return;
    }
    if (cmd.request === "upload") {
      // 送るものは、ドロップなら文脈に、そうでなければ部品 uploadDialog で選ばせる
      let files = send.files || null;
      if (!files) {
        files = await parts.uploadDialog({ ...fill(cmd.input || {}, vars, texts), dest: send.dest });
        if (!files) return; // 取り消し
      }
      if (!files.length) return;
      const results = await runUpload(cmd, send, files, vars, texts);
      Object.assign(vars, { $result: null }, doneOf(results));
      io.changed();
      await doEffects(cmd.then || [], vars, texts, { ctx: send, cmd, results });
      return;
    }
    let input = null;
    let inputError = ""; // 入力に戻ったとき、フォームに出す誤りの理由
    let answers = null; // 状態表示のダイアログ（はい・いいえ）の答え {名前: "yes" | "no"}
    let asked = false; // 答えを付けて送り直すところ（入力はもうしてある）
    for (;;) {
      if (cmd.input && !asked) {
        const opts = fill(cmd.input, vars, texts);
        const initial = typeof opts.value === "string" ? opts.value : "";
        if (cmd.input.part === "inlineEdit") {
          input = await parts.inlineEdit(send, { value: input ?? initial, select: opts.select || "all" });
        } else if (cmd.input.part === "textEdit") {
          input = await parts.textEdit(send, { ...opts, value: input, error: inputError });
        } else {
          input = await parts.prompt({ ...opts, value: input ?? initial, error: inputError });
        }
        if (input == null) return; // 取り消し
        if (cmd.input.part === "inlineEdit" && input === initial) {
          parts.endInput(true); // 変えていない（名前がそのまま）なら送らない
          return;
        }
        vars.$input = input;
      }
      if (cmd.request !== "server") {
        await doEffects(cmd.then || [], vars, texts, { ctx: send, cmd, results: deniedResults, full: ctx, denied });
        return;
      }
      let res;
      try {
        res = await sendCommand(cmd, bodyOf(send, input, answers));
      } catch (err) {
        const handler = (cmd.onError || {})[err.code];
        if (handler) {
          const retry = await doEffects(handler, vars, texts, { ctx: send, cmd });
          if (retry && cmd.input) {
            inputError = err.message;
            if (cmd.input.part === "inlineEdit") parts.endInput(false); // 入力欄を開いたまま、もう一度
            continue;
          }
        } else if (err.code === "cancelled") {
          io.message(err.message, "info"); // 中止は失敗ではない。BackEnd の文（「途中で中止しました」など）をそのまま
        } else {
          io.message(`「${cmd.label}」に失敗しました: ${err.message}`, "error");
        }
        if (cmd.input && cmd.input.part === "inlineEdit") parts.endInput(true);
        io.changed();
        // ジョブは途中まで行っていることがあるので、中止・失敗でも一覧を読み直す
        if (err.fromJob) await io.reload({ keepSelection: true });
        return;
      }
      if (cmd.input && cmd.input.part === "inlineEdit") parts.endInput(true);
      // BackEnd が「はい・いいえ」を尋ねてきたら、答えを付けて同じコマンドを送り直す（then はまだしない）
      const ask = (res.effects || []).find((e) => e.do === "modal" && e.data && e.data.type === "yesno");
      if (ask) {
        const answer = await parts.modal(ask.data);
        answers = { ...(answers || {}), [ask.data.answer]: answer === "yes" ? "yes" : "no" };
        asked = true;
        continue;
      }
      let results = res.results ? await resolveItemErrors(cmd, send, res.results, answers) : [];
      results = [...results, ...deniedResults];
      Object.assign(vars, { $result: res.result ?? null }, doneOf(results));
      if (!onlyNavigation(res)) io.changed();
      await doEffects([...(cmd.then || []), ...(res.effects || [])], vars, texts, { ctx: send, cmd, results });
      return;
    }
  }

  return { run };
}
