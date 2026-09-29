// ドラッグ＆ドロップ（Wiki「画面設計 > ドラッグ＆ドロップ」）。
// - 運ぶデータは独自の型 application/x-webfiledir の JSON {mount, paths}。他のページや OS からのドロップは受け付けない
// - 選択中の項目をドラッグしたら選択全部を、選択外の項目ならその 1 つを運ぶ
// - 既定は移動、Ctrl を押しながらならコピー。落とせない先では禁止のカーソルにする
// - 落とし先は data-drop-mount（と data-drop-path か data-drop-trash）を持つ要素
//   （表示の中のフォルダ・ツリーのフォルダ・パンくず・ツリーの「ごみ箱」）
// - 画面の機能 dnd（features.js）を止めた画面では、運び出すことも、落とすこともできない
//   （二画面で、止めていない画面から運んできても落とせない）。ごみ箱へ落とすのは「削除」の機能も要る

import { splitPath, joinPath, parentPath } from "./location.js";
import { canCopyFrom, canMoveEntries, enabled, selectedEntries, unmovable } from "./model.js";

export const MIME = "application/x-webfiledir";

/**
 * ドロップしたときの動き。同じマウントの中は既定が移動、別のマウントへは既定がコピー
 * （エクスプローラーの「同じドライブなら移動、違うドライブならコピー」と同じ）。
 * Ctrl を押していればコピー、Shift を押していれば移動。
 */
export function dropMode({ ctrl = false, shift = false } = {}, crossMount = false) {
  if (ctrl) return "copy";
  if (shift) return "move";
  return crossMount ? "copy" : "move";
}

/**
 * payload（{mount, paths}）を target（{mount, path, trash}）へ mode（"move" | "copy"）で落とせるか。
 * caps は落とし先のマウントでできる操作の集合、srcCaps は運ぶ元のマウントの集合。{ok, reason}
 */
export function canDrop(payload, target, caps, mode, srcCaps = caps) {
  if (!payload || !target) return { ok: false, reason: "" };
  // 権限（Wiki「画面設計 > 権限」）: 移動・ごみ箱へは項目それぞれの「動かす」、コピーは項目の「読む」、落とし先はその
  // フォルダの「書く」。canMove（1 つでも動かせるか）・canCopy はドラッグを始めたときに決める（無ければ許す）。
  // 動かせない項目（payload.denied）は、落としたときにその項目だけ失敗にし、残りは動かす
  if ((mode === "move" || target.trash) && payload.canMove === false) {
    return { ok: false, reason: "動かす権限のある項目がありません" };
  }
  if (mode === "copy" && !target.trash && payload.canCopy === false) {
    return { ok: false, reason: "コピーする権限の無い項目があります" };
  }
  if (target.denied && !target.trash) return { ok: false, reason: "このフォルダに入れる権限がありません" };
  if (payload.mount !== target.mount) {
    // マウントをまたぐ: 元を読み（移動なら消し）、先に書く。ごみ箱はそのマウントの中のものだけ
    if (target.trash) return { ok: false, reason: "ほかのマウントのごみ箱へは移せません" };
    if (!srcCaps.has("stream") || !caps.has("stream")) return { ok: false, reason: "このマウントの間では写せません" };
    if (mode === "move" && !srcCaps.has("delete")) return { ok: false, reason: "元のマウントから消せないので移動できません" };
    return { ok: true, reason: "" };
  }
  if (target.trash) {
    return caps.has("trash") ? { ok: true, reason: "" } : { ok: false, reason: "このマウントにはごみ箱がありません" };
  }
  if (!caps.has(mode)) return { ok: false, reason: "このマウントではできません" };
  for (const src of payload.paths) {
    if (target.path === src) return { ok: false, reason: "自分自身の上には落とせません" };
    if (target.path.startsWith(src + "/")) return { ok: false, reason: "フォルダをそのフォルダ自身の中へは入れられません" };
  }
  if (mode === "move" && payload.paths.every((src) => parentPath(src) === target.path)) {
    return { ok: false, reason: "同じフォルダです" }; // 動かしても何も変わらない
  }
  return { ok: true, reason: "" };
}

/** 落とし先の要素から {mount, path, trash} を読む。 */
export function dropTarget(el) {
  if (!el) return null;
  const { dropMount, dropPath, dropTrash, dropDenied } = el.dataset;
  if (!dropMount) return null;
  // dropDenied … そのフォルダに書けない（落とせない）。描くときに権限を見て付ける
  return { mount: dropMount, path: dropPath || "/", trash: dropTrash === "1", denied: dropDenied === "1" };
}

// このページで始めたドラッグの中身（dragover の間は getData が読めないため覚えておく）。
// 二画面モードでは、片方の画面で始めて、もう片方の画面へ落とすので、画面どうしで共有する
let dragging = null;

export function setupDnd(root, store, actions) {
  let highlighted = null;

  const isInternal = (e) => [...e.dataTransfer.types].includes(MIME);
  const modeOf = (e, cross) => dropMode({ ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }, cross);
  const capsFor = (mount) => new Set((store.get().mounts.find((m) => m.id === mount) || {}).capabilities || []);

  function highlight(el) {
    if (highlighted === el) return;
    if (highlighted) highlighted.classList.remove("fd-drop-target");
    highlighted = el;
    if (el) el.classList.add("fd-drop-target");
  }

  const dndOn = () => enabled(store.get(), "dnd");
  // ごみ箱へ落とすのは削除なので、「削除」の機能を止めた画面では落とせない
  const trashBlocked = (target) => !!(target && target.trash && !enabled(store.get(), "delete"));

  root.addEventListener("dragstart", (e) => {
    if (!dndOn()) {
      e.preventDefault(); // 項目は draggable にしていないが、選んだ文字などのドラッグも始めない
      return;
    }
    const item = e.target.closest && e.target.closest(".fd-view .fd-item[draggable='true']");
    if (!item) return;
    const s = store.get();
    const key = item.dataset.key;
    // 選択の外の項目なら、それ 1 つだけを運ぶ。**ここで選択を変えない。**変えると表示が描き直され、
    // ドラッグ元の要素が DOM から消えて、ドラッグが途切れる
    const moving = s.selection.has(key) ? selectedEntries(s) : s.visibleEntries.filter((x) => x.key === key);
    const loc = s.location;
    const paths = moving.map((x) => joinPath([...splitPath(loc.path), x.name]));
    // 動かせるか（項目それぞれの「動かす」。1 つでも動かせれば動かし、動かせない項目は denied として運んで、その項目
    // だけ失敗にする）・コピーできるか（項目の「読む」）をここで決めて運ぶ。落とせるか（移動先・コピー先のフォルダの
    // 「書く」）は落とす側で見る
    const denied = unmovable(moving).map((x) => joinPath([...splitPath(loc.path), x.name]));
    dragging = { mount: loc.mount, paths, denied, canMove: canMoveEntries(moving), canCopy: canCopyFrom(moving) };
    e.dataTransfer.setData(MIME, JSON.stringify(dragging));
    e.dataTransfer.effectAllowed = "copyMove";
  });

  root.addEventListener("dragend", () => {
    dragging = null;
    highlight(null);
  });

  root.addEventListener("dragover", (e) => {
    if (!isInternal(e) || !dndOn()) {
      // 他のページや OS からのドロップは受け付けない。既定の動き（ファイルを開いて画面を離れる）も止める
      e.preventDefault();
      e.dataTransfer.dropEffect = "none";
      return;
    }
    const el = e.target.closest && e.target.closest("[data-drop-mount]");
    const target = dropTarget(el);
    const mode = modeOf(e, !!(dragging && target && dragging.mount !== target.mount));
    // 別のタブで始めたドラッグは中身が分からないので、落とし先だけで判断し、落としたときに確かめる
    let verdict;
    if (trashBlocked(target)) verdict = { ok: false };
    else if (dragging) verdict = canDrop(dragging, target, capsFor(target && target.mount), mode, capsFor(dragging.mount));
    else verdict = { ok: !!target && capsFor(target.mount).has(target.trash ? "trash" : mode) };
    if (!verdict.ok) {
      highlight(null);
      e.dataTransfer.dropEffect = "none";
      return; // preventDefault しない → 禁止のカーソル
    }
    e.preventDefault();
    e.dataTransfer.dropEffect = target.trash ? "move" : mode;
    highlight(el);
  });

  root.addEventListener("dragleave", (e) => {
    if (highlighted && !highlighted.contains(e.relatedTarget)) highlight(null);
  });

  root.addEventListener("drop", (e) => {
    e.preventDefault();
    highlight(null);
    if (!dndOn()) return;
    if (!isInternal(e)) {
      actions.message("ほかのアプリからのドロップ（アップロード）にはまだ対応していません");
      return;
    }
    let payload = dragging;
    if (!payload) {
      try {
        payload = JSON.parse(e.dataTransfer.getData(MIME));
      } catch {
        return;
      }
    }
    dragging = null;
    const target = dropTarget(e.target.closest && e.target.closest("[data-drop-mount]"));
    const mode = modeOf(e, !!(target && payload.mount !== target.mount));
    const verdict = trashBlocked(target) ? { ok: false, reason: "この画面ではごみ箱へ移せません" }
      : canDrop(payload, target, capsFor(target && target.mount), mode, capsFor(payload.mount));
    if (!verdict.ok) {
      if (verdict.reason) actions.message(verdict.reason, "error");
      return;
    }
    // 動かせない項目（denied）は、移動・ごみ箱へのときだけその項目を失敗にする（コピーは動かさないので関係しない）
    const denied = Array.isArray(payload.denied) ? payload.denied : [];
    if (target.trash) actions.trashPaths(payload.mount, payload.paths, denied);
    else actions.transfer(mode, payload.mount, payload.paths, target.path, target.mount,
      { denied: mode === "move" ? denied : [] });
  });
}
