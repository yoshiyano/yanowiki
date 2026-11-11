/*
 * ls プラグインの「その場で開く」（ajaxview=true）ための動き。
 *
 * このファイルは、ページで ls プラグインが実際に使われたときだけ
 * /.plugin/ls.js として読み込まれる（CSSと同じ仕組み）。
 * 読み込み先は同じプラグインの _action（/.plugin/ls?page=…）で、
 * 一覧の見せかたと中身の出しかたが1つのプラグインの中で完結している。
 *
 * ajaxview=false の一覧には .ls-open が無いので、このコードは何もしない。
 *
 * .ls-open は、ページの <li class="ls-page ls-openable"> だけでなく、
 * 中身のあるフォルダの <summary>（<li class="ls-folder ls-openable">）
 * の中にも置かれる（2026-09-03、Wiki設計者の報告により追加）。<summary> は
 * 元々クリックで <details> の開閉を担う要素なので、その中のボタンを
 * 押したときに「その場で開く」動きと「フォルダ自体の開閉」が同時に
 * 起きないよう、event.preventDefault() で <details> 側のトグルを止める。
 */
(function () {
  [].forEach.call(document.querySelectorAll(".ls-columns"), setupClip);

  var lists = [].slice.call(document.querySelectorAll(".ls-ajax"));
  if (!lists.length) return;

  lists.forEach(function (list) {
    var api = list.dataset.lsApi;
    if (!api) return;

    // 項目が増えても効くよう、個々のボタンではなく一覧側で受ける
    list.addEventListener("click", function (event) {
      var button = event.target.closest && event.target.closest(".ls-open");
      if (!button || !list.contains(button)) return;
      // <summary> の中にあるときは、既定の <details> 開閉を止める
      // （ページの <li> の中にあるときは対象が無いだけで、害は無い）
      event.preventDefault();

      // ページの <li class="ls-page ls-openable"> ・フォルダの
      // <li class="ls-folder ls-openable">（<summary>側）のどちらにも効くよう、
      // 共通の目印クラスで受ける（plugin/ls.py参照）
      var item = button.closest(".ls-openable");
      var view = item.querySelector(".ls-view");
      if (!view) return;

      // 開いているなら閉じるだけ。読み込んだ中身はそのまま残しておくので、
      // もう一度開くときに取りに行かなくて済む。
      if (!view.hidden) {
        close(button, view);
        return;
      }

      open(button, view);
      if (view.dataset.loaded === "1") return;

      view.innerHTML = '<p class="ls-view-loading">読み込み中…</p>';
      fetch(api + "?page=" + encodeURIComponent(button.dataset.page),
            { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
        .then(function (html) {
          view.innerHTML = html;
          view.dataset.loaded = "1";
          // 読み込んだ本文の中の #ls() にも、省略の切り替えを付ける
          [].forEach.call(view.querySelectorAll(".ls-columns"), setupClip);
        })
        .catch(function () {
          // 失敗しても一覧は使えるままにしておく。閉じれば元に戻る
          view.innerHTML = '<p class="ls-view-error">読み込めませんでした。</p>';
        });
    });
  });

  // 列に収まらない名前があるときだけ「ファイル名の部分省略」のチェックボックスを出す。
  // 収まるかどうかは列の幅とフォントで決まるので、ここで実測する（plugin/ls.py 参照）
  function setupClip(nav) {
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = true;
    var label = document.createElement("label");
    label.className = "ls-clip-toggle";
    label.appendChild(box);
    label.appendChild(document.createTextNode("ファイル名の部分省略"));
    var slot = document.createElement("li");
    slot.className = "ls-clip-slot";
    slot.hidden = true;
    slot.appendChild(label);

    var list = nav.querySelector(".ls-list");
    list.appendChild(slot);
    var items = [].slice.call(nav.querySelectorAll(".ls-page"));

    // 右上の1項目分をスイッチに使う。段組みに「右上を空ける」指定は無いので、
    // 末尾に置いて最後の列を測り、その列の先頭へ移す。同じ列の中で動かすだけなので
    // 前の列の割り振りは変わらない。列が余る件数のときは、項目のある最後の列に置く
    function placeSlot() {
      var focused = document.activeElement === box;
      slot.classList.remove("ls-clip-slot-placed");
      list.appendChild(slot);
      var left = slot.getBoundingClientRect().left;
      var first = null;
      for (var i = 0; i < items.length && !first; i++) {
        if (Math.abs(items[i].getBoundingClientRect().left - left) < 1) first = items[i];
      }
      if (first) {
        list.insertBefore(slot, first);
        slot.classList.add("ls-clip-slot-placed");
      }
      if (focused) box.focus();
    }

    function update() {
      // オフのときも、省略した姿で測るために一時的に付ける（描画の前に戻すので見えない）
      nav.classList.add("ls-clip");
      var needed = false;
      items.forEach(function (item) {
        var over = item.scrollWidth > item.clientWidth;
        needed = needed || over;
        var link = item.querySelector("a");
        if (over && box.checked) link.title = item.textContent;
        else link.removeAttribute("title");
      });
      nav.classList.toggle("ls-clip", box.checked);
      slot.hidden = !needed;
      if (needed) placeSlot();
    }

    box.addEventListener("change", update);
    // チェックボックスの出し入れでは幅が変わらないので、幅だけを見れば繰り返さない
    var lastWidth = -1;
    new ResizeObserver(function () {
      if (nav.clientWidth === lastWidth) return;
      lastWidth = nav.clientWidth;
      update();
    }).observe(nav);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(update);
  }

  function open(button, view) {
    view.hidden = false;
    button.setAttribute("aria-expanded", "true");
    button.textContent = "▾";
    button.setAttribute("aria-label", "閉じる");
  }

  function close(button, view) {
    view.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.textContent = "▸";
    button.setAttribute("aria-label", "ここに開く");
  }
})();
