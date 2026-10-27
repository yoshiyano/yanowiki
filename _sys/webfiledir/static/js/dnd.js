// ドラッグ＆ドロップ（Wiki「画面設計 > ドラッグ＆ドロップ」）。
// - 運ぶデータは独自の型 application/x-webfiledir の JSON {mount, paths}
// - ほかのアプリ（OS のファイルブラウザ）のファイル・フォルダは、ドロップの条件 from: "files" のコマンドで受け取り、
//   確かめずに送る（アップロード）。フォルダごと送るかは createShell の folderUpload（actions.folderUpload）
// - 選択中の項目をドラッグしたら選択全部を、選択外の項目ならその 1 つを運ぶ
// - 既定は移動、Ctrl を押しながらならコピー。落とせない先では禁止のカーソルにする
// - 落とし先は data-drop-mount（と data-drop-path か data-drop-trash）を持つ要素
//   （表示の中のフォルダ・ツリーのフォルダ・パンくず・ツリーの「ごみ箱」）
// - **落とせるかは、落とし先のマウントの宣言で決める。**落とすときの状態（先・マウント・押しているキー）に合う
//   ドロップのコマンド（drop の条件）が無ければ落とせない（禁止のカーソル）。権限は宣言の when で見る
//   （runner.js の evaluate）。自分の中へ入れない・同じフォルダへの移動・マウントをまたげるかは、画面が見る（canDrop）

import { splitPath, joinPath, parentPath } from "./location.js";
import { allows, selectedEntries } from "./model.js";
import { dropCommand, evaluate } from "./runner.js";
import { carriesFiles, filesFromDrop } from "./upload.js";

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

/** 押しているキー（ドロップの条件の modifier）。Ctrl が先。 */
function modifierOf(e) {
  if (e.ctrlKey || e.metaKey) return "ctrl";
  if (e.shiftKey) return "shift";
  return null;
}

export function setupDnd(root, store, actions) {
  let highlighted = null;

  const isInternal = (e) => [...e.dataTransfer.types].includes(MIME);
  const capsFor = (mount) => new Set((store.get().mounts.find((m) => m.id === mount) || {}).capabilities || []);

  function highlight(el) {
    if (highlighted === el) return;
    if (highlighted) highlighted.classList.remove("fd-drop-target");
    highlighted = el;
    if (el) el.classList.add("fd-drop-target");
  }

  /**
   * payload（運ぶ項目）を target へ、押しているキーで落とすときの、コマンドと文脈。落とせなければ {reason}。
   * 別のタブで始めたドラッグは中身が分からないので、落とすときに読む（dragover では先だけで決める）。
   */
  function plan(payload, target, e) {
    if (!target) return { reason: "" };
    const cross = !!payload && payload.mount !== target.mount;
    const cmd = dropCommand(actions.commandsOf(target.mount), {
      target: target.trash ? "trash" : "folder", sameMount: !cross, modifier: modifierOf(e),
    });
    if (!cmd) return { reason: "" };
    if (!payload) return { cmd, ctx: null };
    const mode = dropMode({ ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }, cross);
    const verdict = canDrop(payload, target, capsFor(target.mount), target.trash ? "move" : mode, capsFor(payload.mount));
    if (!verdict.ok) return { reason: verdict.reason };
    const ctx = {
      mount: target.mount, view: "folder", items: [],
      source: { mount: payload.mount, paths: payload.paths, mode: mode === "move" ? "cut" : "copy",
        denied: payload.denied || [], unreadable: payload.unreadable || [] },
      dest: { mount: target.mount, path: target.path, denied: !!target.denied && !target.trash },
    };
    const ev = evaluate(cmd, ctx);
    if (ev.state !== "enabled") return { reason: ev.reason };
    return { cmd, ctx, mode };
  }

  /** ほかのアプリのファイルを target へ落とすときの、コマンドと文脈。落とせなければ {reason}。 */
  function planFiles(target) {
    if (!target || target.trash) return { reason: "" };
    const cmd = dropCommand(actions.commandsOf(target.mount), { from: "files", target: "folder" });
    if (!cmd) return { reason: "" };
    const ctx = { mount: target.mount, view: "folder", items: [],
      dest: { mount: target.mount, path: target.path, denied: !!target.denied } };
    const ev = evaluate(cmd, ctx);
    if (ev.state !== "enabled") return { reason: ev.reason };
    return { cmd, ctx };
  }

  root.addEventListener("dragstart", (e) => {
    const item = e.target.closest && e.target.closest(".fd-view .fd-item[draggable='true']");
    if (!item) return;
    const s = store.get();
    const key = item.dataset.key;
    // 選択の外の項目なら、それ 1 つだけを運ぶ。**ここで選択を変えない。**変えると表示が描き直され、
    // ドラッグ元の要素が DOM から消えて、ドラッグが途切れる
    const moving = s.selection.has(key) ? selectedEntries(s) : s.visibleEntries.filter((x) => x.key === key);
    const loc = s.location;
    const pathOf = (x) => joinPath([...splitPath(loc.path), x.name]);
    // 動かす権限の無い項目（denied）と読む権限の無い項目（unreadable）を運ぶ。移動は 1 つでも動かせれば動かし、
    // 動かせない項目だけ失敗にする（宣言の partial）。コピーは全部を読めること。落とせるかは落とす側で見る
    const denied = moving.filter((x) => !allows(x, "move")).map(pathOf);
    const unreadable = moving.filter((x) => !allows(x, "read")).map(pathOf);
    dragging = { mount: loc.mount, paths: moving.map(pathOf), denied, unreadable,
      canMove: denied.length < moving.length, canCopy: unreadable.length === 0 };
    e.dataTransfer.setData(MIME, JSON.stringify(dragging));
    e.dataTransfer.effectAllowed = "copyMove";
  });

  root.addEventListener("dragend", () => {
    dragging = null;
    highlight(null);
  });

  root.addEventListener("dragover", (e) => {
    if (!isInternal(e)) {
      // 既定の動き（ファイルを開いて画面を離れる）は、落とせないところでも止める
      e.preventDefault();
      const el = carriesFiles(e.dataTransfer) && e.target.closest && e.target.closest("[data-drop-mount]");
      const p = el ? planFiles(dropTarget(el)) : { reason: "" };
      e.dataTransfer.dropEffect = p.cmd ? "copy" : "none";
      highlight(p.cmd ? el : null);
      return;
    }
    const el = e.target.closest && e.target.closest("[data-drop-mount]");
    const target = dropTarget(el);
    const p = plan(dragging, target, e);
    if (!p.cmd) {
      highlight(null);
      e.dataTransfer.dropEffect = "none";
      return; // preventDefault しない → 禁止のカーソル
    }
    e.preventDefault();
    e.dataTransfer.dropEffect = target.trash ? "move" : (p.mode || "move");
    highlight(el);
  });

  root.addEventListener("dragleave", (e) => {
    if (highlighted && !highlighted.contains(e.relatedTarget)) highlight(null);
  });

  root.addEventListener("drop", (e) => {
    e.preventDefault();
    highlight(null);
    if (!isInternal(e)) {
      if (!carriesFiles(e.dataTransfer)) {
        actions.message("ファイル・フォルダのほかは、ここに落とせません");
        return;
      }
      const p = planFiles(dropTarget(e.target.closest && e.target.closest("[data-drop-mount]")));
      if (!p.cmd) {
        actions.message(p.reason || "ここにはアップロードできません", "error");
        return;
      }
      // DataTransfer の中身は、この事象の中で取り出す（filesFromDrop が await の前に行う）
      filesFromDrop(e.dataTransfer, { folders: actions.folderUpload }).then(({ files, skipped }) => {
        if (skipped.length) {
          actions.message(`フォルダはアップロードできません（${skipped.join("、")}）`, "error");
        }
        if (files.length) return actions.runWith(p.cmd, { ...p.ctx, files });
        return null;
      }).catch(() => actions.message("ドロップしたものを読めませんでした", "error"));
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
    const p = plan(payload, target, e);
    if (!p.ctx) {
      if (p.reason) actions.message(p.reason, "error");
      return;
    }
    actions.runWith(p.cmd, p.ctx);
  });
}
