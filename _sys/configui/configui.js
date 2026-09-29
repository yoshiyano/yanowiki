/* Wikiの設定画面（/.admin/configwiki）。
 *
 * **保存ボタンは無い。** 入力欄を直した時点で、直した項目1つだけを窓口
 * （`data-api`）へ送る。送るのは常に1項目で、画面にある値をまとめて送り直す
 * ことはしない（古い値で他の人の書き換えを踏まないため）。
 *
 * 文字を打つ欄は**打ち終わりを待ってから**送る（PAUSE_MS）。1文字ごとに
 * 送ると、書き途中の「2」で保存してから「24」で保存し直すことになる。
 * 欄から離れた（change）ときは待たずに送り、二重に送らないよう、送った値を
 * 覚えて見比べている。
 *
 * タブの切り替えは `/.groups`（_sys/groups/groups.js）と同じ作り。
 *
 * 「定義ルール」のタブは、項目ではなく行の並びを扱う（下の「定義ルール」）。
 *
 * 警告つきの項目（`data-role="guard"` のチェックがあるもの。パスワードの塩）は、
 * **チェックを入れるまで印も入力欄も触れない**。チェックは画面だけの状態で、
 * 保存はしない。送るときは確認済みの印（`ack`）を添え、窓口もこれが無いと断る。
 *
 * Wiki名のタブだけは**ボタンで実行する**。設定ファイルへの書き込みではなく
 * フォルダの移動でURLが変わる操作なので、打ちかけの名前で走らせられない。
 */
(() => {
  "use strict";

  const root = document.querySelector(".wcfg");
  if (!root) return;

  const api = root.dataset.api;
  const stateBox = document.getElementById("wcfg-state");
  const backupsBox = document.getElementById("wcfg-backups");

  const PAUSE_MS = 700;   // 文字を打つ欄で、打ち終わりと見なすまでの間
  const SAID_MS = 2500;   // 「保存しました」を消すまでの間（断りは消さない）

  /* ---- タブ ------------------------------------------------------------ */

  const tabs = Array.from(root.querySelectorAll(".wcfg-tab-btn"));
  const panels = Array.from(root.querySelectorAll(".wcfg-panel"));
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      tabs.forEach((other) => {
        const active = other === btn;
        other.classList.toggle("wcfg-tab-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.panel !== target;
      });
    });
  });

  /* ---- 窓口 ------------------------------------------------------------ */

  /** 窓口へ送って、返事（JSON）を返す。**つながらないときも同じ形で返す。** */
  async function send(payload) {
    let res;
    try {
      res = await fetch(api, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      return { ok: false, message: "送れませんでした（サーバーにつながりません）。" };
    }
    try {
      return await res.json();
    } catch (e) {
      return { ok: false, message: `保存できませんでした（${res.status}）。` };
    }
  }

  /** 知らせを1つ出す。うまくいった知らせだけ、しばらくして消す。 */
  function tell(where, text, bad) {
    if (!where) return;
    where.textContent = text;
    where.classList.toggle("wcfg-said-error", !!bad);
    if (where.dataset.timer) {
      clearTimeout(Number(where.dataset.timer));
      delete where.dataset.timer;
    }
    if (!bad && text) {
      where.dataset.timer = String(setTimeout(() => {
        where.textContent = "";
        delete where.dataset.timer;
      }, SAID_MS));
    }
  }

  /* ---- 項目 ------------------------------------------------------------ */

  root.querySelectorAll(".wcfg-field").forEach((box) => {
    const path = box.dataset.path;
    const use = box.querySelector('[data-role="use"]');
    const value = box.querySelector('[data-role="value"]');
    const said = box.querySelector('[data-role="said"]');
    const guard = box.querySelector('[data-role="guard"]');
    if (!path || !use || !value) return;

    let timer = null;
    let sent = { use: use.checked, value: value.value };

    /** 印と入力欄を、いまの状態に合わせる。警告つきの項目は、チェックが入るまで触れない。 */
    function sync() {
      const open = !guard || guard.checked;
      use.disabled = !open;
      value.disabled = !open || !use.checked;
    }

    async function save() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      const asking = { use: use.checked, value: value.value };
      sent = asking;
      const got = await send({
        op: "set", path: path, use: asking.use, value: asking.value,
        ack: guard ? guard.checked : undefined,
      });
      if (!got.ok) {
        tell(said, got.message || "保存できませんでした。", true);
        return;
      }
      box.classList.toggle("is-own", !!got.own);
      value.disabled = !got.own || (guard ? !guard.checked : false);
      // 打っている最中の欄は書き換えない（カーソルが飛ぶため）。
      // 印を外したときはこの欄に触っていないので、共通の設定の値が入る
      if (typeof got.value === "string" && document.activeElement !== value) {
        value.value = got.value;
        sent = { use: got.own, value: got.value };
      }
      if (stateBox && typeof got.state === "string") stateBox.innerHTML = got.state;
      if (backupsBox && typeof got.backups === "string") {
        backupsBox.innerHTML = got.backups;
      }
      tell(said, got.message || "保存しました。", false);
    }

    /** 送った値から変わっていなければ、送り直さない。 */
    function saveIfChanged() {
      if (use.checked === sent.use && value.value === sent.value) return;
      save();
    }

    use.addEventListener("change", () => {
      sync();
      save();
    });
    if (guard) {
      guard.addEventListener("change", () => {
        // チェックを外したら、打ちかけの値は送らない
        if (!guard.checked && timer) {
          clearTimeout(timer);
          timer = null;
        }
        sync();
      });
      sync();
    }
    value.addEventListener("change", saveIfChanged);
    if (value.tagName !== "SELECT") {
      value.addEventListener("input", () => {
        if (timer) clearTimeout(timer);
        timer = setTimeout(saveIfChanged, PAUSE_MS);
      });
    }
  });

  /* ---- 定義ルール ------------------------------------------------------ */
  //
  // `COLOR()` や `&smile;` などの置き換えルール（wikilib.extrarulesui）。項目と
  // 違って**行の並び**なので、行ごとに送る。追加・削除・並べ替えのあとは番号が
  // 変わるため、窓口が返す一覧（`body`）で `.wcfg-rx-body` を差し替える。
  // 行の中身を直しただけのときは差し替えない（カーソルが飛ぶため）。
  //
  // **各行は「直す前の中身」（data-pattern / data-replace）を持っていて、送るときに
  // 添える。** 先に誰かが並びを変えていたら、窓口が断る（別の行を直さないため）。

  const rx = root.querySelector(".wcfg-rx");
  if (rx) {
    const rxBody = rx.querySelector(".wcfg-rx-body");
    const rxText = rx.querySelector(".wcfg-rx-text");
    const rxResult = rx.querySelector(".wcfg-rx-result");
    const testSaid = rx.querySelector('[data-role="test-said"]');
    let testTimer = null;
    let testSeq = 0;      // 遅れて返った古い結果で、新しい結果を上書きしない
    // 「試す」で保存前のルールを試しているあいだ、その下書き。文章を直して掛け直す
    // ときも添え続ける。追加や削除で一覧が作り直されると、下書きの入力欄も
    // 消えるので、そこで捨てる（見えないものを掛け続けない）
    let activeDraft = null;

    /** 試験欄を掛け直す。`activeDraft` があれば、保存前のルールも末尾に足して試す。 */
    async function runTest() {
      if (testTimer) {
        clearTimeout(testTimer);
        testTimer = null;
      }
      const seq = ++testSeq;
      const payload = { op: "rx_test", text: rxText.value };
      if (activeDraft) payload.draft = activeDraft;
      const got = await send(payload);
      if (seq !== testSeq) return;
      if (!got.ok) {
        rxResult.innerHTML = "";
        tell(testSaid, got.message || "試せませんでした。", true);
        return;
      }
      tell(testSaid, "", false);
      rxResult.innerHTML = got.result || "";
    }

    function scheduleTest() {
      if (testTimer) clearTimeout(testTimer);
      testTimer = setTimeout(runTest, PAUSE_MS);
    }

    rxText.addEventListener("input", scheduleTest);

    /** 行や追加欄の、知らせを出す場所。 */
    function saidOf(el) {
      const box = el.closest(".wcfg-rx-row, .wcfg-rx-add");
      return box ? box.querySelector(".wcfg-said") : null;
    }

    /** 送って、うまくいけば一覧を差し替え、試験欄も掛け直す。 */
    async function structural(payload, said) {
      const got = await send(payload);
      if (!got.ok) {
        tell(said, got.message || "保存できませんでした。", true);
        return false;
      }
      if (typeof got.body === "string") rxBody.innerHTML = got.body;
      activeDraft = null;
      // 差し替えたので、知らせは新しい一覧の上に出し直す
      const fresh = rx.querySelector('[data-role="own-said"]');
      tell(fresh, got.message || "保存しました。", false);
      runTest();
      return true;
    }

    /** 行の中身が変わったとき。 */
    async function rowChanged(row) {
      const pattern = row.querySelector(".wcfg-rx-pattern");
      const replace = row.querySelector(".wcfg-rx-replace");
      const said = row.querySelector(".wcfg-said");
      if (pattern.value === row.dataset.pattern && replace.value === row.dataset.replace) {
        // 保存されている値へ戻した。断られた印と文言は、もう要らない
        row.classList.remove("is-bad");
        tell(said, "", false);
        return;
      }
      const kind = row.closest(".wcfg-rx-kind").dataset.kind;
      const got = await send({
        op: "rx_set", kind: kind, index: Number(row.dataset.index),
        old_pattern: row.dataset.pattern, old_replace: row.dataset.replace,
        pattern: pattern.value, replace: replace.value,
      });
      if (!got.ok) {
        row.classList.add("is-bad");
        tell(said, got.message || "保存できませんでした。", true);
        return;
      }
      row.classList.remove("is-bad");
      row.dataset.pattern = pattern.value;
      row.dataset.replace = replace.value;
      tell(said, "保存しました。", false);
      runTest();
    }

    rx.addEventListener("change", (event) => {
      const el = event.target;
      if (el.matches('[data-role="own"]')) {
        setOwn(el);
      } else if (el.closest(".wcfg-rx-row") && el.matches("input")) {
        rowChanged(el.closest(".wcfg-rx-row"));
      }
    });

    async function setOwn(box) {
      const on = box.checked;
      if (!on && !window.confirm(
        "このWikiの独自の定義を捨てて、共通の定義に戻します。\n" +
        "（直前のファイルは控えとして残ります）")) {
        box.checked = true;
        return;
      }
      const said = rx.querySelector('[data-role="own-said"]');
      const got = await send({ op: "rx_own", on: on });
      if (!got.ok) {
        box.checked = !on;
        tell(said, got.message || "変えられませんでした。", true);
        return;
      }
      if (typeof got.body === "string") rxBody.innerHTML = got.body;
      activeDraft = null;
      tell(rx.querySelector('[data-role="own-said"]'), got.message || "", false);
      runTest();
    }

    rx.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-act]");
      if (!button || button.disabled) return;
      const act = button.dataset.act;
      if (act === "test") {
        runTest();
        return;
      }
      const row = button.closest(".wcfg-rx-row");
      const add = button.closest(".wcfg-rx-add");
      const kindBox = button.closest(".wcfg-rx-kind");
      if (row && kindBox) {
        const base = {
          kind: kindBox.dataset.kind, index: Number(row.dataset.index),
          old_pattern: row.dataset.pattern, old_replace: row.dataset.replace,
        };
        const said = row.querySelector(".wcfg-said");
        if (act === "up" || act === "down") {
          structural(Object.assign({ op: "rx_move", direction: act }, base), said);
        } else if (act === "del") {
          const show = row.dataset.pattern.length > 40
            ? row.dataset.pattern.slice(0, 40) + "…" : row.dataset.pattern;
          if (window.confirm(`このルールを削除します。\n\n${show}`)) {
            structural(Object.assign({ op: "rx_del" }, base), said);
          }
        }
      } else if (add && kindBox) {
        const pattern = add.querySelector('[data-role="new-pattern"]');
        const replace = add.querySelector('[data-role="new-replace"]');
        const said = add.querySelector(".wcfg-said");
        if (act === "try") {
          if (!pattern.value) {
            tell(said, "試すパターンを入れてください。", true);
            return;
          }
          tell(said, "", false);
          activeDraft = {
            kind: kindBox.dataset.kind, pattern: pattern.value, replace: replace.value,
          };
          runTest();
          rxResult.scrollIntoView({ block: "nearest" });
        } else if (act === "add") {
          structural({
            op: "rx_add", kind: kindBox.dataset.kind,
            pattern: pattern.value, replace: replace.value,
          }, said);
        }
      }
    });

    // 開いたときにも、いまの定義で1回掛けておく
    runTest();
  }

  /* ---- Wiki名 ---------------------------------------------------------- */

  const renameGo = document.getElementById("wcfg-rename-go");
  if (renameGo) {
    const nameBox = document.getElementById("wcfg-newname");
    const confirmBox = document.getElementById("wcfg-confirm");
    const said = document.getElementById("wcfg-rename-said");
    renameGo.addEventListener("click", async () => {
      const name = nameBox.value.trim();
      if (!name) {
        tell(said, "新しい名前を入れてください。", true);
        nameBox.focus();
        return;
      }
      const sure = window.confirm(
        `このWikiの名前を「${name}」に変えます。\n\n` +
        "URLが変わるので、外からのリンクは切れ、いま入っている人は" +
        "ログインし直しになります。\n（名前を戻せば元どおりになります）");
      if (!sure) return;
      renameGo.disabled = true;
      const got = await send({
        op: "rename", name: name, confirm: confirmBox.value.trim(),
      });
      renameGo.disabled = false;
      if (!got.ok) {
        tell(said, got.message || "名前を変えられませんでした。", true);
        return;
      }
      tell(said, `${got.message} 新しいURLへ移ります。`, false);
      if (got.url) window.location.href = got.url;
    });
  }
})();
