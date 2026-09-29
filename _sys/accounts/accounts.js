/* accounts.js — /.admin/accounts の一覧操作（更新・削除）をAPI経由で送る。
 *
 * 一覧のボタンは行ごとではなく上に集約してある（Wiki設計者の指示、2026-09-12）。
 *
 *   削除  … 番号の右のチェックボックスで選んだ行を、チェックが1つでも
 *           入っていれば押せる「選んだ行を削除」ボタンで送る
 *   更新  … ページ内で値を変えた行だけを「変更を更新」ボタンで送る
 *
 * どちらも、対象を**1ユーザーずつ順番に**サーバーへ送る（並べて送らないのは、
 * 途中で1件失敗したときに「どこまで進んだか」を追えるようにするため）。
 * 送り先は1件ずつの操作を受ける /.admin/accounts/api
 * （wikilib.accounts.render_accounts_api）。認証はcookieで送る
 * （credentials: "same-origin"。ログイン中の合言葉がそのまま使われる）。
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector(".acct-list[data-api]");
    if (!root) return;

    var apiUrl = root.getAttribute("data-api");
    var table = root.querySelector("#acct-table");
    var updateBtn = root.querySelector("#acct-update-btn");
    var deleteBtn = root.querySelector("#acct-delete-btn");
    var statusEl = root.querySelector("#acct-bulk-status");
    if (!table || !updateBtn || !deleteBtn || !statusEl) return;

    function checkboxes() {
      return Array.prototype.slice.call(table.querySelectorAll(".acct-check"));
    }

    function rows() {
      return Array.prototype.slice.call(table.querySelectorAll("tr[data-uidnum]"));
    }

    function anyChecked() {
      return checkboxes().some(function (cb) { return cb.checked && !cb.disabled; });
    }

    function refreshDeleteButton() {
      deleteBtn.disabled = !anyChecked();
    }

    table.addEventListener("change", function (ev) {
      if (ev.target.classList.contains("acct-check")) refreshDeleteButton();
    });
    refreshDeleteButton();

    function setBusy(busy) {
      updateBtn.disabled = busy;
      checkboxes().forEach(function (cb) {
        // 管理者の行（data-admin="1"）はもともと押せない。busy中はそれ以外も
        // 押せなくし、busyが終われば元の状態（管理者だけ押せない）へ戻す
        cb.disabled = busy || cb.getAttribute("data-admin") === "1";
      });
      deleteBtn.disabled = busy || !anyChecked();
    }

    function setStatus(text, bad) {
      statusEl.textContent = text || "";
      statusEl.classList.toggle("acct-bulk-status-error", !!bad);
    }

    function callApi(payload) {
      return fetch(apiUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (res) {
        return res.json().catch(function () {
          return { ok: false, message: "サーバーの応答を読めませんでした。" };
        });
      }).catch(function () {
        return { ok: false, message: "通信できませんでした。" };
      });
    }

    // 対象（配列）を1件ずつ、前の結果を待ってから次へ進める形で処理する。
    // handler(item) は callApi(...) の Promise を返すこと。
    function runSequential(items, handler, onProgress, onDone) {
      var total = items.length;
      var failed = [];
      var doneCount = 0;

      function step() {
        if (items.length === 0) {
          onDone(doneCount, failed);
          return;
        }
        var item = items.shift();
        handler(item).then(function (result) {
          doneCount++;
          if (!result || !result.ok) {
            failed.push({ item: item, message: (result && result.message) || "失敗しました。" });
          }
          onProgress(doneCount, total, item, result);
          step();
        });
      }
      step();
    }

    // ロック中の見た目（行の背景色と🔒の印）を、再読み込みなしで合わせる。
    // サーバーが描く行（wikilib.accounts._account_row_html）と同じ形にしてある
    function setLockedView(row, locked) {
      row.classList.toggle("acct-locked", locked);
      var num = row.querySelector(".acct-num");
      if (!num) return;
      var mark = num.querySelector(".acct-lock-mark");
      if (locked && !mark) {
        mark = document.createElement("span");
        mark.className = "acct-lock-mark";
        mark.title = "ロック中。パスワードを付け直すと戻ります";
        mark.textContent = "🔒";
        num.insertBefore(mark, num.querySelector(".acct-pending-mark"));
      } else if (!locked && mark) {
        mark.remove();
      }
    }

    updateBtn.addEventListener("click", function () {
      var targets = rows().filter(function (row) {
        var inputs = row.querySelectorAll("input[data-orig]");
        return Array.prototype.slice.call(inputs).some(function (input) {
          return input.value !== input.getAttribute("data-orig");
        });
      });
      if (targets.length === 0) {
        setStatus("変更した行がありません。");
        return;
      }
      var locking = targets.filter(function (row) {
        var pwInput = row.querySelector(".acct-f-pw");
        return pwInput.value === "" && pwInput.value !== pwInput.getAttribute("data-orig");
      }).map(function (row) { return row.querySelector(".acct-f-uid").getAttribute("data-orig"); });
      if (locking.length > 0 && !window.confirm(
        "パスワード欄が空の行はロックします（元のパスワードでは入れなくなります）。\n"
        + "対象: " + locking.join("、") + "\n続けますか？")) {
        return;
      }
      setBusy(true);
      setStatus("更新しています…（0/" + targets.length + "）");
      runSequential(targets, function (row) {
        var uid = row.querySelector(".acct-f-uid").value;
        var name = row.querySelector(".acct-f-name").value;
        var pwInput = row.querySelector(".acct-f-pw");
        // 欄の扱い:
        //   空にした                     … ロック（lock）
        //   「パスワードとして入力」ON   … 書いた文字を生のパスワード（raw）として送り、
        //                                  ハッシュにするのはサーバー側（変更後のIDで計算する）
        //   OFF                          … 欄をハッシュ値（pw）として送る
        //                                  （元のままなら、変えない扱いになる）
        var rawBox = row.querySelector(".acct-f-raw");
        var payload = {
          cmd: "update", uidnum: row.getAttribute("data-uidnum"), uid: uid, name: name,
        };
        if (pwInput.value === "") {
          payload.lock = true;
        } else if (rawBox && rawBox.checked && pwInput.value !== pwInput.getAttribute("data-orig")) {
          payload.raw = pwInput.value;
        } else {
          payload.pw = pwInput.value;
        }
        return callApi(payload).then(function (result) {
          if (result && result.ok) {
            // 欄はサーバーが保存したハッシュ値の表示に戻す（入れた生のパスワードを
            // 画面に残さない）。元の値（data-orig）も合わせる
            if (typeof result.pw === "string") pwInput.value = result.pw;
            if (rawBox) rawBox.checked = false;
            setLockedView(row, result.pw === "LOCKED");
            Array.prototype.slice.call(row.querySelectorAll("input[data-orig]"))
              .forEach(function (input) { input.setAttribute("data-orig", input.value); });
          }
          return result;
        });
      }, function (done, total) {
        setStatus("更新しています…（" + done + "/" + total + "）");
      }, function (done, failed) {
        setBusy(false);
        if (failed.length === 0) {
          setStatus(done + "件を更新しました。");
        } else {
          setStatus(done + "件のうち" + failed.length + "件失敗しました："
            + failed.map(function (f) { return f.message; }).join("、"), true);
        }
      });
    });

    deleteBtn.addEventListener("click", function () {
      var targets = checkboxes().filter(function (cb) { return cb.checked && !cb.disabled; });
      if (targets.length === 0) return;
      if (!window.confirm(targets.length + "件のアカウントを削除します。よろしいですか？")) return;
      // runSequential は渡した配列を shift() で空にしていく。onDone の中で
      // 対象一覧を見返すために、別にコピーを取っておく
      var allTargets = targets.slice();
      setBusy(true);
      setStatus("削除しています…（0/" + targets.length + "）");
      runSequential(targets, function (cb) {
        return callApi({ cmd: "delete", uidnum: cb.getAttribute("data-uidnum") });
      }, function (done, total) {
        setStatus("削除しています…（" + done + "/" + total + "）");
      }, function (done, failed) {
        setBusy(false);
        // 消えたものは行ごと取り除く。失敗したものはチェックを残し、行も残す
        allTargets.forEach(function (cb) {
          var stillFailed = failed.some(function (f) { return f.item === cb; });
          if (!stillFailed) {
            var row = cb.closest("tr");
            if (row) row.parentNode.removeChild(row);
          }
        });
        if (failed.length === 0) {
          setStatus(done + "件を削除しました。");
        } else {
          setStatus((done - failed.length) + "件を削除しました。" + failed.length + "件失敗しました："
            + failed.map(function (f) { return f.message; }).join("、"), true);
        }
        refreshDeleteButton();
      });
    });
  });
})();
