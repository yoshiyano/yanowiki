// ref プラグイン。添付ファイルへのリンクを右クリックしたとき、ブラウザ標準の
// メニューのかわりに、表示するかダウンロードするかを選べる小さなメニューを出す。
// 標準のメニューにあるリンクの操作のうち、ページの JS からできるもの（新しいタブ・
// 新しいウィンドウで開く、リンクのアドレス・テキストのコピー）も並べる。
// シークレットウィンドウ・ブックマーク・検証などはページからできないので並べず、
// 最後に「標準のメニューは Shift+右クリック」と案内する。
//
// サーバー側は、ブラウザで表示できない種類のリンクにだけ download 属性を付ける
// （plugin/ref.py の技術資料「表示できない種類の添付はダウンロード」）。普通の
// クリックはそれに従い、ここでは開くか保存するかを読み手が選び直せるようにする。
// download 属性のあるリンクは表示できない種類なので、「表示」の2つは押せなくする。
//
// - 対象は ref が描くリンク（.plugin-ref-file / .plugin-ref-link）のうち /.attach/ を
//   指すものだけ（attachls の一覧も ref が描くので含まれる）。画像のリンクの
//   image-link は img プラグインと共有なので、ref 固有のクラスで選ぶ
// - Shift を押しながらの右クリックは奪わず、ブラウザ標準のメニューを出す
//   （「名前を付けてリンク先を保存」などはそちらで使える）
// - 閉じるのは Esc・メニューの外のクリック・スクロール・ウィンドウの移動。
//   メニューは上下の矢印キーと Enter でも操作できる
(function () {
  "use strict";

  var menu = null;

  function fileName(link) {
    var name = link.getAttribute("download");
    if (name) return name;
    var path = link.pathname || "";
    try {
      return decodeURIComponent(path.slice(path.lastIndexOf("/") + 1));
    } catch (e) {
      return path.slice(path.lastIndexOf("/") + 1);
    }
  }

  function download(link) {
    var temp = document.createElement("a");
    temp.href = link.href;
    temp.download = fileName(link);
    temp.style.display = "none";
    document.body.appendChild(temp);
    temp.click();
    document.body.removeChild(temp);
  }

  // SPECIFICATIONS.md「クリップボードへのコピー」と同じ形（http では
  // navigator.clipboard が無いので execCommand に落とす）
  function legacyCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); } catch (e) { /* noop */ }
    document.body.removeChild(area);
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { legacyCopy(text); });
    } else {
      legacyCopy(text);
    }
  }

  function close() {
    if (!menu) return;
    menu.remove();
    menu = null;
  }

  function items() {
    return [].slice.call(menu.querySelectorAll("button:not([disabled])"));
  }

  function open(link, x, y) {
    close();
    var viewable = !link.hasAttribute("download");
    var img = link.querySelector("img");
    var text = img ? (img.getAttribute("alt") || "") : link.querySelector(".ref-name")
      ? link.querySelector(".ref-name").textContent : link.textContent;
    // null は区切り線
    var entries = [
      ["表示", viewable, function () { window.location.href = link.href; }],
      ["新しいタブで表示", viewable, function () { window.open(link.href, "_blank", "noopener"); }],
      ["新しいウィンドウで表示", viewable, function () { window.open(link.href, "_blank", "noopener,popup"); }],
      null,
      ["ダウンロード", true, function () { download(link); }],
      null,
      ["リンクのアドレスをコピー", true, function () { copy(link.href); }],
      ["リンクのテキストをコピー", !!text, function () { copy(text); }],
    ];
    menu = document.createElement("div");
    menu.className = "plugin-ref-menu";
    menu.setAttribute("role", "menu");
    entries.forEach(function (entry) {
      if (!entry) {
        var sep = document.createElement("div");
        sep.className = "plugin-ref-menu-sep";
        sep.setAttribute("role", "separator");
        menu.appendChild(sep);
        return;
      }
      var button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "menuitem");
      button.textContent = entry[0];
      if (!entry[1]) {
        button.disabled = true;
        button.title = entry[0] === "リンクのテキストをコピー"
          ? "リンクに文字がありません" : "この種類のファイルはブラウザで表示できません";
      }
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        close();
        entry[2]();
      });
      menu.appendChild(button);
    });
    var hint = document.createElement("div");
    hint.className = "plugin-ref-menu-hint";
    hint.textContent = "標準のメニューは Shift+右クリック";
    menu.appendChild(hint);
    document.body.appendChild(menu);

    // 画面からはみ出さないように寄せる
    var rect = menu.getBoundingClientRect();
    var left = Math.min(x, window.innerWidth - rect.width - 4);
    var top = Math.min(y, window.innerHeight - rect.height - 4);
    menu.style.left = Math.max(4, left) + "px";
    menu.style.top = Math.max(4, top) + "px";
    var first = items()[0];
    if (first) first.focus();
  }

  document.addEventListener("contextmenu", function (event) {
    if (event.shiftKey) return;
    var link = event.target.closest && event.target.closest("a.plugin-ref-file, a.plugin-ref-link");
    if (!link || link.pathname.indexOf("/.attach/") === -1) return;
    event.preventDefault();
    var x = event.clientX, y = event.clientY;
    if (!x && !y) {
      // キーボードのメニューキーで開いたときは、リンクの下に出す
      var rect = link.getBoundingClientRect();
      x = rect.left;
      y = rect.bottom;
    }
    open(link, x, y);
  });

  document.addEventListener("mousedown", function (event) {
    if (menu && !menu.contains(event.target)) close();
  }, true);
  document.addEventListener("keydown", function (event) {
    if (!menu) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      var list = items();
      var index = list.indexOf(document.activeElement);
      var step = event.key === "ArrowDown" ? 1 : -1;
      list[(index + step + list.length) % list.length].focus();
    }
  }, true);
  window.addEventListener("scroll", close, true);
  window.addEventListener("resize", close);
  window.addEventListener("blur", close);
})();
