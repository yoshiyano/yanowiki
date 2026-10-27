// 組み立て。部品を作って並べ、操作（actions）と読み込みをつなぐ。
// 変更の操作・開く・独自のコマンドは、サーバが宣言したコマンド（mounts の commands）を実行役（runner.js）が動かす。
// 画面に組み込みで実装して宣言によらず常に動かすのは、閲覧の操作（移動・選択・フォルダに入る・表示形式・並べ替え・
// 列の幅・隠しファイル）と、クリップボード・ドラッグの扱い（Wiki「1.0.0 の設計の全体像」）。

import { api } from "./api.js";
import { loadClipboard, saveClipboard, watchClipboard } from "./clipboard.js";
import { openMenu } from "./contextmenu.js";
import { setupDnd } from "./dnd.js";
import { confirmDialog, conflictDialog, modalDialog, progressDialog, promptDialog, setDialogHost, textEditDialog,
  uploadDialog } from "./dialog.js";
import { formatSize } from "./format.js";
import { h, loadIcons } from "./dom.js";
import { isHidden } from "./filetypes.js";
import { splitPath, joinPath, parentPath, sameLocation, formatHash } from "./location.js";
import { allows, attributesOf, canOpenEntry, canPutInto, mountOf, selectedEntries } from "./model.js";
import { loadPref, savePref } from "./prefs.js";
import { createRouter, createMemoryRouter } from "./router.js";
import { createRunner, evaluate, keyOf, ordered } from "./runner.js";
import { emptySelection, pruneSelection } from "./selection.js";
import { effectiveSort, isSort, sortEntries } from "./sort.js";
import { createStore } from "./state.js";
import { createAddressBar } from "./addressbar.js";
import { createStatusBar } from "./statusbar.js";
import { createToolbar, VIEW_MODES } from "./toolbar.js";
import { createTree } from "./tree.js";
import { createView } from "./view.js";
import { setupLiveUpdate } from "./live.js";
import { cameFromChild, createPrefetcher, listCache } from "./prefetch.js";
import { registerMountIcons } from "./icons.js";

const isView = (v) => VIEW_MODES.some(([m]) => m === v);

// ある画面で変更したことを、同じページのほかの画面（二画面モードのもう片方）へ知らせるイベント
const CHANGED_EVENT = "webfiledir:changed";

/** 失敗してもよい読み込み（衝突のダイアログの詳細。読めなければ詳細なしで尋ねる）。 */
async function maybe(promise) {
  try {
    return await promise;
  } catch {
    return null;
  }
}

/**
 * 画面を 1 つ作る。
 * options（二画面モードの枠 shell.js が渡す。1 つだけ置くときは省いてよい）:
 *   paneId        … 画面の名前（変更の知らせで、自分が出したものを見分ける）
 *   router        … "hash"（URL のハッシュとブラウザの履歴。既定）か "memory"（画面の中だけの履歴）
 *   storageKey    … router が "memory" のとき、今の場所を覚える sessionStorage のキー
 *   fallbackLocation() … router が "memory" で、覚えた場所が無いときの最初の場所
 *   initialLocation … router が "memory" のとき、覚えた場所より先に使う最初の場所 {mount, path, trash}
 *   onToggleDual  … ツールバーの［二画面］を押したとき（無ければボタンを出さない）
 *   onOpenInOther(mount, path) … フォルダを隣の画面で表示するとき（結果の語彙の browse・target "other"）。
 *                    無ければ（二画面を止めた画面）知らせるだけ
 *   dialogHost    … false ならダイアログの置き場所にしない（片付けることのある画面）
 *   folderUpload  … false ならフォルダごとのアップロードをさせない（createShell の folderUpload）
 * 戻り値の destroy() で片付ける（自動更新の接続・リスナーを外し、要素を空にする）。
 */
export function createApp(root, options = {}) {
  const {
    paneId = "main", router: routerKind = "hash", storageKey = "webfiledir.pane",
    fallbackLocation = () => null, initialLocation = null, onToggleDual = null, onOpenInOther = null, dialogHost = true,
    folderUpload = true,
  } = options;
  const store = createStore({
    mounts: [],
    location: null,        // {mount, path, trash}
    dir: null,             // 今いるフォルダ自身の項目（一覧の dir。権限を見る）。ごみ箱・読めなかったときは null
    entries: [],           // API から返ったもの（key を足してある）
    visibleEntries: [],    // 隠しファイルを除き、並べ替えたもの
    loading: true,         // 最初の一覧を読み終えるまでは読み込み中
    error: null,           // 中身を読めなかったとき {code, message}
    ...emptySelection(),   // selection（key の集合）・anchor・focus
    editing: null,         // 部品 inlineEdit で名前を入力している項目の key
    editValue: "",         // その入力欄の初めの値
    editSelect: "stem",    // 入って最初に選ぶ範囲（"stem" = 拡張子の手前まで / "all"）
    view: loadPref("view", "details", isView),
    // 詳細表示の列の幅 {マウント: {列のキー: px}}（操作者が変えたものだけ。Wiki「画面設計 > 列の幅」）
    columnWidths: loadPref("columnWidths", {}, (v) => !!v && typeof v === "object" && !Array.isArray(v)),
    // 並べ替えのキーは名前か属性のキー。今のマウントの属性に無いキーなら名前で並べる（effectiveSort）
    sort: loadPref("sort", { key: "name", desc: false }, isSort),
    trashSort: loadPref("trashSort", { key: "deletedAt", desc: true }, isSort),
    showHidden: loadPref("showHidden", false, (v) => typeof v === "boolean"),
    clipboard: loadClipboard(), // 画面の中だけのクリップボード {mount, paths, mode, denied?}
    message: null,         // ステータスバーの知らせ {text, kind, action?}
    progress: null,        // ジョブの進み具合 {label, done, total, item}（ステータスバーのプログレスバー）
    canBack: false,
    canForward: false,
    refreshToken: 0,       // 増やすとツリーが読み直す
    treeOpened: "",        // ツリーで開いていて中身を出している段（"mount\npath" を \0 でつないだもの）。自動更新が見張る
    externalChange: null,  // 自動更新の知らせ {seq, mount, path} / {seq, mount, trash} / {seq, all}
    dual: false,           // 二画面モードか（ツールバーの［二画面］の押された見た目に使う）
  });

  /** entries・sort・showHidden のどれかを変えるときは、ここを通して visibleEntries を作り直す。 */
  function setListing(patch) {
    const s = { ...store.get(), ...patch };
    const trash = !!(s.location && s.location.trash);
    const shown = s.showHidden ? s.entries : s.entries.filter((e) => !isHidden(e));
    const attributes = attributesOf(s);
    const sort = effectiveSort(trash ? s.trashSort : s.sort, attributes);
    const visibleEntries = sortEntries(shown, sort, { foldersFirst: !trash, attributes });
    const sel = pruneSelection({ selection: s.selection, anchor: s.anchor, focus: s.focus },
      visibleEntries.map((e) => e.key));
    store.set({ ...patch, visibleEntries, ...sel });
  }

  let messageTimer = null;
  const prefetcher = createPrefetcher(); // 近い親子フォルダの先読み（覚えは画面どうしで共有、列は画面ごと）
  let cameFrom = null; // 上へ移ってきたときの遷移元の子の名前（cameFromChild）。先読みの順に使う
  const router = routerKind === "memory"
    ? createMemoryRouter(store, { storageKey, fallback: fallbackLocation, initial: initialLocation })
    : createRouter(store);

  function message(text, kind = "info", action = null) {
    clearTimeout(messageTimer);
    store.set({ message: { text, kind, action } });
    // ［元に戻す］のある知らせは、押す時間があるよう長めに出す
    const ms = kind === "error" ? 10000 : action ? 8000 : 4000;
    messageTimer = setTimeout(() => store.set({ message: null }), ms);
  }

  // --- コマンドの文脈（runner.js の ctx） ---

  const childPath = (name) => joinPath([...splitPath(store.get().location.path), name]);
  const commandsOf = (mount) => (mountOf(store.get(), mount) || { commands: [] }).commands || [];
  const withPath = (entry) => ({ ...entry, path: childPath(entry.name) });

  /**
   * コマンド cmd を、今の選択（items を渡せばそれ）で動かすときの文脈。
   * 貼り付け（when.clipboard）はクリップボードを運ぶ項目にし、先は「このフォルダに貼り付け」なら選んだフォルダ、
   * それ以外は今いるフォルダ。
   */
  function contextFor(cmd, items = null) {
    const s = store.get();
    const loc = s.location;
    const trash = !!loc.trash;
    const chosen = (items || selectedEntries(s)).map((e) => (trash ? e : withPath(e)));
    const ctx = { mount: loc.mount, view: trash ? "trash" : "folder", dir: trash ? null : loc.path, dirEntry: s.dir,
      items: chosen };
    if (cmd.when && cmd.when.clipboard && s.clipboard) {
      const clip = s.clipboard;
      ctx.source = { mount: clip.mount, paths: clip.paths, mode: clip.mode, denied: clip.denied || [], unreadable: [] };
    }
    if (!trash) {
      const into = cmd.when && cmd.when.kinds && cmd.when.kinds.length === 1 && cmd.when.kinds[0] === "dir"
        && cmd.when.select === "one" && chosen.length === 1 ? chosen[0] : null;
      ctx.dest = into ? { mount: loc.mount, path: into.path, denied: !canPutInto(into) }
        : { mount: loc.mount, path: loc.path, denied: !canPutInto(s.dir) };
    }
    return ctx;
  }

  /** 今の場所で使えるコマンド（place の場所に出すもの）と、その判断。 */
  function commandsHere(place = null) {
    const s = store.get();
    if (!s.location) return [];
    return ordered(commandsOf(s.location.mount))
      .filter((c) => !place || (c.places || []).includes(place))
      .map((c) => ({ cmd: c, ev: evaluate(c, contextFor(c)) }))
      .filter(({ ev }) => ev.state !== "hidden");
  }

  // --- 部品（Wiki「画面の部品と結果の語彙 > 部品」） ---

  // 部品 inlineEdit: 一覧の中の入力欄（view.js が描く）。submitEdit / cancelEdit で答えが返る
  let edit = null; // {resolve, finish}

  const parts = {
    confirm: (opts) => confirmDialog(opts),
    prompt: (opts) => promptDialog(opts),
    modal: (data) => modalDialog(data),
    progress: (opts) => progressDialog(opts),
    chooseConflict: (opts) => conflictDialog(opts),
    uploadDialog({ dest, ...opts }) {
      const label = (mountOf(store.get(), dest.mount) || { label: dest.mount }).label;
      return uploadDialog({ ...opts, dest: `${label}: ${dest.path}`, folders: folderUpload });
    },
    /**
     * 部品 textEdit: 選んだファイルの中身を読み（UTF-8 のテキストで maxSize まで）、編集のダイアログを出す。
     * 元の改行が CRLF なら、保存する全体も CRLF に戻す（テキスト欄は LF にそろえるため）。BOM はそのまま残す。
     */
    async textEdit(ctx, { title, maxSize, value, error }) {
      const item = ctx.items[0];
      let text = value;
      if (text == null) {
        const tooBig = `「${item.name}」は大きすぎて編集できません（上限は ${formatSize(maxSize)}）`;
        const size = item.attrs ? item.attrs.size : null;
        if (size != null && size > maxSize) {
          message(tooBig, "error");
          return null;
        }
        let buf;
        try {
          buf = await api.readFile(ctx.mount, item.path);
        } catch (err) {
          message(`「${item.name}」を読めませんでした: ${err.message}`, "error");
          return null;
        }
        if (buf.byteLength > maxSize) {
          message(tooBig, "error");
          return null;
        }
        try {
          text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(buf);
        } catch {
          text = null;
        }
        if (text == null || text.includes("\0")) {
          message(`「${item.name}」は UTF-8 のテキストではないので編集できません`, "error");
          return null;
        }
      }
      const crlf = text.includes("\r\n");
      const edited = await textEditDialog({ title, value: text, error });
      if (edited == null) return null;
      return crlf ? edited.replace(/\r?\n/g, "\r\n") : edited;
    },
    inlineEdit(ctx, { value, select }) {
      const item = ctx.items[0];
      return new Promise((resolve) => {
        edit = { resolve, finish: null };
        store.set({ editing: item.key ?? item.name, editValue: value, editSelect: select });
      });
    },
    /** 実行役が入力を終える: ok なら入力欄を閉じる。false なら開いたまま（もう一度入力してもらう）。 */
    endInput(ok) {
      const e = edit;
      if (e && e.finish) e.finish(ok);
      if (ok) {
        edit = null;
        store.set({ editing: null });
      }
    },
  };

  // --- 実行役に渡す関数（runner.js の io） ---

  function setClipboard(clip) {
    store.set({ clipboard: clip });
    saveClipboard(clip);
  }

  const io = {
    command: (id, body) => api.command(id, body),
    upload: (id, params, body, onProgress) => api.upload(id, params, body, onProgress),
    job: (id) => api.job(id),
    cancelJob: (id) => api.cancelJob(id),
    progress: (p) => store.set({ progress: p }),
    stat: (mount, path) => maybe(api.stat(mount, path)),
    trash: (mount) => maybe(api.trash(mount)),
    commandsOf,
    mountOf: (mount) => mountOf(store.get(), mount),
    message,
    changed() {
      // どのフォルダが変わったか（移動先・コピー先など）はここでは分からないので、覚えた一覧をすべて捨てる。
      // 捨てないと、変えたあとに移ったフォルダで古い一覧が一瞬出る（覚えは隣の画面とも共有している）
      listCache.clear();
      store.set({ refreshToken: store.get().refreshToken + 1 });
      window.dispatchEvent(new CustomEvent(CHANGED_EVENT, { detail: { source: paneId } }));
    },
    reload: ({ keepSelection = true, select = null } = {}) =>
      loadList(store.get().location, select ? { select } : { keepSelection }),
    /** 名前 name の項目を選び、その項目 1 つの文脈を返す（作ったあとに名前の変更へ入る）。 */
    editItem(name) {
      const s = store.get();
      const entry = s.visibleEntries.find((e) => e.name === name);
      if (!entry || s.location.trash) return null;
      store.set({ selection: new Set([entry.key]), anchor: entry.key, focus: entry.key });
      return { mount: s.location.mount, view: "folder", dir: s.location.path, dirEntry: s.dir,
        items: [withPath(entry)] };
    },
    setClipboard(mode, ctx, denied) {
      const paths = ctx.items.map((e) => e.path);
      setClipboard({ mount: ctx.mount, paths, mode, ...(denied.length ? { denied } : {}) });
      message(`${paths.length} 個の項目を${mode === "cut" ? "切り取りました" : "コピーしました"}`
        + (denied.length ? `（${denied.length} 個は動かす権限が無いので、貼り付けても動きません）` : "")
        + "。貼り付け先で Ctrl+V を押してください");
    },
    clearClipboard: () => setClipboard(null),
    navigate: (e, name) => navigate(e, name),
    browse: (e, name) => browse(e, name),
  };

  const runner = createRunner(io, parts);

  // --- 結果の語彙のうち、ページへ移る・フォルダを表示する（Wiki「画面の部品と結果の語彙 > 結果の語彙」） ---

  /** ページへ移る（navigate）。POST は見えないフォームで送る。javascript: などは開かない（サーバも確かめている）。 */
  function navigate(e, name) {
    const url = new URL(e.url, document.baseURI); // 相対の URL は画面（index.html）から
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      message(`「${name}」の開き先が使えない形です`, "error");
      return;
    }
    const params = Object.entries(e.params || {});
    if (e.method === "POST") {
      submitForm(url.href, params, e.target);
      return;
    }
    for (const [k, v] of params) url.searchParams.append(k, v); // GET は送る値をクエリに足す
    if (e.target === "_self") {
      window.location.assign(url.href);
      return;
    }
    openTab(url.href, name);
  }

  /**
   * POST で開く: 見えないフォームを作って送る（ページを開く形で POST を送れるのはフォームだけ）。
   * 新しいタブ（_blank）では、開いたページから、この画面を操作させないよう rel="noopener" を付ける。
   * フォームの送信は、ポップアップ抑止に止められても分からない（window.open と違い、止められたかを返さない）。
   */
  function submitForm(href, params, target) {
    const form = h("form", {
      method: "post", action: href, target: target === "_self" ? "_self" : "_blank",
      rel: target === "_self" ? null : "noopener", style: "display:none",
    }, params.map(([k, v]) => h("input", { type: "hidden", name: k, value: v })));
    document.body.append(form);
    form.submit();
    form.remove();
  }

  /** フォルダを表示する（browse）: この画面で / 新しいタブの webFileDir で / 隣の画面で。 */
  function browse({ mount, path, target }, name) {
    if (target === "_self") {
      router.go(mount, path);
    } else if (target === "_blank") {
      // 新しいタブも同じページ（組み込んだページならそのページ）を開き、最初の画面の場所をハッシュで渡す
      const url = new URL(window.location.href);
      url.hash = formatHash(mount, path);
      openTab(url.href, name);
    } else if (target === "other" && onOpenInOther) {
      onOpenInOther(mount, path);
    } else {
      message(`「${name}」を隣の画面で開けません（この画面では二画面を使えません）`, "error");
    }
  }

  function openTab(href, name) {
    const w = window.open(href, "_blank");
    if (w) {
      w.opener = null; // 開いたページから、この画面を操作させない
    } else {
      // 応答を待ってから開くので、ブラウザのポップアップ抑止に止められることがある。押せば開ける
      message(`「${name}」を新しいタブで開けませんでした（ポップアップが止められました）`, "error", {
        label: "開く", run: () => { const again = window.open(href, "_blank"); if (again) again.opener = null; },
      });
    }
  }

  // --- 操作 ---

  /** 開くコマンド（ダブルクリック・Enter は "default"、Shift は "shift"）。 */
  function openCommand(kind, slot) {
    const s = store.get();
    return ordered(commandsOf(s.location.mount)).find((c) => c.open === slot
      && ((c.when && c.when.kinds) || ["file", "dir"]).includes(kind)) || null;
  }

  const actions = {
    go: (mount, path) => router.go(mount, path),
    goTrash: (mount) => { if ((mountOf(store.get(), mount) || {}).trash) router.go(mount, "/", { trash: true }); },
    back: () => router.back(),
    forward: () => router.forward(),
    up() {
      const loc = store.get().location;
      const parent = loc && !loc.trash && parentPath(loc.path);
      if (parent != null) router.go(loc.mount, parent);
    },
    refresh() {
      store.set({ refreshToken: store.get().refreshToken + 1 });
      loadList(store.get().location, { keepSelection: true });
    },
    /** コマンドを今の選択で動かす（メニュー・ツールバー・キーから）。 */
    run(cmd, items = null) {
      if (!store.get().location) return;
      return runner.run(cmd, contextFor(cmd, items));
    },
    /** 文脈を渡してコマンドを動かす（ドロップ。dnd.js が文脈を作る）。 */
    runWith: (cmd, ctx) => runner.run(cmd, ctx),
    commandsOf,
    folderUpload,
    commandsHere,
    /**
     * 項目を開く（ダブルクリック・Enter）。modifier が "shift" なら Shift の開くコマンド。
     * フォルダの既定は、サーバに尋ねずこの画面で中に入る（0.x の設計者の指示を引き継ぐ）。
     */
    open(entry, { modifier = null } = {}) {
      const loc = store.get().location;
      if (loc.trash) {
        message("ごみ箱の中の項目は開けません。元に戻してから開いてください");
      } else if (entry.extra && entry.extra.unreachable) {
        message(entry.extra.unreachable === "outside"
          ? `「${entry.name}」はマウントの外を指すリンクなので開けません`
          : `「${entry.name}」は壊れたリンクです`, "error");
      } else if (!canOpenEntry(entry)) {
        message(`「${entry.name}」${entry.kind === "dir" ? "に入る" : "を開く"}権限がありません`, "error");
      } else {
        const cmd = openCommand(entry.kind, modifier === "shift" ? "shift" : "default");
        if (entry.kind === "dir" && !cmd) router.go(loc.mount, childPath(entry.name));
        else if (!cmd) message("このマウントではファイルを開けません", "error");
        else runner.run(cmd, contextFor(cmd, [entry]));
      }
    },
    /** 部品 inlineEdit の入力欄で確定した（view.js）。入力を終えてよければ true（誤りなら開いたまま false）。 */
    submitEdit(value) {
      const e = edit;
      if (!e) {
        store.set({ editing: null });
        return Promise.resolve(true);
      }
      return new Promise((finish) => {
        e.finish = finish;
        e.resolve(value);
      });
    },
    /** 入力欄を取り消した（Esc）。 */
    cancelEdit() {
      const e = edit;
      edit = null;
      store.set({ editing: null });
      if (e) e.resolve(null);
    },
    /** コピー・切り取りを解除する（ステータスバーの × と、選択が無いときの Esc）。 */
    clearClipboard() {
      const clip = store.get().clipboard;
      if (!clip) return;
      setClipboard(null);
      message(`${clip.mode === "cut" ? "切り取り" : "コピー"}を解除しました`);
    },
    /** 今のマウントの列の幅を変える（width が null なら、変える前の幅＝属性の定義の幅に戻す）。 */
    setColumnWidth(key, width) {
      const s = store.get();
      if (!s.location) return;
      const mount = s.location.mount;
      const widths = { ...(s.columnWidths[mount] || {}) };
      if (width == null) delete widths[key];
      else widths[key] = width;
      const columnWidths = { ...s.columnWidths, [mount]: widths };
      store.set({ columnWidths });
      savePref("columnWidths", columnWidths);
    },
    setView(view) {
      store.set({ view });
      savePref("view", view);
    },
    setSort(sort) {
      if (store.get().location && store.get().location.trash) {
        setListing({ trashSort: sort });
        savePref("trashSort", sort);
      } else {
        setListing({ sort });
        savePref("sort", sort);
      }
    },
    setShowHidden(showHidden) {
      setListing({ showHidden });
      savePref("showHidden", showHidden);
    },
    message,
    toggleDual: onToggleDual,
    openItemMenu: (x, y) => openMenu(root, x, y, tidy(itemMenu())),
    openBackgroundMenu: (x, y) => openMenu(root, x, y, tidy(backgroundMenu())),
  };

  // --- 右クリックメニュー（宣言の places の item・background から作る） ---

  /** 続いた・端の区切りを詰める。 */
  function tidy(items) {
    return items.filter((it, i) => it !== "-" || (i > 0 && i < items.length - 1 && items[i - 1] !== "-"));
  }

  /** 宣言をメニューの項目にする。組が変わるところに区切りを入れる。 */
  function menuItems(list, skip = new Set()) {
    const out = [];
    let group;
    for (const { cmd, ev } of list) {
      if (skip.has(cmd.id)) continue;
      if (out.length && cmd.group !== group) out.push("-");
      group = cmd.group;
      out.push({ label: cmd.label, shortcut: cmd.key || null, disabled: ev.state !== "enabled",
        action: () => actions.run(cmd) });
    }
    return out;
  }

  function itemMenu() {
    const s = store.get();
    const here = commandsHere("item");
    if (s.location.trash) return menuItems(here);
    const sel = selectedEntries(s);
    const one = sel.length === 1 ? sel[0] : null;
    const reachable = !!one && !(one.extra && one.extra.unreachable);
    // 開くコマンドを先に並べる（Wiki「画面設計 > ファイル・フォルダを開く」）。ファイルは既定を「開く（〇〇）」として
    // 先頭に、フォルダは画面の「開く」（中に入る）を先頭に置き、開くコマンドが続く
    const opens = here.filter(({ cmd }) => cmd.group === "open");
    const openItems = [];
    if (one && one.kind === "dir") {
      openItems.push({ label: "開く", shortcut: "Enter", disabled: !reachable || !canOpenEntry(one),
        action: () => actions.open(one) });
    }
    const byDefault = [...opens].sort((a, b) => (b.cmd.open === "default") - (a.cmd.open === "default"));
    for (const { cmd, ev } of byDefault) {
      const isDefault = cmd.open === "default";
      openItems.push({
        label: isDefault ? `開く（${cmd.label}）` : cmd.label,
        shortcut: isDefault ? "Enter" : cmd.open === "shift" ? "Shift+Enter" : null,
        disabled: ev.state !== "enabled", action: () => actions.run(cmd),
      });
    }
    if (!openItems.length) openItems.push({ label: "開く", shortcut: "Enter", disabled: true, action: () => {} });
    return [...openItems, "-", ...menuItems(here, new Set(opens.map(({ cmd }) => cmd.id)))];
  }

  function backgroundMenu() {
    const s = store.get();
    const sort = effectiveSort(s.sort, attributesOf(s));
    const sortItems = s.location.trash ? [] : [
      ...[{ key: "name", label: "名前" }, ...attributesOf(s)].map(({ key, label }) => ({
        label: `${label}順`, checked: sort.key === key, action: () => actions.setSort({ ...sort, key }),
      })),
      { label: "降順", checked: sort.desc, action: () => actions.setSort({ ...sort, desc: !sort.desc }) },
      "-",
    ];
    const viewItems = VIEW_MODES.map(([mode, , label]) => ({
      label, checked: s.view === mode, action: () => actions.setView(mode),
    }));
    return [
      ...menuItems(commandsHere("background")), "-", ...sortItems, ...viewItems, "-",
      { label: "最新の情報に更新", shortcut: "F5", action: actions.refresh },
    ];
  }

  // --- 読み込み ---

  let loadToken = 0;
  /**
   * 今の場所の中身を読む。
   * keepSelection: 選択を残す（無くなった項目は外す） / select: 読んだあとに選ぶ key
   */
  async function loadList(loc, { keepSelection = false, select = null, quiet = false } = {}) {
    const token = ++loadToken;
    if (!loc) return;
    const s = store.get();
    if (s.mounts.length && !s.mounts.some((m) => m.id === loc.mount)) {
      setListing({ entries: [], dir: null, loading: false,
        error: { code: "not_found", message: "指定したマウントはありません" } });
      return;
    }
    // 先に読んでおいた一覧（prefetch.js）があれば、移ったときはそれをすぐ出し、裏で読み直して合わせる
    // （2026-09-29 設計者の選択）。作ったあとの選択など、読み直しの指定があるときは使わない
    const cached = !loc.trash && !quiet && !keepSelection && select == null ? listCache.get(loc.mount, loc.path) : null;
    // quiet: 自動更新の読み直し。「読み込み中」を出さない（見ている一覧をちらつかせない）
    store.set({ ...(quiet || cached ? {} : { loading: true }), error: null, ...(keepSelection ? {} : emptySelection()) });
    // マウントの一覧を読む前（mounts が空）は、ごみ箱を見せるかまだ分からないので読みに行く（サーバも確かめる）
    const mountInfo = mountOf(s, loc.mount);
    if (loc.trash && mountInfo && !mountInfo.trash) {
      // ハッシュ（#trash/<mount>）で直接来たとき。ごみ箱を見せないマウント（ごみ箱のコマンドを止めた）では見せない
      setListing({ entries: [], dir: null, loading: false,
        error: { code: "not_found", message: "このマウントではごみ箱を使えません" } });
      return;
    }
    if (loc.trash) prefetcher.stop();

    /** 一覧の応答を画面に出す。権限の無いフォルダなら中身を見せない。 */
    function show(res, patch = {}) {
      const entries = res.entries.map((e) => ({ ...e, key: e.name }));
      const dir = res.dir;
      // 権限の無いフォルダ。ハッシュ・アドレスバーで直接来たときも中身を見せない（実ファイルなら、たいてい
      // サーバが先に「権限がありません」を返す。仮想構造では権限の値だけが頼り）
      const denied = !dir ? null : !allows(dir, "exec") ? "このフォルダに入る権限がありません"
        : !allows(dir, "read") ? "このフォルダの中身を見る権限がありません" : null;
      if (denied) {
        setListing({ entries: [], dir, loading: false, error: { code: "forbidden", message: denied } });
        return false;
      }
      setListing({ entries, dir, loading: false, error: null, ...patch });
      return true;
    }

    if (cached) show(cached.res);
    try {
      if (loc.trash) {
        const res = await api.trash(loc.mount);
        if (token !== loadToken) return; // 読んでいるあいだに別の場所へ移った
        setListing({
          entries: res.items.map((i) => ({
            ...i.entry, key: i.id, trashId: i.id, originalPath: i.originalPath, deletedAt: i.deletedAt,
          })),
          dir: null, loading: false,
        });
        return;
      }
      const res = await api.list(loc.mount, loc.path);
      listCache.put(loc.mount, loc.path, res);
      if (token !== loadToken) return; // 読んでいるあいだに別の場所へ移った
      const sel = select ? { selection: new Set(select), anchor: select[0], focus: select[0] } : {};
      if (!show(res, sel)) return;
      // 今いるフォルダを出し終えてから、近い親子フォルダを裏で読む（中心が変わったら前の残りは捨てる）
      prefetcher.start(loc.mount, loc.path, res.entries, cameFrom);
    } catch (err) {
      if (token !== loadToken) return;
      const text = err.code === "not_found" && !loc.trash ? `見つかりません: ${loc.path}` : err.message;
      setListing({ entries: [], dir: null, loading: false, error: { code: err.code, message: text } });
    }
  }

  // --- 部品を並べる ---

  const layout = h("div", { class: "fd-layout" }, [
    createToolbar(store, actions),
    createAddressBar(store, actions),
    h("div", { class: "fd-main" }, [createTree(store, actions), createView(store, actions)]),
    createStatusBar(store, actions),
  ]);
  loadIcons(); // アイコンのスプライトをページに埋め込む（まだなら）
  root.classList.add("fd-app");
  root.replaceChildren(layout);
  if (dialogHost) setDialogHost(root);
  setupDnd(root, store, actions);
  // ほかの画面・別のタブで切り取り・コピーしたとき
  const unwatchClipboard = watchClipboard((clipboard) => store.set({ clipboard }));
  const stopLive = setupLiveUpdate(store, root);

  // 自動更新: 今の場所が変わったと知らせが来たら、選択を残して読み直す。
  // 名前を入力しているあいだは読み直さない（入力欄が消える）。終わってから読み直す
  let liveReloadPending = false;
  function liveReload() {
    const s = store.get();
    if (s.editing != null) {
      liveReloadPending = true;
      return;
    }
    liveReloadPending = false;
    loadList(s.location, { keepSelection: true, quiet: true });
  }
  store.subscribe((s, changed) => {
    const c = s.externalChange;
    // 画面の外で変わったフォルダは、覚えた一覧を捨てる（移ったときに古いものを出さない）
    if (changed.has("externalChange") && c) {
      if (c.all) listCache.clear();
      else if (!c.trash) listCache.delete(c.mount, c.path);
    }
    if (changed.has("externalChange") && c && s.location) {
      const loc = s.location;
      const here = c.all || (c.mount === loc.mount && (c.trash ? loc.trash : !loc.trash && c.path === loc.path));
      if (here) liveReload();
    }
    if (changed.has("editing") && s.editing == null && liveReloadPending) liveReload();
  });

  // ほかの画面で変更があったら、ツリーと一覧を読み直す（自動更新が使えない環境でも、隣の画面は合わせる）
  const onOtherChanged = (e) => {
    if (e.detail.source === paneId || !store.get().location) return;
    store.set({ refreshToken: store.get().refreshToken + 1 });
    liveReload();
  };
  window.addEventListener(CHANGED_EVENT, onOtherChanged);

  let lastLocation = null;
  store.subscribe((s, changed) => {
    if (changed.has("location") && !sameLocation(s.location, lastLocation)) {
      // 場所が変わったら、入力の途中の部品は取り消す
      if (edit) actions.cancelEdit();
      // 上へ移ったなら、遷移元の子の名前を覚える（先読みで、名前の並びで隣接する子を先に読む）
      cameFrom = cameFromChild(lastLocation, s.location);
      lastLocation = s.location;
      loadList(s.location);
    }
  });

  // キー操作は、この画面の中にフォーカスがあるときだけ受ける（組み込んだページのキーを横取りしない）。
  // 入力欄（名前の変更・アドレスバー）に打っているときは受けない。閲覧のキーは画面の予約、ほかは宣言のキー
  root.addEventListener("keydown", (e) => {
    const t = e.target;
    if (e.isComposing || t.closest("input, textarea, select, dialog, .fd-menu")) return;
    if ((e.key === "Backspace" && !e.altKey) || (e.altKey && e.key === "ArrowLeft")) {
      e.preventDefault();
      actions.back();
      return;
    }
    if (e.altKey && e.key === "ArrowRight") {
      e.preventDefault();
      actions.forward();
      return;
    }
    if (e.altKey && e.key === "ArrowUp") {
      e.preventDefault();
      actions.up();
      return;
    }
    if (e.key === "F5") {
      e.preventDefault();
      actions.refresh();
      return;
    }
    const key = keyOf(e);
    if (!key || !store.get().location) return;
    const found = commandsHere().find(({ cmd }) => cmd.key === key);
    if (!found) return;
    e.preventDefault();
    actions.run(found.cmd);
  });

  let destroyed = false; // destroy() のあとに、読み込みの続きで場所を決めない
  (async () => {
    try {
      const mounts = await api.mounts();
      registerMountIcons(mounts); // プロバイダが持ち込んだアイコン（描く前に登録する）
      store.set({ mounts });
    } catch (err) {
      store.set({ loading: false, error: { code: err.code, message: `マウントの一覧を読めません: ${err.message}` } });
      return;
    }
    if (destroyed) return;
    router.start(); // 場所が決まると、上の subscribe が読み込む
    const s = store.get();
    if (!s.location && s.mounts.length) {
      // ハッシュが無いか読めないときは、最初のマウントの根へ
      router.go(s.mounts[0].id, "/", { replace: true });
    }
    if (options.focus !== false) root.querySelector(".fd-view").focus();
  })();

  function destroy() {
    destroyed = true;
    prefetcher.stop();
    stopLive();
    unwatchClipboard();
    window.removeEventListener(CHANGED_EVENT, onOtherChanged);
    clearTimeout(messageTimer);
    root.replaceChildren();
    root.classList.remove("fd-app");
  }

  return { store, actions, destroy };
}

