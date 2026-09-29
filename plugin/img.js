// img プラグイン。次の2つを受け持つ（どちらも出番が無ければ何もしない）。
//
// 1. zoom の [MIN;VALUE%;MAX] で MIN/MAX を % 指定したときだけ付く
//    `.plugin-img-zoom-js` の幅を仕上げる。
//    サーバー側では画像の中身を一切見ていない。data-zoom-min/mid/max に
//    書かれた値（%なら画像の実ピクセル寸法に対する割合、数値ならpx）を、
//    ブラウザが画像を読み込んで分かる img.naturalWidth を使ってここで
//    px に直し、clamp() として style.width に設定する。
//
// 2. makelink（既定で有効）で付く `a.plugin-img-link` をクリックしたとき、
//    画像のURLへ移動するかわりに、ページ内のダイアログで拡大表示する。
//    クリック・Escで閉じ、ダイアログ上のダブルクリックで別タブに開く。
//    Ctrl/Shift/中ボタンなどのクリックは奪わず、ブラウザ標準の動き
//    （新しいタブで開く等）に任せる。<dialog> に対応していないブラウザ・
//    JavaScriptが無効な環境では、これまでどおりただのリンクとして動く。
(function () {
  "use strict";

  // ---- 1. zoom の [MIN;VALUE%;MAX] ----

  function resolveBound(token, naturalWidth) {
    if (token.indexOf("%") !== -1) {
      return (naturalWidth * parseFloat(token)) / 100;
    }
    return parseFloat(token);
  }

  function applyClamp(img) {
    var min = img.dataset.zoomMin;
    var mid = img.dataset.zoomMid;
    var max = img.dataset.zoomMax;
    if (!min || !mid || !max || !img.naturalWidth) return;
    var minPx = resolveBound(min, img.naturalWidth);
    var maxPx = resolveBound(max, img.naturalWidth);
    var width = "clamp(" + minPx + "px, " + mid + ", " + maxPx + "px)";
    // 回り込む枠の中なら、幅は枠に付ける（画像は枠いっぱい）。% は枠の幅に対する
    // 割合なので、画像に付けると枠と画像で堂々巡りになり、文章が回り込まない
    // （img.py の技術資料「回り込みと、割合の幅」）
    var box = img.closest(".plugin-img-float");
    if (box) {
      box.style.width = width;
      img.style.width = "100%";
    } else {
      img.style.width = width;
    }
    img.style.height = "auto";
  }

  var imgs = document.querySelectorAll("img.plugin-img-zoom-js");
  imgs.forEach(function (img) {
    if (img.complete && img.naturalWidth) {
      applyClamp(img);
    } else {
      img.addEventListener("load", function () { applyClamp(img); }, { once: true });
    }
  });

  // ---- 2. 拡大表示のダイアログ ----

  if (typeof HTMLDialogElement !== "function" ||
      typeof HTMLDialogElement.prototype.showModal !== "function") {
    return;  // <dialog> 非対応。リンクのまま（画像のURLへ移動する）にしておく
  }

  // 1回目のクリックでは、すぐには閉じずにフェードアウトを始め、この時間が
  // 過ぎてから閉じる。その間に2回目のクリックが来て dblclick になれば、
  // 閉じるのをやめて別タブで開く（閉じてしまうと dblclick が届かない）。
  var CLOSE_DELAY = 300;
  // クリックで閉じた直後に、ダブルクリックの2回目がページ側のリンクに
  // 落ちてダイアログを開き直してしまうのを防ぐ時間。
  var REOPEN_GUARD = 500;

  var dialog = null;
  var dialogImg = null;
  var dialogTitle = null;
  var currentUrl = "";
  var closeTimer = null;
  var closedByClickAt = 0;

  function buildDialog() {
    dialog = document.createElement("dialog");
    dialog.className = "plugin-img-dialog";
    dialog.setAttribute("aria-label", "画像の拡大表示");

    dialogImg = document.createElement("img");
    dialogImg.className = "plugin-img-dialog-image";

    var caption = document.createElement("p");
    caption.className = "plugin-img-dialog-caption";
    dialogTitle = document.createElement("span");
    dialogTitle.className = "plugin-img-dialog-title";
    var hint = document.createElement("span");
    hint.className = "plugin-img-dialog-hint";
    hint.textContent = "クリック・Escで閉じる／ダブルクリックで別タブに開く";
    caption.appendChild(dialogTitle);
    caption.appendChild(hint);

    dialog.appendChild(dialogImg);
    dialog.appendChild(caption);
    document.body.appendChild(dialog);

    // ダイアログは画面全体を覆うので、背景・画像・説明のどこをクリック
    // してもここに届く
    dialog.addEventListener("click", function () {
      if (closeTimer !== null) return;  // ダブルクリックの2回目。dblclick 側で扱う
      dialog.classList.add("is-closing");
      closeTimer = setTimeout(function () {
        closeTimer = null;
        closedByClickAt = Date.now();
        dialog.close();
      }, CLOSE_DELAY);
    });

    dialog.addEventListener("dblclick", function () {
      var url = currentUrl;
      dialog.close();
      window.open(url, "_blank", "noopener");
    });

    // Esc（ブラウザ標準の cancel → close）でも、上の2つからでも、
    // 閉じたときの後始末はここにまとめる
    dialog.addEventListener("close", function () {
      if (closeTimer !== null) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
      dialog.classList.remove("is-closing");
      dialogImg.removeAttribute("src");
      currentUrl = "";
    });
  }

  function openDialog(link) {
    if (!dialog) buildDialog();
    var pageImg = link.querySelector("img");
    var title = pageImg ? pageImg.getAttribute("alt") || "" : "";
    currentUrl = link.href;
    dialogImg.src = currentUrl;
    dialogImg.alt = title;
    dialogTitle.textContent = title;
    dialogTitle.hidden = !title;
    dialog.showModal();
  }

  // include や ls の AJAX で後から差し込まれた画像にも効くよう、
  // document に1つだけ登録する（イベント委譲）
  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    var link = event.target.closest && event.target.closest("a.plugin-img-link");
    if (!link) return;
    event.preventDefault();
    if (Date.now() - closedByClickAt < REOPEN_GUARD) return;
    openDialog(link);
  });
})();
