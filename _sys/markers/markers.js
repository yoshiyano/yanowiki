/* マーカーシステム本体。全ページに自動で差し込まれる（wikilib.themes.render_theme）。
 *
 * 状態（用語・色・用語セット）はブラウザのlocalStorageだけに持つ（サーバーは
 * 一切関与しない）。この本体は:
 *   - アクティブな用語セットの各用語を本文中で色分けして表示する
 *   - 矢印キーで、アクティブな用語（1つ）の一致を移動する
 *   - 数字キー（1〜9・0）で、アクティブな用語を切り替える
 *   - Alt+M で、操作用の別ウィンドウ（/.markers-panel）を開く/前面に出す
 *   - 用語に実際に移動したら、その用語の最終使用時刻を更新する
 *     （開いてから移動していなければ「使った」扱いにしない）
 *   - 1日以上使われていない用語は、次に読み込んだときに捨てる
 *
 * 操作用ウィンドウとは BroadcastChannel（同じオリジンのタブ間だけに届く）で
 * 状態の変化だけを伝え合う。実際の値はどちらも同じlocalStorageを読み直す
 * （どちらかが最新を持ちきる設計にしない）。
 */
(function () {
  "use strict";

  var STORAGE_KEY = "wikisys.markers.v1";
  var EXPIRE_MS = 24 * 60 * 60 * 1000; // 1日: パネルを開いて用語へ移動してからの経過
  var CHANNEL_NAME = "wikisys-markers";
  var MARK_CLASS = "wikisys-mark";
  var CURRENT_CLASS = "wikisys-mark--current";
  // 1→0番目, 2→1番目, … 9→8番目, 0→9番目（テンキー等の並びに合わせる）
  var NUMBER_KEY_ORDER = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

  var scriptEl = document.currentScript;
  var baseUrl = (scriptEl && scriptEl.dataset.baseUrl) || "";
  var panelUrl = (scriptEl && scriptEl.dataset.panelUrl) || (baseUrl + "/.markers-panel");
  var panelWindow = null;

  var channel = null;
  try {
    if ("BroadcastChannel" in window) channel = new BroadcastChannel(CHANNEL_NAME);
  } catch (e) {
    channel = null;
  }

  /* ---- 状態の読み書き ---- */
  // enabled: マーカー表示そのもの（ハイライト・矢印/数字キー）のオン/オフ。
  // 明記されていない古い状態（このフィールドを追加する前に保存されたもの）は
  // undefined になるが、そのときは有効として扱う（state.enabled !== false で判定）。
  function emptyState() {
    return { activeSet: "既定", activeTerm: 0, enabled: true, sets: { "既定": { terms: [] } } };
  }

  function loadState() {
    var raw = null;
    try {
      raw = window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return emptyState();
    }
    if (!raw) return emptyState();
    try {
      var state = JSON.parse(raw);
      if (!state || typeof state !== "object" || !state.sets || !state.activeSet) {
        return emptyState();
      }
      if (!state.sets[state.activeSet]) state.sets[state.activeSet] = { terms: [] };
      return state;
    } catch (e) {
      return emptyState();
    }
  }

  // silent: ページをまたいだ他のタブへ再描画を求めない（ナビゲーションのような
  // 「用語の一覧・色そのものは変わらない」更新に使う。broadcastすると、開いている
  // 他のタブすべてでハイライトの作り直しが走ってしまうため）
  function saveState(state, silent) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      // 保存できなくても（プライベートブラウズ等）閲覧自体は妨げない
    }
    if (!silent && channel) {
      try { channel.postMessage({ type: "state-changed" }); } catch (e2) { /* noop */ }
    }
  }

  function currentTerms(state) {
    var set = state.sets[state.activeSet];
    return (set && set.terms) || [];
  }

  // 1日以上動かしていない用語は捨てる。読み込みのたびに全用語セットぶん見る
  function pruneExpired(state) {
    var now = Date.now();
    var changed = false;
    Object.keys(state.sets).forEach(function (name) {
      var set = state.sets[name];
      var kept = (set.terms || []).filter(function (t) {
        return (now - (t.lastUsed || 0)) < EXPIRE_MS;
      });
      if (kept.length !== (set.terms || []).length) changed = true;
      set.terms = kept;
    });
    if (changed) saveState(state);
    return state;
  }

  /* ---- ハイライト ---- */
  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, SELECT: 1, NOSCRIPT: 1 };

  function collectTextNodes(root) {
    var nodes = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentNode;
        if (!parent || SKIP_TAGS[parent.nodeName]) return NodeFilter.FILTER_REJECT;
        if (parent.closest && parent.closest("." + MARK_CLASS)) return NodeFilter.FILTER_REJECT;
        if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    return nodes;
  }

  // マークする範囲。メニュー・見出し・検索フォームなどの「操作のための部品」は
  // 対象外にし、本文（<main>）とフッター（<footer>）だけを対象にする
  // （テーマのクラス名・ID名には依存せず、HTMLの意味的な要素で判断する）。
  // どちらも無いテーマでは、後方互換として document.body 全体を対象にする。
  function markableRoots() {
    var roots = Array.prototype.slice.call(document.querySelectorAll("main, footer"));
    return roots.length ? roots : [document.body];
  }

  function unmark() {
    var marks = document.querySelectorAll("." + MARK_CLASS);
    marks.forEach(function (mark) {
      var parent = mark.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(mark.textContent), mark);
      parent.normalize();
    });
  }

  function buildPattern(terms) {
    // 同じ開始位置で複数の用語が当てはまる場合、長いほうを優先する
    // （"検索" と "検索窓" の両方があるとき、"検索窓" を丸ごと拾えるように）
    var order = terms.map(function (t, i) { return i; })
      .sort(function (a, b) { return terms[b].term.length - terms[a].term.length; });
    var alt = order.map(function (i) { return escapeRegExp(terms[i].term); }).join("|");
    if (!alt) return null;
    return new RegExp(alt, "gi");
  }

  function markAll(terms) {
    if (!terms.length) return;
    var pattern = buildPattern(terms);
    if (!pattern) return;
    var lower = terms.map(function (t) { return t.term.toLowerCase(); });

    var nodes = [];
    markableRoots().forEach(function (root) {
      nodes = nodes.concat(collectTextNodes(root));
    });
    nodes.forEach(function (textNode) {
      var text = textNode.nodeValue;
      pattern.lastIndex = 0;
      var m = pattern.exec(text);
      if (!m) return;
      var frag = document.createDocumentFragment();
      var pos = 0;
      while (m) {
        if (m.index > pos) frag.appendChild(document.createTextNode(text.slice(pos, m.index)));
        var idx = lower.indexOf(m[0].toLowerCase());
        var mark = document.createElement("mark");
        mark.className = MARK_CLASS;
        mark.dataset.termIdx = String(idx < 0 ? 0 : idx);
        mark.style.backgroundColor = terms[idx < 0 ? 0 : idx].color;
        mark.textContent = m[0];
        frag.appendChild(mark);
        pos = m.index + m[0].length;
        pattern.lastIndex = pos;
        m = pattern.exec(text);
      }
      if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
      textNode.parentNode.replaceChild(frag, textNode);
    });
  }

  /* ---- ナビゲーション（アクティブな用語の一致を移動） ---- */
  var navIndex = -1; // アクティブな用語の一致のうち、今どこにいるか

  function activeMarks(state) {
    var idx = state.activeTerm || 0;
    return Array.prototype.slice.call(
      document.querySelectorAll("." + MARK_CLASS + '[data-term-idx="' + idx + '"]'));
  }

  function clearCurrent() {
    var el = document.querySelector("." + CURRENT_CLASS);
    if (el) el.classList.remove(CURRENT_CLASS);
  }

  // marks[index] を「今の位置」にする（強調表示・画面内へスクロール）。
  // lastUsedの更新はしない（実際にキーで「動かした」ときだけ更新する既存の
  // ルールに合わせるため。goTo と setActiveTerm の両方から使う）。
  function placeCurrent(marks, index) {
    if (!marks.length) return false;
    navIndex = (index + marks.length) % marks.length;
    clearCurrent();
    var el = marks[navIndex];
    el.classList.add(CURRENT_CLASS);
    el.scrollIntoView({ block: "center", inline: "nearest" });
    return true;
  }

  function goTo(marks, index, state) {
    if (!placeCurrent(marks, index)) return;
    touchTerm(state);
    postPageInfo(state, marks.length);
  }

  // referenceEl（直前にいた場所の一致要素）を基準に、marks（DOM順で並んだ、
  // 切り替えた先の用語の一致一覧）の中から「referenceElと同じか、それより
  // 後にある最初の一致」の添字を返す。全部が referenceEl より前にしか
  // 無ければ最後（＝いちばん近い）を返す。marks が空なら -1。
  function positionAmongMarks(marks, referenceEl) {
    for (var i = 0; i < marks.length; i++) {
      if (marks[i] === referenceEl) return i;
      if (referenceEl.compareDocumentPosition(marks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) return i;
    }
    return marks.length - 1;
  }

  function step(dir, state) {
    var marks = activeMarks(state);
    if (!marks.length) return;
    goTo(marks, navIndex < 0 ? 0 : navIndex + dir, state);
  }

  // 上下: 今のビューポートに見えている一致をまとめて飛ばし、外側にある次/前へ
  function jumpFar(dir, state) {
    var marks = activeMarks(state);
    if (!marks.length) return;
    if (navIndex < 0) return goTo(marks, 0, state);

    var vh = window.innerHeight || document.documentElement.clientHeight;
    function inView(el) {
      var r = el.getBoundingClientRect();
      return r.bottom > 0 && r.top < vh;
    }
    var i = navIndex;
    var seenOutside = false;
    for (var steps = 0; steps < marks.length; steps++) {
      i = (i + dir + marks.length) % marks.length;
      if (!inView(marks[i])) { seenOutside = true; break; }
    }
    // 全部が画面内に収まっている場合は、ふつうの1件送りにフォールバックする
    goTo(marks, seenOutside ? i : navIndex + dir, state);
  }

  function touchTerm(state) {
    var terms = currentTerms(state);
    var idx = state.activeTerm || 0;
    if (!terms[idx]) return;
    terms[idx].lastUsed = Date.now();
    saveState(state, true); // 用語の一覧・色は変わらないので、他のタブは巻き込まない
  }

  /* ---- パネルとの連携 ---- */
  function postPageInfo(state, activeCount) {
    if (!channel) return;
    var terms = currentTerms(state);
    var counts = terms.map(function (t, i) {
      return document.querySelectorAll("." + MARK_CLASS + '[data-term-idx="' + i + '"]').length;
    });
    try {
      channel.postMessage({
        type: "page-info",
        url: location.href,
        title: document.title,
        activeTerm: state.activeTerm || 0,
        navIndex: navIndex,
        counts: counts,
      });
    } catch (e) { /* noop */ }
    void activeCount;
  }

  function openPanel() {
    if (panelWindow && !panelWindow.closed) {
      panelWindow.focus();
      return;
    }
    panelWindow = window.open(panelUrl, "wikisys-markers-panel",
      "width=360,height=520,menubar=no,toolbar=no,location=no,status=no");
  }

  // 開いていれば閉じる、閉じていれば開く。テーマ側のヘッダーリンク用
  // （Alt+M は「解除する手段を残す」ため、これまでどおり openPanel のまま）
  function togglePanel() {
    if (panelWindow && !panelWindow.closed) {
      panelWindow.close();
      panelWindow = null;
      return;
    }
    openPanel();
  }

  /* ---- ホットキー ---- */
  function isTypingElsewhere(target) {
    if (!target) return false;
    var tag = target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    return !!(target.isContentEditable);
  }

  function setActiveTerm(index, state) {
    var terms = currentTerms(state);
    if (index < 0 || index >= terms.length) return;

    // 直前の用語で実際に動いたことがあれば（navIndex >= 0）、その文書内の
    // 位置を基準に、切り替えた先の用語でも「続きから」を再現する。複数の
    // 用語をまたいで検索できることを目指しているため、用語を変えるたびに
    // 先頭へ戻ってしまうのは不便という判断（一度も動かしていない用語からの
    // 切り替えでは基準が無いので、これまでどおり先頭に戻す）。
    var referenceEl = navIndex >= 0 ? document.querySelector("." + CURRENT_CLASS) : null;

    state.activeTerm = index;
    navIndex = -1;
    clearCurrent();
    saveState(state, true); // どの用語がアクティブかは、他のタブの表示には影響しない

    if (referenceEl) {
      var marks = activeMarks(state);
      if (marks.length) placeCurrent(marks, positionAmongMarks(marks, referenceEl));
    }
    postPageInfo(state, 0);
  }

  function onKeydown(event) {
    if (isTypingElsewhere(event.target)) return;
    if (event.altKey && !event.ctrlKey && !event.metaKey &&
        (event.key === "m" || event.key === "M")) {
      event.preventDefault();
      openPanel();
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;

    var state = loadState();
    if (state.enabled === false) return; // 無効化中は、Alt+M以外のホットキーも動かさない
    var terms = currentTerms(state);
    if (!terms.length) return; // 用語が無いページ・サイトでは、他のキーの邪魔をしない

    var numIdx = NUMBER_KEY_ORDER.indexOf(event.key);
    if (numIdx !== -1) {
      if (numIdx < terms.length) {
        event.preventDefault();
        setActiveTerm(numIdx, state);
      }
      return;
    }

    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        step(-1, state);
        return;
      case "ArrowRight":
        event.preventDefault();
        step(1, state);
        return;
      case "ArrowUp":
        event.preventDefault();
        jumpFar(-1, state);
        return;
      case "ArrowDown":
        event.preventDefault();
        jumpFar(1, state);
        return;
    }
  }

  /* ---- 起動 ---- */
  function render() {
    unmark();
    navIndex = -1;
    var state = pruneExpired(loadState());
    if (state.enabled !== false) markAll(currentTerms(state));
    postPageInfo(state, 0);
  }

  /* ---- テーマ側（メニュー等）から使う公開API ----
   * サイドバー等にマーカーの状態を出したいテーマ側のJSは、直接
   * localStorage/BroadcastChannelを触らずこのAPIだけを使う。使いかたは
   * Tech/MarkerSystem を参照。
   *
   * 読み込み順序に依存しないよう、`window.WikisysMarkers` はこのスクリプトの
   * 評価時点（<script defer> の実行時）で用意する。summary は
   * wikisys-markers:ready / :change イベントの detail としても渡される。 */
  function summary() {
    var state = loadState();
    return {
      enabled: state.enabled !== false,
      activeSet: state.activeSet,
      setNames: Object.keys(state.sets).sort(),
    };
  }

  function notifyChange() {
    try {
      window.dispatchEvent(new CustomEvent("wikisys-markers:change", { detail: summary() }));
    } catch (e) { /* noop（古いブラウザでCustomEventが無い等） */ }
  }

  window.WikisysMarkers = {
    // 現在の状態の要約（{enabled, activeSet, setNames}）を返す
    getSummary: summary,
    // マーカー表示（ハイライト・ホットキー）そのもののオン/オフを切り替える。
    // Alt+M（パネルを開く）だけは無効化中でも動く（解除する手段を残すため）
    setEnabled: function (value) {
      var state = loadState();
      state.enabled = !!value;
      saveState(state);
      render();
      notifyChange();
    },
    // アクティブな用語セットを切り替える。無い名前を渡すとfalseを返すだけ
    setActiveSet: function (name) {
      var state = loadState();
      if (!state.sets[name]) return false;
      state.activeSet = name;
      state.activeTerm = 0;
      saveState(state);
      render();
      notifyChange();
      return true;
    },
    // 操作用の別ウィンドウ（/.markers-panel）を開く。Alt+Mと同じ
    openPanel: function () { openPanel(); },
    // 開いていれば閉じる、閉じていれば開く。ヘッダーの「マーカー」リンクなど、
    // トグル動作にしたい呼び出し元向け
    togglePanel: function () { togglePanel(); },
  };

  function init() {
    render();
    document.addEventListener("keydown", onKeydown);
    if (channel) {
      channel.onmessage = function (event) {
        var data = event.data || {};
        if (data.type === "state-changed") {
          render();
          notifyChange();
        } else if (data.type === "request-page-info") {
          postPageInfo(loadState(), 0);
        }
      };
    }
    try {
      window.dispatchEvent(new CustomEvent("wikisys-markers:ready", { detail: summary() }));
    } catch (e) { /* noop */ }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
