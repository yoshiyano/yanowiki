// 組み立て。部品を作って並べ、操作（actions）と読み込みをつなぐ。

import { api } from "./api.js";
import { loadClipboard, watchClipboard } from "./clipboard.js";
import { createCommands } from "./commands.js";
import { openMenu } from "./contextmenu.js";
import { setupDnd } from "./dnd.js";
import { setDialogHost } from "./dialog.js";
import { h, loadIcons } from "./dom.js";
import { isHidden } from "./filetypes.js";
import { splitPath, joinPath, parentPath, sameLocation, formatHash } from "./location.js";
import {
  allows, attributesOf, canCopyFrom, canDeleteEntries, canMoveEntries, canOpenEntry, canPutInto, capsOf, dirOpenMethodsOf, enabled,
  openMethodsOf, selectedEntries,
} from "./model.js";
import { parseFeatures } from "./features.js";
import { loadPref, savePref } from "./prefs.js";
import { createRouter, createMemoryRouter } from "./router.js";
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

/**
 * 画面を 1 つ作る。
 * options（二画面モードの枠 shell.js が渡す。1 つだけ置くときは省いてよい）:
 *   paneId        … 画面の名前（変更の知らせで、自分が出したものを見分ける）
 *   router        … "hash"（URL のハッシュとブラウザの履歴。既定）か "memory"（画面の中だけの履歴）
 *   storageKey    … router が "memory" のとき、今の場所を覚える sessionStorage のキー
 *   fallbackLocation() … router が "memory" で、覚えた場所が無いときの最初の場所
 *   initialLocation … router が "memory" のとき、覚えた場所より先に使う最初の場所 {mount, path, trash}
 *   onToggleDual  … ツールバーの［二画面］を押したとき（無ければボタンを出さない）
 *   onOpenInOther(mount, path) … フォルダを隣の画面で表示するとき（開く API の browse・target "other"）。
 *                    無ければ（二画面を止めた画面）知らせるだけ
 *   dialogHost    … false ならダイアログの置き場所にしない（片付けることのある画面）
 *   features      … 画面の機能の ON/OFF {機能の名前: false, ...}（features.js。書かなかった機能は ON）。
 *                    画面で出さないだけで API は止めない。知らない名前を書くと Error
 * 戻り値の destroy() で片付ける（自動更新の接続・リスナーを外し、要素を空にする）。
 */
export function createApp(root, options = {}) {
  const {
    paneId = "main", router: routerKind = "hash", storageKey = "webfiledir.pane",
    fallbackLocation = () => null, initialLocation = null, onToggleDual = null, onOpenInOther = null, dialogHost = true,
  } = options;
  const features = parseFeatures(options.features);
  const store = createStore({
    features,              // ON の画面の機能の集合（作ったあとは変えない）
    mounts: [],
    location: null,        // {mount, path, trash}
    dir: null,             // 今いるフォルダ自身の項目（一覧の dir。権限を見る）。ごみ箱・読めなかったときは null
    entries: [],           // API から返ったもの（key を足してある）
    visibleEntries: [],    // 隠しファイルを除き、並べ替えたもの
    loading: true,         // 最初の一覧を読み終えるまでは読み込み中
    error: null,           // 中身を読めなかったとき {code, message}
    ...emptySelection(),   // selection（key の集合）・anchor・focus
    editing: null,         // 名前を変えている項目の key
    view: loadPref("view", "details", isView),
    // 詳細表示の列の幅 {マウント: {列のキー: px}}（操作者が変えたものだけ。Wiki「画面設計 > 列の幅」）
    columnWidths: loadPref("columnWidths", {}, (v) => !!v && typeof v === "object" && !Array.isArray(v)),
    // 並べ替えのキーは名前か属性のキー。今のマウントの属性に無いキーなら名前で並べる（effectiveSort）
    sort: loadPref("sort", { key: "name", desc: false }, isSort),
    trashSort: loadPref("trashSort", { key: "deletedAt", desc: true }, isSort),
    showHidden: loadPref("showHidden", false, (v) => typeof v === "boolean"),
    clipboard: loadClipboard(), // 画面の中だけのクリップボード {mount, paths, mode}
    message: null,         // ステータスバーの知らせ {text, kind, action?}
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

  const commands = createCommands(store, {
    reload: (opts) => loadList(store.get().location, opts),
    // 変更したあとに呼ばれる。ほかの画面にも知らせる（隣の画面が同じフォルダを出していれば読み直す）
    refreshTree: () => {
      // どのフォルダが変わったか（移動先・コピー先など）はここでは分からないので、覚えた一覧をすべて捨てる。
      // 捨てないと、変えたあとに移ったフォルダで古い一覧が一瞬出る（覚えは隣の画面とも共有している）
      listCache.clear();
      store.set({ refreshToken: store.get().refreshToken + 1 });
      window.dispatchEvent(new CustomEvent(CHANGED_EVENT, { detail: { source: paneId } }));
    },
    message,
  });

  const actions = {
    ...commands,
    go: (mount, path) => router.go(mount, path),
    goTrash: (mount) => { if (features.has("trash")) router.go(mount, "/", { trash: true }); },
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
    /**
     * 項目を開く。開く経路を選んでサーバに尋ねる: method（経路の id。右クリックメニューから）、
     * modifier（"shift" など。押しながら開いたとき）、どちらも無ければ既定。
     * フォルダの既定は、サーバに尋ねずこの画面で中に入る（modifier の経路が無いときも同じ）。
     */
    open(entry, { method = null, modifier = null } = {}) {
      const loc = store.get().location;
      if (loc.trash) {
        message("ごみ箱の中の項目は開けません。元に戻してから開いてください");
      } else if (entry.extra && entry.extra.unreachable) {
        message(entry.extra.unreachable === "outside"
          ? `「${entry.name}」はマウントの外を指すリンクなので開けません`
          : `「${entry.name}」は壊れたリンクです`, "error");
      } else if (!canOpenEntry(entry)) {
        message(`「${entry.name}」${entry.kind === "dir" ? "に入る" : "を開く"}権限がありません`, "error");
      } else if (entry.kind === "dir") {
        const path = joinPath([...splitPath(loc.path), entry.name]);
        const methods = dirOpenMethodsOf(store.get());
        const chosen = (method && methods.find((o) => o.id === method))
          || (modifier && methods.find((o) => o.modifier === modifier));
        if (!chosen) router.go(loc.mount, path);
        else openWithServer(loc.mount, path, entry.name, chosen.id);
      } else {
        const methods = openMethodsOf(store.get());
        const chosen = (method && methods.find((o) => o.id === method))
          || (modifier && methods.find((o) => o.modifier === modifier)) || methods[0];
        if (!chosen) message("このマウントではファイルを開けません", "error");
        else openWithServer(loc.mount, joinPath([...splitPath(loc.path), entry.name]), entry.name, chosen.id);
      }
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
    openItemMenu: (x, y) => openMenu(root, x, y, withoutDisabledFeatures(itemMenu())),
    openBackgroundMenu: (x, y) => openMenu(root, x, y, withoutDisabledFeatures(backgroundMenu())),
  };

  // --- 項目を開く（Wiki「画面設計 > 項目を開く」） ---

  /**
   * サーバに開きかたを尋ね、返ってきたことをする: ページへ移る（navigate）、webFileDir の画面でフォルダを
   * 表示する（browse）。モーダルで表示する形（action: "modal"）は今後。
   */
  async function openWithServer(mount, path, name, method) {
    let res;
    try {
      res = await api.open(mount, path, method);
    } catch (err) {
      message(`「${name}」を開けませんでした: ${err.message}`, "error");
      return;
    }
    if (res.action === "modal") {
      message(`「${name}」はモーダルで表示する形ですが、この画面ではまだ表示できません`);
      return;
    }
    if (res.action === "browse") {
      browse(res, name);
      return;
    }
    // 相対の URL は画面（index.html）から。javascript: などは開かない（サーバも確かめている）
    const url = new URL(res.url, document.baseURI);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      message(`「${name}」の開き先が使えない形です`, "error");
      return;
    }
    const params = Object.entries(res.params || {});
    if (res.method === "POST") {
      submitForm(url.href, params, res.target);
      return;
    }
    for (const [k, v] of params) url.searchParams.append(k, v); // GET は送る値をクエリに足す
    if (res.target === "_self") {
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

  /** フォルダを表示する: この画面で / 新しいタブの webFileDir で / 隣の画面で。 */
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

  // --- 右クリックメニュー ---

  /** 止めた機能（feature）の項目を除き、続いた・端の区切りを詰める。 */
  function withoutDisabledFeatures(items) {
    const kept = items.filter((it) => it === "-" || !it.feature || features.has(it.feature));
    return kept.filter((it, i) => it !== "-" || (i > 0 && i < kept.length - 1 && kept[i - 1] !== "-"));
  }

  function itemMenu() {
    const s = store.get();
    const caps = capsOf(s);
    const sel = selectedEntries(s);
    if (s.location.trash) {
      return [
        { label: "元に戻す", feature: "trash", action: actions.restoreSelected, disabled: !caps.has("trash") },
        "-",
        { label: "完全に削除", feature: "purge", shortcut: "Delete", action: actions.purgeSelected, disabled: !caps.has("trash") },
      ];
    }
    const one = sel.length === 1 ? sel[0] : null;
    const canOpen = !!one && canOpenEntry(one);
    const canMove = canMoveEntries(sel);
    const canDelete = canDeleteEntries(sel);
    const folderPath = one && one.kind === "dir" && !(one.extra && one.extra.unreachable)
      ? joinPath([...splitPath(s.location.path), one.name]) : null;
    const reachable = !!one && !(one.extra && one.extra.unreachable);
    const shortcutOf = (o) => (o.modifier === "shift" ? "Shift+Enter" : null);
    return [
      // 開く経路をすべて並べる（Wiki「画面設計 > ファイル・フォルダを開く」）。ファイルは先頭が既定、
      // フォルダは画面の「開く」（中に入る）が既定で、サーバが返したフォルダの経路が続く
      ...(reachable && one.kind !== "dir" && openMethodsOf(s).length
        ? openMethodsOf(s).map((o, i) => ({
          label: i === 0 ? `開く（${o.label}）` : o.label,
          shortcut: i === 0 ? "Enter" : shortcutOf(o),
          action: () => actions.open(one, { method: o.id }), disabled: !canOpen,
        }))
        : reachable && one.kind === "dir"
          ? [{ label: "開く", shortcut: "Enter", action: () => actions.open(one), disabled: !canOpen },
            ...dirOpenMethodsOf(s).map((o) => ({
              label: o.label, shortcut: shortcutOf(o),
              action: () => actions.open(one, { method: o.id }), disabled: !canOpen,
            }))]
          : [{ label: "開く", shortcut: "Enter", action: () => actions.open(one), disabled: true }]),
      "-",
      { label: "切り取り", feature: "cut", shortcut: "Ctrl+X", action: actions.cutSelected,
        disabled: !caps.has("move") || !canMove },
      { label: "コピー", feature: "copy", shortcut: "Ctrl+C", action: actions.copySelected,
        disabled: !canCopyFrom(sel) },
      ...(folderPath ? [{ label: "このフォルダに貼り付け", feature: "paste", action: () => actions.paste(folderPath),
        disabled: !actions.canPaste(folderPath) }] : []),
      "-",
      { label: "名前の変更", feature: "rename", shortcut: "F2", action: actions.startRename,
        disabled: !one || !caps.has("rename") || !canMove },
      { label: "削除", feature: "delete", shortcut: "Delete", action: () => actions.deleteSelected(),
        disabled: !(caps.has("trash") || caps.has("delete")) || !canDelete },
      // ごみ箱の無いマウントでは「削除」も完全に削除になり、同じ項目が2つ並ぶので「完全に削除」を出さない
      ...(caps.has("trash") ? [{ label: "完全に削除", feature: "purge", shortcut: "Shift+Delete",
        action: () => actions.deleteSelected({ permanent: true }), disabled: !caps.has("delete") || !canDelete }] : []),
    ];
  }

  function backgroundMenu() {
    const s = store.get();
    const caps = capsOf(s);
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
    if (s.location.trash) {
      return [
        { label: "ごみ箱を空にする", feature: "purge", action: actions.emptyTrash, disabled: !caps.has("trash") || !s.entries.length },
        "-", ...viewItems, "-",
        { label: "最新の情報に更新", shortcut: "F5", action: actions.refresh },
      ];
    }
    return [
      { label: "貼り付け", feature: "paste", shortcut: "Ctrl+V", action: () => actions.paste(), disabled: !actions.canPaste() },
      "-",
      { label: "新しいフォルダ", feature: "newFolder", shortcut: "Ctrl+Shift+N", action: () => actions.newItem("dir"),
        disabled: !caps.has("mkdir") || !canPutInto(s.dir) },
      { label: "新しいテキスト ドキュメント", feature: "newFile", action: () => actions.newItem("file"),
        disabled: !caps.has("touch") || !canPutInto(s.dir) },
      "-", ...sortItems, ...viewItems, "-",
      { label: "最新の情報に更新", shortcut: "F5", action: actions.refresh },
    ];
  }

  // --- 読み込み ---

  let loadToken = 0;
  /**
   * 今の場所の中身を読む。
   * keepSelection: 選択を残す（無くなった項目は外す） / select: 読んだあとに選ぶ key / edit: 名前の変更に入る key
   */
  async function loadList(loc, { keepSelection = false, select = null, edit = null, quiet = false } = {}) {
    const token = ++loadToken;
    if (!loc) return;
    const s = store.get();
    if (s.mounts.length && !s.mounts.some((m) => m.id === loc.mount)) {
      setListing({ entries: [], dir: null, loading: false,
        error: { code: "not_found", message: "指定したマウントはありません" } });
      return;
    }
    // 先に読んでおいた一覧（prefetch.js）があれば、移ったときはそれをすぐ出し、裏で読み直して合わせる
    // （2026-09-29 設計者の選択）。作ったあとの選択・名前の変更など、読み直しの指定があるときは使わない
    const cached = !loc.trash && !quiet && !keepSelection && select == null && edit == null
      ? listCache.get(loc.mount, loc.path) : null;
    // quiet: 自動更新の読み直し。「読み込み中」を出さない（見ている一覧をちらつかせない）
    store.set({ ...(quiet || cached ? {} : { loading: true }), error: null, editing: null,
      ...(keepSelection ? {} : emptySelection()) });
    if (loc.trash && !enabled(s, "trash")) {
      // ハッシュ（#trash/<mount>）で直接来たとき。ごみ箱の機能を止めた画面では中身を見せない
      setListing({ entries: [], dir: null, loading: false,
        error: { code: "not_found", message: "この画面ではごみ箱を使えません" } });
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
      if (edit != null && store.get().visibleEntries.some((e) => e.key === edit)) store.set({ editing: edit });
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
      // 上へ移ったなら、遷移元の子の名前を覚える（先読みで、名前の並びで隣接する子を先に読む）
      cameFrom = cameFromChild(lastLocation, s.location);
      lastLocation = s.location;
      loadList(s.location);
    }
  });

  // キー操作は、この画面の中にフォーカスがあるときだけ受ける（組み込んだページのキーを横取りしない）。
  // 入力欄（名前の変更・アドレスバー）に打っているときは受けない
  root.addEventListener("keydown", (e) => {
    const t = e.target;
    if (e.isComposing || t.closest("input, textarea, select, dialog, .fd-menu")) return;
    const ctrl = e.ctrlKey || e.metaKey;
    if ((e.key === "Backspace" && !e.altKey) || (e.altKey && e.key === "ArrowLeft")) {
      e.preventDefault();
      actions.back();
    } else if (e.altKey && e.key === "ArrowRight") {
      e.preventDefault();
      actions.forward();
    } else if (e.altKey && e.key === "ArrowUp") {
      e.preventDefault();
      actions.up();
    } else if (e.key === "F5") {
      e.preventDefault();
      actions.refresh();
    } else if (e.key === "F2") {
      e.preventDefault();
      actions.startRename();
    } else if (e.key === "Delete") {
      e.preventDefault();
      actions.deleteSelected({ permanent: e.shiftKey });
    } else if (ctrl && !e.shiftKey && !e.altKey && ["c", "x", "v"].includes(e.key.toLowerCase())) {
      e.preventDefault();
      ({ c: actions.copySelected, x: actions.cutSelected, v: () => actions.paste() })[e.key.toLowerCase()]();
    } else if (ctrl && e.shiftKey && e.key.toLowerCase() === "n") {
      e.preventDefault();
      actions.newItem("dir");
    }
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
