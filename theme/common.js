/*
 * すべてのテーマが読み込むスクリプト。
 *
 * ここに置くのは「テーマの作りに関わらず働くもの」だけです。目印は2通りあります。
 *
 * (1) サーバーがどのテーマにも同じ形で渡すもの
 *
 *   .content[data-editable]   本文（編集できるページのみ）＝セクション編集
 *   .content[data-draft]      別で編集中（セクション編集を開くだけにする）
 *   .toc a[href^="#"]         目次のリンク
 *
 * (2) テーマがHTMLで用意する、決まったクラス名（検索）
 *
 *   .search             検索フォーム全体
 *   .search-word        検索語の入力欄
 *   .search-scope       範囲の切り替えボタン（data-scope="site"|"page"）
 *   .search-submit      検索ボタン
 *   .search-options     サイト全体検索の条件パネル（hidden で閉じる）
 *   .page-search-nav    ページ内検索の前へ/次へ（hidden で閉じる）
 *   .page-search-prev / .page-search-next / .page-search-count
 *     ページ内検索では矢印キーも使える。左右=1つ前/次（ボタンと同じ）、
 *     上下=今の画面に見えている候補群を飛ばして画面外へジャンプ。
 *     入力欄（.search-word）にフォーカスが無くても、.search（検索窓）か
 *     .page-search-panel（結果一覧）にマウスが乗っている間は有効
 *   .page-search-panel  一致箇所の一覧（hidden で閉じる）。
 *     見出し行.page-search-panel-headをつかみ手にマウスでドラッグ移動できる
 *   .page-search-list / .page-search-more / .page-search-close
 *   .search-modal-open / .search-modal / .search-modal-close /
 *     .search-modal-panel / .search-modal-head  検索を独立したモーダルに
 *     する（任意。使うテーマだけ持てばよい）。.search-modal-openクリック
 *     で.searchを含む.search-modalのhidden属性を外し、.search-modal-close
 *     クリックかEscapeで閉じる（外側クリックでは閉じない・入力欄の値や
 *     検索結果も消さない）。.search-modal-panelは.search-modal-headを
 *     つかみ手にドラッグ移動できる（.page-search-panelと同じ仕組み）
 *   [data-hotkey="edit"]  編集リンク。付いていればAlt+Eで直接遷移する
 *   [data-new-page-open] / .new-page-dialog  コマンドバーの「新規」ボタン。
 *     押すと.new-page-dialog（本体のcommon_menuが渡す<dialog>）を開いてページ名を
 *     入力させ、「開く」でそのページの編集画面へ cmd=edit で移る（既存
 *     ページ名でも、ふつうにその編集画面が開くだけでよい）。入口URLは
 *     .new-page-dialog自身のdata-base-urlから読む（ダイアログは本体の
 *     common_menuが組み立てるので、テーマの作りに関わらず必ずある）
 *   .subbar / .mainbar  タップ/スワイプでの開閉。CSS側が
 *     position: fixed にして折りたたみ表示にしている間だけ動く
 *     （それ以外の画面幅では何もしない）
 *   .zoom-in / .zoom-out / .zoom-value  表示の拡大縮小。ボタンは
 *     LABELSの前後の段階へ移動（ループしない、端ではdisabledになる、
 *     倍率はtitle属性でマウスオーバー時に表示）。.zoom-valueは現在の
 *     倍率(%)を表示する数値入力欄で、書き換えてEnterを押すと
 *     LABELSに無い任意の値にもできる。
 *     --bp-narrow / --bp-narrower をテーマの:rootが持っていれば、
 *     いまの拡大率に応じて html.bp-narrow / html.bp-narrower も
 *     付け外しする（レスポンシブのしきい値を拡大率と連動させたい
 *     テーマ向け。持っていなければ何もしない）
 *   .site-header / #header  画面上部に固定したヘッダ（position: sticky/fixed
 *     のときだけ）。高さを測って html の --anchor-offset に入れ、
 *     common.css の scroll-padding-top でページ内アンカーの移動先が
 *     ヘッダに隠れないようにする。無い・固定していないなら 0
 *
 * (2) は common.js が作るのではなく、**テーマが置いたものに振る舞いを付ける**
 * 形です。クラス名を合わせておけば、一から書いたテーマでも検索が使えます。
 * 見つからなければ何もしないので、検索フォームを置かないテーマでも問題ありません。
 *
 * このファイルを wikidata/<Wiki名>/theme/common.js にコピーすると、
 * そのWikiだけ挙動を差し替えられます。
 */
(function () {
  "use strict";

  /* ---- セクション編集（試験的）--------------------------------------------
   * Ctrl+Alt+ダブルクリックした見出し／本文のかたまりを、その場でtextareaに
   * 差し替えて生テキストを編集し、サーバーでレンダリングしたプレビューを
   * その下に表示する。トリプルクリックは通常のテキスト選択と紛らわしいため、
   * 他の操作とまず衝突しないCtrl+Alt+ダブルクリックを検出条件にしている。
   *
   * 編集範囲の考えかた:
   *   見出しをクリック   … その見出し（レベルLとする）から、次に現れる
   *                        レベルL以下（同じか、より上位）の見出しの手前まで。
   *                        配下の下位見出し（レベルが深いもの）は内包する。
   *   本文をクリック     … 直前の見出しの「次の行」から、同じ規則で決まる
   *                        終端まで（見出し行自体は含まない）。
   *   見出しが1つも無い、またはどの見出しより前をクリック … ページ先頭から
   *                        最初の見出しの手前まで（無ければページ全体）。
   *
   * サーバー側 (/.section/<page>, <page>?cmd=preview) が同じ考えかたで生テキストの
   * 切り出しとレンダリングを行う。
   *
   * 保存は「ページ全体」を送る（Wiki設計者の指示、2026-09-01）。開くときに
   * ?parts=1 を付けて {before, section, after, origin} をJSONで受け取り、
   * before/afterはそのまま隠し持っておく。保存時は before + textareaの
   * 中身 + after をPOSTし、origin（開いたときのページ全体のハッシュ）を
   * 添えて競合を判定してもらう。見出しidの管理も、切り出し範囲の食い違いも
   * 気にしなくてよくなる（詳細は/Tech/SectionEditingの「保存のやりとり」）。
   * 1回のPOSTの上限に届く長さのページは、編集画面の一時保存と同じ仕組み
   * （chunk_id/chunk_index/chunk_total/part）で分けて送る。
   */
  (function () {
    var content = document.querySelector(".content[data-editable]");
    if (!content) return;

    var baseUrl = content.dataset.baseUrl || "";
    var page = content.dataset.page || "";
    var PREVIEW_DEBOUNCE = 300;
    // 分けて送るときの1回ぶんの大きさ。_sys/editor/editor.jsのwikiSendと同じ値
    // （サーバー側 wikilib.chunked.CHUNK_BYTES も1MB）。セクション編集は
    // 独立ページなのでwikiSendを読み込んでおらず、ここで小さく作り直している。
    var CHUNK_BYTES = 1024 * 1024;

    function newChunkId() {
      var chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
      var out = "";
      for (var i = 0; i < 24; i += 1) {
        out += chars.charAt(Math.floor(Math.random() * chars.length));
      }
      return out;
    }

    // 送って、応答をJSONとして読む。204（分割送信の途中）はbody=nullで返す。
    function postAndParse(url, data) {
      return fetch(url, { method: "POST", body: data }).then(function (r) {
        if (r.status === 204) return { status: 204, body: null };
        return r.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (e) { /* bodyはnullのまま */ }
          return { status: r.status, body: body };
        });
      });
    }

    // ページ全体（before + 編集した節 + after）を保存する。CHUNK_BYTESを
    // 超える長さなら、編集画面の一時保存と同じ形（chunk_id/chunk_index/
    // chunk_total/part）で分けて送る。応答が204である間（＝まだ途中）は
    // 続きを送り、204でなくなった時点の応答bodyを返す（成功でも断りでも）。
    function saveSection(url, text, origin) {
      var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      if (blob.size <= CHUNK_BYTES) {
        var data = new FormData();
        data.append("source", text);
        data.append("origin", origin);
        return postAndParse(url, data).then(function (res) { return res.body; });
      }
      var total = Math.max(1, Math.ceil(blob.size / CHUNK_BYTES));
      var id = newChunkId();
      var index = 0;
      function step() {
        var start = index * CHUNK_BYTES;
        var piece = blob.slice(start, Math.min(blob.size, start + CHUNK_BYTES));
        var data = new FormData();
        data.append("origin", origin);
        data.append("chunk_id", id);
        data.append("chunk_index", String(index));
        data.append("chunk_total", String(total));
        data.append("part", piece, "part");
        return postAndParse(url, data).then(function (res) {
          if (res.status === 204) {
            index += 1;
            return step();
          }
          return res.body;
        });
      }
      return step();
    }

    function isHeading(el) {
      return !!el && /^H[1-6]$/.test(el.tagName);
    }

    function levelOf(el) {
      return parseInt(el.tagName.slice(1), 10);
    }

    // event.targetから、contentの直接の子（今回の「かたまり」の単位）まで遡る。
    // content自身がクリックされた場合（要素の外の余白等）はnullを返す。
    function topLevelAncestor(el) {
      if (!content.contains(el) || el === content) return null;
      var node = el;
      while (node.parentElement !== content) node = node.parentElement;
      return node;
    }

    // nodeの属するセクションの見出しを返す。nodeが見出しならそれ自身。
    // 見つからなければnull（＝最初の見出しより前の領域）。
    function ownerHeading(node) {
      if (isHeading(node)) return node;
      var cur = node.previousElementSibling;
      while (cur && !isHeading(cur)) cur = cur.previousElementSibling;
      return cur;
    }

    // headingElから、次の「同レベル以上」の見出しの手前までの要素を集める。
    // includeHeading=true なら見出し自身も含む（見出しクリック時）。
    // headingEl=null なら、contentの先頭から最初の見出しの手前まで。
    function collectRange(headingEl, includeHeading) {
      var maxLevel = headingEl ? levelOf(headingEl) : null;
      var els = [];
      var cur;
      if (headingEl && includeHeading) {
        // 見出し自身は「境界チェック」の対象外として無条件に含める
        // （自分自身のレベルは常にmaxLevel以下なので、含めた上でチェックすると
        // 最初の1件でその場で境界条件に一致してしまう）
        els.push(headingEl);
        cur = headingEl.nextElementSibling;
      } else {
        cur = headingEl ? headingEl.nextElementSibling : content.firstElementChild;
      }
      while (cur) {
        if (isHeading(cur) && (maxLevel === null || levelOf(cur) <= maxLevel)) break;
        els.push(cur);
        cur = cur.nextElementSibling;
      }
      return els;
    }

    // プレビューの応答ヘッダー（JSONの配列）からURLの一覧を読む。無い・壊れていれば空
    function headerUrls(r, name) {
      try {
        var list = JSON.parse(r.headers.get(name) || "[]");
        return Array.isArray(list) ? list : [];
      } catch (e) {
        return [];
      }
    }

    // プレビューで使われたプラグインの資材のうち、このページがまだ読み込んで
    // いないものだけを足す。ページは「そのページで使われたプラグイン」の資材しか
    // 読み込まないので、元々数式の無いページで初めて &katex を書くと、組版する
    // JSが無い。足したJSは読み込まれた時点でページ全体を処理する（katex.js も
    // Prism も読み込み時に自分で走る）ので、差し込み済みのプレビューも組版される。
    // 読み込み済みかはURLの完全一致で見る（サーバーがページと同じ関数で作る）
    function loadPluginAssets(r) {
      var head = document.head;
      headerUrls(r, "X-Wiki-Plugin-Styles").forEach(function (url) {
        var known = Array.prototype.some.call(
          document.querySelectorAll('link[rel="stylesheet"]'),
          function (el) { return el.getAttribute("href") === url; });
        if (known) return;
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        head.appendChild(link);
      });
      headerUrls(r, "X-Wiki-Plugin-Scripts").forEach(function (url) {
        var known = Array.prototype.some.call(
          document.querySelectorAll("script[src]"),
          function (el) { return el.getAttribute("src") === url; });
        if (known) return;
        var script = document.createElement("script");
        script.src = url;
        head.appendChild(script);
      });
    }

    function renderPreview(previewEl, url, text) {
      var response = null;
      fetch(url, { method: "POST", body: text })
        .then(function (r) {
          response = r;
          return r.ok ? r.text() : Promise.reject(r.status);
        })
        .then(function (html) {
          previewEl.innerHTML = html;
          // 資材を足すのは差し込んだあと（読み込まれたJSが、差し込んだ分を拾えるように）
          loadPluginAssets(response);
          // 編集画面のライブプレビューと同じ理由（Prismはページ読み込み時の
          // highlightAll()しか自動で走らないため、差し込んだ分は自分で
          // 拾い直す）。まだ読み込まれていなければ（このページが元々 #code を
          // 使っていない）、上で足したJSが読み込まれた時点で自分で処理する。
          if (typeof Prism !== "undefined") Prism.highlightAllUnder(previewEl);
          // Prismと同じ理由。まだ無ければ、足した katex.js が読み込み時に組版する。
          if (window.KatexPlugin) window.KatexPlugin.renderAllUnder(previewEl);
        })
        .catch(function () {
          // プレビューの失敗は編集の妨げにしない。前回の表示を残す。
        });
    }

    function openEditor(topEl) {
      var clickedIsHeading = isHeading(topEl);
      var owner = ownerHeading(topEl);
      var scope = clickedIsHeading ? "header" : "body";
      var headingId = owner ? owner.id : "";
      var rangeEls = collectRange(owner, clickedIsHeading);
      if (!rangeEls.length) return false;

      var wrap = document.createElement("div");
      wrap.className = "section-editor";

      var textarea = document.createElement("textarea");
      textarea.className = "section-editor-source";
      textarea.spellcheck = false;
      textarea.disabled = true;
      textarea.value = "読み込み中…";

      var toolbar = document.createElement("div");
      toolbar.className = "section-editor-toolbar";
      var status = document.createElement("span");
      status.className = "section-editor-status";

      var saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.className = "section-editor-save";
      saveButton.textContent = "保存";
      saveButton.disabled = true;  // 節の中身（before/after/origin含む）を受け取るまでは押せない

      var closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "section-editor-close";
      closeButton.textContent = "閉じる";
      toolbar.appendChild(status);
      toolbar.appendChild(saveButton);
      toolbar.appendChild(closeButton);

      var preview = document.createElement("div");
      preview.className = "section-editor-preview content";

      wrap.appendChild(toolbar);
      wrap.appendChild(textarea);
      wrap.appendChild(preview);

      rangeEls[0].parentNode.insertBefore(wrap, rangeEls[0]);
      rangeEls.forEach(function (el) { el.remove(); });

      function close() {
        rangeEls.forEach(function (el) { wrap.parentNode.insertBefore(el, wrap); });
        wrap.remove();
      }
      closeButton.addEventListener("click", close);

      // "" の場合、'/.section/' + page がそのまま /.section/ になり、
      // 先頭見出しより前の領域（heading省略）として扱われる。
      // parts=1 を付けると、節の生テキストだけでなく前後とorigin（保存時に
      // 使う）もJSONで返る。
      var editUrl = baseUrl + "/.section/" + page;
      var sectionUrl = editUrl
        + "?heading=" + encodeURIComponent(headingId) + "&scope=" + scope + "&parts=1";
      // プレビューはページ自身の通常URLへ送る（2026-09-17に `/.preview/<page>` から変更）
      var previewUrl = baseUrl + "/" + page + "?cmd=preview";

      var before = "";
      var after = "";
      var origin = "";

      fetch(sectionUrl)
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function (data) {
          before = data.before || "";
          after = data.after || "";
          origin = data.origin || "";
          textarea.disabled = false;
          textarea.value = data.section || "";
          saveButton.disabled = false;
          textarea.focus();
          renderPreview(preview, previewUrl, textarea.value);
        })
        .catch(function () {
          status.classList.add("is-error");
          status.textContent = "取得に失敗しました";
        });

      var timer = null;
      textarea.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          renderPreview(preview, previewUrl, textarea.value);
        }, PREVIEW_DEBOUNCE);
      });

      // 別で編集中（data-draft）でも保存を試せる。踏み潰さないための
      // 判定はサーバー側（保存時、突き合わせる）に任せる。「書きかけを
      // 預かっていて、しかもその間に更新もあった」場合だけ断られ、
      // そのmessageをそのまま出す（/Tech/SectionEditing#保存のやりとり）。
      saveButton.addEventListener("click", function () {
        if (saveButton.disabled) return;
        saveButton.disabled = true;
        closeButton.disabled = true;  // 送信中に閉じると宛先を失うため
        status.classList.remove("is-error");
        status.textContent = "保存中…";

        saveSection(editUrl, before + textarea.value + after, origin)
          .then(function (data) {
            if (data && data.ok && data.changed) {
              window.location.reload();
              return;
            }
            if (data && data.ok) {
              // 中身が変わっていなかった。保存済みの状態と同じなので閉じるだけ
              close();
              return;
            }
            if (data && data.conflict && data.url) {
              window.location.href = data.url;
              return;
            }
            saveButton.disabled = false;
            closeButton.disabled = false;
            status.classList.add("is-error");
            status.textContent = (data && data.message) || "保存できませんでした。";
          })
          .catch(function () {
            saveButton.disabled = false;
            closeButton.disabled = false;
            status.classList.add("is-error");
            status.textContent = "通信に失敗しました。";
          });
      });

      return true;
    }

    content.addEventListener("dblclick", function (event) {
      if (!event.ctrlKey || !event.altKey) return;
      if (content.querySelector(".section-editor")) return;  // 同時に1つまで
      var top = topLevelAncestor(event.target);
      if (!top) return;
      if (openEditor(top)) event.preventDefault();
    });
  })();

  /* ---- 目次: 現在表示中の見出しに .current を付ける ---- */
  (function () {
    var tocLinks = document.querySelectorAll(".toc a[href^='#']");
    if (!tocLinks.length || !("IntersectionObserver" in window)) return;

    var byId = {};
    tocLinks.forEach(function (a) {
      byId[decodeURIComponent(a.getAttribute("href").slice(1))] = a;
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = byId[entry.target.id];
        if (link) link.classList.toggle("current", entry.isIntersecting);
      });
    }, { rootMargin: "0px 0px -70% 0px" });

    Object.keys(byId).forEach(function (id) {
      var heading = document.getElementById(id);
      if (heading) observer.observe(heading);
    });
  })();


  /* ---- ページ内検索 ----------------------------------------------------
   * 本文中の一致箇所をすべて強調し、前へ/次へで順に辿れるようにする。
   * 検索結果から ?q= 付きで開いた場合も、同じ仕組みで最初の一致へ移動する。
   */
  (function () {
    var content = document.querySelector(".content");
    var form = document.querySelector(".search");
    if (!content || !form) return;

    var input = form.querySelector(".search-word");
    var scope = form.querySelector(".search-scope");
    var nav = form.querySelector(".page-search-nav");
    var counter = form.querySelector(".page-search-count");
    var prevButton = form.querySelector(".page-search-prev");
    var nextButton = form.querySelector(".page-search-next");
    if (!input || !scope || !nav) return;

    // .search-options はテンプレート上フォームの外（overflow:hiddenの外）に
    // 置かれているため、form.querySelector ではなく文書全体から探す。
    var options = document.querySelector(".search-options");
    var panel = document.querySelector(".page-search-panel");
    var list = panel && panel.querySelector(".page-search-list");
    var more = panel && panel.querySelector(".page-search-more");
    var closeButton = panel && panel.querySelector(".page-search-close");

    var LIST_LIMIT = 100;  // 一覧に並べる上限。多すぎると表示が重くなるため
    var hits = [];
    var entries = [];
    var index = -1;
    var timer = null;

    var SCOPE_LABEL = { site: "サイト全体", page: "このページ内" };

    function inPage() {
      return scope.dataset.scope === "page";
    }

    function setScope(value) {
      scope.dataset.scope = value;
      scope.textContent = SCOPE_LABEL[value];
      scope.setAttribute("aria-pressed", String(value === "page"));
      scope.setAttribute("aria-label", "検索範囲を切り替え（現在: " + SCOPE_LABEL[value] + "）");
    }

    // 範囲を実際に切り替えたときの後処理（トグルでもメニュー選択でも共通）
    function applyScope(value) {
      if (value === scope.dataset.scope) return;
      setScope(value);
      if (inPage()) {
        showOptions(false);
        run(input.value, true);
      } else {
        clearMarks();
        updateCounter("");
        showOptions(true);
      }
    }

    // サイト全体を検索するときの条件パネル。ページ内検索では使わないので出さない。
    // .search は連結した見た目にするため overflow:hidden を掛けており、その中に
    // 置くとクリップされてしまうため、表示時にdocument.body直下へ移し、
    // 検索フォームの右端に合わせて位置を計算する（範囲メニューと同じ考えかた）。
    function showOptions(show) {
      if (!options) return;
      var visible = show && !inPage();
      if (visible) {
        if (options.parentElement !== document.body) document.body.appendChild(options);
        var r = form.getBoundingClientRect();
        options.style.top = (r.bottom + 6) + "px";
        // window.innerWidthはスクロールバーを含むためgetBoundingClientRectの座標系と
        // ずれる。documentElement.clientWidthはスクロールバーを含まず一致する。
        options.style.right = (document.documentElement.clientWidth - r.right) + "px";
      }
      options.hidden = !visible;
    }

    // サーバ側の検索と同じ切り出しかた。"..." でくくると空白を含む語になる。
    // ワイルドカードの記号は本文には現れないので取り除く。
    function parseTerms(query) {
      var terms = [];
      var re = /"([^"]+)"|(\S+)/g;
      var found;
      while ((found = re.exec(query))) {
        var term = (found[1] || found[2]).replace(/[*?[\]]/g, "");
        if (term) terms.push(term);
      }
      return terms;
    }

    // 前回の強調を取り消して、元のテキストに戻す
    function clearMarks() {
      var marks = content.querySelectorAll("mark.search-hit");
      for (var i = 0; i < marks.length; i++) {
        var parent = marks[i].parentNode;
        parent.replaceChild(document.createTextNode(marks[i].textContent), marks[i]);
        parent.normalize();
      }
      hits = [];
      entries = [];
      index = -1;
      if (list) list.textContent = "";
      if (panel) panel.hidden = true;
    }

    // 一致箇所の前後を、その段落や項目の範囲で切り出す
    function contextOf(mark) {
      var block = mark.closest("p, li, td, th, h1, h2, h3, h4, h5, h6, pre, blockquote") || content;
      var before = document.createRange();
      before.setStart(block, 0);
      before.setEndBefore(mark);
      var after = document.createRange();
      after.setStartAfter(mark);
      after.setEnd(block, block.childNodes.length);

      var head = before.toString().replace(/\s+/g, " ");
      var tail = after.toString().replace(/\s+/g, " ");
      return {
        head: head.length > 30 ? "…" + head.slice(-30) : head,
        tail: tail.length > 50 ? tail.slice(0, 50) + "…" : tail
      };
    }

    // 一致箇所の一覧をパネルに並べる
    function renderPanel() {
      if (!panel || !list) return;
      list.textContent = "";
      entries = [];

      hits.slice(0, LIST_LIMIT).forEach(function (mark, i) {
        var around = contextOf(mark);
        var item = document.createElement("li");
        var button = document.createElement("button");
        button.type = "button";
        button.className = "page-search-item";
        button.appendChild(document.createTextNode(around.head));
        var strong = document.createElement("mark");
        strong.textContent = mark.textContent;
        button.appendChild(strong);
        button.appendChild(document.createTextNode(around.tail));
        button.addEventListener("click", function () {
          focusHit(i);
          updateCounter(input.value.trim());
        });
        item.appendChild(button);
        list.appendChild(item);
        entries.push(button);
      });

      if (more) {
        var rest = hits.length - LIST_LIMIT;
        more.hidden = rest <= 0;
        more.textContent = rest > 0 ? "ほか " + rest + " 件（前へ/次へで辿れます）" : "";
      }
      panel.hidden = hits.length === 0;
    }

    function markAll(terms) {
      var pattern = new RegExp(
        terms.map(function (t) {
          return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }).join("|"),
        "gi"
      );

      var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
      var nodes = [];
      var node;
      while ((node = walker.nextNode())) nodes.push(node);

      nodes.forEach(function (textNode) {
        if (!textNode.nodeValue.trim()) return;
        if (textNode.parentNode.closest("script, style")) return;

        pattern.lastIndex = 0;
        if (!pattern.test(textNode.nodeValue)) return;

        pattern.lastIndex = 0;
        var fragment = document.createDocumentFragment();
        var last = 0;
        var match;
        while ((match = pattern.exec(textNode.nodeValue))) {
          fragment.appendChild(
            document.createTextNode(textNode.nodeValue.slice(last, match.index))
          );
          var mark = document.createElement("mark");
          mark.className = "search-hit";
          mark.textContent = match[0];
          fragment.appendChild(mark);
          hits.push(mark);
          last = match.index + match[0].length;
          if (match[0].length === 0) pattern.lastIndex++;  // 無限ループ防止
        }
        fragment.appendChild(document.createTextNode(textNode.nodeValue.slice(last)));
        textNode.parentNode.replaceChild(fragment, textNode);
      });
    }

    function updateCounter(query) {
      nav.hidden = !inPage() || !query;
      if (!query) {
        counter.textContent = "";
      } else if (!hits.length) {
        counter.textContent = "一致なし";
      } else {
        counter.textContent = (index + 1) + " / " + hits.length;
      }
      var disabled = hits.length === 0;
      prevButton.disabled = disabled;
      nextButton.disabled = disabled;
    }

    // i番目の一致を現在位置にして画面内へ送る
    function focusHit(i) {
      if (!hits.length) return;
      if (index >= 0 && hits[index]) hits[index].classList.remove("current");
      if (index >= 0 && entries[index]) entries[index].classList.remove("current");
      index = (i + hits.length) % hits.length;
      hits[index].classList.add("current");
      hits[index].scrollIntoView({ block: "center", behavior: "smooth" });
      if (entries[index]) {
        entries[index].classList.add("current");
        entries[index].scrollIntoView({ block: "nearest" });
      }
    }

    function run(query, jump) {
      clearMarks();
      var terms = parseTerms(query);
      if (terms.length) markAll(terms);
      renderPanel();
      if (jump && hits.length) {
        focusHit(0);
      }
      updateCounter(query.trim());
    }

    function step(delta) {
      if (!hits.length) return;
      focusHit(index + delta);
      updateCounter(input.value.trim());
    }

    // 現在ビューポートに見えている候補かどうか
    function isInViewport(el) {
      var r = el.getBoundingClientRect();
      return r.bottom > 0 && r.top < window.innerHeight;
    }

    // 上下矢印用: 今の画面内に見えている候補群を飛ばして、
    // 画面外にある次/前の候補へジャンプする
    function stepPastViewport(delta) {
      if (!hits.length) return;
      var i = index < 0 ? 0 : index;
      var start = i;
      do {
        i = (i + delta + hits.length) % hits.length;
      } while (i !== start && isInViewport(hits[i]));
      focusHit(i);
      updateCounter(input.value.trim());
    }

    // 「このページ内」のときは移動せず、その場で検索する
    form.addEventListener("submit", function (event) {
      if (!inPage()) return;  // サイト全体の検索は通常どおり検索ページへ送る
      event.preventDefault();
      window.clearTimeout(timer);
      if (hits.length) {
        // .page-search-closeで窓を閉じただけ（hitsは保持したまま）の
        // ときも、「検索」ボタン（このsubmit）を押せば再表示する
        if (panel) panel.hidden = false;
        step(1);
      } else {
        run(input.value, true);
      }
    });

    input.addEventListener("input", function () {
      if (!inPage()) return;
      // 打っている途中で毎回走らせると重いので、少し待ってからまとめて処理する
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        run(input.value, true);
      }, 150);
    });

    input.addEventListener("keydown", function (event) {
      if (!inPage()) return;
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();  // Shift+Enterで前の一致へ戻る
        step(-1);
      } else if (event.key === "Escape") {
        input.value = "";
        run("", false);
      }
    });

    // ---- 矢印キーでの候補移動は、入力欄にフォーカスが無くても、
    // 検索窓（.search）か結果一覧（.page-search-panel）にマウスが
    // 乗っている間は使えるようにする。カーソルを外欄に置いたまま
    // マウスだけ結果一覧に持っていって辿れるようにするため。
    // hoverCountは「入れ子・複数要素にまたがって乗っている」場合も
    // 正しく判定できるよう、enter/leaveで加減算する単純なカウンタ。
    var hoverCount = 0;
    function hoverEnter() { hoverCount++; }
    function hoverLeave() { hoverCount = Math.max(0, hoverCount - 1); }
    form.addEventListener("mouseenter", hoverEnter);
    form.addEventListener("mouseleave", hoverLeave);
    if (panel) {
      panel.addEventListener("mouseenter", hoverEnter);
      panel.addEventListener("mouseleave", hoverLeave);
    }

    document.addEventListener("keydown", function (event) {
      if (!inPage()) return;
      if (document.activeElement !== input && hoverCount === 0) return;
      if (event.key === "ArrowLeft") {
        // 左右矢印: prev/nextボタンと同じ、1つ前/次の候補へ
        event.preventDefault();
        step(-1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        step(1);
      } else if (event.key === "ArrowUp") {
        // 上下矢印: 今の画面に見えている候補群を飛ばして画面外へ大きくジャンプ
        event.preventDefault();
        stepPastViewport(-1);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        stepPastViewport(1);
      }
    });

    input.addEventListener("focus", function () { showOptions(true); });

    // 検索フォームからも条件パネル（.search-options、フォームの外にある）からも
    // 外れたらパネルを閉じる。2箇所どちらにも属さない場所へフォーカスが移った
    // ときだけ閉じるようにし、フォーム↔パネル間の行き来では閉じないようにする。
    function stillInSearchUI(el) {
      return !!el && (form.contains(el) || (options && options.contains(el)));
    }
    function handleFocusOut(event) {
      if (!stillInSearchUI(event.relatedTarget)) showOptions(false);
    }
    form.addEventListener("focusout", handleFocusOut);
    if (options) options.addEventListener("focusout", handleFocusOut);

    // 検索範囲ボタン: そのままクリックすればトグル、押したまま動かす（ドラッグ）と
    // 選択メニューが出て、指を離した場所の項目が選ばれる。
    (function () {
      var DRAG_THRESHOLD = 6;  // これ未満の移動はクリックとして扱う（誤操作防止）
      var menu = null;
      var pressed = false;
      var dragging = false;
      var startX = 0;
      var startY = 0;
      var suppressClick = false;

      function buildMenu() {
        if (menu) return menu;
        menu = document.createElement("div");
        menu.className = "search-scope-menu";
        menu.hidden = true;
        Object.keys(SCOPE_LABEL).forEach(function (value) {
          var item = document.createElement("button");
          item.type = "button";
          item.className = "search-scope-item";
          item.dataset.scope = value;
          item.textContent = SCOPE_LABEL[value];
          menu.appendChild(item);
        });
        // .search は連結した見た目にするため overflow:hidden を掛けているので、
        // メニューはその外（body直下）に置く。位置はshowMenuで実際の座標から設定する。
        document.body.appendChild(menu);
        return menu;
      }

      function itemAt(x, y) {
        var items = buildMenu().querySelectorAll(".search-scope-item");
        for (var i = 0; i < items.length; i++) {
          var r = items[i].getBoundingClientRect();
          if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return items[i];
        }
        return null;
      }

      function showMenu(x, y) {
        var m = buildMenu();
        var items = m.querySelectorAll(".search-scope-item");
        for (var i = 0; i < items.length; i++) {
          items[i].classList.toggle("current", items[i].dataset.scope === scope.dataset.scope);
        }
        var r = scope.getBoundingClientRect();
        m.style.left = r.left + "px";
        m.style.top = (r.bottom + 4) + "px";
        m.hidden = false;
        highlight(x, y);
      }

      function highlight(x, y) {
        var hit = itemAt(x, y);
        buildMenu().querySelectorAll(".search-scope-item").forEach(function (item) {
          item.classList.toggle("hover", item === hit);
        });
        return hit;
      }

      scope.addEventListener("pointerdown", function (event) {
        if (event.button !== undefined && event.button !== 0) return;  // 左クリック/タップのみ
        pressed = true;
        dragging = false;
        startX = event.clientX;
        startY = event.clientY;
        scope.setPointerCapture(event.pointerId);
      });

      scope.addEventListener("pointermove", function (event) {
        if (!pressed) return;
        if (!dragging) {
          var moved = Math.hypot(event.clientX - startX, event.clientY - startY);
          if (moved < DRAG_THRESHOLD) return;
          dragging = true;
          showMenu(event.clientX, event.clientY);
        }
        highlight(event.clientX, event.clientY);
      });

      scope.addEventListener("pointerup", function (event) {
        pressed = false;
        if (!dragging) return;  // クリックとして扱う。トグルはclickイベント側で行う
        dragging = false;
        suppressClick = true;  // 直後に発火するclickイベントで二重にトグルしない
        var hit = itemAt(event.clientX, event.clientY);
        if (menu) menu.hidden = true;
        if (hit) applyScope(hit.dataset.scope);
      });

      // 何かに触れずに終わった場合（画面外でボタンを離した等）の後始末
      scope.addEventListener("pointercancel", function () {
        pressed = false;
        dragging = false;
        if (menu) menu.hidden = true;
      });

      scope.addEventListener("click", function (event) {
        if (suppressClick) {
          suppressClick = false;
          event.preventDefault();
          return;
        }
        applyScope(inPage() ? "site" : "page");
      });
    })();

    prevButton.addEventListener("click", function () { step(-1); });
    nextButton.addEventListener("click", function () { step(1); });

    if (closeButton) {
      // 窓を閉じるだけ。キーワード・ハイライト・件数（hits）はそのまま
      // 保持する（Wiki設計者の指示）。再表示は「検索」ボタン（フォームの
      // submit）を押したときだけ（下のsubmitハンドラ参照）。
      closeButton.addEventListener("click", function () {
        panel.hidden = true;
      });
    }

    // どこにいてもEscapeで検索を解除できるようにする
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      if (options && !options.hidden) {
        showOptions(false);
      } else if (inPage() && hits.length) {
        input.value = "";
        run("", false);
      }
    });

    // 検索結果から ?q= 付きで開かれた場合は、同じ語のままページ内を辿れる状態で始める
    if (input.value.trim()) {
      setScope("page");
      run(input.value, true);
    } else {
      updateCounter("");
    }
  })();

  /* ---- 編集ホットキー(Alt+E) ------------------------------------------------
   * [data-hotkey="edit"] を持つリンクがあれば、Alt+E単発（Ctrl/Shift/Meta
   * 同時押しは除外）でそこへ直接遷移する。見つからなければ何もしない。
   * post_it_1も他テーマと同じくこの目印を置き、この処理を使う
   * （以前のAlt+E 3連打の独自実装は廃止。2026-09-24）。
   */
  document.addEventListener("keydown", function (event) {
    if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.code !== "KeyE") return;
    var link = document.querySelector('[data-hotkey="edit"]');
    if (!link) return;
    event.preventDefault();
    link.click();  // <a>のGET遷移と<button type=submit>のフォーム送信、両方に対応
  });

  /* ---- 検索ホットキー(Ctrl+F) ----------------------------------------------
   * Wiki設計者の「検索のショートカットキー Ctrl-F で wiki の検索がアクティブになるように
   * する」（2026-09-29）。以下はクロコの実装例:
   * Ctrl+F（Mac は ⌘F）で、ブラウザのページ内検索の代わりに Wiki の検索欄
   * （.search .search-word）へ入り、入っている語を選んだ状態にする。範囲（サイト全体／
   * ページ内）は切り替えない。
   * 検索をモーダルに入れているテーマ（.search-modal-open を持つもの。bloom）では、
   * 検索欄が見えていなければ「検索」ボタンを押してモーダルを開いてから入る。
   * ブラウザの動きに任せるのは次のとき（ブラウザのページ内検索も使えるように残す）:
   *   - 検索欄にすでに入っている（もう一度 Ctrl+F）
   *   - 見えている検索欄も「検索」ボタンも無い（編集画面など）
   */
  document.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
    if (event.code !== "KeyF") return;
    function visible(selector) {
      var els = document.querySelectorAll(selector);
      for (var i = 0; i < els.length; i++) {
        if (els[i].offsetParent !== null) return els[i];
      }
      return null;
    }
    var input = visible(".search .search-word");
    if (input && document.activeElement === input) return;
    if (!input) {
      var opener = visible(".search-modal-open");
      if (!opener) return;
      opener.click();  // 検索モーダルを開く（開くと検索欄に入る）
      input = visible(".search .search-word");
      if (!input) return;
    }
    event.preventDefault();
    input.focus();
    input.select();
  });

  /* ---- 新規ページ（コマンドバーの「新規」ボタン） --------------------------
   * [data-new-page-open] を押すと .new-page-dialog を開き、ページ名を
   * 1行だけ入力させる。「開く」を押すと、そのページ自身の編集画面へ
   * POST + cmd=edit で移る（404画面の「このページを作る」ボタンと同じ
   * 入りかた）。既にあるページ名を入れても、ふつうにその編集画面が
   * 開くだけでよい（新規かどうかは wikilib.editor.render_edit が見るので、
   * ここでは区別しない）。
   *
   * 「開く」は、ページ名が空・"="/"."で始まる（予約名。
   * wikilib.paths.is_valid_pagepathと同じ決まり）ときは押せない
   * （page-pickerダイアログのpage-picker-ok「選ぶまで押させない」と
   * 同じ考えかた。エラーメッセージを出す代わりに、そもそも押せなくする）。
   *
   * 入力欄でのEnterは「開く」として扱う。フォームの暗黙送信に任せると、
   * ツリー上で最初のsubmitボタン（見出しの×）が押されたことになり、
   * 「やめる」と同じになってしまうため。
   */
  (function () {
    // 同じページに複数あってよい（テーマがヘッダと右メニューの両方に置く場合。
    // pukiwiki_default は畳んだ幅でだけ右メニュー側が見える）
    var openBtns = document.querySelectorAll("[data-new-page-open]");
    var dialog = document.querySelector(".new-page-dialog");
    if (!openBtns.length || !dialog || !dialog.showModal) return;
    // 入口URLはダイアログ自身が持つ（.content[data-editable]のdata-base-urlは
    // テーマ次第で無く、空だと既定のWikiへ送ってしまうため読まない）
    var baseUrl = dialog.dataset.baseUrl || "";
    var input = dialog.querySelector(".new-page-input");
    var okBtn = dialog.querySelector(".new-page-ok");

    function isValidName(name) {
      return !!name && name.split("/").every(function (seg) {
        return seg !== "" && seg[0] !== "=" && seg[0] !== ".";
      });
    }

    function normalized() {
      return input.value.trim().replace(/^\/+/, "");
    }

    function updateOk() {
      okBtn.disabled = !isValidName(normalized());
    }

    openBtns.forEach(function (openBtn) {
      openBtn.addEventListener("click", function () {
        input.value = "";
        updateOk();
        dialog.showModal();
        input.focus();
      });
    });

    input.addEventListener("input", updateOk);

    input.addEventListener("keydown", function (event) {
      // 日本語入力の変換確定のEnterは除く
      if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      if (!okBtn.disabled) dialog.close("ok");
    });

    // 決定されたら、隠しフォームを組み立てて編集画面へ送る
    // （editor.jsのサイドバーnavigate()と同じ形。"/"は区切りとして残し、
    // 区切りごとにencodeURIComponentする）
    dialog.addEventListener("close", function () {
      var name = normalized();
      if (dialog.returnValue !== "ok" || !isValidName(name)) return;
      var form = document.createElement("form");
      form.method = "post";
      form.action = baseUrl + "/" + name.split("/").map(encodeURIComponent).join("/");
      form.style.display = "none";
      var cmdField = document.createElement("input");
      cmdField.type = "hidden";
      cmdField.name = "cmd";
      cmdField.value = "edit";
      form.appendChild(cmdField);
      document.body.appendChild(form);
      form.submit();
    });
  })();

  /* ---- サイドバーの折りたたみ（.subbar / .mainbar） ------------------
   * 画面が狭く、テーマ側のCSSがposition: fixedの帯（5px想定）にして
   * いる間だけ、タップ/スワイプで開閉できるようにする。それ以外の
   * 画面幅（サイドバーが普通にグリッドへ並んでいるとき）は何もしない。
   * 「開いているか」はis-openクラスで、<body>にはdrawer-openを付け外し
   * して背景の暗幕（CSS側の body.drawer-open::after）を出し分ける。
   */
  (function () {
    var sides = Array.prototype.slice.call(
      document.querySelectorAll(".subbar, .mainbar")
    );
    if (!sides.length) return;

    // OSがオーバーレイ式スクロールバー（普段は隠れ、スクロールやカーソルを
    // 端へ寄せると細く出て、レイアウト幅を取らない方式。Firefoxの
    // Windows/macOS/GTK設定など）を使っているとき、html.overlay-scrollbar を
    // 付ける。右端に貼り付いた帯（.subbar）はこのスクロールバーの操作領域と
    // 重なり、クリックがスクロールバーに取られて開けなくなる。CSS側
    // （common.css）でこのクラスを見て、閉じた帯を端から少し内側へ離す。
    // 検出は、スクロール可能なテスト用要素の (offsetWidth - clientWidth) を測る
    // （常時表示のスクロールバーなら幅ぶん>0、オーバーレイなら0）。
    (function () {
      var probe = document.createElement("div");
      probe.style.cssText =
        "position:absolute;top:-9999px;width:100px;height:100px;" +
        "overflow:scroll;visibility:hidden";
      document.body.appendChild(probe);
      var overlay = probe.offsetWidth - probe.clientWidth === 0;
      document.body.removeChild(probe);
      if (overlay) document.documentElement.classList.add("overlay-scrollbar");
    })();

    function isCollapsed(el) {
      return getComputedStyle(el).position === "fixed";
    }
    function openOf() {
      return sides.filter(function (el) { return el.classList.contains("is-open"); })[0];
    }
    function close(el) {
      el.classList.remove("is-open");
      document.body.classList.remove("drawer-open");
    }
    function open(el) {
      var current = openOf();
      if (current) close(current);
      el.classList.add("is-open");
      document.body.classList.add("drawer-open");
    }

    sides.forEach(function (el) {
      el.addEventListener("click", function (event) {
        if (!isCollapsed(el) || el.classList.contains("is-open")) return;
        event.preventDefault();
        open(el);
      });
    });

    // 開いている帯の外をクリックしたら閉じる（暗幕クリックでの閉じかたも兼ねる）
    document.addEventListener("click", function (event) {
      var current = openOf();
      if (!current || current.contains(event.target)) return;
      close(current);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      var current = openOf();
      if (current) close(current);
    });

    // スワイプ: 閉じているときは画面端からのスワイプで開く。
    // 開いているときは、その帯がある側へなぞると閉じる。
    var EDGE_ZONE = 24; // 端から何pxまでを「端からのスワイプ」とみなすか
    var SWIPE_THRESHOLD = 40;
    var startX = null;
    var startY = null;

    document.addEventListener("touchstart", function (event) {
      if (event.touches.length !== 1) return;
      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
    }, { passive: true });

    document.addEventListener("touchend", function (event) {
      if (startX === null) return;
      var touch = event.changedTouches[0];
      var dx = touch.clientX - startX;
      var dy = touch.clientY - startY;
      var fromX = startX;
      startX = null;
      startY = null;
      if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return;

      var current = openOf();
      if (current) {
        var isMenu1 = current.classList.contains("mainbar");
        var closingSwipe = isMenu1 ? dx < 0 : dx > 0;
        if (closingSwipe) close(current);
        return;
      }

      var menu1 = document.querySelector(".mainbar");
      var subbar = document.querySelector(".subbar");
      if (dx > 0 && fromX <= EDGE_ZONE && menu1 && isCollapsed(menu1)) {
        open(menu1);
      } else if (dx < 0 && window.innerWidth - fromX <= EDGE_ZONE && subbar && isCollapsed(subbar)) {
        open(subbar);
      }
    }, { passive: true });
  })();

  /* ---- 表示の拡大縮小(.zoom-in / .zoom-out / .zoom-value) --------------------
   * 現在の倍率は「表示上のラベル」(%)で管理する。ボタンはLABELSに定義した
   * 段階の一つ上・一つ下へ移動する（LABELSの範囲を超えない。端では
   * disabledになる）。.zoom-valueは現在のラベルを表示する数値入力欄で、
   * 書き換えてEnterを押すとLABELSに無い任意の値にもできる（デバイスごとの
   * 適切な最小/最大値を探るためのもの）。選んだ値はlocalStorageに覚えて
   * おき、次にページを開いたときも復元する。
   *
   * 実際に<html>へ与えるfont-sizeは ラベル × BASE_PX ÷ 100 （px指定）で
   * 計算する。BASE_PXは、このIIFEが最初に実行された時点（＝まだこのJSが
   * font-sizeを書き換える前）での<html>の実際のcomputed font-sizeを
   * そのまま使う。common.cssは画面幅に応じて既定のfont-size（例:
   * デスクトップ85%、スマホは480px以下で65%）を出し分けているので、
   * 「ラベル100%」がそのまま「そのデバイス・画面幅の既定サイズ」になる。
   * デバイスごとの基準はcommon.css側のメディアクエリを直接編集すれば
   * 変わり、この計算式は変更不要。
   *
   * あわせて、テーマの:rootが --bp-narrow / --bp-narrower を持っていれば
   * （例: base.css）、いまの拡大率に応じてhtml.bp-narrow /
   * html.bp-narrowerを付け外しする。@mediaはページのfont-size変更を
   * 反映できない（ブラウザ既定の16px基準に固定される）ため、拡大率と
   * 連動させたいレスポンシブしきい値はこちらで肩代わりしている。
   * 持たないテーマ（bloom/fresh等）では何もしない＝従来どおり@media任せ。
   */
  (function () {
    var zoomIn = document.querySelector(".zoom-in");
    var zoomOut = document.querySelector(".zoom-out");
    var zoomValue = document.querySelector(".zoom-value");
    if (!zoomIn && !zoomOut && !zoomValue) return;

    // ボタンで移動する段階（縮小側3・既定・拡大側4）。既定を「100%」と呼ぶ。
    // 50/60は実機検証の結果、本文・メニューフォントとも70%以下と体感差が
    // 乏しく実質不要と判断し廃止した（.zoom-valueへの手入力ではLABELSの
    // 外の値も引き続き使える）。
    var LABELS = [70, 80, 90, 100, 115, 130, 145, 165];
    var DEFAULT_LABEL = 100;
    // .zoom-valueへの手入力はLABELSの外でも受け付けるが、極端な値で
    // レイアウトが壊れないよう、常識的な範囲だけ設ける
    var MIN_VALUE = 10;
    var MAX_VALUE = 400;
    var STORAGE_KEY = "wikiTheme.zoom";
    var root = document.documentElement;
    // まだ何もfont-sizeを書き換えていない、common.css由来のcomputed値
    // （画面幅に応じてcommon.cssが出し分けている既定値）を基準にする
    var BASE_PX = parseFloat(getComputedStyle(root).fontSize);

    var current = DEFAULT_LABEL;
    try {
      var saved = parseFloat(localStorage.getItem(STORAGE_KEY));
      if (!isNaN(saved) && saved >= MIN_VALUE && saved <= MAX_VALUE) current = saved;
    } catch (e) {
      // プライベートブラウジング等でlocalStorageが使えなくても、
      // ボタン・入力欄自体はページ内での切り替えとして機能する
    }

    // --bp-narrow・--bp-narrowerは「ラベル100%のときのビューポート幅」
    // という基準で書かれているので、いまのラベルぶん引き伸ばして比べる
    function readBreakpoint(name) {
      var value = getComputedStyle(root).getPropertyValue(name);
      var px = parseFloat(value);
      return isNaN(px) ? null : px;
    }

    function updateBreakpoints() {
      var ratio = current / DEFAULT_LABEL;
      var w = window.innerWidth;
      var narrow = readBreakpoint("--bp-narrow");
      var narrower = readBreakpoint("--bp-narrower");
      if (narrow !== null) root.classList.toggle("bp-narrow", w < narrow * ratio);
      if (narrower !== null) root.classList.toggle("bp-narrower", w < narrower * ratio);
    }

    function apply() {
      root.style.fontSize = (BASE_PX * current / 100) + "px";
      updateBreakpoints();
      // 表示は小数を丸める（内部の値はそのまま持っておく）
      var shown = Math.round(current * 10) / 10;
      if (zoomIn) {
        zoomIn.disabled = current >= LABELS[LABELS.length - 1];
        zoomIn.title = "拡大（現在" + shown + "%）";
      }
      if (zoomOut) {
        zoomOut.disabled = current <= LABELS[0];
        zoomOut.title = "縮小（現在" + shown + "%）";
      }
      if (zoomValue && zoomValue !== document.activeElement) {
        zoomValue.value = shown;
      }
    }

    function save() {
      try {
        localStorage.setItem(STORAGE_KEY, String(current));
      } catch (e) {
        // 保存できなくても、その場での切り替えは動く
      }
    }

    function setCurrent(value) {
      current = Math.max(MIN_VALUE, Math.min(MAX_VALUE, value));
      apply();
      save();
    }

    if (zoomIn) {
      zoomIn.addEventListener("click", function () {
        var next = LABELS.filter(function (v) { return v > current; })[0];
        if (next === undefined) return;
        setCurrent(next);
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener("click", function () {
        var prev = LABELS.filter(function (v) { return v < current; }).pop();
        if (prev === undefined) return;
        setCurrent(prev);
      });
    }
    if (zoomValue) {
      zoomValue.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;
        var value = parseFloat(zoomValue.value);
        if (isNaN(value)) return;
        setCurrent(value);
        zoomValue.blur();
      });
      // フォーカスを外したときも、それまでに入力した値を反映する
      zoomValue.addEventListener("blur", function () {
        var value = parseFloat(zoomValue.value);
        if (!isNaN(value)) setCurrent(value);
        else apply(); // 数値でなければ表示を現在値に戻す
      });
    }

    apply();

    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(updateBreakpoints, 100);
    });
  })();

  /* ---- 浮いたパネルのドラッグ移動（.page-search-panel・任意で.search-modal-panel） ----
   * .page-search-panel（ページ内検索の結果。どのテーマにもある）と、
   * 使うテーマだけが持つ.search-modal-panel（検索モーダル本体）を、
   * それぞれの見出し行（.page-search-panel-head / .search-modal-head）を
   * つかみ手にしてマウスでドラッグ移動できるようにする。見出し行を
   * 左クリックで押し下げた位置からのマウス移動ぶんだけpanelを動かす。
   * ドラッグ開始時にleft/top指定へ切り替え、初期配置に使っていた
   * transform（中央寄せ等）・right（右寄せ等）は上書きして無効化する。
   * 画面の外へは出さない。要素が無いテーマでは何も起きない。 */
  (function () {
    function makeDraggable(panel, handle) {
      if (!panel || !handle) return;
      var dragging = false;
      var startX = 0, startY = 0, startLeft = 0, startTop = 0;

      handle.addEventListener("mousedown", function (event) {
        if (event.button !== 0) return;  // 左クリックのみ
        // 見出し行の中の閉じるボタン等は、それ自体のクリックを優先する
        if (event.target.closest("button, a")) return;
        dragging = true;
        var rect = panel.getBoundingClientRect();
        startX = event.clientX;
        startY = event.clientY;
        startLeft = rect.left;
        startTop = rect.top;
        panel.style.left = startLeft + "px";
        panel.style.top = startTop + "px";
        panel.style.right = "auto";
        panel.style.transform = "none";
        document.body.style.userSelect = "none";
        event.preventDefault();
      });

      document.addEventListener("mousemove", function (event) {
        if (!dragging) return;
        var dx = event.clientX - startX;
        var dy = event.clientY - startY;
        var maxLeft = Math.max(0, window.innerWidth - panel.offsetWidth);
        var maxTop = Math.max(0, window.innerHeight - panel.offsetHeight);
        panel.style.left = Math.min(Math.max(0, startLeft + dx), maxLeft) + "px";
        panel.style.top = Math.min(Math.max(0, startTop + dy), maxTop) + "px";
      });

      document.addEventListener("mouseup", function () {
        if (!dragging) return;
        dragging = false;
        document.body.style.userSelect = "";
      });
    }

    makeDraggable(
      document.querySelector(".page-search-panel"),
      document.querySelector(".page-search-panel-head")
    );
    makeDraggable(
      document.querySelector(".search-modal-panel"),
      document.querySelector(".search-modal-head")
    );
  })();

  /* ---- 検索モーダルの開閉（任意。.search-modal-open等を持つテーマだけ） ----
   * .search-modal-open（開くボタン）・.search-modal（開閉全体、hidden属性で
   * 閉じる）・.search-modal-close（閉じるボタン）という決まったクラス名を
   * 使うテーマ向け。閉じるボタン・Escapeのいずれかでのみ閉じる（外側
   * クリックでは閉じない。理由: .search-modal-backdropを画面全体に
   * 敷いてクリックを検出すると、.page-search-panel等モーダルの外にある
   * 要素の上に重なったとき、そちらのクリックまで拾って閉じてしまう）。
   * 閉じても入力欄の値・検索結果（ハイライト・.page-search-panel）は
   * 一切消さない（Wiki設計者の指示）。要素が無いテーマでは何も起きない。 */
  (function () {
    var openBtn = document.querySelector(".search-modal-open");
    var modal = document.querySelector(".search-modal");
    if (!openBtn || !modal) return;

    var closeBtn = modal.querySelector(".search-modal-close");
    var input = modal.querySelector(".search-word");

    function open() {
      modal.hidden = false;
      if (input) input.focus({ preventScroll: true });
    }
    function close() {
      modal.hidden = true;
      openBtn.focus();
    }

    openBtn.addEventListener("click", open);
    if (closeBtn) closeBtn.addEventListener("click", close);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !modal.hidden) close();
    });
  })();

  /* ---- マーカー操作（.marker-controls、任意。持つテーマだけ） ----
   * 状態・実際の切り替え処理は本体（_sys/markers/markers.js、全ページ末尾へ
   * 自動で差し込まれる）が持つ window.WikisysMarkers を使う（Tech/MarkerSystem.md
   * 参照）。markers.js は defer で読み込まれるため、このスクリプトの方が先に
   * 実行される場合がある。window.WikisysMarkers が無ければ wikisys-markers:ready
   * を待ってから配線する。
   *
   * 2026-08-25にbase.jsから昇格した（他テーマでも同じマークアップ
   * （.marker-controls等）を置けばそのまま使えるようにするため）。
   * 要素が無いテーマ（.marker-controlsのマークアップを持たないbloom・
   * post_it_1）では何も起きない。 */
  (function () {
    var root = document.querySelector(".marker-controls");
    if (!root) return;

    var panelToggleButton = root.querySelector(".marker-panel-toggle");
    var toggleInput = root.querySelector(".marker-toggle-input");
    var setSelect = root.querySelector(".marker-set-select");

    function render(summary) {
      toggleInput.checked = summary.enabled;
      setSelect.innerHTML = "";
      summary.setNames.forEach(function (name) {
        var option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        if (name === summary.activeSet) option.selected = true;
        setSelect.appendChild(option);
      });
      root.hidden = false;
    }

    function setup(summary) {
      render(summary);

      panelToggleButton.addEventListener("click", function () {
        window.WikisysMarkers.togglePanel();
      });
      toggleInput.addEventListener("change", function () {
        window.WikisysMarkers.setEnabled(toggleInput.checked);
      });
      setSelect.addEventListener("change", function () {
        window.WikisysMarkers.setActiveSet(setSelect.value);
      });
    }

    if (window.WikisysMarkers) {
      setup(window.WikisysMarkers.getSummary());
    } else {
      window.addEventListener(
        "wikisys-markers:ready",
        function (event) { setup(event.detail); },
        { once: true }
      );
    }

    // 他タブ・パネル操作・API呼び出しでの変更もここで拾い、表示を最新化する
    // （自分の操作で発火した分も同じ値を入れ直すだけなので実害はない）。
    window.addEventListener("wikisys-markers:change", function (event) {
      render(event.detail);
    });
  })();

  /* ---- ページ内アンカーが固定ヘッダの下に隠れないようにする ----------------
     ヘッダを position: sticky / fixed で画面上部に留めるテーマでは、#見出し や
     &aname などのページ内リンクで移動すると、移動先が画面の最上端に来てヘッダの
     下に隠れる。ヘッダの高さはテーマ・画面幅・拡大率・折り返しで 50〜150px ほど
     変わるので、固定値では足りない。実際の高さを測って html の --anchor-offset
     に入れ、common.css の html { scroll-padding-top } がそれを使う
     （scroll-padding はアンカー移動にも scrollIntoView にも効き、見出し以外の
     要素にも一律に効く）。

     対象のヘッダは .site-header（base 系）か #header（post_it_1 / pkwk）。
     position が sticky / fixed のときだけ数える（post_it_1 / pkwk は狭い幅で
     固定を外すので、そのときは 0 になる）。どちらも無いテーマ（bloom）は 0。
     高さが変わったら（拡大縮小・bp-narrow の切り替え・折り返し）測り直す。 */
  (function () {
    var header = document.querySelector(".site-header, #header");
    var root = document.documentElement;
    if (!header) return;

    function update() {
      var cs = getComputedStyle(header);
      var px = 0;
      if (cs.position === "sticky" || cs.position === "fixed") {
        // sticky の top（多くは0）ぶんも足す。まだ貼り付く前でも、移動した先では
        // 貼り付いた状態になるので、そのときの下端の位置を使う。
        px = header.offsetHeight + (parseFloat(cs.top) || 0);
      }
      root.style.setProperty("--anchor-offset", px + "px");
    }

    update();
    if (window.ResizeObserver) {
      new ResizeObserver(update).observe(header);
    }
    // 幅の変化で position が切り替わる（sticky ⇔ static）場合は高さが変わらない
    // こともあるので、ウィンドウのリサイズでも測り直す。
    window.addEventListener("resize", update);
  })();
})();
