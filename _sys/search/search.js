/* 検索結果のページ送り（/.search.js）。
 *
 * ページ送りを押したとき、ページ全体を読み直さずに結果の部分だけを差し替える。
 * 読みに行くのは表示中と同じURLに `fragment=1` を足したもので、サーバーは
 * 同じ組み立て（search.render_results_block）の結果だけを返す。
 *
 * **JavaScriptが無くても使える。** ページ送りはふつうのリンク（href付き）として
 * 出してあるので、ここが動かなければ素直にページ遷移するだけになる。
 */
(function () {
  "use strict";

  var block = document.querySelector(".search-block");
  if (!block || !window.fetch || !window.history || !window.history.pushState) return;

  /* 差し替えても同じ位置に居続けるための入れもの。
     .search-block ごと入れ替えるので、その親を覚えておく。 */
  var host = block.parentNode;

  function fragmentUrl(url) {
    return url + (url.indexOf("?") >= 0 ? "&" : "?") + "fragment=1";
  }

  function load(url, push) {
    var current = host.querySelector(".search-block");
    if (current) current.className += " is-loading";

    fetch(fragmentUrl(url), { headers: { "X-Requested-With": "fetch" } })
      .then(function (res) {
        if (!res.ok) throw new Error(res.status);
        return res.text();
      })
      .then(function (html) {
        var holder = document.createElement("div");
        holder.innerHTML = html;
        var fresh = holder.querySelector(".search-block");
        if (!fresh) throw new Error("no block");
        current.parentNode.replaceChild(fresh, current);
        if (push) history.pushState({ searchUrl: url }, "", url);
        /* 結果の先頭が見えるところまで戻す。ページを送ったのに前のページの
           末尾を見たままだと、切り替わったことに気づけない。 */
        fresh.scrollIntoView({ block: "start", behavior: "smooth" });
      })
      .catch(function () {
        /* 読めなければ、ふつうのページ遷移に任せる（結果が出ないまま
           止まってしまうより、遅くても確実に出るほうがよい） */
        window.location.href = url;
      });
  }

  /* ページ送りは差し替えのたびに作り直されるので、個々のリンクではなく
     親でクリックを受ける（張り直しが要らない）。 */
  host.addEventListener("click", function (event) {
    var link = event.target.closest ? event.target.closest("a[data-search-page]") : null;
    if (!link || !host.contains(link)) return;
    /* 別タブで開く操作（Ctrl/Cmd/中クリック）は邪魔しない */
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    load(link.getAttribute("href"), true);
  });

  /* 「戻る」で前のページ番号に戻れるようにする */
  window.addEventListener("popstate", function (event) {
    var url = (event.state && event.state.searchUrl) || window.location.href;
    load(url, false);
  });
})();
