/*
 * calendar_viewer — 長い記事を約7行に抑え、「（省略）」を押すと続きを開く。
 * 開いたあとはボタンが「（閉じる）」になり、押すと元の高さに戻す
 * （plugin/calendar_viewer.py の技術資料「長い記事」）。
 *
 * 本文はサーバーが全部出しているので、ここでは .calendar_viewer-body の高さを測り、
 * 抑えた高さ（calendar.css の is-clamped。10lh）を超えるものだけを畳む。
 * スクリプトが動かなければ何も畳まない（全文のまま）。
 */
(function () {
  "use strict";

  var MORE = "（省略）";
  var LESS = "（閉じる）";

  function buttonOf(body) {
    var next = body.nextElementSibling;
    return next && next.classList.contains("calendar_viewer-more") ? next : null;
  }

  function setOpen(body, button, open) {
    body.dataset.cvExpanded = open ? "1" : "0";
    body.classList.toggle("is-clamped", !open);
    button.textContent = open ? LESS : MORE;
    button.title = open ? "記事を畳む" : "続きを表示";
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function check(body) {
    if (body.dataset.cvExpanded === "1") return;   // 開いているあいだは測り直さない
    body.classList.add("is-clamped");
    var overflow = body.scrollHeight > body.clientHeight + 4;
    var button = buttonOf(body);
    if (!overflow) {
      body.classList.remove("is-clamped");
      if (button) button.remove();
      return;
    }
    if (button) return;
    button = document.createElement("button");
    button.type = "button";
    button.className = "calendar_viewer-more";
    button.addEventListener("click", function () {
      var open = body.dataset.cvExpanded !== "1";
      setOpen(body, button, open);
      if (!open) {
        // 閉じると記事が縮むので、画面が記事の下に取り残されないよう、
        // 記事の頭が画面の上に隠れていれば、そこまで戻す
        var top = body.getBoundingClientRect().top;
        if (top < 0) {
          var head = body.previousElementSibling || body;
          head.scrollIntoView({ block: "start" });
        }
      }
    });
    body.insertAdjacentElement("afterend", button);
    setOpen(body, button, false);
  }

  function checkAll() {
    document.querySelectorAll(".calendar_viewer-body").forEach(check);
  }

  checkAll();
  // 画像が後から読み込まれて高さが変わるため、読み込み終わりにも測り直す
  window.addEventListener("load", checkAll);
})();
