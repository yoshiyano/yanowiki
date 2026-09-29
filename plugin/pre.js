// pre プラグイン。copy=true のときだけ現れる「COPY」ボタンの動き。
//
// `.pre-copy` が無ければ何もしない。ボタンは document 側で1つだけ
// イベントを受ける（ls.js と同じイベント委譲）。ls の ajaxview や
// include で後からページに差し込まれた <pre> ブロックにも、登録し
// 直さずそのまま効く。
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".pre-copy");
    if (!button) return;
    copyPre(button);
  });

  function flash(button, label, cls) {
    if (button.dataset.busy) return;
    button.dataset.busy = "1";
    var original = button.textContent;
    button.classList.add(cls);
    button.textContent = label;
    setTimeout(function () {
      button.textContent = original;
      button.classList.remove(cls);
      delete button.dataset.busy;
    }, 1600);
  }

  // クリップボードに書けない場面がある（httpsでない場所からの利用、
  // 権限が下りていない場合など）。黙って何も起きないと壊れて見えるので、
  // 昔ながらのやりかたを試す。
  function legacyCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  function copyPre(button) {
    var text = button.dataset.preCopy || "";
    var ok = function () { flash(button, "COPIED", "is-copied"); };
    var ng = function () { flash(button, "FAILED", "is-failed"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok, function () {
        if (legacyCopy(text)) ok(); else ng();
      });
      return;
    }
    if (legacyCopy(text)) ok(); else ng();
  }
})();
