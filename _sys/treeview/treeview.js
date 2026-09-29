/* ページ一覧のTreeView（/.treeview.js）。
 *
 * ページ選択ダイアログ・名前を変える画面・バックアップ管理画面が同じものを使う。
 * 3か所に同じ木を別々に持っていたので、1つにまとめてある。**同じ見た目のものが
 * 場所によって違う動きをする**のがいちばん困るため。
 *
 * ## index は出さない
 *
 * `index` はファイルの置き場所を決めるためにシステムが要求している名前で、
 * 使う人から見れば**フォルダそのもの**を指す。`/Tech` を開けば `Tech/index` が
 * 出るのだから、一覧で2つに分けて見せる意味がない。そこでフォルダの行が
 * `index` を兼ねる（フォルダを選ぶ＝その入口ページを選ぶ）。
 *
 * `index` を名指しで扱いたい場面のために `showIndex` を用意してある。真にすると
 * これまでどおり `index` が別の行として並ぶ。
 *
 * ## 畳んだ状態で始める（collapsed）
 *
 * `collapsed` を真にすると、`render` した直後はフォルダをすべて畳む。
 * 全部が開いていると行が多すぎて扱いにくい画面（編集画面のページ一覧・
 * 名前を変える画面の移し先）向け。呼び出し側が続けて `selectSubpath` を
 * 呼べば、選んだ行までの道だけが開く（Wiki設計者の指示、2026-09-19）。
 *
 * ## titleOnly のとき、行ごとにファイル名かタイトルかが変わる
 *
 * `titleOnly` な使いかた（編集画面のサイドバー）は、ページの記法
 * （PukiWiki記法はファイル名基準、Markdownはタイトル基準）によって
 * どちらを出すか変わる。ここでは各行に埋め込まれた `listname`
 * （`"fname"`/`"title"`。サーバー側 `editor._apply_listnames` が決める）を
 * 見るだけで、記法そのものは知らない（Wiki設計者の指示、2026-09-18）。
 *
 * ## フォルダも選べる
 *
 * フォルダの行を押すと**選ばれる**（開閉ではない）。開閉は左の三角で行う。
 * 押すたびに開いたり閉じたりすると、選ぶつもりで押した人が驚くため。
 *
 * ## キーボードでも動かせる
 *
 *     ↑ ↓        選んでいる行を上下に動かす
 *     →          フォルダを開く（開いていれば中の先頭へ）
 *     ←          フォルダを閉じる（閉じていれば親へ）
 *     Enter      決定（呼び出し側の onEnter）
 *
 * 見えている行だけを順に辿る。畳んだ中の行は飛ばす（画面で見えている並びと
 * キーで動く順番が食い違わないようにするため）。
 */
(function (global) {
  "use strict";

  var INDEX_NAME = "index";

  /* 属性セレクタに入れる値を逃がす。ページ名に " が入っていても壊れないように */
  function escapeAttr(value) {
    return String(value).replace(/["\\]/g, "\\$&");
  }

  /* そのフォルダの中にある index の行。フォルダの行がこれを兼ねる */
  function indexChildOf(node) {
    for (var i = 0; i < node.children.length; i++) {
      if (node.children[i].name === INDEX_NAME) return node.children[i];
    }
    return null;
  }

  /* 全角文字を2文字ぶんとして数える幅（titleOnlyでの打ち切りに使う）。
     厳密なEast Asian Widthの判定表は持たず、CJK系のよく使う範囲だけを
     「全角」として扱う簡易版（タイトルの見た目の目安が取れれば十分なため） */
  function isWideChar(codePoint) {
    return (
      (codePoint >= 0x1100 && codePoint <= 0x115F) ||   // ハングル字母
      (codePoint >= 0x2E80 && codePoint <= 0xA4CF) ||   // 部首・仮名・ハングル互換等〜CJK統合漢字
      (codePoint >= 0xAC00 && codePoint <= 0xD7A3) ||   // ハングル音節
      (codePoint >= 0xF900 && codePoint <= 0xFAFF) ||   // CJK互換漢字
      (codePoint >= 0xFF00 && codePoint <= 0xFF60) ||   // 全角英数・記号
      (codePoint >= 0xFFE0 && codePoint <= 0xFFE6) ||   // 全角記号
      (codePoint >= 0x20000 && codePoint <= 0x3FFFD)    // CJK拡張（追加面）
    );
  }

  function displayWidth(text) {
    var w = 0;
    Array.prototype.forEach.call(Array.from(text), function (ch) {
      w += isWideChar(ch.codePointAt(0)) ? 2 : 1;
    });
    return w;
  }

  /* maxWidthを超える分だけ切り詰め、末尾に … を1文字ぶんとして付ける */
  function truncateToWidth(text, maxWidth) {
    if (!maxWidth || displayWidth(text) <= maxWidth) return text;
    var out = "", w = 0, budget = Math.max(maxWidth - 1, 0);
    var chars = Array.from(text);
    for (var i = 0; i < chars.length; i++) {
      var cw = isWideChar(chars[i].codePointAt(0)) ? 2 : 1;
      if (w + cw > budget) break;
      out += chars[i];
      w += cw;
    }
    return out + "…";
  }

  function TreeView(box, options) {
    this.box = box;
    this.opt = options || {};
    this.prefix = this.opt.prefix || "tv";
    this.showIndex = !!this.opt.showIndex;
    this.selected = null;
    this._bind();
  }

  TreeView.prototype._cls = function (name) {
    return this.prefix + "-" + name;
  };

  /* 使う場所ごとの名前（`rp-row` など）と、どこでも同じ共通の名前（`tv-row`）を
     並べて付ける。**CSSは共通のほうだけを見る。** 属性セレクタで末尾を見る形に
     すると、クラスを2つ以上持つ要素（`rp-node rp-dir`）に当たらなくなるため。 */
  TreeView.prototype._classFor = function (name, extra) {
    return this._cls(name) + " tv-" + name + (extra ? " " + extra : "");
  };

  /* 木を組み立てて描く。data は /.pagetree が返すもの */
  TreeView.prototype.render = function (tree) {
    this.box.textContent = "";
    this.selected = null;
    var self = this;
    (tree.children || []).forEach(function (child) {
      self._build(child, 0, self.box);
    });
  };

  TreeView.prototype._build = function (node, depth, container) {
    var isDir = node.kind === "dir";
    /* index はフォルダの行が兼ねるので、単独では出さない */
    if (!this.showIndex && !isDir && node.name === INDEX_NAME) return;

    var item = document.createElement("div");
    item.className = this._classFor("node", isDir ? this._cls("dir") + " tv-dir" : "");
    item.dataset.subpath = node.subpath;
    item.dataset.pagepath = node.pagepath;
    item.dataset.kind = node.kind;

    /* フォルダの行は中の index を兼ねる。選んだときは index のほうを指す */
    var own = isDir && !this.showIndex ? indexChildOf(node) : null;
    if (own) item.dataset.subpath = own.subpath;
    /* 実体の有無は、木がその情報を持っているときだけ見る。
       持たない木（バックアップ管理画面の一覧）で「無い」と決めつけると、
       ぜんぶが「まだありません」の見た目になってしまう */
    var src = own || node;
    if (src.has_file !== undefined) item.dataset.hasFile = src.has_file ? "1" : "";

    var kids = (node.children || []).filter(function (c) {
      return !(own && c === own);  // 兼ねた index は中から外す
    });

    var row = document.createElement("div");
    row.className = this._classFor("row", isDir ? this._cls("row-dir") + " tv-row-dir" : "");
    row.setAttribute("role", "treeitem");
    row.tabIndex = -1;
    row.style.setProperty("--" + this.prefix + "-depth", depth);

    /* 開閉の三角。押しやすいよう大きめに出す（選ぶ操作と場所を分けるため）。
       子を持たない行では**ボタンを作らない**。押せないボタンが全行に並ぶと、
       Tabで拾われるうえ見た目もうるさいので、字下げのための空きだけを置く。 */
    var hasKids = kids.length > 0;
    var twisty;
    if (hasKids) {
      twisty = document.createElement("button");
      twisty.type = "button";
      twisty.className = this._classFor("twisty");
      twisty.textContent = "▾";
      twisty.setAttribute("aria-label", "折りたたむ");
      twisty.tabIndex = -1;  // 辿るのは行のほう。開閉は ← → で行う
    } else {
      twisty = document.createElement("span");
      twisty.className = this._classFor("twisty", "is-leaf");
      twisty.setAttribute("aria-hidden", "true");
    }
    row.appendChild(twisty);

    var nodeTitle = (own ? own.title : node.title) || "";
    var name = isDir ? (node.name || "/") : node.name;
    /* そのページの記法（PukiWiki/Markdown）で一覧の基準が違う
       （`listname`。サーバー側 editor._apply_listnames が埋め込む）。
       "fname" ならファイル名を出す。それ以外（"title"・無指定）は
       これまでどおりタイトル優先（無ければファイル名で代用）。 */
    var listSrc = own || node;
    var showTitle = listSrc.listname !== "fname";

    var label = document.createElement("span");
    label.className = this._classFor(
      "label", isDir ? this._cls("dirlabel") + " tv-dirlabel" : "");
    /* titleOnly: ファイル名かタイトルのどちらか一方だけを出す（幅の狭い
       サイドバー向け）。出さなかったほうは title 属性（ホバー）で確かめられる。
       titleMaxWidth を渡していれば、長い分は末尾を … に切り詰める
       （全角は2文字ぶんとして数える。半角換算の幅） */
    if (this.opt.titleOnly) {
      var primary = showTitle ? (nodeTitle || name) : name;
      label.textContent = truncateToWidth(primary, this.opt.titleMaxWidth);
      label.title = showTitle ? item.dataset.subpath : (nodeTitle || item.dataset.subpath);
    } else {
      label.textContent = name;
    }
    if (item.dataset.hasFile === "") {
      label.className += " " + this._cls("nopage") + " tv-nopage";
      label.title = "このページはまだありません";
    }
    row.appendChild(label);

    /* 使う側がその行に独自の目印を足せるようにしておく（バックアップ管理画面が
       「削除済み」を出すのに使う）。中身の決めかたは使う側にあるので、
       TreeView は呼ぶだけにする */
    if (this.opt.decorate) this.opt.decorate(node, { row: row, label: label, item: item });

    if (!this.opt.titleOnly) {
      var title = document.createElement("span");
      title.className = this._classFor("title");
      title.textContent = nodeTitle;
      title.title = item.dataset.subpath;
      row.appendChild(title);
    }

    item.appendChild(row);
    if (hasKids) {
      var box = document.createElement("div");
      box.className = this._classFor("children");
      var self = this;
      kids.forEach(function (c) { self._build(c, depth + 1, box); });
      item.appendChild(box);
      /* collapsed: 最初はすべて畳んでおく。選んだ行までの道だけは
         selectSubpath が開く */
      if (this.opt.collapsed) this._fold(item, true);
    }
    container.appendChild(item);
  };

  /* ---- 選ぶ ---- */

  TreeView.prototype.select = function (row, notify) {
    var current = this.box.querySelectorAll(".tv-row.is-chosen");
    [].forEach.call(current, function (r) {
      r.classList.remove("is-chosen");
      r.tabIndex = -1;
    });
    if (!row) { this.selected = null; return; }
    row.classList.add("is-chosen");
    /* キーボードで辿れるのは「いま選んでいる行」だけにする。全部を辿れると
       Tabキーで一覧の中に閉じ込められてしまう */
    row.tabIndex = 0;
    this.selected = row;
    /* 選んだ行は必ず見えるところへ。マウスで選んだときも、下に隠れたまま
       「選んだはずのものが見えない」とならないようにする */
    row.scrollIntoView({ block: "nearest" });
    if (notify !== false && this.opt.onSelect) {
      this.opt.onSelect(this.infoOf(row));
    }
  };

  /* その行を選べるか。使う側が selectable を渡さなければ、どの行も選べる */
  TreeView.prototype._selectable = function (row) {
    if (!this.opt.selectable) return true;
    return !!this.opt.selectable(this.infoOf(row));
  };

  TreeView.prototype.infoOf = function (row) {
    var item = row.closest("." + this._cls("node"));
    return {
      subpath: item.dataset.subpath,
      pagepath: item.dataset.pagepath,
      kind: item.dataset.kind,
      hasFile: item.dataset.hasFile === "1",
      row: row, node: item
    };
  };

  /* 実体パスを指定して選ぶ。畳まれた親は開いて見えるようにする
     （選んだのがフォルダなら、その中身も開く。いま居る場所の周りが
     見えるようにするため） */
  TreeView.prototype.selectSubpath = function (subpath, notify) {
    var item = this.box.querySelector(
      "." + this._cls("node") + '[data-subpath="' + escapeAttr(subpath) + '"]');
    if (!item) return false;
    for (var p = item; p && p !== this.box; p = p.parentNode) {
      if (p.classList && p.classList.contains("is-folded")) this._fold(p, false);
    }
    this.select(item.querySelector("." + this._cls("row")), notify);
    return true;
  };

  /* ---- 開閉 ---- */

  TreeView.prototype._fold = function (item, folded) {
    item.classList.toggle("is-folded", folded);
    var twisty = item.querySelector(".tv-twisty");
    if (twisty && !twisty.classList.contains("is-leaf")) {
      twisty.textContent = folded ? "▸" : "▾";
      twisty.setAttribute("aria-label", folded ? "展開する" : "折りたたむ");
    }
  };

  TreeView.prototype._hasKids = function (item) {
    return !!item.querySelector(".tv-children");
  };

  /* ---- キーボード ---- */

  /* 見えている行だけを上から順に。畳んだ中は飛ばす（画面の並びと揃える） */
  TreeView.prototype._visibleRows = function () {
    var rows = [], self = this;
    (function walk(container) {
      [].forEach.call(container.children, function (item) {
        if (!item.classList || !item.classList.contains(self._cls("node"))) return;
        if (item.classList.contains("is-hidden")) return;
        var row = item.querySelector("." + self._cls("row"));
        if (row && row.parentNode === item) rows.push(row);
        var kids = item.querySelector("." + self._cls("children"));
        if (kids && !item.classList.contains("is-folded")) walk(kids);
      });
    })(this.box);
    return rows;
  };

  TreeView.prototype._move = function (step) {
    var rows = this._visibleRows();
    if (!rows.length) return;
    var i = this.selected ? rows.indexOf(this.selected) : -1;
    /* 選べない行は飛ばして、次に選べるものまで進む。止まれない場所で
       止まると、キーを押しても何も起きないように見えるため */
    var j = i;
    do {
      j += step;
      if (j < 0 || j >= rows.length) return;
    } while (!this._selectable(rows[j]));
    if (i === -1 && this._selectable(rows[0])) j = 0;
    this.select(rows[j]);
    rows[j].focus();
  };

  TreeView.prototype._onKey = function (event) {
    var key = event.key;
    if (key !== "ArrowUp" && key !== "ArrowDown" && key !== "ArrowLeft"
        && key !== "ArrowRight" && key !== "Enter") return;
    event.preventDefault();

    if (key === "ArrowDown") return this._move(1);
    if (key === "ArrowUp") return this._move(-1);
    if (key === "Enter") {
      if (this.selected && this.opt.onEnter) this.opt.onEnter(this.infoOf(this.selected));
      return;
    }
    if (!this.selected) return;
    var item = this.selected.closest("." + this._cls("node"));
    if (key === "ArrowRight") {
      /* 閉じていれば開く。開いていれば中の先頭へ進む */
      if (this._hasKids(item) && item.classList.contains("is-folded")) {
        this._fold(item, false);
      } else if (this._hasKids(item)) {
        this._move(1);
      }
      return;
    }
    /* ← 開いていれば閉じる。閉じている（か葉）なら親へ戻る */
    if (this._hasKids(item) && !item.classList.contains("is-folded")) {
      this._fold(item, true);
      return;
    }
    var parent = item.parentNode.closest
      ? item.parentNode.closest("." + this._cls("node")) : null;
    if (parent) {
      var row = parent.querySelector("." + this._cls("row"));
      this.select(row);
      row.focus();
    }
  };

  /* ---- 絞り込み ---- */

  TreeView.prototype.filter = function (query) {
    var q = (query || "").trim().toLowerCase();
    var nodes = [].slice.call(this.box.querySelectorAll("." + this._cls("node")));
    nodes.forEach(function (n) { n.classList.remove("is-hidden"); });
    if (!q) return;
    nodes.forEach(function (n) {
      if ((n.dataset.subpath || "").toLowerCase().indexOf(q) === -1) {
        n.classList.add("is-hidden");
      }
    });
    /* 深い側から見直す。文書順の逆＝子が先なので、親を見るとき子は確定している */
    var self = this;
    nodes.reverse().forEach(function (n) {
      if (n.querySelector("." + self._cls("node") + ":not(.is-hidden)")) {
        n.classList.remove("is-hidden");
      }
    });
  };

  /* ---- 出来事を受ける ---- */

  TreeView.prototype._bind = function () {
    var self = this;
    this.box.addEventListener("click", function (event) {
      var twisty = event.target.closest("." + self._cls("twisty"));
      if (twisty && !twisty.classList.contains("is-leaf")) {
        var item = twisty.closest("." + self._cls("node"));
        self._fold(item, !item.classList.contains("is-folded"));
        return;
      }
      var row = event.target.closest("." + self._cls("row"));
      if (!row || !self.box.contains(row)) return;
      /* フォルダも選べる。開閉は三角のほうで行う。
         ただし選べないことにした行（selectable が偽）は、選ばずに素通りする */
      if (!self._selectable(row)) return;
      self.select(row);
      row.focus();
    });
    this.box.addEventListener("dblclick", function (event) {
      var row = event.target.closest("." + self._cls("row"));
      if (!row || !self.box.contains(row)) return;
      if (self.opt.onEnter) self.opt.onEnter(self.infoOf(row));
    });
    this.box.addEventListener("keydown", function (event) { self._onKey(event); });
  };

  TreeView.INDEX_NAME = INDEX_NAME;   /* 呼び出し側が組み立てに使う */
  global.WikiTreeView = TreeView;
})(window);
