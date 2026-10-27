/*
 * comment プラグインの、名前欄の記憶と投稿。
 *
 * 名前欄: ブラウザのlocalStorageに前回使った名前を覚えておき、次にページを
 * 開いたときの既定値として入れておく（Wiki設計者の指示）。
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
 *
 * 投稿: fetch で送る（ページ遷移も履歴の追加も起きない）。JS が無い環境では
 * 投稿を受け付けない（Wiki設計者の指示、2026-10-20。送信ボタンは
 * _polling.js が押せるようにする）。成功したら、書いた文を消して
 * "wiki:poll-refresh" を投げ、_polling.js にコメント欄だけを差し替えてもらう。
 * 断られたら、理由をフォームのそばに出し、入力した内容はそのまま残す
 * （書き直しや待避は投稿者に任せる）。
 *
 * コメント欄は polling で差し替わるので、送信はページ全体（document）で受ける。
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

  function message(form, text) {
    var p = form.querySelector(".poll-message");
    if (!p) {
      p = document.createElement("p");
      p.className = "poll-message";
      form.appendChild(p);
    }
    p.textContent = text;
    p.hidden = !text;
  }

  document.querySelectorAll(".comment-form").forEach(function (form) {
    var input = form.querySelector('input[name="name"]');
    if (input && !input.value) input.value = readName();  // noname指定時は名前欄自体が無い
  });

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form.classList || !form.classList.contains("comment-form")) return;
    ev.preventDefault();
    if (!window.fetch) {
      message(form, "この環境では投稿ができません（JavaScript の fetch が必要です）。");
      return;
    }
    var input = form.querySelector('input[name="name"]');
    if (input) {
      var value = input.value.trim();
      if (value !== readName()) writeName(value);
    }
    var box = form.closest(".poll-box");
    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;  // 二重送信を防ぐ
    if (box) box.dataset.pollBusy = "1";
    message(form, "");
    fetch(form.action, {
      method: "POST",
      body: new URLSearchParams(new FormData(form)),
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin"
    }).then(function (res) {
      if (res.status === 204) return null;
      return res.text().then(function (text) { return text || "投稿できませんでした。"; });
    }, function () {
      return "通信に失敗しました。入力した内容は残っています。";
    }).then(function (error) {
      if (box) delete box.dataset.pollBusy;
      if (button) button.disabled = false;
      if (error) {
        message(form, error);
        return;
      }
      var msg = form.querySelector('input[name="msg"]');
      if (msg) msg.value = "";
      form.dispatchEvent(new CustomEvent("wiki:poll-refresh", { bubbles: true }));
    });
  });
})();
