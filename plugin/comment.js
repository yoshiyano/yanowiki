/*
 * comment プラグインの名前欄: ブラウザのlocalStorageに前回使った名前を
 * 覚えておき、次にページを開いたときの既定値として入れておく（Wiki設計者の指示）。
 *
 *   - ページを開いたとき、名前欄が空ならlocalStorageの記録を入れておく
 *   - 投稿（送信）時、名前欄の値が記録と違っていれば新しい記録として覚える
 *   - 投稿時、名前欄が空になっていれば記録を削除する
 *
 * キーは1つだけ（サイト全体・複数の#comment()で共有）。「自分の名前」は
 * ページ単位の情報ではなくブラウザ単位の情報のため。
 *
 * サーバ側（comment.py）は名前をそのまま文字列として本文に書き足すだけで、
 * リンクは作らない。ここでの記憶もあくまで入力の手間を減らすためのもので、
 * 送信されるまではサーバに一切渡らない。
 */
(function () {
  "use strict";
  var STORAGE_KEY = "wikisys-comment-name";

  function readName() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch (e) {
      return "";  // プライベートブラウジング等で使えなくても投稿自体は妨げない
    }
  }

  function writeName(value) {
    try {
      if (value) {
        localStorage.setItem(STORAGE_KEY, value);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch (e) {
      // 上と同じ理由で無視する
    }
  }

  document.querySelectorAll(".comment-form").forEach(function (form) {
    var input = form.querySelector('input[name="name"]');
    if (!input) return;  // noname指定時は名前欄自体が無い

    if (!input.value) {
      input.value = readName();
    }

    form.addEventListener("submit", function () {
      var value = input.value.trim();
      if (value !== readName()) writeName(value);
    });
  });
})();
