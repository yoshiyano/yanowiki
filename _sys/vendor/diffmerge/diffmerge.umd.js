/*! diffmerge v1.1.1 — build.py が生成。直接編集しないこと。
 *  公開 API: version / compare / build / render / toHunks / toSingleLineHunks / applyMerge / compare3 / build3 / render3 / buildMerge3 / applyMerge3 / lowlevel
 *  ソース: https://github.com/yoshiyano/diff-merge_3way (src/)  ライセンス: MIT
 */
(function (root, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory();
  } else if (typeof define === "function" && define.amd) {
    define([], factory);
  } else {
    root.DiffMerge = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

// ===== src/diff/text.js =====
// テキストを行・単語へ分割するユーティリティ。

/**
 * 文字列を行配列へ分割する。改行コードは \n に正規化する。
 * 末尾の改行 1 個は「行終端」であって空行ではないため取り除く。
 * @param {string} text
 * @returns {{ lines: string[], noFinalNewline: boolean }}
 */
function splitLines(text) {
  const normalized = text.replace(/\r\n?/g, '\n');
  if (normalized === '') {
    return { lines: [''], noFinalNewline: true };
  }
  const noFinalNewline = !normalized.endsWith('\n');
  const body = noFinalNewline ? normalized : normalized.slice(0, -1);
  return { lines: body.split('\n'), noFinalNewline };
}

// 単語分割用トークナイザ。
// 連続する空白 / 英数字の並び / CJK は 1 文字ずつ / その他の記号は 1 文字ずつ、に分ける。
// CJK を 1 文字単位にすることで日本語文の語内差分が細かく取れる。
const WORD_RE =
  /[ \t]+|[A-Za-z0-9_]+|[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]|[^ \t]/gu;

/**
 * 1 行を単語トークン配列へ分割する。
 * @param {string} line
 * @returns {string[]}
 */
function splitWords(line) {
  return line.match(WORD_RE) ?? [];
}

/** HTML 特殊文字をエスケープする。 */
function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}


// ===== src/diff/myers.js =====
// Myers O(ND) 差分アルゴリズム（Myers 1986）の実装。
// 行配列・単語配列など任意の要素列に対して最短編集スクリプトを求める。
//
// 返り値: 操作オブジェクトの配列（元の並び順）
//   { type: 'equal',  aIndex, bIndex }  a[aIndex] と b[bIndex] は等しい
//   { type: 'delete', aIndex }          a[aIndex] を削除
//   { type: 'insert', bIndex }          b[bIndex] を挿入

/**
 * @param {Array}   a   比較元の要素列
 * @param {Array}   b   比較先の要素列
 * @param {(x, y) => boolean} [eq]  要素の等価判定（既定は ===）
 * @returns {Array<{type: string, aIndex?: number, bIndex?: number}>}
 */
function myersDiff(a, b, eq = (x, y) => x === y) {
  const n = a.length;
  const m = b.length;
  const max = n + m;

  // k（対角線番号）は負値を取るため offset を足して 0 起点の配列に格納する。
  const offset = max;
  const v = new Int32Array(2 * max + 1);
  const trace = []; // 各 d ラウンド開始前の v スナップショット

  let editDistance = -1;
  for (let d = 0; d <= max; d++) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let x;
      // k == -d なら下移動（挿入）しか選べない。
      // k == d なら右移動（削除）しか選べない。
      // それ以外は到達 x が大きい側を選ぶ。
      if (k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])) {
        x = v[offset + k + 1]; // 下移動: b を 1 つ消費
      } else {
        x = v[offset + k - 1] + 1; // 右移動: a を 1 つ消費
      }
      let y = x - k;

      // 一致が続く限り対角線上を進む（スネーク）。
      while (x < n && y < m && eq(a[x], b[y])) {
        x++;
        y++;
      }
      v[offset + k] = x;

      if (x >= n && y >= m) {
        editDistance = d;
        break;
      }
    }
    if (editDistance >= 0) break;
  }

  // 終点 (n, m) から始点へ逆向きに経路復元する。
  const ops = [];
  let x = n;
  let y = m;
  for (let d = editDistance; d > 0; d--) {
    const vPrev = trace[d];
    const k = x - y;

    let prevK;
    if (k === -d || (k !== d && vPrev[offset + k - 1] < vPrev[offset + k + 1])) {
      prevK = k + 1;
    } else {
      prevK = k - 1;
    }
    const prevX = vPrev[offset + prevK];
    const prevY = prevX - prevK;

    // 対角線（一致）区間を戻す。
    while (x > prevX && y > prevY) {
      ops.push({ type: 'equal', aIndex: x - 1, bIndex: y - 1 });
      x--;
      y--;
    }
    // 非対角の 1 ステップ（挿入または削除）を戻す。
    if (x === prevX) {
      ops.push({ type: 'insert', bIndex: y - 1 });
    } else {
      ops.push({ type: 'delete', aIndex: x - 1 });
    }
    x = prevX;
    y = prevY;
  }
  // d == 0 の残り: 先頭の一致区間。
  while (x > 0 && y > 0) {
    ops.push({ type: 'equal', aIndex: x - 1, bIndex: y - 1 });
    x--;
    y--;
  }

  ops.reverse();
  return ops;
}


// ===== src/diff/align.js =====
// 行差分の結果を side-by-side 表示用の「行ペア」列へ整形する。


/**
 * @typedef {Object} Side
 * @property {number} lineNo  1 起点の行番号
 * @property {string} text    行テキスト
 *
 * @typedef {Object} Row
 * @property {'equal'|'replace'|'delete'|'insert'} type
 * @property {Side|null} left
 * @property {Side|null} right
 */

/**
 * @param {string[]} aLines
 * @param {string[]} bLines
 * @returns {{ rows: Row[], stats: { added: number, removed: number } }}
 */
function alignLines(aLines, bLines) {
  const ops = myersDiff(aLines, bLines);
  const rows = [];
  let added = 0;
  let removed = 0;

  // 連続する削除・挿入をバッファし、equal に当たった時点で確定する。
  let delBuf = [];
  let insBuf = [];

  const flushChange = () => {
    const paired = Math.min(delBuf.length, insBuf.length);
    // 対応が取れる分は「変更行（replace）」として左右に並べる。
    for (let i = 0; i < paired; i++) {
      rows.push({
        type: 'replace',
        left: { lineNo: delBuf[i] + 1, text: aLines[delBuf[i]] },
        right: { lineNo: insBuf[i] + 1, text: bLines[insBuf[i]] },
      });
    }
    // あふれた削除は左のみ、あふれた挿入は右のみ。
    for (let i = paired; i < delBuf.length; i++) {
      rows.push({
        type: 'delete',
        left: { lineNo: delBuf[i] + 1, text: aLines[delBuf[i]] },
        right: null,
      });
    }
    for (let i = paired; i < insBuf.length; i++) {
      rows.push({
        type: 'insert',
        left: null,
        right: { lineNo: insBuf[i] + 1, text: bLines[insBuf[i]] },
      });
    }
    removed += delBuf.length;
    added += insBuf.length;
    delBuf = [];
    insBuf = [];
  };

  for (const op of ops) {
    if (op.type === 'equal') {
      flushChange();
      rows.push({
        type: 'equal',
        left: { lineNo: op.aIndex + 1, text: aLines[op.aIndex] },
        right: { lineNo: op.bIndex + 1, text: bLines[op.bIndex] },
      });
    } else if (op.type === 'delete') {
      delBuf.push(op.aIndex);
    } else {
      insBuf.push(op.bIndex);
    }
  }
  flushChange();

  return { rows, stats: { added, removed } };
}

/**
 * 片側の行を「対応なし」として取り除き、反対側の指定行の直前へ差し戻した
 * 行ペア列を返す。マージ画面の ↓（片側の列を 1 つ下へ送る）で使う。
 *
 * 取り除いた行は差分計算から外れるので、残りの行が 1 つずつずれて対応し直す
 * ＝反対側の列が 1 行分下へ送られたように見える。差分アルゴリズム自体には
 * 手を入れないので、前後の一致行は保たれる。
 *
 * 位置の基準（anchor）は**取り除かない側**の行番号にすること。そちらが
 * マージで書き換わらない側なら、いくら編集しても anchor は安定して見つかる。
 * 取り除く側の行番号を基準にすると、取り除いた結果が空になったときに
 * 差し戻す位置を決められない。
 *
 * 呼び出し側の対応: 2 文書は takeSide='right'（編集コラム側を取り除き、
 * 左コラムの行番号を anchor に）、3 文書は takeSide='left'（編集コラム側を
 * 取り除き、アクティブ側の行番号を anchor に）。
 *
 * @param {string[]} aLines
 * @param {string[]} bLines
 * @param {Array<{take: number, anchor: number}>} removals
 *   take   … 取り除く側の行（0 起点）
 *   anchor … 反対側の行（0 起点）。その行を含む行ペアの直前へ差し戻す
 * @param {'left'|'right'} takeSide  取り除く側
 * @returns {{ rows: Row[], stats: { added: number, removed: number } }}
 */
function alignLinesShifted(aLines, bLines, removals, takeSide) {
  const takeLeft = takeSide === 'left';
  const takenLines = takeLeft ? aLines : bLines;

  // 1. 取り除く行を外した配列で通常どおり差分を取る
  const reduced = [];
  const origIndex = []; // reduced 上の位置 -> 元の位置（0 起点）
  const takenSet = new Set(removals.map((s) => s.take));
  takenLines.forEach((line, i) => {
    if (!takenSet.has(i)) {
      reduced.push(line);
      origIndex.push(i);
    }
  });
  const { rows, stats } = takeLeft
    ? alignLines(reduced, bLines)
    : alignLines(aLines, reduced);

  // anchor（取り除かない側の行）ごとに、そこへ差し戻す行をまとめる
  const byAnchor = new Map();
  const sorted = removals.slice().sort((x, y) => x.take - y.take);
  for (const s of sorted) {
    if (!byAnchor.has(s.anchor)) byAnchor.set(s.anchor, []);
    byAnchor.get(s.anchor).push(s.take);
  }

  const takenRow = (i) =>
    takeLeft
      ? { type: 'delete', left: { lineNo: i + 1, text: aLines[i] }, right: null }
      : { type: 'insert', left: null, right: { lineNo: i + 1, text: bLines[i] } };

  // 2. 歩きながら差し戻す
  const out = [];
  const emitted = new Set();
  for (const row of rows) {
    const anchorCell = takeLeft ? row.right : row.left;
    if (anchorCell) {
      const pending = byAnchor.get(anchorCell.lineNo - 1);
      if (pending) {
        for (const t of pending) {
          out.push(takenRow(t));
          emitted.add(t);
        }
      }
    }
    // 取り除いた側の行番号を reduced 上の位置から元の位置へ戻す
    const takenCell = takeLeft ? row.left : row.right;
    if (takenCell) {
      const restored = {
        lineNo: origIndex[takenCell.lineNo - 1] + 1,
        text: takenCell.text,
      };
      if (takeLeft) row.left = restored;
      else row.right = restored;
    }
    out.push(row);
  }
  // anchor が見つからなかったぶん（反対側が空など）は末尾へ
  for (const s of sorted) {
    if (!emitted.has(s.take)) out.push(takenRow(s.take));
  }

  if (takeLeft) stats.removed += sorted.length;
  else stats.added += sorted.length;
  return { rows: out, stats };
}


// ===== src/diff/inline.js =====
// 変更行ペアに対する語単位（インライン）差分。
// diff2html の "変更行内の差分ハイライト" に相当する。


/**
 * 左右 1 行ずつを語単位で比較し、変更箇所を <del>/<ins> で囲んだ HTML を返す。
 * @param {string} leftText
 * @param {string} rightText
 * @returns {{ leftHtml: string, rightHtml: string }}
 */
function inlineDiff(leftText, rightText) {
  const a = splitWords(leftText);
  const b = splitWords(rightText);
  const ops = myersDiff(a, b);

  let leftHtml = '';
  let rightHtml = '';
  let delRun = '';
  let insRun = '';

  const flush = () => {
    if (delRun) {
      leftHtml += `<del class="dm-inline-del">${escapeHtml(delRun)}</del>`;
      delRun = '';
    }
    if (insRun) {
      rightHtml += `<ins class="dm-inline-ins">${escapeHtml(insRun)}</ins>`;
      insRun = '';
    }
  };

  for (const op of ops) {
    if (op.type === 'equal') {
      flush();
      leftHtml += escapeHtml(a[op.aIndex]);
      rightHtml += escapeHtml(b[op.bIndex]);
    } else if (op.type === 'delete') {
      delRun += a[op.aIndex];
    } else {
      insRun += b[op.bIndex];
    }
  }
  flush();

  return { leftHtml, rightHtml };
}


// ===== src/diff/align3.js =====
// 3 文書（b / a / c、中心は a）の行アライメント。
// UI 上の呼び名は b = 左コラム、a = 編集コラム（マージの編集対象）、
// c = 右コラム。
//
// 表示は b・a・c の 3 カラム。どちらか一方の外側文書が「アクティブ」で、
// a との差分をこれまでどおり色付き行として見せる。もう一方（非アクティブ）は
// a の行に合わせて並べるだけで、差分は a 側の枠線寄りのマーカーで示す。
//
// 空行調整（フィラー）は **a とアクティブ文書の間だけ** で行う。非アクティブ側は
// 行が余っても行を増やさず隠し、隠した数を hiddenCount で返す。ただし
// 「a に対応が無く、しかも直前が差分でない」挿入だけは見落とすため、
// 行番号なしの行を 1 行だけ足して知らせる（type: 'other-insert'）。


/**
 * @typedef {{ lineNo: number, text: string }} Side
 *
 * @typedef {Object} Row3
 * @property {'equal'|'replace'|'delete'|'insert'|'other-insert'} type
 *   a とアクティブ文書の関係。a を基準（変更前）とみなし、
 *   delete = a のみ（アクティブに無い）、insert = アクティブのみ。
 *   'other-insert' は非アクティブの挿入を知らせるために足した行。
 * @property {Side|null} a
 * @property {Side|null} b
 * @property {Side|null} c
 * @property {'insert'|'delete'|'replace'|null} mark
 *   非アクティブ文書と a の差分。a セルの枠線寄りに出すマーカーの種類。
 * @property {number} hiddenCount  非アクティブ側でこの行に畳み込んだ行数
 */

/**
 * 3 文書を、アクティブ側を基準に 1 本の行列へ整列する。
 *
 * @param {string[]} aLines  中心文書
 * @param {string[]} bLines  左の文書
 * @param {string[]} cLines  右の文書
 * @param {'b'|'c'} [active] アクティブな外側文書（既定は b）
 * @param {Array<{a: number, anchor: number}>} [shifts]
 *   マージ画面の ↓（アクティブ側の列を 1 つ下へ送る）で送り出した行。
 *   a      … 対応なしにする編集コラムの行（0 起点）
 *   anchor … その行を直前へ置くアクティブ側の行（0 起点）
 *   位置の基準をアクティブ側の行番号に置くのは、マージで書き換わるのは
 *   編集コラムだけで、アクティブ側の行番号のほうが安定して見つかるため。
 * @returns {{
 *   rows: Row3[],
 *   active: 'b'|'c',
 *   stats: {
 *     active: { added: number, removed: number },
 *     inactive: { added: number, removed: number }
 *   }
 * }}
 */
function alignThree(aLines, bLines, cLines, active = 'b', shifts) {
  const activeKey = active === 'c' ? 'c' : 'b';
  const otherKey = activeKey === 'c' ? 'b' : 'c';
  const activeLines = activeKey === 'c' ? cLines : bLines;
  const otherLines = activeKey === 'c' ? bLines : cLines;

  // a を左（基準）に固定して 2 回比較する。左 = a、右 = 相手文書。
  // ↓ で送り出した行があるときは、編集コラム側を取り除く向きで整列する
  // （＝アクティブ側の列が 1 行分下へ送られたように見える）。
  const main =
    shifts && shifts.length > 0
      ? alignLinesShifted(
          aLines,
          activeLines,
          shifts.map((s) => ({ take: s.a, anchor: s.anchor })),
          'left'
        )
      : alignLines(aLines, activeLines); // 行の骨組みを決める
  const sub = alignLines(aLines, otherLines); // a の行番号へ写像するだけ

  // --- 非アクティブ側を a の行番号で引けるようにする ---
  const byA = new Map(); // aLineNo -> { side: Side|null, type }
  const surplus = new Map(); // aLineNo -> { lines: Side[], anchored: boolean }
  let lastA = 0; // 直前に見た a の行番号（0 = まだ無い）
  let lastType = null; // 直前の非 insert 行の種別

  for (const r of sub.rows) {
    if (r.type === 'insert') {
      // a に対応の無い行。直前が差分（replace / delete）ならその行に畳み込めるが、
      // 直前が equal または先頭なら見落とすので独立した行を足す。
      let g = surplus.get(lastA);
      if (!g) {
        g = { lines: [], anchored: lastType === 'replace' || lastType === 'delete' };
        surplus.set(lastA, g);
      }
      g.lines.push(r.right);
      continue;
    }
    lastA = r.left.lineNo;
    lastType = r.type;
    byA.set(lastA, { side: r.right, type: r.type });
  }

  // --- 骨組みを歩きながら 3 カラム分の行を組み立てる ---
  const rows = [];

  // 独立行（a に対応が無く直前も差分でない挿入）を 1 行だけ足す。
  const emitLoneInsert = (aLineNo) => {
    const g = surplus.get(aLineNo);
    if (!g || g.anchored || g.done) return;
    g.done = true;
    const [first, ...rest] = g.lines;
    rows.push({
      type: 'other-insert',
      a: null,
      [activeKey]: null,
      [otherKey]: first,
      mark: 'insert',
      hiddenCount: rest.length,
    });
  };

  emitLoneInsert(0); // 先頭より前の挿入

  for (const r of main.rows) {
    const aSide = r.left;
    const activeSide = r.right;

    let otherSide = null;
    let mark = null;
    let hiddenCount = 0;

    if (aSide) {
      const s = byA.get(aSide.lineNo);
      if (s) {
        if (s.type === 'replace') {
          otherSide = s.side;
          mark = 'replace';
        } else if (s.type === 'delete') {
          otherSide = null; // 非アクティブにこの行は無い
          mark = 'delete';
        } else {
          otherSide = s.side; // equal
        }
      }
      const g = surplus.get(aSide.lineNo);
      if (g && g.anchored && !g.done) {
        g.done = true;
        hiddenCount = g.lines.length;
        mark = mark ?? 'insert';
      }
    }

    rows.push({
      type: r.type,
      a: aSide,
      [activeKey]: activeSide,
      [otherKey]: otherSide,
      mark,
      hiddenCount,
    });

    if (aSide) emitLoneInsert(aSide.lineNo);
  }

  return {
    rows,
    active: activeKey,
    stats: { active: main.stats, inactive: sub.stats },
  };
}


// ===== src/render/side-by-side.js =====
// side-by-side（2 カラム）差分ビューの描画。
// diff2html の side-by-side 出力の見た目・構造を素の DOM で再現する。
//
// 用語（UI 表示と合わせる）:
//   左コラム   … 左に置く参照用の文書。マージでも書き換えない
//   編集コラム … 右に置く文書。マージの編集対象はこちらだけ
// コード内の left / right、ハンクの aLines / bLines はそれぞれ
// 左コラム / 編集コラムに対応する。
//
// 提供する API:
//   computeRows()        … 差分データのみ（DOM 非依存 / Node でも動作）
//   toHunks()            … 差分データ → 相違点のかたまり（マージ操作の単位）
//   toSingleLineHunks()  … 同上、行ごとに独立したハンクにする版（singleline 用）
//   applyMerge()         … 相違点を左から右へ取り込んだ右文書テキストを返す（DOM 非依存）
//   build()              … 差分データ + ビュー HTML 文字列（DOM 非依存）
//   render()             … 指定要素へ描画し、操作ハンドルを返す（要 DOM。merge 対応）


const ROW_CLASS = {
  equal: 'dm-row-equal',
  replace: 'dm-row-replace',
  delete: 'dm-row-delete',
  insert: 'dm-row-insert',
};

const DEFAULTS = {
  leftTitle: '文書 A(変更前)',
  rightTitle: '文書 B(変更後)',
  inlineDiff: true, // 変更行ペアの語単位ハイライト
  merge: false, // 2 コラムの間に取り込み操作ボタンを出す（編集対象は編集コラムのみ）
  // true にすると、複数行にまたがる相違点をひとかたまりで扱わず、行ごとに
  // 個別の操作パネルを出す（ボタンも → ↗ ↘ に加え ↓ x の 5 つになる）
  singleline: false,
  // merge 時のキー操作（Ctrl+Z 取り消し / Ctrl+Shift+Z・Ctrl+Y やり直し）。
  // ビューにフォーカスがあるときだけ効く
  hotkeys: true,
  // singleline の ↓（左コラムの行を 1 つ下へ送る）で送り出した行の一覧。
  // { r: 編集コラムの行（0 起点）, anchor: その直前へ置く左コラムの行（0 起点） }。
  // render() が内部で管理する（compare()/build() へ直接渡すこともできる）
  shifts: [],
  onChange: null, // merge 時、右文書が更新されたら (newRight, info) で呼ばれる
  // 表示エリアの高さ。'auto'（既定）は親要素が高さを持つ flex/grid 文脈なら
  // そこまで広がり（.dm-wrapper だけスクロール）、そうでなければ内容なりに
  // 育つ（--dm-table-max-height が上限）。数値は px、文字列は任意の CSS 長さ
  // （例 '50vh'）として、その高さを上限に固定する
  viewH: 'auto',
};

const NO_NEWLINE_LABEL = '(末尾に改行なし)';

// マージ操作ボタンのアイコン。→（右）は上書き、↗↘ は上下への挿入を表す。
// singleline（行単位）モード専用の 2 つ:
//   ↓ … 左コラムの行を 1 つ下へ送る。編集コラムの内容は消さず、左コラムの
//        どの行とも対応しない独立した挿入行として残す（テキストは変えない）
//   x … 編集コラムのその行を取り除く（左コラムの内容は取り込まない）
const MERGE_ICON = {
  overwrite:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10h12"/><path d="M10 5l5 5-5 5"/></svg>',
  'insert-above':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16 15 5"/><path d="M8 5h7v7"/></svg>',
  'insert-below':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4 15 15"/><path d="M8 15h7V8"/></svg>',
  skip:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 4v10"/><path d="M5 10l5 5 5-5"/></svg>',
  delete:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l8 8"/><path d="M14 6l-8 8"/></svg>',
};

const MERGE_LABEL = {
  overwrite: '上書き(この相違点で編集コラムを左コラムの内容に置き換え)',
  'insert-above': '上に挿入(左コラムの内容を相違点の上へ追加)',
  'insert-below': '下に挿入(左コラムの内容を相違点の下へ追加)',
  skip: '下へ送る(編集コラムはそのままに、左コラムの行を 1 つ下へずらす)',
  delete: '削除(編集コラムのこの行を取り除く)',
};

// 取り消し / やり直し（操作列の見出しに置く）。
const HIST_ICON = {
  undo:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6 4 10l4 4"/><path d="M4 10h8a4 4 0 0 1 0 8"/></svg>',
  redo:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6l4 4-4 4"/><path d="M16 10H8a4 4 0 0 0 0 8"/></svg>',
};
const HIST_LABEL = {
  undo: '取り消し(直前の取り込みを戻す。Ctrl+Z)',
  redo: 'やり直し(Ctrl+Shift+Z / Ctrl+Y)',
};

// マージビューの操作説明（表の下に出す）。singleline なら増える 2 つも案内する。
function mergeHint(singleline) {
  return (
    '左コラムの操作ボタンで相違点を編集コラムへ取り込み(→ 上書き / ↗ 上に挿入 / ↘ 下に挿入' +
    (singleline ? ' / ↓ 下へ送る / x 削除' : '') +
    ')。↶(Ctrl+Z)取り消し ↷(Ctrl+Shift+Z)やり直し。' +
    '編集単位を見出しの「まとめて」と「1 行ごと」で切り替え。'
  );
}

// マージ単位の切り替え（見出しに置くラジオ）。同じページに複数のビューが
// あってもラジオが混ざらないよう、name をインスタンスごとに変える。
let SL_SEQ = 0;
function singlelineRadios(singleline) {
  const name = `dm-sl-${(SL_SEQ += 1)}`;
  const opt = (value, label, on) =>
    '<label class="dm-sl-opt">' +
    `<input type="radio" class="dm-sl" name="${name}" value="${value}"` +
    `${on ? ' checked' : ''} />${label}</label>`;
  return (
    '<span class="dm-sl-group" role="radiogroup" aria-label="マージ単位">' +
    opt('hunk', 'まとめて', !singleline) +
    opt('line', '1 行ごと', singleline) +
    '</span>'
  );
}

// 中身が空文字 1 行だけ（＝実質空の入力）か。
function isBlank(split) {
  return split.lines.length === 1 && split.lines[0] === '';
}

/**
 * 2 文書の行差分データを求める（DOM 非依存）。
 *
 * 末尾改行の扱い:
 *   - 改行の有無が左右で食い違う場合、最終行そのものが差分。最終行ペアが
 *     まだ equal ならここで replace へ格上げする（統計にも反映）。
 *   - `noFinalNewline` に左右の改行なしフラグを返す。ビュー側はこれを見て
 *     行番号なしの「（末尾に改行なし）」マーカー行を出す。
 *
 * @param {string} left
 * @param {string} right
 * @returns {{
 *   rows: import('../diff/align.js').Row[],
 *   stats: { added: number, removed: number },
 *   noFinalNewline: { left: boolean, right: boolean }
 * }}
 */
function computeRows(left, right, shifts) {
  const a = splitLines(String(left));
  const b = splitLines(String(right));

  const rowsAndStats =
    shifts && shifts.length > 0
      ? alignWithShifts(a.lines, b.lines, shifts)
      : alignLines(a.lines, b.lines);
  const { rows, stats } = rowsAndStats;

  const noFinalNewline = {
    left: a.noFinalNewline && !isBlank(a),
    right: b.noFinalNewline && !isBlank(b),
  };

  if (noFinalNewline.left !== noFinalNewline.right && rows.length > 0) {
    const last = rows[rows.length - 1];
    const isLastLinePair =
      last.type === 'equal' &&
      last.left &&
      last.right &&
      last.left.lineNo === a.lines.length &&
      last.right.lineNo === b.lines.length;
    if (isLastLinePair) {
      last.type = 'replace';
      stats.added += 1;
      stats.removed += 1;
    }
  }

  return { rows, stats, noFinalNewline };
}

/**
 * 「左の行を 1 つ下へ送る」（singleline の ↓）を反映した行列を組み立てる。
 *
 * ↓ は編集コラムの行 `r` を「左コラムのどの行とも対応しない独立した挿入行」に
 * し、その行を、送り出された左コラムの行 `anchor` の**直前**へ置く操作。
 * テキストは何も変えない。実体は align.js の `alignLinesShifted`
 * （編集コラム側を取り除く向き）。位置の基準を左コラムの行番号に置くのが要点で、
 * 左コラムは書き換えないので常に安定して見つかる（編集コラムの行番号を基準に
 * すると、取り除いた結果が空になったときに差し込み位置を決められない）。
 *
 * @param {string[]} aLines  左コラムの行
 * @param {string[]} bLines  編集コラムの行
 * @param {Array<{r: number, anchor: number}>} shifts
 */
function alignWithShifts(aLines, bLines, shifts) {
  return alignLinesShifted(
    aLines,
    bLines,
    shifts.map((s) => ({ take: s.r, anchor: s.anchor })),
    'right'
  );
}

/**
 * 差分の行列を「相違点のかたまり（ハンク）」へまとめる。マージ操作の単位。
 *
 * @param {import('../diff/align.js').Row[]} rows  computeRows() の rows
 * @returns {Array<{
 *   aStart: number, aEnd: number,   // 左コラムの行範囲 [start, end)（0 起点）
 *   bStart: number, bEnd: number,   // 編集コラムの行範囲 [start, end)
 *   aLines: string[], bLines: string[]
 * }>}
 */
function toHunks(rows) {
  const hunks = [];
  let ai = 0;
  let bi = 0;
  let cur = null;

  for (const row of rows) {
    if (row.type === 'equal') {
      if (cur) {
        cur.aEnd = ai;
        cur.bEnd = bi;
        hunks.push(cur);
        cur = null;
      }
      ai += 1;
      bi += 1;
      continue;
    }
    if (!cur) cur = { aStart: ai, bStart: bi, aLines: [], bLines: [] };
    if (row.left) {
      cur.aLines.push(row.left.text);
      ai += 1;
    }
    if (row.right) {
      cur.bLines.push(row.right.text);
      bi += 1;
    }
  }
  if (cur) {
    cur.aEnd = ai;
    cur.bEnd = bi;
    hunks.push(cur);
  }
  return hunks;
}

/**
 * `toHunks()` の行単位（singleline）版。複数行にまたがる相違点でも
 * まとめず、行 1 つごとに独立したハンクにする（マージ操作の単位を細かくする）。
 *
 * @param {import('../diff/align.js').Row[]} rows  computeRows() の rows
 * @returns {Array<ReturnType<typeof toHunks>[number]|null>}
 *   rows と同じ長さの配列。equal 行は null、それ以外はその行だけのハンク。
 */
function toSingleLineHunks(rows) {
  const result = rows.map(() => null);
  let ai = 0;
  let bi = 0;

  rows.forEach((row, idx) => {
    if (row.type === 'equal') {
      ai += 1;
      bi += 1;
      return;
    }
    const hunk = { aStart: ai, bStart: bi, aLines: [], bLines: [] };
    if (row.left) {
      hunk.aLines.push(row.left.text);
      ai += 1;
    }
    if (row.right) {
      hunk.bLines.push(row.right.text);
      bi += 1;
    }
    hunk.aEnd = ai;
    hunk.bEnd = bi;
    result[idx] = hunk;
  });

  return result;
}

/**
 * 相違点（ハンク）を左コラムから編集コラムへ取り込んだ、新しい編集コラムの
 * テキストを返す。書き換えるのは編集コラムだけ。
 *
 * @param {string} rightText  現在の編集コラムのテキスト
 * @param {ReturnType<typeof toHunks>[number]} hunk
 * @param {'overwrite'|'insert-above'|'insert-below'|'delete'} op
 *   overwrite     … その相違点の編集コラムの行を、左コラムの行で置き換える
 *   insert-above  … 左コラムの行を相違点の上へ挿入する（編集コラムの行は残す）
 *   insert-below  … 左コラムの行を相違点の下へ挿入する（編集コラムの行は残す）
 *   delete        … 左コラムの内容は取り込まず、編集コラムの行を取り除く
 *                   （singleline 向け）
 *
 * singleline の「↓（下へ送る）」はテキストを変えない別操作なので、ここには
 * 無い（`shifts` オプションで扱う）。
 * @returns {string}
 */
function applyMerge(rightText, hunk, op) {
  const r = splitLines(String(rightText));
  const lines = r.lines.slice();
  const a = hunk.aLines;

  if (op === 'overwrite') {
    lines.splice(hunk.bStart, hunk.bEnd - hunk.bStart, ...a);
  } else if (op === 'insert-above') {
    lines.splice(hunk.bStart, 0, ...a);
  } else if (op === 'insert-below') {
    lines.splice(hunk.bEnd, 0, ...a);
  } else if (op === 'delete') {
    lines.splice(hunk.bStart, hunk.bEnd - hunk.bStart);
  } else {
    throw new Error('applyMerge: 未知の操作: ' + String(op));
  }

  const joined = lines.join('\n');
  return r.noFinalNewline ? joined : joined + '\n';
}

/**
 * 片側セル（行番号 + コード）2 つ分の <td> 群を生成する。
 * 追加・削除は行の背景色と左右どちらの列かで示すので、unified diff の
 * ような - / + の記号は付けない（diff の記法を知らない利用者には
 * 意味が伝わらないため）。
 * @param {import('../diff/align.js').Side|null} side
 * @param {string} codeHtml  すでにエスケープ／マークアップ済みの HTML
 * @returns {string}
 */
function sideCells(side, codeHtml) {
  if (side === null) {
    return (
      '<td class="dm-lineno dm-empty"></td>' + '<td class="dm-code dm-empty"></td>'
    );
  }
  return (
    `<td class="dm-lineno">${side.lineNo}</td>` +
    `<td class="dm-code">${codeHtml}</td>`
  );
}

// 各行がどのハンクに属するか（先頭行かどうか・ハンク内行数）を求める。
function rowHunkInfo(rows) {
  const info = rows.map(() => null);
  let i = 0;
  let hunk = -1;
  while (i < rows.length) {
    if (rows[i].type === 'equal') {
      i += 1;
      continue;
    }
    hunk += 1;
    const start = i;
    while (i < rows.length && rows[i].type !== 'equal') i += 1;
    info[start] = { first: true, hunk, count: i - start };
    for (let j = start + 1; j < i; j += 1) info[j] = { first: false, hunk };
  }
  return info;
}

// 2 コラムの間の操作領域セル。全行に出す（列数を一定に保つため）。
// ボタンはそのハンクの先頭行にだけ置く。
function mergeGutterCell(hinfo, hunk) {
  if (!hinfo || !hinfo.first) return '<td class="dm-mgut"></td>';
  const canInsert = hunk && hunk.aLines.length > 0;
  const btn = (op, extra = '') =>
    `<button type="button" class="dm-mop" data-op="${op}"` +
    ` title="${MERGE_LABEL[op]}" aria-label="${MERGE_LABEL[op]}"${extra}>` +
    `${MERGE_ICON[op]}</button>`;
  return (
    '<td class="dm-mgut dm-mgut-ops">' +
    `<div class="dm-merge-ops" data-hunk="${hinfo.hunk}">` +
    btn('overwrite') +
    btn('insert-above', canInsert ? '' : ' disabled') +
    btn('insert-below', canInsert ? '' : ' disabled') +
    '</div></td>'
  );
}

// singleline 版の操作領域セル。行ごとに出す（5 ボタン: → ↗ ↘ ↓ x）。
function singleLineGutterCell(hunk, rowIdx) {
  if (!hunk) return '<td class="dm-mgut"></td>';
  const canInsert = hunk.aLines.length > 0;
  const canRemove = hunk.bLines.length > 0;
  // ↓（左の行を 1 つ下へ送る）は、左右が実際に対応している行にだけ意味がある
  const canShift = hunk.aLines.length > 0 && hunk.bLines.length > 0;
  const btn = (op, extra = '') =>
    `<button type="button" class="dm-mop" data-op="${op}"` +
    ` title="${MERGE_LABEL[op]}" aria-label="${MERGE_LABEL[op]}"${extra}>` +
    `${MERGE_ICON[op]}</button>`;
  return (
    '<td class="dm-mgut dm-mgut-ops">' +
    `<div class="dm-merge-ops" data-row="${rowIdx}">` +
    btn('overwrite') +
    btn('insert-above', canInsert ? '' : ' disabled') +
    btn('insert-below', canInsert ? '' : ' disabled') +
    btn('skip', canShift ? '' : ' disabled') +
    btn('delete', canRemove ? '' : ' disabled') +
    '</div></td>'
  );
}

/**
 * 差分データからビュー全体の HTML 文字列を組み立てる。
 * @param {ReturnType<typeof computeRows>} data
 * @param {typeof DEFAULTS} opt
 * @returns {string}
 */
function rowsToHtml(data, opt) {
  const { rows, stats, noFinalNewline } = data;
  const merge = !!opt.merge;
  // viewH: 'auto'（既定）なら何もしない。数値/文字列なら --dm-table-max-height を
  // このインスタンスだけ上書きし、表示エリアの高さ上限を固定する。
  const viewH =
    opt.viewH == null || opt.viewH === 'auto'
      ? ''
      : ` style="--dm-table-max-height: ${escapeHtml(
          typeof opt.viewH === 'number' ? `${opt.viewH}px` : String(opt.viewH)
        )}"`;
  const singleline = merge && !!opt.singleline;
  const hunks = merge && !singleline ? toHunks(rows) : null;
  const hinfos = merge && !singleline ? rowHunkInfo(rows) : null;
  const lineHunks = singleline ? toSingleLineHunks(rows) : null;
  const bodyParts = [];

  rows.forEach((row, idx) => {
    let leftCode;
    let rightCode;

    if (row.type === 'replace' && opt.inlineDiff) {
      const { leftHtml, rightHtml } = inlineDiff(row.left.text, row.right.text);
      leftCode = leftHtml;
      rightCode = rightHtml;
    } else {
      leftCode = row.left ? escapeHtml(row.left.text) : '';
      rightCode = row.right ? escapeHtml(row.right.text) : '';
    }

    let gut = '';
    if (merge) {
      if (singleline) {
        gut = singleLineGutterCell(lineHunks[idx], idx);
      } else {
        const hinfo = hinfos[idx];
        gut = mergeGutterCell(hinfo, hinfo ? hunks[hinfo.hunk] : null);
      }
    }

    bodyParts.push(
      `<tr class="${ROW_CLASS[row.type]}">` +
        sideCells(row.left, leftCode) +
        gut +
        sideCells(row.right, rightCode) +
        '</tr>'
    );
  });

  if (noFinalNewline.left || noFinalNewline.right) {
    const cell = (show) =>
      '<td class="dm-lineno"></td>' +
      (show
        ? `<td class="dm-code dm-nonewline">${NO_NEWLINE_LABEL}</td>`
        : '<td class="dm-code"></td>');
    bodyParts.push(
      '<tr class="dm-row-nonewline">' +
        cell(noFinalNewline.left) +
        (merge ? '<td class="dm-mgut"></td>' : '') +
        cell(noFinalNewline.right) +
        '</tr>'
    );
  }

  const colgroup = merge
    ? '<col class="dm-col-lineno" /><col class="dm-col-code" />' +
      '<col class="dm-col-mgut" />' +
      '<col class="dm-col-lineno" /><col class="dm-col-code" />'
    : '<col class="dm-col-lineno" /><col class="dm-col-code" />' +
      '<col class="dm-col-lineno" /><col class="dm-col-code" />';

  const histBtn = (kind, enabled) =>
    `<button type="button" class="dm-mop" data-hist="${kind}"` +
    ` title="${HIST_LABEL[kind]}" aria-label="${HIST_LABEL[kind]}"` +
    `${enabled ? '' : ' disabled'}>${HIST_ICON[kind]}</button>`;

  const thead = merge
    ? `<th colspan="2">${escapeHtml(opt.leftTitle)}</th>` +
      '<th class="dm-mgut" title="左 → 右 に取り込み / 取り消し・やり直し">' +
      '<div class="dm-merge-history">' +
      histBtn('undo', !!opt.canUndo) +
      histBtn('redo', !!opt.canRedo) +
      '</div></th>' +
      `<th colspan="2">${escapeHtml(opt.rightTitle)}(編集コラム)</th>`
    : `<th colspan="2">${escapeHtml(opt.leftTitle)}</th>` +
      `<th colspan="2">${escapeHtml(opt.rightTitle)}</th>`;

  return (
    `<div class="dm-file${merge ? ' dm-merge' : ''}"${
      merge ? ' tabindex="0"' : ''
    }${viewH}>` +
    '<div class="dm-file-header">' +
    `<span class="dm-file-title">${escapeHtml(opt.leftTitle)} → ${escapeHtml(
      opt.rightTitle
    )}</span>` +
    (merge ? singlelineRadios(singleline) : '') +
    '<span class="dm-file-stats">' +
    `<span class="dm-stat-added">+${stats.added}</span>` +
    `<span class="dm-stat-removed">-${stats.removed}</span>` +
    '</span></div>' +
    '<div class="dm-wrapper"><table class="dm-table">' +
    `<colgroup>${colgroup}</colgroup>` +
    `<thead><tr class="dm-colhead">${thead}</tr></thead>` +
    `<tbody>${bodyParts.join('')}</tbody>` +
    '</table></div>' +
    (merge ? `<div class="dm-hint">${mergeHint(singleline)}</div>` : '') +
    '</div>'
  );
}

/**
 * 差分データ + ビュー HTML 文字列を返す（DOM 非依存。SSR やテスト向け）。
 * @param {string} left
 * @param {string} right
 * @param {Partial<typeof DEFAULTS>} [options]
 * @returns {ReturnType<typeof computeRows> & { html: string }}
 */
// op ごとに編集コラムのどこを splice するか（applyMerge の実装と対応させる）。
function spliceRangeFor(hunk, op) {
  const len = hunk.aLines.length;
  if (op === 'overwrite') {
    return { at: hunk.bStart, removed: hunk.bEnd - hunk.bStart, inserted: len };
  }
  if (op === 'insert-above') return { at: hunk.bStart, removed: 0, inserted: len };
  if (op === 'insert-below') return { at: hunk.bEnd, removed: 0, inserted: len };
  if (op === 'delete') {
    return { at: hunk.bStart, removed: hunk.bEnd - hunk.bStart, inserted: 0 };
  }
  return null;
}

// 編集コラムの splice にあわせて、送り出し済みの行番号をずらす。
// 送り出した行そのものが消えた場合はその送り出しを取り消す。
function shiftAfterSplice(shifts, { at, removed, inserted }) {
  const delta = inserted - removed;
  const next = [];
  for (const s of shifts) {
    if (s.r < at) next.push(s);
    else if (s.r >= at + removed) next.push({ ...s, r: s.r + delta });
    // at..at+removed の範囲にあった行は消えたので、送り出しも落とす
  }
  return next;
}

function build(left, right, options = {}) {
  const opt = { ...DEFAULTS, ...options };
  const data = computeRows(left, right, opt.shifts);
  return { ...data, html: rowsToHtml(data, opt) };
}

/**
 * 指定要素へ side-by-side 差分ビューを描画する。
 *
 * `options.merge` が真なら、2 コラムの間に取り込み操作ボタン（→ ↗ ↘）と、
 * 操作列の見出しに取り消し / やり直しボタン（↶ ↷）を出す。ボタンを押すと
 * 編集コラムだけが更新され、差分を計算し直して再描画する。更新後の内容は
 * `options.onChange(newRight, { op })` と `handle.getMergedText()` で得られる。
 * `op` は 'overwrite' / 'insert-above' / 'insert-below' / 'undo' / 'redo'。
 *
 * @param {HTMLElement|string} target  描画先要素、または CSS セレクタ
 * @param {string} left   左コラム（変更前 / 参照用。書き換えない）
 * @param {string} right  編集コラム（変更後 / マージの編集対象）
 * @param {Partial<typeof DEFAULTS>} [options]
 * @returns {{
 *   el: HTMLElement,
 *   rows: import('../diff/align.js').Row[],
 *   stats: { added: number, removed: number },
 *   getMergedText: () => string,
 *   canUndo: () => boolean,
 *   canRedo: () => boolean,
 *   undo: () => boolean,
 *   redo: () => boolean,
 *   update: (left?: string, right?: string, options?: object) => object,
 *   destroy: () => void
 * }}
 */
function render(target, left, right, options = {}) {
  const el =
    typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) {
    throw new Error('render: 描画先が見つかりません: ' + String(target));
  }

  let opt = { ...DEFAULTS, ...options };
  let curLeft = String(left);
  let curRight = String(right);
  // ↓（左の行を 1 つ下へ送る）で送り出した行。右テキストと並ぶ状態として持つ
  let shifts = (opt.shifts || []).map((s) => ({ ...s }));
  let data = null;

  // マージの取り消し / やり直し用（編集コラム + 送り出しのスナップショット）
  const history = []; // 古い状態（古い順）
  const future = []; // やり直し用（新しい状態）
  const snapshot = () => ({ right: curRight, shifts: shifts.map((s) => ({ ...s })) });
  const restore = (s) => {
    curRight = s.right;
    shifts = s.shifts;
  };

  const paint = () => {
    // 再描画で中身ごと差し替わるとフォーカスが外れ、キー操作が効かなくなる。
    // 取り込みボタンを押した直後も続けて Ctrl+Z できるよう、控えて戻す。
    const hadFocus = el.contains(document.activeElement);
    data = build(curLeft, curRight, {
      ...opt,
      shifts,
      canUndo: history.length > 0,
      canRedo: future.length > 0,
    });
    el.innerHTML = data.html;
    if (hadFocus) el.querySelector('.dm-file')?.focus({ preventScroll: true });
  };

  const emit = (op) => {
    if (typeof opt.onChange === 'function') opt.onChange(curRight, { op });
  };

  // テキストを書き換える操作（overwrite / insert-above / insert-below / delete）。
  // 編集コラムの行が増減するので、送り出し済みの行番号もあわせてずらす。
  const applyOp = (hunk, op) => {
    history.push(snapshot());
    future.length = 0;
    const range = spliceRangeFor(hunk, op);
    curRight = applyMerge(curRight, hunk, op);
    if (range) shifts = shiftAfterSplice(shifts, range);
    paint();
    emit(op);
  };

  // ↓。テキストは変えず、この行の編集コラム側を「左コラムのどの行とも対応
  // しない独立した挿入行」として、送り出した左コラムの行の直前へ置くだけ。
  const applyShift = (hunk) => {
    history.push(snapshot());
    future.length = 0;
    shifts = shifts.concat([{ r: hunk.bStart, anchor: hunk.aStart }]);
    paint();
    emit('skip');
  };

  const doUndo = () => {
    if (!history.length) return false;
    future.push(snapshot());
    restore(history.pop());
    paint();
    emit('undo');
    return true;
  };

  const doRedo = () => {
    if (!future.length) return false;
    history.push(snapshot());
    restore(future.pop());
    paint();
    emit('redo');
    return true;
  };

  // 操作のあとはルートへフォーカスを戻す。ボタンは再描画で消えるので、
  // そのままだと続けて Ctrl+Z が押せなくなるため。
  const focusRoot = () => {
    el.querySelector('.dm-file')?.focus({ preventScroll: true });
  };

  const onClick = (e) => {
    if (!opt.merge) return;
    const btn = e.target.closest && e.target.closest('.dm-mop');
    if (!btn || btn.disabled) return;

    if (btn.dataset.hist === 'undo') {
      doUndo();
      focusRoot();
      return;
    }
    if (btn.dataset.hist === 'redo') {
      doRedo();
      focusRoot();
      return;
    }

    const group = btn.closest('.dm-merge-ops');
    if (!group) return;
    const hunk = opt.singleline
      ? toSingleLineHunks(data.rows)[Number(group.dataset.row)]
      : toHunks(data.rows)[Number(group.dataset.hunk)];
    if (!hunk) return;
    if (btn.dataset.op === 'skip') applyShift(hunk);
    else applyOp(hunk, btn.dataset.op);
    focusRoot();
  };

  // 見出しのラジオでマージ単位（まとめて / 1 行ごと）を切り替える。
  // 表示の粒度が変わるだけなので、取り込み履歴や ↓ の行送りはそのまま保つ。
  const setSingleline = (next) => {
    const v = !!next;
    if (!!opt.singleline === v) return;
    opt = { ...opt, singleline: v };
    paint();
  };
  const onChangeMode = (e) => {
    const r = e.target;
    if (!r || !r.classList || !r.classList.contains('dm-sl')) return;
    setSingleline(r.value === 'line');
  };

  // Ctrl+Z で取り消し、Ctrl+Shift+Z / Ctrl+Y でやり直し（merge のときだけ）。
  // ビューにフォーカスがあるときだけ効くので、ページの他の入力欄には影響しない。
  const onKeyDown = (e) => {
    if (!opt.merge || !opt.hotkeys) return;
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const z = e.key === 'z' || e.key === 'Z';
    const y = e.key === 'y' || e.key === 'Y';
    if (z && !e.shiftKey) {
      e.preventDefault();
      doUndo();
    } else if ((z && e.shiftKey) || y) {
      e.preventDefault();
      doRedo();
    }
  };

  el.addEventListener('click', onClick);
  el.addEventListener('change', onChangeMode);
  el.addEventListener('keydown', onKeyDown);
  paint();

  const handle = {
    el,
    get rows() {
      return data.rows;
    },
    get stats() {
      return data.stats;
    },
    getMergedText() {
      return curRight;
    },
    canUndo() {
      return history.length > 0;
    },
    canRedo() {
      return future.length > 0;
    },
    undo: doUndo,
    redo: doRedo,
    get singleline() {
      return !!opt.singleline;
    },
    setSingleline,
    update(nextLeft, nextRight, nextOptions) {
      if (nextLeft != null) curLeft = String(nextLeft);
      if (nextRight != null) curRight = String(nextRight);
      if (nextOptions) opt = { ...opt, ...nextOptions };
      // 文書が差し替わったら取り消し履歴と送り出しはリセット
      shifts = (opt.shifts || []).map((s) => ({ ...s }));
      history.length = 0;
      future.length = 0;
      paint();
      return handle;
    },
    destroy() {
      el.removeEventListener('click', onClick);
      el.removeEventListener('change', onChangeMode);
      el.removeEventListener('keydown', onKeyDown);
      el.innerHTML = '';
    },
  };
  return handle;
}


// ===== src/render/three-column.js =====
// 3 カラム（b / a / c、中心は a）差分ビューの描画。
//
// 用語（UI 表示と合わせる）:
//   左コラム   … b。画面の左に置く
//   編集コラム … a。画面の中心に置く。マージの編集対象はこれだけ
//   右コラム   … c。画面の右に置く
// 左右のうち片方が「アクティブ」で、編集コラムとの差分を色付きで見せる。
// コード内の a / b / c と、ハンクの aLines / bLines（= 編集コラム /
// アクティブ側）はこの対応。
//
// b と c のどちらか一方がアクティブで、a との差分を色付きの行として見せる。
// 非アクティブ側は a の行に合わせて並べるだけで、差分は a セルの枠線寄りの
// 太いマーカーで示す。アクティブの切り替えは左右キー、または見出しのクリック。
//
// 3 段階の API は 2 文書版（side-by-side.js）と同じ形:
//   compute3() … 差分データのみ（DOM 非依存 / Node でも動作）
//   build3()   … 差分データ + ビュー HTML 文字列（DOM 非依存）
//   render3()  … 指定要素へ描画し、操作ハンドルを返す（要 DOM）


// 名前は side-by-side.js と衝突しないようにしてある（配布版は単純連結のため）
const DEFAULTS3 = {
  aTitle: '文書 A',
  bTitle: '文書 B',
  cTitle: '文書 C',
  active: 'b', // 既定でアクティブな外側文書
  inlineDiff: true, // a とアクティブ文書の変更行を語単位でハイライト
  hotkeys: true, // ← → でアクティブを切り替える
  // merge:true のとき、相違点のかたまりをまとめず行ごとに操作パネルを出す
  // （ボタンも → ↗ ↘ に加え ↓ x の 5 つになる）
  singleline: false,
  // singleline の ↓（アクティブ側の列を 1 つ下へ送る）で送り出した行。
  // { a: 対応なしにする編集コラムの行, anchor: 直前へ置くアクティブ側の行 }
  // （どちらも 0 起点）。アクティブ側ごとに別々なので render3 が b / c で
  // 分けて管理する。compute3()/build3() へ直接渡すこともできる
  shifts: [],
  // 表示エリアの高さ。'auto'（既定）は親要素が高さを持つ flex/grid 文脈なら
  // そこまで広がり（.dm3-wrapper だけスクロール）、そうでなければ内容なりに
  // 育つ（--dm-table-max-height が上限）。数値は px、文字列は任意の CSS 長さ
  // （例 '50vh'）として、その高さを上限に固定する
  viewH: 'auto',
};

const NO_NEWLINE_LABEL3 = '(末尾に改行なし)';

// 幅の下限（文字数）。非アクティブ列はここまで縮む（行番号＋先頭 6 文字）。
const MIN_OFF_CH = 6;
const CLIP_CH = 14; // これ以下なら折り返さず省略記号で切る

function isBlank3(split) {
  return split.lines.length === 1 && split.lines[0] === '';
}

// 等幅フォントでの見た目の桁数。CJK や全角記号は 2 桁として数える。
const WIDE_RE =
  /[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/;

/**
 * 1 行を表示するのに必要な桁数を数える。
 * @param {string} text
 * @returns {number}
 */
function displayWidth(text) {
  let w = 0;
  for (const ch of text) {
    if (ch === '\t') w += 4;
    else if (WIDE_RE.test(ch)) w += 2;
    else w += 1;
  }
  return w;
}

/** 文書全体で最も長い行の桁数。列幅の必要量の見積もりに使う。 */
function maxDisplayWidth(lines) {
  let m = 0;
  for (const line of lines) {
    const w = displayWidth(line);
    if (w > m) m = w;
  }
  return m;
}

/**
 * 3 文書の差分データを求める（DOM 非依存）。
 * @param {{a: string, b: string, c: string}} docs
 * @param {{active?: 'b'|'c'}} [options]
 */
function compute3(docs, options = {}) {
  const A = splitLines(String(docs.a ?? ''));
  const B = splitLines(String(docs.b ?? ''));
  const C = splitLines(String(docs.c ?? ''));
  const active = options.active === 'c' ? 'c' : 'b';
  const shifts = options.shifts || [];

  const r = alignThree(A.lines, B.lines, C.lines, active, shifts);

  // マージ用: 編集コラムとアクティブ側のハンク（取り込みの単位）。
  // singleline のときは行ごと、そうでなければ相違点のかたまりごと。
  // どちらも整列済みの行から起こすので、↓ の送り出しも織り込まれる。
  const activeHunks = options.merge
    ? options.singleline
      ? toSingleLineHunks3(r.rows, active)
      : toHunks(
          computeRows(
            String(docs.a ?? ''),
            String((active === 'c' ? docs.c : docs.b) ?? '')
          ).rows
        )
    : null;

  const lineCounts = { a: A.lines.length, b: B.lines.length, c: C.lines.length };
  // 折り返さずに表示するのに必要な桁数（列幅の配分に使う）
  const maxCols = {
    a: maxDisplayWidth(A.lines),
    b: maxDisplayWidth(B.lines),
    c: maxDisplayWidth(C.lines),
  };
  const noFinalNewline = {
    a: A.noFinalNewline && !isBlank3(A),
    b: B.noFinalNewline && !isBlank3(B),
    c: C.noFinalNewline && !isBlank3(C),
  };

  markFinalNewlineDiff(r, lineCounts, noFinalNewline);

  return { ...r, activeHunks, lineCounts, maxCols, noFinalNewline };
}

/**
 * 末尾改行の有無が a と食い違う場合、その最終行そのものが差分。
 * 2 文書版（side-by-side.js）と同じ扱いにする。
 *   - アクティブ文書と違う → 最終行を replace に格上げして色を付ける
 *   - 非アクティブ文書と違う → 最終行に replace のマーカーを立てる
 * どちらも統計に 1 件として数える。
 *
 * @param {{rows: Array, active: 'b'|'c', stats: object}} r
 * @param {{a:number,b:number,c:number}} lineCounts
 * @param {{a:boolean,b:boolean,c:boolean}} nfn
 */
function markFinalNewlineDiff(r, lineCounts, nfn) {
  const other = r.active === 'c' ? 'b' : 'c';

  // a の最終行と、その文書の最終行が同じ行に並んでいる行を末尾から探す
  const lastPairedRow = (key) => {
    for (let i = r.rows.length - 1; i >= 0; i--) {
      const row = r.rows[i];
      if (
        row.a &&
        row.a.lineNo === lineCounts.a &&
        row[key] &&
        row[key].lineNo === lineCounts[key]
      ) {
        return row;
      }
    }
    return null;
  };

  if (nfn[r.active] !== nfn.a) {
    const row = lastPairedRow(r.active);
    if (row && row.type === 'equal') {
      row.type = 'replace';
      r.stats.active.added += 1;
      r.stats.active.removed += 1;
    }
  }

  if (nfn[other] !== nfn.a) {
    const row = lastPairedRow(other);
    if (row && row.mark === null) {
      row.mark = 'replace';
      r.stats.inactive.added += 1;
      r.stats.inactive.removed += 1;
    }
  }
}

/** 1 カラム分（行番号 + コード）の <td> を作る。 */
function cells(side, role, opt) {
  const { codeHtml = null, mark = null, hidden = 0, filler = false } = opt ?? {};
  const noCls = `dm3-no dm3-no-${role}`;
  const codeCls = `dm3-code dm3-code-${role}`;

  if (side === null) {
    const extra = filler ? ' dm3-filler' : ' dm3-blank';
    const markCls = mark ? ` dm3-mark dm3-mark-${mark}` : '';
    return (
      `<td class="${noCls}${extra}"></td>` +
      `<td class="${codeCls}${extra}${markCls}">${codeHtml ?? ''}</td>`
    );
  }

  const markCls = mark ? ` dm3-mark dm3-mark-${mark}` : '';
  const more = hidden > 0 ? `<span class="dm3-more">…+${hidden}</span>` : '';
  // 本文を span で包む。非アクティブ列はこの span を省略記号で切り、
  // …+N バッジ（more）は切らずに残せるようにするため。
  const text = codeHtml ?? escapeHtml(side.text);
  return (
    `<td class="${noCls}">${side.lineNo}</td>` +
    `<td class="${codeCls}${markCls}"><span class="dm3-text">${text}</span>${more}</td>`
  );
}

const GUTTER = '<td class="dm3-gutter"></td>';

// ===== 3 文書マージ（3 文書比較の画面をベースに、アクティブ側だけ操作パネルを出す）
// 編集対象は編集コラム（中央）だけ。左コラム / 右コラムは書き換えない。 =====

// 取り込みボタンのアイコン。アクティブが左コラムなら編集コラムへ右向き、
// 右コラムなら左向き。
const MERGE3_ICON = {
  'b:overwrite':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10h12"/><path d="M10 5l5 5-5 5"/></svg>',
  'b:insert-above':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16 15 5"/><path d="M8 5h7v7"/></svg>',
  'b:insert-below':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4 15 15"/><path d="M8 15h7V8"/></svg>',
  'c:overwrite':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 10H5"/><path d="M10 5l-5 5 5 5"/></svg>',
  'c:insert-above':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 16 5 5"/><path d="M12 5H5v7"/></svg>',
  'c:insert-below':
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4 5 15"/><path d="M12 15H5V8"/></svg>',
  // ↓ x は singleline 専用。向きに意味が無いので b / c で同じ絵にする
  'b:skip': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 4v10"/><path d="M5 10l5 5 5-5"/></svg>',
  'c:skip': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 4v10"/><path d="M5 10l5 5 5-5"/></svg>',
  'b:delete': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l8 8"/><path d="M14 6l-8 8"/></svg>',
  'c:delete': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l8 8"/><path d="M14 6l-8 8"/></svg>',
};
const MERGE3_HIST = {
  undo:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6 4 10l4 4"/><path d="M4 10h8a4 4 0 0 1 0 8"/></svg>',
  redo:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6l4 4-4 4"/><path d="M16 10H8a4 4 0 0 0 0 8"/></svg>',
};
// マージ単位の切り替え（見出しに置くラジオ）。2 文書版と同じ見た目・同じ
// クラス（dm-sl-*）を使い、name はインスタンスごとに変える。
let SL3_SEQ = 0;
function singlelineRadios3(singleline) {
  const name = `dm3-sl-${(SL3_SEQ += 1)}`;
  const opt = (value, label, on) =>
    '<label class="dm-sl-opt">' +
    `<input type="radio" class="dm3-sl" name="${name}" value="${value}"` +
    `${on ? ' checked' : ''} />${label}</label>`;
  return (
    '<span class="dm-sl-group" role="radiogroup" aria-label="マージ単位">' +
    opt('hunk', 'まとめて', !singleline) +
    opt('line', '1 行ごと', singleline) +
    '</span>'
  );
}

const MERGE3_LABEL = {
  overwrite: '上書き(この相違点で編集コラムを置き換え)',
  'insert-above': '上に挿入(編集コラムの相違点の上へ追加)',
  'insert-below': '下に挿入(編集コラムの相違点の下へ追加)',
  skip: '下へ送る(編集コラムはそのままに、アクティブ側の行を 1 つ下へずらす)',
  delete: '削除(編集コラムのこの行を取り除く)',
};

/**
 * 相違点（ハンク）をアクティブ側から編集コラムへ取り込んだ、新しい編集コラムの
 * テキストを返す。hunk は整列済みの行から起こしたもの。書き換えるのは
 * 編集コラムだけ。
 * @param {string} aText  現在の編集コラムのテキスト
 * @param {{aStart:number,aEnd:number,bLines:string[]}} hunk
 * @param {'overwrite'|'insert-above'|'insert-below'|'delete'} op
 *   delete は取り込まずに編集コラムのその行を取り除く（singleline 向け）。
 *   ↓（下へ送る）はテキストを変えない別操作なので、ここには無い
 *   （`shifts` オプションで扱う）。
 * @returns {string}
 */
function applyMerge3(aText, hunk, op) {
  const r = splitLines(String(aText));
  const lines = r.lines.slice();
  const incoming = hunk.bLines; // ハンクの右側 = アクティブ側の行
  if (op === 'overwrite') {
    lines.splice(hunk.aStart, hunk.aEnd - hunk.aStart, ...incoming);
  } else if (op === 'insert-above') {
    lines.splice(hunk.aStart, 0, ...incoming);
  } else if (op === 'insert-below') {
    lines.splice(hunk.aEnd, 0, ...incoming);
  } else if (op === 'delete') {
    lines.splice(hunk.aStart, hunk.aEnd - hunk.aStart);
  } else {
    throw new Error('applyMerge3: 未知の操作: ' + String(op));
  }
  const joined = lines.join('\n');
  return r.noFinalNewline ? joined : joined + '\n';
}

/**
 * 整列済みの 3 文書行から、行ごとの取り込み単位（ハンク）を起こす。
 * 2 文書版の `toSingleLineHunks` に相当する singleline 用。
 *
 * @param {Array} rows   alignThree() の rows（↓ の送り出しも反映済み）
 * @param {'b'|'c'} active
 * @returns {Array<{aStart,aEnd,bStart,bEnd,aLines,bLines}|null>}
 *   rows と同じ長さ。equal 行と other-insert 行は null。
 */
function toSingleLineHunks3(rows, active) {
  const out = rows.map(() => null);
  let ai = 0; // 編集コラムの行（0 起点）
  let bi = 0; // アクティブ側の行（0 起点）

  rows.forEach((row, i) => {
    const aSide = row.a;
    const actSide = row[active];
    if (row.type === 'equal') {
      ai += 1;
      bi += 1;
      return;
    }
    // 非アクティブの挿入を知らせるだけの行は、どちらの行も消費しない
    if (!aSide && !actSide) return;

    const hunk = { aStart: ai, bStart: bi, aLines: [], bLines: [] };
    if (aSide) {
      hunk.aLines.push(aSide.text);
      ai += 1;
    }
    if (actSide) {
      hunk.bLines.push(actSide.text);
      bi += 1;
    }
    hunk.aEnd = ai;
    hunk.bEnd = bi;
    out[i] = hunk;
  });

  return out;
}

// singleline 版のアクティブ側操作列セル。行ごとに 5 ボタン（→ ↗ ↘ ↓ x）。
// side は 'b'（左コラム）/ 'c'（右コラム）。
function singleLineGutterCell3(side, hunk, rowIdx) {
  if (!hunk) return '<td class="dm3-gutter dm3-gutter-active"></td>';
  const canTake = hunk.bLines.length > 0; // 取り込む中身がある
  const canRemove = hunk.aLines.length > 0; // 編集コラムに消せる行がある
  // ↓ は編集コラムとアクティブ側が実際に対応している行にだけ意味がある
  const canShift = canTake && canRemove;
  const btn = (op, extra = '') =>
    `<button type="button" class="dm3-mop" data-op="${op}"` +
    ` title="${MERGE3_LABEL[op]}" aria-label="${MERGE3_LABEL[op]}"${extra}>` +
    `${MERGE3_ICON[side + ':' + op]}</button>`;
  return (
    '<td class="dm3-gutter dm3-gutter-active dm3-gutter-ops">' +
    `<div class="dm3-merge-ops" data-row="${rowIdx}">` +
    btn('overwrite', canTake ? '' : ' disabled') +
    btn('insert-above', canTake ? '' : ' disabled') +
    btn('insert-below', canTake ? '' : ' disabled') +
    btn('skip', canShift ? '' : ' disabled') +
    btn('delete', canRemove ? '' : ' disabled') +
    '</div></td>'
  );
}

// 各行がアクティブ側のどのハンクに属するか（先頭行かどうか）。other-insert は中立。
function rowActiveHunkInfo(rows) {
  const info = rows.map(() => null);
  let idx = -1;
  let inHunk = false;
  rows.forEach((row, i) => {
    const t = row.type;
    if (t === 'replace' || t === 'delete' || t === 'insert') {
      if (!inHunk) {
        idx += 1;
        inHunk = true;
        info[i] = { first: true, hunk: idx };
      } else {
        info[i] = { first: false, hunk: idx };
      }
    } else if (t === 'equal') {
      inHunk = false;
    }
    // other-insert（非アクティブの挿入）は中立
  });
  return info;
}

// アクティブ側の操作列セル（先頭行にだけ取り込みボタン）。side は 'b' | 'c'。
function mergeGutterCell3(side, hinfo, hunk) {
  if (!hinfo || !hinfo.first) return '<td class="dm3-gutter dm3-gutter-active"></td>';
  const canInsert = hunk && hunk.bLines.length > 0;
  const btn = (op, extra = '') =>
    `<button type="button" class="dm3-mop" data-op="${op}"` +
    ` title="${MERGE3_LABEL[op]}" aria-label="${MERGE3_LABEL[op]}"${extra}>` +
    `${MERGE3_ICON[side + ':' + op]}</button>`;
  return (
    '<td class="dm3-gutter dm3-gutter-active dm3-gutter-ops">' +
    `<div class="dm3-merge-ops" data-hunk="${hinfo.hunk}">` +
    btn('overwrite') +
    btn('insert-above', canInsert ? '' : ' disabled') +
    btn('insert-below', canInsert ? '' : ' disabled') +
    '</div></td>'
  );
}

/** 3 文書マージビューの HTML（= build3(docs, { merge: true }) の別名）。 */
function buildMerge3(docs, options = {}) {
  return build3(docs, { ...options, merge: true });
}


/** 差分データからビュー全体の HTML を組み立てる。 */
function rows3ToHtml(data, opt) {
  const { rows, active, stats, noFinalNewline } = data;
  const other = active === 'c' ? 'b' : 'c';
  const merge = !!opt.merge;
  // viewH: 'auto'（既定）なら何もしない。数値/文字列なら --dm-table-max-height を
  // このインスタンスだけ上書きし、表示エリアの高さ上限を固定する。
  const viewH =
    opt.viewH == null || opt.viewH === 'auto'
      ? ''
      : ` style="--dm-table-max-height: ${escapeHtml(
          typeof opt.viewH === 'number' ? `${opt.viewH}px` : String(opt.viewH)
        )}"`;
  const singleline = merge && !!opt.singleline;
  const hinfos = merge && !singleline ? rowActiveHunkInfo(rows) : null;
  const activeHunks = data.activeHunks || [];
  const body = [];

  // アクティブ側の操作列セル（merge のときだけ）。位置は active によって左 / 右。
  // singleline なら行ごと、そうでなければ相違点のかたまりの先頭行だけに出す。
  const activeGut = (i) => {
    if (!merge) return GUTTER;
    if (singleline) return singleLineGutterCell3(active, activeHunks[i], i);
    return mergeGutterCell3(
      active,
      hinfos[i],
      hinfos[i] ? activeHunks[hinfos[i].hunk] : null
    );
  };

  rows.forEach((row, i) => {
    const aSide = row.a;
    const actSide = row[active];
    const offSide = row[other];

    // a とアクティブの変更行を語単位ハイライト
    let aHtml = null;
    let actHtml = null;
    if (row.type === 'replace' && opt.inlineDiff && aSide && actSide) {
      const d = inlineDiff(aSide.text, actSide.text);
      aHtml = d.leftHtml;
      actHtml = d.rightHtml;
    }

    // 非アクティブの変更行も語単位ハイライト（色は CSS 側で青系にする）
    let offHtml = null;
    if (row.mark === 'replace' && opt.inlineDiff && aSide && offSide) {
      offHtml = inlineDiff(aSide.text, offSide.text).rightHtml;
    }

    // a とアクティブの間ではフィラー（斜線）を出す。非アクティブ側は出さない。
    const aFiller = aSide === null && row.type !== 'other-insert';
    const actFiller = actSide === null && row.type !== 'other-insert';

    const aCells = cells(aSide, 'a', {
      codeHtml: aHtml,
      mark: row.mark,
      filler: aFiller,
    });
    const actCells = cells(actSide, 'act', { codeHtml: actHtml, filler: actFiller });
    const offCells = cells(offSide, 'off', {
      codeHtml: offHtml,
      hidden: row.hiddenCount,
    });

    const left = active === 'b' ? actCells : offCells;
    const right = active === 'b' ? offCells : actCells;

    // 操作パネルはアクティブ側だけ。b が左 → gut1 が active、c が右 → gut2 が active
    const gut1 = active === 'b' ? activeGut(i) : GUTTER;
    const gut2 = active === 'c' ? activeGut(i) : GUTTER;

    const omark = row.mark ? ` dm3-omark-${row.mark}` : '';
    body.push(
      `<tr class="dm3-row dm3-row-${row.type}${omark}">` +
        left + gut1 + aCells + gut2 + right +
        '</tr>'
    );
  });

  if (noFinalNewline.a || noFinalNewline.b || noFinalNewline.c) {
    const nl = (show) =>
      '<td class="dm3-no"></td>' +
      `<td class="dm3-code${show ? ' dm3-nonewline' : ''}">${
        show ? NO_NEWLINE_LABEL3 : ''
      }</td>`;
    body.push(
      '<tr class="dm3-row dm3-row-nonewline">' +
        nl(noFinalNewline.b) + GUTTER + nl(noFinalNewline.a) + GUTTER + nl(noFinalNewline.c) +
        '</tr>'
    );
  }

  const t = { a: opt.aTitle, b: opt.bTitle, c: opt.cTitle };
  // アクティブ／非アクティブは見出しの背景色で示す（バッジは出さない）
  const head = (key) => {
    const roleCls =
      key === 'a' ? 'dm3-th-a' : key === active ? 'dm3-th-act' : 'dm3-th-off';
    const hint = key === 'a' ? '' : ' data-side="' + key + '"';
    return `<th colspan="2" class="dm3-th ${roleCls}"${hint}>${escapeHtml(
      t[key]
    )}</th>`;
  };

  // 操作列の見出し。アクティブ側には取り消し / やり直しボタンを置く。
  const gutHead = (key) => {
    if (!merge || key !== active) return '<th class="dm3-gutter"></th>';
    const hbtn = (kind, enabled) =>
      `<button type="button" class="dm3-mop" data-hist="${kind}"` +
      ` title="${
        kind === 'undo' ? '取り消し(Ctrl+Z)' : 'やり直し(Ctrl+Shift+Z / Ctrl+Y)'
      }"${enabled ? '' : ' disabled'}>` +
      `${MERGE3_HIST[kind]}</button>`;
    return (
      '<th class="dm3-gutter dm3-gutter-active"><div class="dm3-merge-history">' +
      hbtn('undo', !!opt.canUndo) +
      hbtn('redo', !!opt.canRedo) +
      '</div></th>'
    );
  };

  const s = stats.active;
  const si = stats.inactive;

  return (
    `<div class="dm3 dm3-active-${active}${merge ? ' dm3-merge' : ''}${
      singleline ? ' dm3-singleline' : ''
    }" tabindex="0"${viewH}>` +
    '<div class="dm3-header">' +
    `<span class="dm3-title">${escapeHtml(t.a)}${
      merge ? '(編集コラム)に ' : ' を中心に '
    }${escapeHtml(t[active])}${merge ? ' から取り込み中' : ' と比較中'}</span>` +
    (merge ? singlelineRadios3(singleline) : '') +
    '<span class="dm3-stats">' +
    `<span class="dm3-stat-added">+${s.added}</span>` +
    `<span class="dm3-stat-removed">-${s.removed}</span>` +
    `<span class="dm3-stat-off">(${escapeHtml(t[other])}: +${si.added} -${
      si.removed
    })</span>` +
    '</span></div>' +
    '<div class="dm3-wrapper"><table class="dm3-table"><colgroup>' +
    '<col class="dm3-col-no" /><col class="dm3-col-code dm3-col-b" />' +
    `<col class="dm3-col-gut${merge && active === 'b' ? ' dm3-col-gut-active' : ''}" />` +
    '<col class="dm3-col-no" /><col class="dm3-col-code dm3-col-a" />' +
    `<col class="dm3-col-gut${merge && active === 'c' ? ' dm3-col-gut-active' : ''}" />` +
    '<col class="dm3-col-no" /><col class="dm3-col-code dm3-col-c" />' +
    '</colgroup><thead><tr class="dm3-colhead">' +
    head('b') + gutHead('b') + head('a') + gutHead('c') + head('c') +
    '</tr></thead>' +
    `<tbody>${body.join('')}</tbody></table></div>` +
    `<div class="dm3-hint">${
      merge
        ? '操作ボタンで相違点を編集コラムへ取り込み(→ 上書き / ↗ 上に挿入 / ↘ 下に挿入' +
          (singleline ? ' / ↓ 下へ送る / x 削除' : '') +
          ')。↶(Ctrl+Z)取り消し ↷(Ctrl+Shift+Z)やり直し。見出しのクリックか左右キーでアクティブな比較文書を切り替え。編集単位を見出しの「まとめて」と「1 行ごと」で切り替え。'
        : '左右キー、または見出しのクリックで比較する文書を切り替え'
    }</div>` +
    '</div>'
  );
}

// applyMerge3 が編集コラムのどこを splice するか（実装と対応させる）。
function spliceRange3For(hunk, op) {
  const len = hunk.bLines.length;
  if (op === 'overwrite') {
    return { at: hunk.aStart, removed: hunk.aEnd - hunk.aStart, inserted: len };
  }
  if (op === 'insert-above') return { at: hunk.aStart, removed: 0, inserted: len };
  if (op === 'insert-below') return { at: hunk.aEnd, removed: 0, inserted: len };
  if (op === 'delete') {
    return { at: hunk.aStart, removed: hunk.aEnd - hunk.aStart, inserted: 0 };
  }
  return null;
}

// 編集コラムの splice にあわせて、送り出し済みの行番号をずらす。
// 送り出した行そのものが消えた場合はその送り出しを取り消す。
function shiftAfterSplice3(list, { at, removed, inserted }) {
  const delta = inserted - removed;
  const next = [];
  for (const s of list) {
    if (s.a < at) next.push(s);
    else if (s.a >= at + removed) next.push({ ...s, a: s.a + delta });
  }
  return next;
}

/**
 * 差分データ + ビュー HTML 文字列を返す（DOM 非依存）。
 * @param {{a: string, b: string, c: string}} docs
 * @param {Partial<typeof DEFAULTS3>} [options]
 */
function build3(docs, options = {}) {
  const opt = { ...DEFAULTS3, ...options };
  const data = compute3(docs, opt);
  return { ...data, html: rows3ToHtml(data, opt) };
}

/** テーブルの等幅フォントでの 1 文字幅を測る。 */

function measureCharWidth(table) {
  const probe = document.createElement('span');
  probe.textContent = '0'.repeat(20);
  probe.style.cssText =
    'position:absolute;visibility:hidden;white-space:pre;left:-9999px;';
  const cs = getComputedStyle(table);
  probe.style.font = cs.font || `${cs.fontSize} ${cs.fontFamily}`;
  document.body.appendChild(probe);
  const w = probe.getBoundingClientRect().width / 20;
  probe.remove();
  return w > 0 ? w : 7.5;
}

/**
 * 3 カラムの幅を決める。
 *
 * 各文書の「折り返さずに表示するのに必要な幅」を内容から見積もり、
 *   - 3 列とも 1/3 ずつで足りる → 等幅
 *   - 中心とアクティブが 1/3 では足りない → その分だけ非アクティブ列を縮めて回す
 * とする。非アクティブ列の下限は行番号＋先頭 6 文字。横スクロールは出さない。
 *
 * 折り返しが始まってから縮めるのでは遅いので、必要幅を先に見積もって配分する。
 */
function applyWidths(root) {
  const wrapper = root.querySelector('.dm3-wrapper');
  const table = root.querySelector('.dm3-table');
  if (!wrapper || !table) return;

  const total = wrapper.clientWidth;
  if (total <= 0) return;

  const charW = measureCharWidth(table);
  const digits = String(root.dataset.maxLineNo || '999').length;
  const noW = Math.ceil(charW * digits + 16);
  const cellPad = 18; // .dm3-code の左右パディング + 余白

  const avail = total - noW * 3;
  if (avail <= 0) return;

  const active = root.classList.contains('dm3-active-c') ? 'c' : 'b';
  const off = active === 'b' ? 'c' : 'b';

  // 内容から見積もった必要幅（px）
  const need = (key) =>
    charW * Number(root.dataset['need' + key.toUpperCase()] || 0) + cellPad;

  const third = avail / 3;
  const offMin = Math.min(third, charW * MIN_OFF_CH + cellPad);
  // 中心とアクティブは同じ幅にそろえるので、必要幅は大きい方に合わせる
  const pairNeed = Math.max(need('a'), need(active));

  // 中心とアクティブに必要な分を先に確保し、残りを非アクティブへ。
  // ただし非アクティブは 1/3 を超えず、下限も割らない。
  const offW = Math.min(third, Math.max(offMin, avail - pairNeed * 2));
  const pairW = Math.max(0, avail - offW) / 2;

  const cols = {
    b: root.querySelector('.dm3-col-b'),
    a: root.querySelector('.dm3-col-a'),
    c: root.querySelector('.dm3-col-c'),
  };

  for (const el of root.querySelectorAll('.dm3-col-no')) {
    el.style.width = `${noW}px`;
  }
  if (cols.a) cols.a.style.width = `${pairW}px`;
  if (cols[active]) cols[active].style.width = `${pairW}px`;
  if (cols[off]) cols[off].style.width = `${offW}px`;

  // 折り返す余地が無いほど狭ければ、非アクティブ列は省略記号で切る
  root.classList.toggle('dm3-clip', offW < charW * CLIP_CH + cellPad);
}

/**
 * 指定要素へ 3 カラム差分ビューを描画する。
 *
 * @param {HTMLElement|string} target 描画先要素、または CSS セレクタ
 * @param {{a: string, b: string, c: string}} docs 3 文書。a が編集コラム
 * @param {Partial<typeof DEFAULTS3>} [options]
 * @returns {{
 *   el: HTMLElement,
 *   get rows: Row3[],
 *   get stats: object,
 *   get active: 'b'|'c',
 *   setActive: (side: 'b'|'c') => void,
 *   toggle: () => void,
 *   update: (docs: object, options?: object) => void,
 *   destroy: () => void
 * }}
 */
function render3(target, docs, options = {}) {
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) {
    throw new Error('render3: 描画先が見つかりません: ' + String(target));
  }

  let opt = { ...DEFAULTS3, ...options };
  let current = { a: docs.a ?? '', b: docs.b ?? '', c: docs.c ?? '' };
  let data = null;

  // 3 文書マージ: 編集コラムの編集履歴（取り消し / やり直し）
  const merge = !!opt.merge;
  const history = [];
  const future = [];
  // ↓ で送り出した行。anchor はアクティブ側の行番号なので、左コラム /
  // 右コラムのどちらがアクティブかで意味が変わる。そのため b / c で分ける
  let shifts = { b: [], c: [] };
  for (const sh of opt.shifts || []) shifts[opt.active === 'c' ? 'c' : 'b'].push({ ...sh });
  const snapshot = () => ({
    a: current.a,
    shifts: { b: shifts.b.map((x) => ({ ...x })), c: shifts.c.map((x) => ({ ...x })) },
  });
  const restore = (s) => {
    current = { ...current, a: s.a };
    shifts = s.shifts;
  };

  const relayout = () => {
    const root = el.querySelector('.dm3');
    if (root) applyWidths(root);
  };

  const paint = () => {
    // 再描画で .dm3 ごと差し替わるとフォーカスが外れ、キー操作が効かなくなる。
    // 取り込みボタンを押した直後も続けて Ctrl+Z できるよう、控えて戻す。
    const hadFocus = el.contains(document.activeElement);
    data = build3(current, {
      ...opt,
      shifts: shifts[opt.active === 'c' ? 'c' : 'b'],
      canUndo: history.length > 0,
      canRedo: future.length > 0,
    });
    el.innerHTML = data.html;
    const root = el.querySelector('.dm3');
    if (!root) return;
    if (hadFocus) root.focus({ preventScroll: true });
    // マージビューは固定レイアウト（CSS 任せ）。動的な列幅配分はしない。
    if (merge) return;
    const m = data.lineCounts;
    root.dataset.maxLineNo = String(Math.max(m.a, m.b, m.c));
    // 内容から見積もった必要桁数を applyWidths へ渡す
    root.dataset.needA = String(data.maxCols.a);
    root.dataset.needB = String(data.maxCols.b);
    root.dataset.needC = String(data.maxCols.c);
    applyWidths(root);
    // フォントの読み込み完了後にずれることがあるので、次のフレームでもう一度
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(relayout);
  };

  const emitChange = (op) => {
    if (typeof opt.onChange === 'function') opt.onChange(current.a, { op });
  };
  const doUndo = () => {
    if (!history.length) return false;
    future.push(snapshot());
    restore(history.pop());
    paint();
    emitChange('undo');
    return true;
  };
  const doRedo = () => {
    if (!future.length) return false;
    history.push(snapshot());
    restore(future.pop());
    paint();
    emitChange('redo');
    return true;
  };

  const setActive = (side) => {
    const next = side === 'c' ? 'c' : 'b';
    if (next === opt.active) return;
    // 再描画で .dm3 ごと差し替わるため、フォーカスの有無を先に控えて戻す。
    // これをしないと 1 回切り替えた時点でキー操作が効かなくなる。
    const hadFocus = el.contains(document.activeElement);
    opt = { ...opt, active: next };
    paint();
    if (hadFocus) {
      el.querySelector('.dm3')?.focus({ preventScroll: true });
    }
  };

  const onKeyDown = (e) => {
    if (!opt.hotkeys) return;
    // Ctrl+Z で取り消し、Ctrl+Shift+Z / Ctrl+Y でやり直し（merge のときだけ）
    if ((e.ctrlKey || e.metaKey) && !e.altKey) {
      const z = e.key === 'z' || e.key === 'Z';
      const y = e.key === 'y' || e.key === 'Y';
      if (!merge || (!z && !y)) return;
      e.preventDefault();
      if (z && !e.shiftKey) doUndo();
      else doRedo();
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setActive('b');
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setActive('c');
    }
  };

  const onClick = (e) => {
    if (merge) {
      const btn = e.target.closest?.('.dm3-mop');
      if (btn && !btn.disabled) {
        // 操作のあとはルートへフォーカスを戻す。ボタンは再描画で消えるので、
        // そのままだと続けて Ctrl+Z が押せなくなるため。
        const focusRoot = () => {
          el.querySelector('.dm3')?.focus({ preventScroll: true });
        };
        if (btn.dataset.hist === 'undo') {
          doUndo();
          focusRoot();
          return;
        }
        if (btn.dataset.hist === 'redo') {
          doRedo();
          focusRoot();
          return;
        }
        const group = btn.closest('.dm3-merge-ops');
        if (!group) return;
        // singleline は行ごと（data-row）、そうでなければハンクごと（data-hunk）
        const idx = Number(
          opt.singleline ? group.dataset.row : group.dataset.hunk
        );
        const hunk = (data.activeHunks || [])[idx];
        if (!hunk) return;
        const side = opt.active === 'c' ? 'c' : 'b';
        history.push(snapshot());
        future.length = 0;
        if (btn.dataset.op === 'skip') {
          // ↓ は編集コラムのテキストを変えない。アクティブ側の列を 1 つ下へ
          // 送る（＝編集コラムのこの行を対応なしにする）だけ。
          shifts = {
            ...shifts,
            [side]: shifts[side].concat([{ a: hunk.aStart, anchor: hunk.bStart }]),
          };
        } else {
          const range = spliceRange3For(hunk, btn.dataset.op);
          current = { ...current, a: applyMerge3(current.a, hunk, btn.dataset.op) };
          // 編集コラムのテキストが動いたので、送り出し済みの行番号も追従させる
          if (range) {
            shifts = {
              b: shiftAfterSplice3(shifts.b, range),
              c: shiftAfterSplice3(shifts.c, range),
            };
          }
        }
        paint();
        emitChange(side + ':' + btn.dataset.op);
        focusRoot();
        return;
      }
      // 操作ボタン以外のクリックなら、見出しクリックでの切り替えへフォールスルーする
    }
    const th = e.target.closest?.('.dm3-th[data-side]');
    if (th) setActive(th.dataset.side);
  };

  // 見出しのラジオでマージ単位（まとめて / 1 行ごと）を切り替える。
  const setSingleline = (next) => {
    const v = !!next;
    if (!!opt.singleline === v) return;
    const hadFocus = el.contains(document.activeElement);
    opt = { ...opt, singleline: v };
    paint();
    if (hadFocus) el.querySelector('.dm3')?.focus({ preventScroll: true });
  };
  const onChangeMode = (e) => {
    const r = e.target;
    if (!r || !r.classList || !r.classList.contains('dm3-sl')) return;
    setSingleline(r.value === 'line');
  };

  el.addEventListener('keydown', onKeyDown);
  el.addEventListener('click', onClick);
  el.addEventListener('change', onChangeMode);

  let ro = null;
  if (typeof ResizeObserver === 'function') {
    ro = new ResizeObserver(relayout);
    ro.observe(el);
  }
  // ResizeObserver が無い環境や、通知が間引かれた場合の保険
  const onWinResize = () => relayout();
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', onWinResize);
  }

  paint();

  return {
    el,
    get rows() {
      return data.rows;
    },
    get stats() {
      return data.stats;
    },
    get active() {
      return opt.active;
    },
    setActive,
    relayout, // 列幅を計算し直す（親要素の幅を変えた直後などに呼ぶ）
    // 3 文書マージ用（merge:true のとき）
    getMergedText() {
      return current.a;
    },
    canUndo() {
      return history.length > 0;
    },
    canRedo() {
      return future.length > 0;
    },
    undo: doUndo,
    redo: doRedo,
    get singleline() {
      return !!opt.singleline;
    },
    setSingleline,
    toggle() {
      setActive(opt.active === 'b' ? 'c' : 'b');
    },
    update(nextDocs, nextOptions) {
      current = { ...current, ...(nextDocs ?? {}) };
      if (nextOptions) opt = { ...opt, ...nextOptions };
      shifts = { b: [], c: [] };
      history.length = 0;
      future.length = 0;
      paint();
    },
    destroy() {
      el.removeEventListener('keydown', onKeyDown);
      el.removeEventListener('click', onClick);
      el.removeEventListener('change', onChangeMode);
      if (typeof window !== 'undefined') {
        window.removeEventListener('resize', onWinResize);
      }
      if (ro) ro.disconnect();
      el.innerHTML = '';
    },
  };
}


// ===== src/diffmerge.js =====
// diffmerge 公開 API エントリポイント。
//
// 他アプリへの組み込みは、このモジュール（開発版）または dist/ の配布版
// （単一ファイル）から下記の関数だけを使えばよい。内部モジュール構成
// （src/diff/*, src/render/*）へ直接依存しないこと。
//
// 開発版:   import { render } from './src/diffmerge.js'
// 配布版:   import { render } from './dist/diffmerge.esm.js'
//           <script src="dist/diffmerge.umd.js"> → window.DiffMerge.render
//
// 2 文書は compare / build / render、3 文書は compare3 / build3 / render3。
//
// 用語（UI 表示と合わせる）:
//   2 文書 … 左コラム（参照）/ 編集コラム（マージの編集対象）
//   3 文書 … 左コラム（b）/ 編集コラム（a・中央）/ 右コラム（c）


/** ライブラリのバージョン。build.py がこの値を dist の banner に埋め込む。 */
const version = '1.1.1';

/**
 * 2 文書を比較し、差分データのみを返す（DOM 非依存 / Node 可）。
 * ビューを描画せず、行ペア列と統計だけが欲しいときに使う。
 *
 * @param {string} left   左コラム（変更前 / 参照用）
 * @param {string} right  編集コラム（変更後 / マージの編集対象）
 * @param {{ shifts?: Array<{r: number, anchor: number}> }} [options]
 *   shifts は singleline マージの ↓（左コラムの行を 1 つ下へ送る）で送り出した行。
 *   r = 編集コラムの行（0 起点）、anchor = その直前へ置く左コラムの行（0 起点）
 * @returns {{
 *   rows: Array<{
 *     type: 'equal'|'replace'|'delete'|'insert',
 *     left:  { lineNo: number, text: string } | null,
 *     right: { lineNo: number, text: string } | null
 *   }>,
 *   stats: { added: number, removed: number },
 *   noFinalNewline: { left: boolean, right: boolean }
 * }}
 */
function compare(left, right, options = {}) {
  return computeRows(left, right, options.shifts);
}

// build:  ビュー HTML 文字列を返す（DOM 非依存。サーバーサイド生成やテスト向け）
// render: 指定要素へ描画し、update() / destroy() を持つハンドルを返す（要 DOM）
//         options.merge:true で 2 コラムの間に取り込み操作ボタン（→ ↗ ↘）を出す。
//         options.singleline:true にすると複数行のかたまりをまとめず行ごとに
//         操作パネルを出す（ボタンも → ↗ ↘ ↓ x の 5 つになる）
// toHunks / toSingleLineHunks / applyMerge: マージを自前で組み立てるとき用（DOM 非依存）

/**
 * 3 文書（b / a / c、中心は a）を比較し、差分データのみを返す。
 * 表示は左コラム（b）・編集コラム（a）・右コラム（c）の順。左右のうち一方が
 * アクティブで、編集コラムとの差分を色付き行で示す。非アクティブ側は
 * 編集コラムの行に合わせて並べ、差分は mark で知らせる。
 *
 * @param {{a: string, b: string, c: string}} docs 3 文書。a が編集コラム
 * @param {{active?: 'b'|'c'}} [options] 既定のアクティブは 'b'
 * @returns {{
 *   rows: Array<{
 *     type: 'equal'|'replace'|'delete'|'insert'|'other-insert',
 *     a: { lineNo: number, text: string } | null,
 *     b: { lineNo: number, text: string } | null,
 *     c: { lineNo: number, text: string } | null,
 *     mark: 'insert'|'delete'|'replace'|null,
 *     hiddenCount: number
 *   }>,
 *   active: 'b'|'c',
 *   stats: {
 *     active: { added: number, removed: number },
 *     inactive: { added: number, removed: number }
 *   },
 *   lineCounts: { a: number, b: number, c: number },
 *   noFinalNewline: { a: boolean, b: boolean, c: boolean }
 * }}
 */
function compare3(docs, options = {}) {
  return compute3(docs, options);
}

// build3:  3 カラムのビュー HTML 文字列を返す（DOM 非依存）
// render3: 指定要素へ描画し、setActive() / toggle() / update() / destroy() を返す
//          options.merge:true で 左 / 右コラムから編集コラムへ取り込むマージビューになる
// buildMerge3 / applyMerge3: 3 文書マージを自前で組み立てるとき用（DOM 非依存）

/**
 * 低レベル関数群（上級者向け・準公開）。
 * 通常の組み込みでは compare / render（3 文書なら compare3 / render3）で足りる。
 */
const lowlevel = {
  myersDiff, // 任意の要素列に対する Myers O(ND) 差分
  alignLines, // 行差分 → side-by-side 用の行ペア列
  inlineDiff, // 1 行ペアの語単位差分（<del>/<ins> 付き HTML）
  splitLines, // テキスト → 行配列（改行正規化・末尾改行判定）
  splitWords, // 1 行 → 単語トークン配列（CJK は 1 文字単位）
  escapeHtml, // HTML 特殊文字のエスケープ
  displayWidth, // 等幅フォントでの見た目の桁数（CJK は 2 桁）
};

/**
 * まとめてインポートしたい利用者向けの名前空間オブジェクト。
 * `import DiffMerge from './src/diffmerge.js'` で default として受け取れる。
 */
const DiffMerge = {
  version,
  compare,
  build,
  render,
  toHunks,
  toSingleLineHunks,
  applyMerge,
  compare3,
  build3,
  render3,
  buildMerge3,
  applyMerge3,
  lowlevel,
};


  return DiffMerge;
});
