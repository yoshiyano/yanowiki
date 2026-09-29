/*
 * 編集画面の「履歴」タブの中身（`<iframe>` に埋め込む。wikilib.backupui）。
 *
 * ページの選択も履歴の一覧も編集画面（親）が持つ。ここは、親から選ばれた時点の
 * 内容（「すべて戻す」「部分的に戻す」の2タブ）を出して、復元を受け持つだけ。
 * 読み書きはページ自身のURLへの POST（`?cmd=history`。data-action）で行う
 * （以前は /.backup という別のURLだった。Wiki設計者の指示、2026-09-28）。
 * 対象のページはURLで決まるので、`page` は送らない。
 *
 * 1つの状態（detail）・1回の読み込みトークンで両方のタブをまとめて描画する
 * （2026-08-31、Wiki設計者の指示。以前はファイルが分かれ、非同期の応答の順序の
 * ズレで古い値をつかむ不具合が繰り返し起きていた）。タブ切替そのものはfetchも
 * 再描画もせず、描画済みのパネルを hidden で出し入れするだけ。
 *
 * 差分・マージの表示そのものはdiffmerge（/.vendor/diffmerge/diffmerge.umd.js、
 * window.DiffMerge）に**そのまま**まかせる。ここが呼ぶのは render(target, left,
 * right, options) と、その戻り値が持つ getMergedText()/destroy() だけ。
 */
(function () {
  var shell = document.querySelector(".bk-shell");
  if (!shell) return;

  var action = shell.dataset.action;
  var restoreView = shell.querySelector(".bk-restore-view");
  var mergeView = shell.querySelector(".bk-merge-view");
  var restoreForm = shell.querySelector(".bk-restore");
  var restoreBtn = shell.querySelector(".bk-restore-btn");
  var restoreNote = shell.querySelector(".bk-restore-note");
  var mergeForm = shell.querySelector(".bk-merge-form");
  var mergeSaveBtn = shell.querySelector(".bk-merge-save");
  var mergeNote = shell.querySelector(".bk-merge-note");

  var hasDiffMerge = !!window.DiffMerge;

  function get(fields) {
    var data = new FormData();
    Object.keys(fields).forEach(function (k) { data.append(k, fields[k]); });
    return fetch(action, { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json(); });
  }

  function prettyStamp(s) {
    if (!s || s.length !== 13) return s || "";
    return "20" + s.slice(0, 2) + "-" + s.slice(2, 4) + "-" + s.slice(4, 6)
      + " " + s.slice(7, 9) + ":" + s.slice(9, 11) + ":" + s.slice(11, 13);
  }

  // ---- 右: 内容（すべて戻す／部分的に戻す。どちらもdiffmerge） ----
  // 選んでいる時点まわりの状態を1つにまとめておく。両タブはすべて
  // ここ（特に data）から描画され、タブ切替そのものは何も読み直さない。
  var detail = {
    page: null,
    key: null,
    label: "",
    loadToken: 0,   // 選び直すたびに進める。応答が届いたときにこれで照合し、
                    // 後から選んだものだけを反映する（2タブ共通の1つの番号にすることで、
                    // タブ間で順序がずれる余地そのものを無くす）
    data: null,
    restoreHandle: null,  // diffmergeのrender()戻り値（merge:false）
    mergeHandle: null,    // diffmergeのrender()戻り値（merge:true）
  };

  function destroyHandles() {
    if (detail.restoreHandle) { detail.restoreHandle.destroy(); detail.restoreHandle = null; }
    if (detail.mergeHandle) { detail.mergeHandle.destroy(); detail.mergeHandle = null; }
  }

  // 読み込み中の見た目（二重に選んでも loadToken で最後のものだけが残る）
  function setLoading(on) {
    shell.classList.toggle("bk-loading", on);
  }

  function selectVersion(subpath, key) {
    detail.page = subpath;
    detail.key = key;
    detail.data = null;
    var token = ++detail.loadToken;
    setLoading(true);

    get({ data: "version", key: key }).then(function (res) {
      if (token !== detail.loadToken) return;  // 後から選んだものの応答がまだ届いていない
      setLoading(false);
      if (res.error) {
        restoreBtn.disabled = true;
        restoreNote.textContent = res.error;
        mergeSaveBtn.disabled = true;
        mergeNote.textContent = res.error;
        return;
      }
      detail.data = res;
      detail.label = prettyStamp(res.stamp);
      renderAllPanels();
    }).catch(function () {
      if (token !== detail.loadToken) return;
      setLoading(false);
      restoreNote.textContent = "読み込めませんでした。";
      mergeNote.textContent = "読み込めませんでした。";
    });
  }

  // data=version の応答が届いた直後に、2タブぶんをまとめて組み立てる。
  // タブを開いたときに初めて作る、という特別扱いはしない
  // （以前は「一部を戻す」タブだけそうなっていて、それが不具合の元だった）。
  //
  // 差分・マージの中身はdiffmergeの render() にそのまま渡すだけ
  // （left=選んだ時点、right=現在。merge の有無だけが違う）。
  function renderAllPanels() {
    var res = detail.data;
    destroyHandles();

    restoreForm.querySelector('input[name="key"]').value = detail.key;
    // 押すまでの間に他の変更が入っていたら断るための目印。復元も取り込みも
    // 「画面に出ていた差分のとおりに起きる」ことを守るため、両方に持たせる
    restoreForm.querySelector('input[name="base_rev"]').value = res.current_rev;
    mergeForm.querySelector('input[name="base_rev"]').value = res.current_rev;

    if (res.same_as_current || res.empty) {
      var note = res.same_as_current
        ? "この保存前の内容は、いまのページと同じです。"
        : "この保存の前には、ページがまだありません。";
      restoreView.innerHTML = '<p class="bk-empty">' + note + "</p>";
      mergeView.innerHTML = '<p class="bk-empty">' + note + "</p>";
      restoreBtn.disabled = true;
      restoreNote.textContent = note;
      mergeSaveBtn.disabled = true;
      mergeNote.textContent = note;
      return;
    }

    if (hasDiffMerge) {
      detail.restoreHandle = window.DiffMerge.render(restoreView, res.text, res.current, {
        leftTitle: "この保存の前", rightTitle: "現在", merge: false,
      });
      detail.mergeHandle = window.DiffMerge.render(mergeView, res.text, res.current, {
        leftTitle: "この保存の前", rightTitle: "現在", merge: true,
      });
      mergeSaveBtn.disabled = false;
      // 取り込みボタンの使いかた・取り消し/やり直し・編集単位の切り替えは、
      // diffmerge自身がビューの下に説明（.dm-hint）を出す。ここで同じことを
      // 書くと、diffmergeが更新されるたびに古くなるので、この画面ならではの
      // こと（取り込んだ結果をどう保存するか）だけを書く
      mergeNote.textContent = "取り込んだ結果を、いまのページに保存します。";
    } else {
      var dmNote = '<p class="bk-empty">差分の表示を読み込めませんでした。</p>';
      restoreView.innerHTML = dmNote;
      mergeView.innerHTML = dmNote;
      mergeSaveBtn.disabled = true;
      mergeNote.textContent = "差分の表示を読み込めませんでした。";
    }

    restoreBtn.disabled = false;
    restoreNote.textContent = detail.label + " の保存前の状態に戻します。";
  }

  // ---- タブ ----
  // 切替そのものは、すでに renderAllPanels が組み立て終えているパネルを
  // hidden で出し入れするだけ。fetchも再描画もしない
  var tabs = [].slice.call(shell.querySelectorAll(".bk-tab"));
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) {
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      [].forEach.call(shell.querySelectorAll(".bk-panel"), function (p) {
        p.hidden = p.dataset.tab !== tab.dataset.tab;
      });
    });
  });

  // 復元も取り消せないので、いつの状態に戻すのかを見せて確認する
  restoreForm.addEventListener("submit", function (event) {
    if (!window.confirm(detail.label + " の保存前の状態に戻します。\n"
        + "この保存で入った変更が取り消されます。\n"
        + "いまの内容は履歴に残りますが、表示は置き換わります。よろしいですか？")) {
      event.preventDefault();
    }
  });

  // 部分的に戻す（マージ）の保存。取り込んだ結果は画面側（diffmergeのハンドル）
  // が持っているので、送信直前にそこから取り出す
  mergeForm.addEventListener("submit", function (event) {
    if (!detail.mergeHandle) { event.preventDefault(); return; }
    mergeForm.querySelector('input[name="merged"]').value = detail.mergeHandle.getMergedText();
    if (!window.confirm("選んだ内容をいまのページへ保存します。よろしいですか？")) {
      event.preventDefault();
    }
  });

  /* 親（編集画面）から、選ばれた時点を受け取る */
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    var data = event.data;
    if (!data || data.type !== "wiki-backup-select" || !data.key) return;
    selectVersion(data.page || shell.dataset.page || "", data.key);
  });

  /* 復元が済んだら、親の編集画面へ知らせる。復元でページの保存内容が変わるので、
     編集画面は開き直す（editor.js が受ける）。復元の直後の表示にだけ
     data-restored が付いている（wikilib.backupui.build_history_html）。 */
  if (window.parent !== window && shell.dataset.restored === "1") {
    window.parent.postMessage({ type: "wiki-backup-restored", message: shell.dataset.message || "" },
                              window.location.origin);
  }
})();
