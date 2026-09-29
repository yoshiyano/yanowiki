/*
 * tasklist プラグインの、チェックボックスを組み立てて押した結果を
 * 保存する動き。
 *
 * サーバー側（plugin/tasklist.py）は、チェックボックスの生HTML
 * （<input>）をそもそも描かない。allow_html の設定（既定はOFF）に
 * よってエスケープされ、実際のチェックボックスにならない場合がある
 * ため（plugin/tasklist.pyの技術資料「チェックボックスをJavaScriptで
 * 組み立てる理由」参照）。代わりに <li class="task-list-item"> 自身に
 * data-page/data-line/data-checked が付いているので、ここでチェック
 * ボックス要素を組み立てて先頭に差し込む。
 *
 * data-api は、そのページに #tasklist(sync) が書かれているときだけ
 * 付く（plugin/tasklist.pyの技術資料「sync（書き戻しは既定でオフ）」
 * 参照）。無いときは押しても保存されない・保存できない。**操作できない
 * ものをinput(disabled)にすると、ブラウザ標準のグレーアウトで色が抜けて
 * 見えにくくなるうえ、そもそも操作できないものをフォーム部品にする理由が
 * 無い**（Wiki設計者の指摘、2026-09-08）。そのためdata-apiが無い項目は
 * <input>ではなく、状態だけを示す絵文字（<span>。Wiki設計者の指示、
 * 2026-09-08「icon画像にはemojiを利用」）にする。
 *
 * このファイルは、ページで tasklist が実際に使われた（チェックリストが
 * 1つでもある）ときだけ /.plugin/tasklist.js として読み込まれる
 * （CSSと同じ仕組み。plugin/tasklist.pyの技術資料「context.used_plugins
 * への追加」参照）。
 */
(function () {
  var items = [].slice.call(document.querySelectorAll(".task-list-item[data-line]"));
  if (!items.length) return;

  // チェック状態を表す絵文字（Wiki設計者の指示、2026-09-08）。絵文字はどの
  // テーマでも自前の色を持つため、disabledのinputのような色抜けが起きない。
  var ICON_CHECKED = "✅"; // ✅ White Heavy Check Mark
  var ICON_UNCHECKED = "⬜"; // ⬜ White Large Square

  items.forEach(function (li) {
    if (!li.dataset.api) {
      // #tasklist(sync) が無いページ、または見ている人に編集の権限が無い
      // （data-noauth）: 変更そのものを許可しない。フォーム部品（input）には
      // せず、状態だけを示す絵文字を差し込む。
      var icon = document.createElement("span");
      icon.className = "task-list-item-icon";
      icon.title = li.hasAttribute("data-noauth")
        ? "このページを編集する権限が無いため、変更できません。"
        : "このページでは変更を保存できません（#tasklist(sync) が必要です）。";
      icon.textContent = li.dataset.checked === "1" ? ICON_CHECKED : ICON_UNCHECKED;
      li.insertBefore(icon, li.firstChild);
      return;
    }

    var box = document.createElement("input");
    box.type = "checkbox";
    box.className = "task-list-item-checkbox";
    box.checked = li.dataset.checked === "1";
    li.insertBefore(box, li.firstChild);

    box.addEventListener("change", function () {
      var checked = box.checked;
      var body = new URLSearchParams({
        page: li.dataset.page,
        line: li.dataset.line,
        checked: checked ? "1" : "0",
      });

      box.disabled = true;
      fetch(li.dataset.api, { method: "POST", credentials: "same-origin", body: body })
        .then(function (res) {
          box.disabled = false;
          if (!res.ok) fail();
        })
        .catch(fail);

      function fail() {
        // 通信に失敗した・ページが変わっていた等。押す前の状態へ戻し、
        // <li> を一瞬だけ縁取りして知らせる（plugin/tasklist.css）。
        box.disabled = false;
        box.checked = !checked;
        li.classList.add("task-list-item-error");
        setTimeout(function () {
          li.classList.remove("task-list-item-error");
        }, 2000);
      }
    });
  });
})();
