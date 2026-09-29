// 変更の操作: 作成・名前の変更・削除・ごみ箱（元に戻す・完全に削除・空にする）・コピー・移動・クリップボード。
// API を呼び、結果をステータスバーに知らせ、一覧とツリーを読み直す。
// 一括の操作は項目ごとに結果が返る（一部だけ失敗することがある。Wiki「API 設計 > 一括の結果」）。
// 画面の機能（features.js）を止めていたら、どこから呼ばれても（ボタン・メニュー・キー・ドロップ）何もしない。

import { api } from "./api.js";
import { saveClipboard } from "./clipboard.js";
import { confirmDialog, conflictDialog } from "./dialog.js";
import { splitPath, joinPath, parentPath, baseName } from "./location.js";
import {
  canCopyFrom, canDeleteEntries, canMoveEntries, canPutInto, capsOf, enabled, mountOf, selectedEntries, unmovable,
} from "./model.js";

/** 「report.txt」か「3 個の項目」。 */
function describe(names) {
  return names.length === 1 ? `「${names[0]}」` : `${names.length} 個の項目`;
}

/** 失敗した項目の知らせ。最初の 1 つは理由まで書く。 */
function failureText(failures, verb) {
  if (failures.length === 0) return "";
  const first = failures[0];
  const name = baseName(first.src || (first.error && first.error.path) || "") || "項目";
  const more = failures.length > 1 ? ` ほか ${failures.length - 1} 個` : "";
  return `${failures.length} 個の項目を${verb}ませんでした（${name}: ${first.error.message}${more}）`;
}

/**
 * 権限の無い項目の結果（サーバへは送らず、その項目だけ失敗にする。Wiki「画面設計 > 権限」）。
 * サーバが返す項目ごとの結果と同じ形にし、知らせ（report）でまとめて数える。
 */
function deniedResults(paths, message) {
  return paths.map((src) => ({ src, ok: false, error: { code: "forbidden", message, path: src } }));
}

/** 数えるときの「済んだ」（スキップや、同じ場所への移動で何も変わらなかったものは数えない）。 */
const counted = (r) => r.ok && !r.skipped && !r.unchanged;

/** 失敗してもよい読み込み（衝突のダイアログの詳細。読めなければ詳細なしで尋ねる）。 */
async function maybe(promise) {
  try {
    return await promise;
  } catch {
    return null;
  }
}

/**
 * 一括の結果のうち、名前が衝突した項目（exists）を 1 つずつ尋ねて送り直す。
 * retry(result, choice) は 1 項目の新しい結果を返す。
 * details(result) は {incoming, existing, incomingWhere, incomingTitle}（ダイアログに並べる 2 つの項目の詳細）を返す。
 */
async function resolveConflicts(results, retry, details) {
  const final = results.filter((r) => r.ok || r.error.code !== "exists");
  const conflicts = results.filter((r) => !r.ok && r.error.code === "exists");
  let applyAll = null;
  for (let i = 0; i < conflicts.length; i++) {
    const c = conflicts[i];
    let choice = applyAll;
    if (!choice) {
      const answer = await conflictDialog({
        name: baseName(c.error.path), where: parentPath(c.error.path) || "/", remaining: conflicts.length - i - 1,
        ...(await details(c)),
      });
      if (!answer) {
        // 取り消し: 残りは何もしない（スキップと同じ）
        final.push(...conflicts.slice(i).map((x) => ({ ...x, ok: true, skipped: true })));
        break;
      }
      choice = answer.choice;
      if (answer.all) applyAll = choice;
    }
    try {
      final.push(await retry(c, choice));
    } catch (err) {
      final.push({ ...c, error: { message: err.message, path: c.error.path } });
    }
  }
  return final;
}

export function createCommands(store, ui) {
  // ui: {reload(opts), refreshTree(), message(text, kind, action)}

  const loc = () => store.get().location;
  const childPath = (name) => joinPath([...splitPath(loc().path), name]);

  async function afterChange(opts = {}) {
    ui.refreshTree();
    await ui.reload({ keepSelection: true, ...opts });
  }

  function report(results, doneText, failVerb, action = null) {
    const done = results.filter(counted).length;
    const failures = results.filter((r) => !r.ok);
    const parts = [];
    if (done) parts.push(`${done} 個の項目を${doneText}`);
    if (failures.length) parts.push(failureText(failures, failVerb));
    if (parts.length) ui.message(parts.join("。"), failures.length ? "error" : "info", action);
  }

  // --- 作成・名前の変更 ---

  async function newItem(kind) {
    const s = store.get();
    if (!s.location || s.location.trash || !enabled(s, kind === "dir" ? "newFolder" : "newFile")
      || !capsOf(s).has(kind === "dir" ? "mkdir" : "touch")) return;
    if (!canPutInto(s.dir)) {
      ui.message("このフォルダの中に作る権限がありません", "error");
      return;
    }
    try {
      const entry = await (kind === "dir" ? api.mkdir : api.touch)(s.location.mount, s.location.path);
      if (kind === "dir") ui.refreshTree();
      // 作ってすぐ名前の変更に入る（エクスプローラーと同じ。途中でやめても作ったものは残る）
      await ui.reload({ select: [entry.name], edit: entry.name });
    } catch (err) {
      ui.message(`作れませんでした: ${err.message}`, "error");
    }
  }

  function startRename() {
    const s = store.get();
    const sel = selectedEntries(s);
    if (sel.length !== 1 || s.location.trash || !enabled(s, "rename") || !capsOf(s).has("rename")) return;
    if (!canMoveEntries(sel)) {
      ui.message(`「${sel[0].name}」の名前を変える権限がありません`, "error");
      return;
    }
    store.set({ editing: sel[0].key });
  }

  function cancelRename() {
    store.set({ editing: null });
  }

  /** 名前の変更を確定する。続けて入力してもらうとき（誤りがあった）は false。 */
  async function commitRename(entry, name) {
    if (name === entry.name) {
      cancelRename();
      return true;
    }
    if (name.trim() === "" || name.includes("/") || name === "." || name === "..") {
      ui.message("名前に / は使えません。空・「.」・「..」も使えません", "error");
      return false;
    }
    try {
      const renamed = await api.rename(loc().mount, childPath(entry.name), name);
      store.set({ editing: null });
      if (entry.kind === "dir") ui.refreshTree();
      await ui.reload({ select: [renamed.name] });
      return true;
    } catch (err) {
      ui.message(err.code === "exists" ? `「${name}」という名前の項目は既にあります` : `名前を変えられませんでした: ${err.message}`,
        "error");
      return false;
    }
  }

  // --- 削除 ---

  /**
   * paths を削除する。既定はごみ箱へ（確認なし・［元に戻す］）。permanent か、ごみ箱が無ければ完全に削除（確認あり）。
   * hasDir: フォルダを含むか（確認の文に「中身ごと」と書く）
   */
  /**
   * 削除する（ごみ箱へ、または完全に）。denied は削除する権限の無い項目のパスで、サーバへは送らず、その項目だけ
   * 失敗にする（残りは消す）。
   */
  async function deletePaths(mount, paths, { permanent = false, hasDir = false, denied = [] } = {}) {
    const m = store.get().mounts.find((x) => x.id === mount);
    const caps = new Set(m ? m.capabilities : []);
    const toTrash = !permanent && caps.has("trash");
    // ごみ箱へ移すのは「削除」、ごみ箱を通らず消すのは（ごみ箱の無いマウントでの削除も）「完全に削除」
    if (!enabled(store.get(), toTrash ? "delete" : "purge")) return;
    const deniedSet = new Set(denied);
    const sending = paths.filter((p) => !deniedSet.has(p));
    const refused = deniedResults(paths.filter((p) => deniedSet.has(p)), "削除する権限がありません");
    if (!toTrash && sending.length) {
      if (!caps.has("delete")) return;
      const ok = await confirmDialog({
        title: "完全に削除",
        message: `${describe(sending.map(baseName))}を完全に削除しますか？`,
        detail: `この操作は元に戻せません。${hasDir ? "フォルダは中身ごと消えます。" : ""}`
          + (refused.length ? `削除する権限の無い ${refused.length} 個の項目は消しません。` : ""),
        okLabel: "削除する", danger: true,
      });
      if (!ok) return;
    }
    let res = { results: [] };
    if (sending.length) {
      try {
        res = await api.delete(mount, sending, !toTrash);
      } catch (err) {
        ui.message(`削除できませんでした: ${err.message}`, "error");
        return;
      }
    }
    const results = [...res.results, ...refused];
    const ids = res.results.filter((r) => r.ok).map((r) => r.trashId);
    // ［元に戻す］はごみ箱から戻す操作なので、ごみ箱の機能を止めた画面では出さない
    const action = toTrash && ids.length && enabled(store.get(), "trash")
      ? { label: "元に戻す", run: () => restoreIds(mount, ids) } : null;
    report(results, toTrash ? "ごみ箱へ移しました" : "完全に削除しました", toTrash ? "ごみ箱へ移せ" : "削除でき", action);
    dropFromClipboard(mount, res.results.filter((r) => r.ok).map((r) => r.src));
    if (sending.length) await afterChange();
  }

  function deleteSelected({ permanent = false } = {}) {
    const s = store.get();
    const sel = selectedEntries(s);
    if (!s.location || sel.length === 0) return;
    if (s.location.trash) return purgeSelected();
    if (!canDeleteEntries(sel)) {
      ui.message(sel.length === 1 ? `「${sel[0].name}」を削除する権限がありません` : "削除する権限のある項目がありません", "error");
      return;
    }
    return deletePaths(s.location.mount, sel.map((e) => childPath(e.name)),
      { permanent, hasDir: sel.some((e) => e.kind === "dir"), denied: unmovable(sel).map((e) => childPath(e.name)) });
  }

  /** ごみ箱へドロップしたとき（ごみ箱のあるマウントだけ。deletePaths が「削除」の機能を確かめる）。 */
  function trashPaths(mount, paths, denied = []) {
    return deletePaths(mount, paths, { denied });
  }

  // --- ごみ箱 ---

  /** ごみ箱から戻す。元の場所に同じ名前があれば、項目ごとに尋ねる（「以降すべてに適用」あり）。 */
  async function restoreIds(mount, ids) {
    let res;
    try {
      res = await api.restore(mount, ids);
    } catch (err) {
      ui.message(`元に戻せませんでした: ${err.message}`, "error");
      return;
    }
    let trashItems = null; // ［元に戻す］から呼ばれたときは、ごみ箱の中身を 1 回だけ読む
    const results = await resolveConflicts(res.results,
      async (c, choice) => (await api.restore(mount, [c.id], choice)).results[0],
      async (c) => {
        const s = store.get();
        let item = s.location && s.location.trash && s.location.mount === mount
          ? s.entries.find((e) => e.trashId === c.id) : null;
        if (!item) {
          trashItems = trashItems || ((await maybe(api.trash(mount))) || { items: [] }).items;
          const found = trashItems.find((i) => i.id === c.id);
          item = found ? { ...found.entry, originalPath: found.originalPath } : null;
        }
        return {
          incomingTitle: "元に戻す項目",
          incoming: item,
          incomingWhere: item ? `ごみ箱（元の場所: ${parentPath(item.originalPath) || "/"}）` : "ごみ箱",
          existing: await maybe(api.stat(mount, c.error.path)),
          incomingMount: mountOf(store.get(), mount),
          mount: mountOf(store.get(), mount),
        };
      });
    report(results, "元に戻しました", "戻せ");
    await afterChange();
  }

  function restoreSelected() {
    const s = store.get();
    const sel = selectedEntries(s);
    if (!s.location || !s.location.trash || sel.length === 0 || !enabled(s, "trash")) return;
    return restoreIds(s.location.mount, sel.map((e) => e.trashId));
  }

  async function purgeSelected() {
    const s = store.get();
    const sel = selectedEntries(s);
    if (!s.location || !s.location.trash || sel.length === 0 || !enabled(s, "purge")) return;
    const ok = await confirmDialog({
      title: "完全に削除",
      message: `${describe(sel.map((e) => e.name))}をごみ箱から完全に削除しますか？`,
      detail: "この操作は元に戻せません。",
      okLabel: "削除する", danger: true,
    });
    if (!ok) return;
    await simple(() => api.purge(s.location.mount, sel.map((e) => e.trashId)), "完全に削除しました", "削除でき");
  }

  async function emptyTrash() {
    const s = store.get();
    if (!s.location || !s.location.trash || s.entries.length === 0 || !enabled(s, "purge")) return;
    const ok = await confirmDialog({
      title: "ごみ箱を空にする",
      message: `ごみ箱の ${s.entries.length} 個の項目をすべて完全に削除しますか？`,
      detail: "この操作は元に戻せません。",
      okLabel: "空にする", danger: true,
    });
    if (!ok) return;
    await simple(() => api.emptyTrash(s.location.mount), "完全に削除しました", "削除でき");
  }

  async function simple(call, doneText, failVerb) {
    let res;
    try {
      res = await call();
    } catch (err) {
      ui.message(`できませんでした: ${err.message}`, "error");
      return;
    }
    report(res.results, doneText, failVerb);
    await afterChange();
  }

  // --- コピー・移動・クリップボード ---

  function setClipboard(clip) {
    store.set({ clipboard: clip });
    saveClipboard(clip);
  }

  /** 消したり移したりした項目は、切り取りの中身から外す（貼り付けると not_found になるだけなので）。 */
  function dropFromClipboard(mount, paths) {
    const clip = store.get().clipboard;
    if (!clip || clip.mount !== mount) return;
    const gone = new Set(paths);
    const rest = clip.paths.filter((p) => !gone.has(p) && !paths.some((g) => p.startsWith(g + "/")));
    if (rest.length !== clip.paths.length) setClipboard(rest.length ? { ...clip, paths: rest } : null);
  }

  function toClipboard(mode) {
    const s = store.get();
    const sel = selectedEntries(s);
    if (!s.location || s.location.trash || sel.length === 0 || !enabled(s, mode)) return;
    if (mode === "cut" && !capsOf(s).has("move")) return;
    // 切り取りは項目を動かす（項目それぞれの「動かす」。1 つでも動かせれば切り取り、動かせない項目は貼り付けたときに
    // その項目だけ失敗にする）、コピーは中身を読む
    if (mode === "cut" ? !canMoveEntries(sel) : !canCopyFrom(sel)) {
      ui.message(mode === "cut" ? "動かす権限のある項目がありません" : "コピーする権限の無い項目があります", "error");
      return;
    }
    const denied = mode === "cut" ? unmovable(sel).map((e) => childPath(e.name)) : [];
    setClipboard({ mount: s.location.mount, paths: sel.map((e) => childPath(e.name)), mode,
      ...(denied.length ? { denied } : {}) });
    ui.message(`${sel.length} 個の項目を${mode === "cut" ? "切り取りました" : "コピーしました"}`
      + (denied.length ? `（${denied.length} 個は動かす権限が無いので、貼り付けても動きません）` : "")
      + "。貼り付け先で Ctrl+V を押してください");
  }

  const copySelected = () => toClipboard("copy");
  const cutSelected = () => toClipboard("cut");

  /** コピー・切り取りを解除する（ステータスバーの × と、選択が無いときの Esc）。 */
  function clearClipboard() {
    const clip = store.get().clipboard;
    if (!clip) return;
    setClipboard(null);
    ui.message(`${clip.mode === "cut" ? "切り取り" : "コピー"}を解除しました`);
  }

  const capsOfMount = (id) => new Set((store.get().mounts.find((m) => m.id === id) || {}).capabilities || []);

  /** 貼り付けられるか。dest は貼り付け先のフォルダ（省くとカレントフォルダ）。 */
  function canPaste(dest = null) {
    const s = store.get();
    const clip = s.clipboard;
    if (!clip || !s.location || s.location.trash || !enabled(s, "paste")) return false;
    const mode = clip.mode === "cut" ? "move" : "copy";
    // 貼り付け先のフォルダ（今いるフォルダか、選んだフォルダの項目）に書けるか
    const destEntry = dest == null ? s.dir : s.visibleEntries.find((e) => childPath(e.name) === dest);
    if (!canPutInto(destEntry)) return false;
    if (clip.mount !== s.location.mount) {
      // マウントをまたぐ: 元を読み（切り取りなら消し）、先に書く
      const src = capsOfMount(clip.mount);
      return src.has("stream") && capsOf(s).has("stream") && (mode === "copy" || src.has("delete"));
    }
    const target = dest ?? s.location.path;
    if (!capsOf(s).has(mode)) return false;
    return !clip.paths.some((p) => target === p || target.startsWith(p + "/"));
  }

  async function paste(dest = null) {
    const s = store.get();
    const clip = s.clipboard;
    if (!clip || !s.location || s.location.trash || !enabled(s, "paste")) return;
    if (!canPaste(dest)) {
      ui.message("ここには貼り付けられません", "error");
      return;
    }
    const mode = clip.mode === "cut" ? "move" : "copy";
    // 切り取りは貼り付けたら空にする（エクスプローラーと同じ）。コピーは何度でも貼り付けられる
    if (mode === "move") setClipboard(null);
    await transfer(mode, clip.mount, clip.paths, dest ?? s.location.path, s.location.mount,
      { denied: mode === "move" ? clip.denied || [] : [] });
  }

  /**
   * コピー（mode="copy"）か移動（mode="move"）。貼り付けとドロップが使う。destMount が違えばマウントをまたぐ。
   * denied は動かす権限の無い項目のパスで、サーバへは送らず、その項目だけ失敗にする（残りは動かす）。
   */
  async function transfer(mode, mount, srcs, dest, destMount = mount, { denied = [] } = {}) {
    const call = mode === "copy" ? api.copy : api.move;
    const deniedSet = new Set(denied);
    const sending = srcs.filter((p) => !deniedSet.has(p));
    const refused = deniedResults(srcs.filter((p) => deniedSet.has(p)), "動かす権限がありません");
    let res = { results: [] };
    if (sending.length) {
      try {
        res = await call(mount, sending, dest, "error", destMount);
      } catch (err) {
        ui.message(`${mode === "copy" ? "コピー" : "移動"}できませんでした: ${err.message}`, "error");
        return;
      }
    }
    const resolved = await resolveConflicts(res.results,
      async (c, choice) => (await call(mount, [c.src], dest, choice, destMount)).results[0],
      async (c) => {
        // 写す項目は元のマウントから、今ある項目は先のマウントから読む
        const [incoming, existing] = await Promise.all([
          maybe(api.stat(mount, c.src)), maybe(api.stat(destMount, c.error.path)),
        ]);
        // マウントをまたぐときは、どちらのマウントの場所かが分かるよう、場所の前にマウントの名前を付ける
        const label = (id) => (store.get().mounts.find((m) => m.id === id) || { label: "(root)" }).label;
        const at = (id, path) => (mount === destMount ? path : `${label(id)}: ${path}`);
        return {
          incomingTitle: `${mode === "copy" ? "コピー" : "移動"}する項目`, incoming, existing,
          incomingWhere: at(mount, parentPath(c.src) || "/"),
          where: at(destMount, parentPath(c.error.path) || "/"),
          // 属性・アイコンはマウントごとに違う（写す項目は元のマウント、今ある項目は先のマウントで見せる）
          incomingMount: mountOf(store.get(), mount),
          mount: mountOf(store.get(), destMount),
        };
      });
    const results = [...resolved, ...refused];
    report(results, mode === "copy" ? "コピーしました" : "移動しました", mode === "copy" ? "コピーでき" : "移動でき");
    if (mode === "move") dropFromClipboard(mount, results.filter(counted).map((r) => r.src));
    // カレントフォルダへ貼り付けたなら、貼り付けたものを選ぶ（エクスプローラーと同じ）
    const here = loc() && !loc().trash && loc().mount === destMount && loc().path === dest;
    const names = results.filter((r) => r.ok && r.entry).map((r) => r.entry.name);
    await afterChange(here && names.length ? { keepSelection: false, select: names } : {});
  }

  return {
    newItem, startRename, cancelRename, commitRename, deleteSelected, trashPaths,
    restoreSelected, purgeSelected, emptyTrash,
    copySelected, cutSelected, clearClipboard, paste, canPaste, transfer,
  };
}
