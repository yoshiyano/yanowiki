/*
 * 編集の競合を統合する画面のスクリプト（/.conflict.js）。
 *
 * サーバーが埋め込んだ3つの文書（script.cf-docs）をdiffmergeへ渡し、
 * 保存を押された瞬間に統合結果を受け取ってフォームへ詰めるだけ。
 *
 * **diffmergeは組み込まず、公開APIをそのまま呼ぶ**（バックアップ画面と同じ
 * 方針。向こうの更新に素直に乗れるようにするため）。ここが呼ぶのは
 * render(target, left, right, options) と、その戻り値が持つ
 * getMergedText() だけ。
 *
 * **編集の単位は「1行ごと」を既定にする**（Wiki設計者の指示、2026-09-01）。
 * diffmerge自身の既定は「まとめて」だが、競合の統合では**同じかたまりの中で
 * 採りたい行が左右に分かれる**ことがあり、まとめて取り込むと片方が消える。
 * 画面の見出しにあるラジオボタンで「まとめて」へ戻せる。
 */
(function () {
  var root = document.querySelector(".cf");
  if (!root) return;

  var view = root.querySelector(".cf-view");
  var actions = root.querySelector(".cf-actions");
  var holder = document.querySelector("script.cf-docs");
  if (!view || !actions || !holder) return;

  var docs = null;
  try {
    docs = JSON.parse(holder.textContent);
  } catch (e) {
    docs = null;
  }
  if (!docs) {
    view.textContent = "突き合わせる内容を読み取れませんでした。";
    return;
  }

  if (!window.DiffMerge) {
    // 差分表示が無いと取り込む手段が無い。保存できてしまうと、統合していない
    // 内容がそのまま書き込まれるので、押せないようにしておく
    view.textContent = "差分の表示を読み込めませんでした。";
    var saveBtn = actions.querySelector(".cf-save");
    if (saveBtn) saveBtn.disabled = true;
    return;
  }

  view.textContent = "";
  // 「別の場所での更新」から「自分の編集」へ取り込む。
  // 編集対象は右（＝自分の編集）で、それがそのまま保存される
  var handle = window.DiffMerge.render(view, docs.theirs, docs.mine, {
    leftTitle: "別の場所での更新", rightTitle: "自分の編集（保存されます）",
    merge: true, singleline: true,
  });

  // 送信するのはボタンだけのフォーム（.cf-actions）。統合結果はここで詰める
  // （編集画面と同じ作り。本文を隠しフィールドに常時置いておかない）
  actions.addEventListener("submit", function () {
    var field = actions.querySelector('input[name="merged"]');
    if (field) field.value = handle.getMergedText();
  });
}());
