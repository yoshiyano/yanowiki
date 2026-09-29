/* マーカー操作用ウィンドウ（/.markers-panel）のロジック。
 * markers.js（本体・全ページに差し込まれる側）と同じlocalStorageを読み書きし、
 * BroadcastChannelで変化を伝え合う。 */
(function () {
  "use strict";

  var STORAGE_KEY = "wikisys.markers.v1";
  var CHANNEL_NAME = "wikisys-markers";
  var MAX_TERMS = 10; // 数字キー 1〜9・0 に対応する上限
  var NUMBER_KEY_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

  /* ---- 色（32色パレット: プリセット20色 + カスタム12色） ----
   * 濃い色はマーカーとしては読みにくいため、自由な色選択（旧 <input type=color>）を
   * やめ、あらかじめ用意した淡いトーンのパレットから選ぶ形にした。
   * プリセット20色は色相環を均等割り（H: 18度刻み、S45%/V90%固定）にした
   * 淡い色で、編集できない。残り12色はユーザーがHSVエディタで自分の色を
   * 決めて使えるスロットで、決めた色は次に開いたときも同じ位置に残る
   * （wikisys.markers.palette.v1、用語セットとは別にオリジン全体で共有）。 */
  var PALETTE_KEY = "wikisys.markers.palette.v1";
  var CUSTOM_SLOT_COUNT = 12;
  var PRESET_COUNT = 20;

  function hsvToHex(h, s, v) {
    h = ((h % 360) + 360) % 360;
    s = Math.max(0, Math.min(100, s)) / 100;
    v = Math.max(0, Math.min(100, v)) / 100;
    var c = v * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = v - c;
    var r, g, b;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    function toHex(n) {
      var v2 = Math.max(0, Math.min(255, Math.round((n + m) * 255)));
      var s2 = v2.toString(16);
      return s2.length < 2 ? "0" + s2 : s2;
    }
    return "#" + toHex(r) + toHex(g) + toHex(b);
  }

  function hexToHsv(hex) {
    var r = parseInt(hex.slice(1, 3), 16) / 255;
    var g = parseInt(hex.slice(3, 5), 16) / 255;
    var b = parseInt(hex.slice(5, 7), 16) / 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var d = max - min;
    var h = 0;
    if (d !== 0) {
      if (max === r) h = 60 * (((g - b) / d) % 6);
      else if (max === g) h = 60 * ((b - r) / d + 2);
      else h = 60 * ((r - g) / d + 4);
    }
    if (h < 0) h += 360;
    return { h: h, s: max === 0 ? 0 : (d / max) * 100, v: max * 100 };
  }

  var PRESET_COLORS = (function () {
    var arr = [];
    for (var i = 0; i < PRESET_COUNT; i++) {
      arr.push(hsvToHex((360 / PRESET_COUNT) * i, 45, 90));
    }
    return arr;
  })();

  function loadPalette() {
    try {
      var raw = window.localStorage.getItem(PALETTE_KEY);
      var arr = raw ? JSON.parse(raw) : null;
      if (!Array.isArray(arr)) arr = [];
      arr = arr.slice(0, CUSTOM_SLOT_COUNT);
      while (arr.length < CUSTOM_SLOT_COUNT) arr.push(null);
      return arr;
    } catch (e) {
      return new Array(CUSTOM_SLOT_COUNT).fill(null);
    }
  }

  function savePalette(arr) {
    try { window.localStorage.setItem(PALETTE_KEY, JSON.stringify(arr)); } catch (e) { /* noop */ }
  }

  var DEFAULT_COLOR = PRESET_COLORS[0];

  /* ポップオーバーは常に1つだけ（新しく開くときは前のを閉じる） */
  var activePicker = null;
  var activePickerCleanup = null;

  function closeColorPicker() {
    if (activePickerCleanup) activePickerCleanup();
    if (activePicker) activePicker.remove();
    activePicker = null;
    activePickerCleanup = null;
  }

  // クリックしたボタンの近くに出すと、用語一覧の下のほうから開いたときに
  // 画面外へはみ出して操作できなくなっていたため、常に画面中央の固定位置に
  // 出すようにした（anchorElは使わない。ウィンドウの外側クリック判定にだけ
  // 別途使っている）。
  function positionPopover(pop) {
    pop.style.top = "50%";
    pop.style.left = "50%";
    pop.style.transform = "translate(-50%, -50%)";
  }

  // anchorEl: クリックされたボタン（ポップオーバーの位置決めに使う）
  // currentHex: いま選ばれている色（パレット内にあればそこを選択状態にする）
  // onPick(hex): 色が確定したときに呼ばれる
  function openColorPicker(anchorEl, currentHex, onPick) {
    closeColorPicker();
    var custom = loadPalette();
    var normalizedCurrent = (currentHex || "").toLowerCase();

    var pop = document.createElement("div");
    pop.className = "mp-colorpicker";

    var grid = document.createElement("div");
    grid.className = "mp-cp-swatches";
    pop.appendChild(grid);

    var editorBox = document.createElement("div");
    editorBox.className = "mp-cp-editor";
    editorBox.hidden = true;
    pop.appendChild(editorBox);

    function addSwatch(hex, customIdx) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mp-cp-swatch" + (hex ? "" : " mp-cp-swatch--empty");
      if (hex) {
        btn.style.backgroundColor = hex;
        btn.title = hex;
        if (hex.toLowerCase() === normalizedCurrent) btn.classList.add("mp-cp-swatch--selected");
      } else {
        btn.title = "未設定（右下の✎で色を決める）";
      }
      btn.addEventListener("click", function () {
        if (hex) { onPick(hex); closeColorPicker(); }
        else openEditor(customIdx, DEFAULT_COLOR);
      });
      if (customIdx !== undefined) {
        var edit = document.createElement("span");
        edit.className = "mp-cp-swatch-edit";
        edit.textContent = "✎";
        edit.title = "この色を編集";
        edit.addEventListener("click", function (e) {
          e.stopPropagation();
          openEditor(customIdx, hex || DEFAULT_COLOR);
        });
        btn.appendChild(edit);
      }
      grid.appendChild(btn);
    }

    PRESET_COLORS.forEach(function (hex) { addSwatch(hex, undefined); });
    custom.forEach(function (hex, idx) { addSwatch(hex, idx); });

    var svPointerHandlers = null;

    function openEditor(customIdx, seedHex) {
      if (svPointerHandlers) svPointerHandlers.cleanup();
      editorBox.hidden = false;
      editorBox.textContent = "";
      var cur = hexToHsv(seedHex);

      var svpad = document.createElement("div");
      svpad.className = "mp-cp-svpad";
      var cursor = document.createElement("div");
      cursor.className = "mp-cp-svpad-cursor";
      svpad.appendChild(cursor);
      editorBox.appendChild(svpad);

      var hue = document.createElement("input");
      hue.type = "range";
      hue.className = "mp-cp-hue";
      hue.min = "0"; hue.max = "360"; hue.value = String(Math.round(cur.h));
      hue.setAttribute("aria-label", "色相");
      editorBox.appendChild(hue);

      var row = document.createElement("div");
      row.className = "mp-cp-previewrow";
      var preview = document.createElement("div");
      preview.className = "mp-cp-preview";
      var applyBtn = document.createElement("button");
      applyBtn.type = "button";
      applyBtn.textContent = "この色を使う";
      row.appendChild(preview);
      row.appendChild(applyBtn);
      editorBox.appendChild(row);

      function refresh() {
        svpad.style.background =
          "linear-gradient(to top, #000, rgba(0,0,0,0)), " +
          "linear-gradient(to right, #fff, hsl(" + cur.h + ",100%,50%))";
        cursor.style.left = cur.s + "%";
        cursor.style.top = (100 - cur.v) + "%";
        preview.style.backgroundColor = hsvToHex(cur.h, cur.s, cur.v);
      }
      refresh();

      hue.addEventListener("input", function () {
        cur.h = Number(hue.value);
        refresh();
      });

      function svFromEvent(evt) {
        var rect = svpad.getBoundingClientRect();
        var x = Math.min(Math.max(evt.clientX - rect.left, 0), rect.width);
        var y = Math.min(Math.max(evt.clientY - rect.top, 0), rect.height);
        cur.s = rect.width ? (x / rect.width) * 100 : 0;
        cur.v = rect.height ? 100 - (y / rect.height) * 100 : 0;
        refresh();
      }
      var dragging = false;
      function onDown(e) { dragging = true; svpad.setPointerCapture(e.pointerId); svFromEvent(e); }
      function onMove(e) { if (dragging) svFromEvent(e); }
      function onUp() { dragging = false; }
      svpad.addEventListener("pointerdown", onDown);
      svpad.addEventListener("pointermove", onMove);
      svpad.addEventListener("pointerup", onUp);
      svPointerHandlers = {
        cleanup: function () {
          svpad.removeEventListener("pointerdown", onDown);
          svpad.removeEventListener("pointermove", onMove);
          svpad.removeEventListener("pointerup", onUp);
        },
      };

      applyBtn.addEventListener("click", function () {
        var hex = hsvToHex(cur.h, cur.s, cur.v);
        var arr = loadPalette();
        arr[customIdx] = hex;
        savePalette(arr);
        onPick(hex);
        closeColorPicker();
      });
    }

    document.body.appendChild(pop);
    positionPopover(pop);
    activePicker = pop;

    function onOutsideClick(e) {
      if (activePicker && !activePicker.contains(e.target) && e.target !== anchorEl) closeColorPicker();
    }
    function onEscape(e) { if (e.key === "Escape") closeColorPicker(); }
    // 開いた瞬間のクリック（このボタン自身のclickバブリング）で即閉じないよう
    // 次のイベントループから外側クリック監視を始める
    setTimeout(function () {
      document.addEventListener("mousedown", onOutsideClick, true);
      document.addEventListener("keydown", onEscape, true);
    }, 0);
    activePickerCleanup = function () {
      document.removeEventListener("mousedown", onOutsideClick, true);
      document.removeEventListener("keydown", onEscape, true);
      if (svPointerHandlers) svPointerHandlers.cleanup();
    };
  }

  var channel = null;
  try {
    if ("BroadcastChannel" in window) channel = new BroadcastChannel(CHANNEL_NAME);
  } catch (e) {
    channel = null;
  }

  var lastPageInfo = null; // 直近に届いた、本体側ページの一致数などの情報

  function emptyState() {
    return { activeSet: "既定", activeTerm: 0, sets: { "既定": { terms: [] } } };
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

  function saveState(state) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      window.alert("保存できませんでした（ブラウザの設定でlocalStorageが使えない可能性があります）。");
    }
    if (channel) {
      try { channel.postMessage({ type: "state-changed" }); } catch (e2) { /* noop */ }
    }
    render();
  }

  function pruneExpired(state) {
    var now = Date.now();
    var day = 24 * 60 * 60 * 1000;
    var changed = false;
    Object.keys(state.sets).forEach(function (name) {
      var set = state.sets[name];
      var kept = (set.terms || []).filter(function (t) {
        return (now - (t.lastUsed || 0)) < day;
      });
      if (kept.length !== (set.terms || []).length) changed = true;
      set.terms = kept;
    });
    if (changed) {
      try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) { /* noop */ }
    }
    return state;
  }

  function currentTerms(state) {
    var set = state.sets[state.activeSet];
    return (set && set.terms) || [];
  }

  /* ---- 描画 ---- */
  var els = {};

  function q(sel) { return document.querySelector(sel); }

  function renderSetSelect(state) {
    var select = els.setSelect;
    select.textContent = "";
    Object.keys(state.sets).sort().forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === state.activeSet) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function countFor(idx) {
    if (!lastPageInfo || !lastPageInfo.counts) return null;
    return lastPageInfo.counts[idx];
  }

  function renderTerms(state) {
    var terms = currentTerms(state);
    var list = els.terms;
    list.textContent = "";
    terms.forEach(function (t, idx) {
      var li = document.createElement("li");
      li.className = "mp-term" + (idx === (state.activeTerm || 0) ? " mp-term--active" : "");

      var key = document.createElement("span");
      key.className = "mp-term-key";
      key.textContent = NUMBER_KEY_LABELS[idx] || "";
      key.title = "クリックでアクティブにする";
      key.addEventListener("click", function () { setActiveTerm(idx); });
      li.appendChild(key);

      var color = document.createElement("button");
      color.type = "button";
      color.className = "mp-term-color";
      color.style.backgroundColor = t.color || DEFAULT_COLOR;
      color.title = "色を変更";
      color.addEventListener("click", function () {
        openColorPicker(color, t.color || DEFAULT_COLOR, function (hex) {
          var s = loadState();
          var list2 = currentTerms(s);
          if (list2[idx]) {
            list2[idx].color = hex;
            saveState(s);
          }
        });
      });
      li.appendChild(color);

      var text = document.createElement("span");
      text.className = "mp-term-text";
      text.textContent = t.term;
      text.title = "クリックでアクティブにする";
      text.addEventListener("click", function () { setActiveTerm(idx); });
      li.appendChild(text);

      var count = document.createElement("span");
      count.className = "mp-term-count";
      var c = countFor(idx);
      count.textContent = c === null || c === undefined ? "" : c + "件";
      li.appendChild(count);

      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "mp-term-remove";
      remove.textContent = "×";
      remove.title = "この用語を削除";
      remove.addEventListener("click", function () {
        var s = loadState();
        var list2 = currentTerms(s);
        list2.splice(idx, 1);
        if ((s.activeTerm || 0) >= list2.length) s.activeTerm = Math.max(0, list2.length - 1);
        saveState(s);
      });
      li.appendChild(remove);

      list.appendChild(li);
    });
  }

  function renderPageInfo() {
    if (!lastPageInfo) {
      els.pageinfo.textContent = "(まだ開いているページの情報がありません)";
      return;
    }
    var total = (lastPageInfo.counts || []).reduce(function (a, b) { return a + b; }, 0);
    els.pageinfo.textContent =
      (lastPageInfo.title || lastPageInfo.url || "このページ") +
      "：一致 " + total + "件";
  }

  function setActiveTerm(idx) {
    var s = loadState();
    var terms = currentTerms(s);
    if (idx < 0 || idx >= terms.length) return;
    s.activeTerm = idx;
    saveState(s);
  }

  function render() {
    var state = pruneExpired(loadState());
    renderSetSelect(state);
    renderTerms(state);
    renderPageInfo();
  }

  /* ---- 操作 ---- */
  function bindEvents() {
    els.setSelect.addEventListener("change", function () {
      var s = loadState();
      if (s.sets[els.setSelect.value]) {
        s.activeSet = els.setSelect.value;
        s.activeTerm = 0;
        saveState(s);
      }
    });

    q(".mp-set-new").addEventListener("click", function () {
      var name = window.prompt("新しい用語セットの名前:");
      if (!name) return;
      var s = loadState();
      if (s.sets[name]) { window.alert("その名前はすでにあります。"); return; }
      s.sets[name] = { terms: [] };
      s.activeSet = name;
      s.activeTerm = 0;
      saveState(s);
    });

    q(".mp-set-rename").addEventListener("click", function () {
      var s = loadState();
      var oldName = s.activeSet;
      var name = window.prompt("新しい名前:", oldName);
      if (!name || name === oldName) return;
      if (s.sets[name]) { window.alert("その名前はすでにあります。"); return; }
      s.sets[name] = s.sets[oldName];
      delete s.sets[oldName];
      s.activeSet = name;
      saveState(s);
    });

    q(".mp-set-delete").addEventListener("click", function () {
      var s = loadState();
      var names = Object.keys(s.sets);
      if (names.length <= 1) { window.alert("最後の用語セットは削除できません。"); return; }
      if (!window.confirm('用語セット「' + s.activeSet + '」を削除しますか？')) return;
      delete s.sets[s.activeSet];
      s.activeSet = Object.keys(s.sets).sort()[0];
      s.activeTerm = 0;
      saveState(s);
    });

    q(".mp-add-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var term = els.addTerm.value.trim();
      if (!term) return;
      var s = loadState();
      var terms = currentTerms(s);
      if (terms.length >= MAX_TERMS) {
        window.alert("1つの用語セットにつき" + MAX_TERMS + "個までです（数字キーに対応させるため）。");
        return;
      }
      if (terms.some(function (t) { return t.term === term; })) {
        window.alert("すでに登録されています。");
        return;
      }
      terms.push({ term: term, color: addColorValue, lastUsed: Date.now() });
      els.addTerm.value = "";
      saveState(s);

      // 次に追加する用語の色は、今の用語セットでまだ使っていない色から
      // ランダムに選んでおく（毎回同じ色を選び直す手間を省くため）
      addColorValue = pickUnusedColor(terms);
      els.addColor.style.backgroundColor = addColorValue;
    });

    els.addColor.addEventListener("click", function () {
      openColorPicker(els.addColor, addColorValue, function (hex) {
        addColorValue = hex;
        els.addColor.style.backgroundColor = hex;
      });
    });
  }

  // 32色パレット（プリセット20 + 設定済みのカスタム）のうち、渡した用語の
  // 一覧でまだ使われていない色をランダムに1つ選ぶ。全部使われていれば
  // （用語が多い・カスタムを埋めていない等）パレット全体から選び直す。
  function pickUnusedColor(terms) {
    var used = {};
    (terms || []).forEach(function (t) { if (t.color) used[t.color.toLowerCase()] = true; });
    var pool = PRESET_COLORS.concat(loadPalette().filter(function (c) { return !!c; }));
    var unused = pool.filter(function (c) { return !used[c.toLowerCase()]; });
    var from = unused.length ? unused : pool;
    return from.length ? from[Math.floor(Math.random() * from.length)] : DEFAULT_COLOR;
  }

  var addColorValue = DEFAULT_COLOR; // 「新しい用語」フォームで、次に追加する用語の色

  function init() {
    els.setSelect = q(".mp-set-select");
    els.terms = q(".mp-terms");
    els.addTerm = q(".mp-add-term");
    els.addColor = q(".mp-add-color");
    els.pageinfo = q(".mp-pageinfo");
    addColorValue = pickUnusedColor(currentTerms(pruneExpired(loadState())));
    els.addColor.style.backgroundColor = addColorValue;

    bindEvents();
    render();

    if (channel) {
      channel.onmessage = function (event) {
        var data = event.data || {};
        if (data.type === "state-changed") {
          render();
        } else if (data.type === "page-info") {
          lastPageInfo = data;
          renderTerms(loadState());
          renderPageInfo();
        }
      };
      try { channel.postMessage({ type: "request-page-info" }); } catch (e) { /* noop */ }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
