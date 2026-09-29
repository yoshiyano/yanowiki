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
        })
        .catch(function () {
          // 失敗しても一覧は使えるままにしておく。閉じれば元に戻る
          view.innerHTML = '<p class="ls-view-error">読み込めませんでした。</p>';
        });
    });
  });

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
