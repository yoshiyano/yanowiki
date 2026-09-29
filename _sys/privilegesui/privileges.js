/* ページごとのアクセス制限の画面（/.admin/privileges）。
 *
 * 1行が1ページ（ページ名・閲覧の許可者・編集の許可者）。一覧の描き直し・
 * 並べ替え・絞り込み・行ごとの編集は、すべてここが持つ。
 *
 *   一覧の行    ふだんは読むだけ。「編集」アイコンでその行だけ入力欄になり、
 *               アイコンが「確定」に変わる。確定で書き込む（許可者は入力の
 *               とおりに置き換わる）。「やめる」で、書き込まずに読むだけへ戻る
 *   いちばん上  新規の入力。同じページ名が既にあれば、サーバーが古い情報と
 *               マージする（許可者を足す）
 *
 * サーバーへ送るのは追加(add)・書き換え(set)・削除(delete)の3つで、どれも
 * **更新後の一覧をまるごと受け取って**描き直す（差分を組み立てない）。
 *
 * **消えるのは「削除」のときだけ。** 確定は、そのページの許可者を書き換える
 * だけで、他の行には触らない（2026-09-18の不具合の教訓）。
 *
 * 行を開いたときの version を確定・削除のたびに送る。開いたあとに別の操作で
 * 変わっていれば、サーバーが断っていまの一覧を返すので、その行の編集を閉じて
 * いまの内容を出し直す（古い画面が、他の人の書き換えを踏まないため）。
 *
 * 入力欄の打鍵では描き直さない（描き直すと打っている欄が作り直されて、
 * カーソルが消える）。打った内容は、控え（fresh・editing）にだけ持つ。
 */
(() => {
  "use strict";

  const root = document.querySelector(".prv");
  if (!root) return;

  const api = root.dataset.api;
  const filterInput = document.getElementById("prv-filter");
  const noticeBox = document.getElementById("prv-notice");
  const tbody = document.getElementById("prv-rows");

  let rows = [];
  try {
    rows = JSON.parse(document.getElementById("prv-data").textContent || "[]");
  } catch (e) {
    rows = [];
  }

  // 新規の入力の控え
  const fresh = { page: "", r: "", w: "" };
  // 編集中の行。ページ名 -> { version, r, w }（version は開いたときの値、
  // r・w は入力欄の中身の控え）
  const editing = new Map();
  // いま描いてある入力欄（描き直すたびに作り直す）。開いた直後の focus 用
  const refs = { fresh: null, edit: new Map() };

  let sortKey = "stamp";
  let sortAsc = false;
  let filter = "";
  let busy = false;

  /** 260913_103000 → 2026-09-13 10:30:00（サーバー側の _pretty_stamp と同じ形） */
  function prettyStamp(stamp) {
    if (!stamp || stamp.length !== 13) return stamp || "";
    return `20${stamp.slice(0, 2)}-${stamp.slice(2, 4)}-${stamp.slice(4, 6)} ` +
           `${stamp.slice(7, 9)}:${stamp.slice(9, 11)}:${stamp.slice(11, 13)}`;
  }

  function notice(message, ok) {
    if (!message) {
      noticeBox.hidden = true;
      return;
    }
    noticeBox.textContent = message;
    noticeBox.classList.toggle("prv-notice-error", !ok);
    noticeBox.hidden = false;
  }

  // ---- アイコン（外部の資材を使わず、線だけの絵を自前で持つ） -------------

  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    commit: '<polyline points="20 6 9 17 4 12"/>',
    cancel: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    remove: '<polyline points="3 6 5 6 21 6"/>' +
            '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' +
            '<path d="M10 11v6"/><path d="M14 11v6"/>' +
            '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  };

  function icon(name) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = ICONS[name];
    return svg;
  }

  /** 絵だけのボタン。**名前は title と aria-label に持つ**（読み上げ・ホバー用） */
  function iconButton(name, label, className, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `prv-icon ${className}`;
    b.title = label;
    b.setAttribute("aria-label", label);
    b.appendChild(icon(name));
    b.addEventListener("click", onClick);
    return b;
  }

  // ---- 表の部品 ---------------------------------------------------------

  function cell(className) {
    const td = document.createElement("td");
    if (className) td.className = className;
    return td;
  }

  /** 許可者のリストを、読むだけの形で出す。空は「指定なし」 */
  function chips(list) {
    const box = document.createElement("span");
    box.className = "prv-chips";
    if (!list.length) {
      const none = document.createElement("span");
      none.className = "prv-none";
      none.textContent = "—";
      none.title = "指定なし";
      box.appendChild(none);
      return box;
    }
    for (const who of list) {
      const chip = document.createElement("span");
      chip.className = "prv-chip" + (who.startsWith("g:") ? " prv-chip-group" : "");
      chip.textContent = who;
      box.appendChild(chip);
    }
    return box;
  }

  /** 入力欄。打鍵は控えにだけ写す（描き直さない）。Enter で確定、Esc でやめる */
  function textInput(value, label, placeholder, onInput, onEnter, onEscape) {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "prv-input";
    input.value = value;
    input.placeholder = placeholder;
    input.setAttribute("aria-label", label);
    input.autocomplete = "off";
    input.addEventListener("input", () => onInput(input.value));
    input.addEventListener("keydown", (ev) => {
      // 変換中の Enter（日本語入力の確定）では動かさない
      if (ev.isComposing || ev.keyCode === 229) return;
      if (ev.key === "Enter") {
        ev.preventDefault();
        onEnter();
      } else if (ev.key === "Escape" && onEscape) {
        ev.preventDefault();
        onEscape();
      }
    });
    return input;
  }

  /** 新規の入力の行。いつでもいちばん上 */
  function makeFreshRow() {
    const tr = document.createElement("tr");
    tr.className = "prv-row-new";
    const page = textInput(fresh.page, "ページ名", "Tech/Secret",
                           (v) => { fresh.page = v; }, commitFresh, null);
    const r = textInput(fresh.r, "閲覧の許可者", "alice, g:staff",
                        (v) => { fresh.r = v; }, commitFresh, null);
    const w = textInput(fresh.w, "編集の許可者", "bob",
                        (v) => { fresh.w = v; }, commitFresh, null);
    refs.fresh = { page, r, w };
    for (const input of [page, r, w]) {
      const td = cell(input === page ? "prv-page" : "prv-who");
      td.appendChild(input);
      tr.appendChild(td);
    }
    const stamp = cell("prv-stamp");
    stamp.textContent = "新規";
    tr.appendChild(stamp);
    const ops = cell("prv-ops");
    ops.appendChild(iconButton(
      "commit", "登録（同じページ名があれば、許可者を足してまとめます）",
      "prv-commit", commitFresh));
    tr.appendChild(ops);
    return tr;
  }

  /** ふだんの行。読むだけ */
  function makeViewRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.page = row.page;
    const page = cell("prv-page");
    page.textContent = row.page;
    tr.appendChild(page);
    const r = cell("prv-who");
    r.appendChild(chips(row.r));
    tr.appendChild(r);
    const w = cell("prv-who");
    w.appendChild(chips(row.w));
    tr.appendChild(w);
    const stamp = cell("prv-stamp");
    stamp.textContent = prettyStamp(row.stamp);
    tr.appendChild(stamp);
    const ops = cell("prv-ops");
    ops.appendChild(iconButton("edit", "この行を編集する", "prv-edit",
                               () => startEdit(row)));
    ops.appendChild(iconButton("remove", "この行を削除する", "prv-del",
                               () => remove(row)));
    tr.appendChild(ops);
    return tr;
  }

  /** 編集中の行。許可者だけが入力欄になる（ページ名は行の鍵なので書き換えない） */
  function makeEditRow(row, st) {
    const tr = document.createElement("tr");
    tr.className = "prv-row-editing";
    tr.dataset.page = row.page;
    const page = cell("prv-page");
    page.textContent = row.page;
    tr.appendChild(page);
    const done = () => commitEdit(row.page);
    const back = () => cancelEdit(row.page);
    const r = textInput(st.r, `${row.page} の閲覧の許可者`, "指定なし",
                        (v) => { st.r = v; }, done, back);
    const w = textInput(st.w, `${row.page} の編集の許可者`, "指定なし",
                        (v) => { st.w = v; }, done, back);
    refs.edit.set(row.page, { r, w });
    const rCell = cell("prv-who");
    rCell.appendChild(r);
    tr.appendChild(rCell);
    const wCell = cell("prv-who");
    wCell.appendChild(w);
    tr.appendChild(wCell);
    const stamp = cell("prv-stamp");
    stamp.textContent = prettyStamp(row.stamp);
    tr.appendChild(stamp);
    const ops = cell("prv-ops");
    // 「編集」が「確定」に変わる。押すと、入力のとおりに書き込む
    ops.appendChild(iconButton("commit", "確定する（許可者は入力のとおりに置き換わります）",
                               "prv-commit", done));
    ops.appendChild(iconButton("cancel", "やめる（書き込まずに戻す）", "prv-cancel", back));
    tr.appendChild(ops);
    return tr;
  }

  // ---- 並べ替えと絞り込み ---------------------------------------------

  /** 並べ替えと絞り込み。**絞り込みは隠さず、合うものを上へ回すだけ。** */
  function ordered() {
    const list = rows.slice();
    const key = (row) => {
      if (sortKey === "r" || sortKey === "w") return row[sortKey].join(",");
      return row[sortKey] || "";
    };
    list.sort((a, b) => {
      const x = key(a), y = key(b);
      if (x === y) return a.page.localeCompare(b.page);
      return (x < y ? -1 : 1) * (sortAsc ? 1 : -1);
    });
    if (filter) {
      const needle = filter.toLowerCase();
      const hit = (row) => row.r.concat(row.w).join(",").toLowerCase().includes(needle);
      // Array.prototype.sort は安定なので、上の並びを保ったまま2つに分かれる
      list.sort((a, b) => (hit(b) ? 1 : 0) - (hit(a) ? 1 : 0));
    }
    return list;
  }

  function render() {
    tbody.textContent = "";
    refs.edit.clear();
    tbody.appendChild(makeFreshRow());
    for (const row of ordered()) {
      const st = editing.get(row.page);
      tbody.appendChild(st ? makeEditRow(row, st) : makeViewRow(row));
    }
  }

  /** 書き込みが済んだ行を、少しのあいだ光らせて見せる（どこが変わったかの手がかり） */
  function flash(page) {
    const tr = Array.from(tbody.children).find((el) => el.dataset.page === page);
    if (!tr) return;
    tr.classList.add("prv-row-flash");
    tr.scrollIntoView({ block: "nearest" });
    setTimeout(() => tr.classList.remove("prv-row-flash"), 2500);
  }

  // ---- 操作 ------------------------------------------------------------

  function startEdit(row) {
    editing.set(row.page, { version: row.version, r: row.r.join(", "), w: row.w.join(", ") });
    notice("", true);
    render();
    const box = refs.edit.get(row.page);
    if (box) box.r.focus();
  }

  /** 書き込まずに、読むだけへ戻す */
  function cancelEdit(page) {
    editing.delete(page);
    render();
  }

  function commitEdit(page) {
    const st = editing.get(page);
    if (!st) return;
    send({ op: "set", page, r: st.r, w: st.w, version: st.version });
  }

  function commitFresh() {
    send({ op: "add", page: fresh.page.trim(), r: fresh.r, w: fresh.w });
  }

  function remove(row) {
    const show = (list) => (list.length ? list.join(", ") : "なし");
    const ok = window.confirm(
      `«${row.page}» の記録を消します。\n` +
      `閲覧: ${show(row.r)}\n編集: ${show(row.w)}\nよろしいですか？`);
    if (!ok) return;
    send({ op: "delete", page: row.page, version: row.version });
  }

  /** 開いたあとに内容が変わった（または無くなった）行の、編集を閉じる。
   *  閉じた行のページ名を返す */
  function closeStaleEdits() {
    const closed = [];
    for (const [page, st] of Array.from(editing)) {
      const now = rows.find((row) => row.page === page);
      if (!now || now.version !== st.version) {
        editing.delete(page);
        closed.push(page);
      }
    }
    return closed;
  }

  async function send(payload) {
    if (busy) return;
    busy = true;
    root.classList.add("prv-busy");
    let data;
    try {
      const res = await fetch(api, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      data = await res.json();
    } catch (e) {
      notice("送れませんでした。画面を読み込み直してください。", false);
      return;
    } finally {
      busy = false;
      root.classList.remove("prv-busy");
    }
    if (Array.isArray(data.rows)) rows = data.rows;
    if (data.ok) {
      // 書けた行の編集は閉じる。新規の入力は、次の入力のために空へ戻す
      if (payload.op === "add") {
        fresh.page = fresh.r = fresh.w = "";
      } else {
        editing.delete(payload.page);
      }
    }
    // 他の操作で変わってしまった行の編集は、いまの内容で出し直す。
    // 書き換え・削除した行自身の編集が閉じるのは当たり前なので知らせない。
    // **新規の入力がマージした先の行を編集中だったときは知らせる**
    // （打っていた内容が、黙って消えたように見えないように）
    const own = payload.op === "add" ? null : payload.page;
    const closed = closeStaleEdits().filter((page) => page !== own);
    let message = data.message || "";
    if (closed.length) {
      message += `（編集中だった ${closed.map((p) => `«${p}»`).join("・")} は、` +
                 "内容が変わったので編集を閉じました）";
    }
    notice(message, data.ok);
    render();
    if (data.ok && payload.op !== "delete") flash(payload.page);
    if (data.ok && payload.op === "add" && refs.fresh) refs.fresh.page.focus();
  }

  for (const btn of root.querySelectorAll(".prv-sort")) {
    btn.addEventListener("click", () => {
      const key = btn.dataset.sort;
      if (key === sortKey) {
        sortAsc = !sortAsc;
      } else {
        sortKey = key;
        sortAsc = true;
      }
      for (const other of root.querySelectorAll(".prv-sort")) {
        other.removeAttribute("data-dir");
      }
      btn.dataset.dir = sortAsc ? "asc" : "desc";
      render();
    });
  }

  // 最初の並び（更新日の新しい順）を、見出しにも示しておく
  const first = root.querySelector(`.prv-sort[data-sort="${sortKey}"]`);
  if (first) first.dataset.dir = "desc";

  filterInput.addEventListener("input", () => {
    filter = filterInput.value.trim();
    render();
  });

  render();

  // ---- アクセス権を評価する（Wiki設計者の指示、2026-09-22） -------------
  //
  // ページ名を入れると、`op: "evaluate"` を叩いて、登録されている全ユーザ＋未認証、
  // それぞれの判定を表で出す。読むだけで、rows・editing など表の状態には一切触れない。
  //
  // 「その他のユーザ」（未登録のIDを自分で打つ欄）は持たない。未登録のIDは判定の上では
  // どれも未認証と同じ答えにしかならない（全員が共通の状態なので、未認証の1行で足りる）。

  const EVAL_PAUSE_MS = 300;   // 打ち終わりと見なすまでの間

  const RESULT_LABEL = { W: "閲覧・編集", R: "閲覧のみ", "-": "不許可" };
  const RESULT_CLASS = { W: "prv-eval-badge-write", R: "prv-eval-badge-read", "-": "prv-eval-badge-none" };

  const evalPageInput = document.getElementById("prv-eval-page");
  const evalResult = document.getElementById("prv-eval-result");

  if (evalPageInput && evalResult) {
    let evalTimer = null;
    let evalSeq = 0;   // 遅れて返った古い答えで、新しい入力の答えを上書きしない

    function line(className, text) {
      const p = document.createElement("p");
      p.className = className;
      p.textContent = text;
      return p;
    }

    /** 閲覧・編集それぞれの、当たった行の説明。**ページだけで決まり、誰が見るかには関係ない**
     *  ので、ユーザごとに繰り返さず、表の上に1回だけ出す。system（config/privileges）に
     *  加えて、plugin（#readauth・#writeauthの記録）に規則があればそれも出す
     *  （Wiki設計者の指示、2026-09-23。pluginはsystemより優先されるが緩和はしない）。 */
    function ruleBox(label, systemRule, pluginRule) {
      const box = document.createElement("div");
      box.className = "prv-eval-side";
      if (!systemRule) {
        box.appendChild(line("prv-eval-side-head", `${label}: 指定なし（誰にでも許します）`));
      } else {
        box.appendChild(line("prv-eval-side-head", `${label}: 当たった行 ${systemRule.rules.join(" / ")}`));
        box.appendChild(line("prv-eval-side-who", `書かれている許可者: ${systemRule.who.join(", ")}`));
      }
      if (pluginRule) {
        box.appendChild(line("prv-eval-side-plugin",
          `#readauth・#writeauthの記録（優先・緩和しない）: ${pluginRule.who.join(", ")}`));
      }
      return box;
    }

    /** そのユーザの状態（管理者・助手・ロック中・承認待ち）を短い文字列にする。 */
    function accountNotes(account) {
      if (!account) return "";
      const notes = [];
      if (account.admin) notes.push("管理者");
      if (account.staff) notes.push("助手");
      if (!account.approved) notes.push("承認待ち");
      if (account.locked) notes.push("ロック中");
      return notes.join("・");
    }

    /** 表の1行。ロック中・承認待ちは、判定の上では未認証と同じ扱いになる行として目立たせる。 */
    function userRow(u) {
      const tr = document.createElement("tr");
      const warn = u.account && (u.account.locked || !u.account.approved);
      if (warn) tr.className = "prv-eval-row-warn";

      const name = document.createElement("td");
      name.textContent = u.label;
      tr.appendChild(name);

      const status = document.createElement("td");
      status.className = "prv-eval-status";
      status.textContent = accountNotes(u.account);
      tr.appendChild(status);

      const result = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `prv-eval-badge ${RESULT_CLASS[u.result]}`;
      badge.textContent = RESULT_LABEL[u.result];
      result.appendChild(badge);
      tr.appendChild(result);

      return tr;
    }

    function renderEvalResult(data) {
      evalResult.textContent = "";
      if (!data || !data.ok) {
        evalResult.appendChild(line("prv-eval-error", (data && data.message) || "評価できませんでした。"));
        return;
      }
      const shownPage = data.page ? ` /${data.page}` : " /（トップページ）";
      evalResult.appendChild(line("prv-eval-head", shownPage));
      evalResult.appendChild(ruleBox("閲覧", data.system.read, data.plugin.read));
      evalResult.appendChild(ruleBox("編集", data.system.write, data.plugin.write));

      const table = document.createElement("table");
      table.className = "prv-eval-table";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      for (const text of ["ユーザ", "状態", "結果"]) {
        const th = document.createElement("th");
        th.textContent = text;
        headRow.appendChild(th);
      }
      thead.appendChild(headRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const u of data.users) tbody.appendChild(userRow(u));
      table.appendChild(tbody);
      evalResult.appendChild(table);

      if (data.users.some((u) => u.account && (u.account.locked || !u.account.approved))) {
        evalResult.appendChild(line("prv-eval-hint",
          "ロック中・承認待ちのアカウントは、判定の上では未認証と同じ扱いになります。"));
      }
    }

    async function runEval() {
      const seq = ++evalSeq;
      const payload = { op: "evaluate", page: evalPageInput.value.trim() };
      let data;
      try {
        const res = await fetch(api, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        data = await res.json();
      } catch (e) {
        data = { ok: false, message: "送れませんでした。" };
      }
      if (seq !== evalSeq) return;
      renderEvalResult(data);
    }

    function scheduleEval() {
      if (evalTimer) clearTimeout(evalTimer);
      evalTimer = setTimeout(runEval, EVAL_PAUSE_MS);
    }

    evalPageInput.addEventListener("input", scheduleEval);

    // details（アクセス権を評価する）は既定で閉じている（Wiki設計者の指示、2026-09-23。
    // 一番下に置き、開くまで問い合わせない）。**最初に開いたときだけ**、トップページの
    // 表を出しておく。以後の開閉では、いま入っている値のままにする（打ちかけを消さない）
    const evalDetails = document.getElementById("prv-eval");
    let evalStarted = false;
    if (evalDetails) {
      evalDetails.addEventListener("toggle", () => {
        if (evalDetails.open && !evalStarted) {
          evalStarted = true;
          runEval();
        }
      });
    }
  }
})();
