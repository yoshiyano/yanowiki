// URL のハッシュとカレントフォルダの行き来。
// 戻る・進むはブラウザの履歴（history）に任せ、自前の履歴は持たない（2 つ持つと食い違う）。
// ただし「このページの中で何歩目か」だけを history.state に書き、最初の場所で［戻る］を押して
// ページの外へ出てしまわないようにする。

import { parseHash, formatHash } from "./location.js";

export function createRouter(store) {
  let current = 0;  // いま何歩目か
  let maxIndex = 0; // 進める先があるか。再読み込みすると分からなくなるので、そのときは進めない扱い

  function stateIndex() {
    const st = history.state;
    return st && typeof st.webfiledirIndex === "number" ? st.webfiledirIndex : null;
  }

  function apply() {
    const i = stateIndex();
    if (i == null) {
      // 手でハッシュを打ち替えたとき。直前の場所から 1 歩進んだものとして記す
      current += 1;
      history.replaceState({ webfiledirIndex: current }, "");
    } else {
      current = i;
    }
    maxIndex = Math.max(maxIndex, current);
    store.set({ location: parseHash(location.hash), canBack: current > 0, canForward: current < maxIndex });
  }

  return {
    start() {
      // 最初に開いた場所（ブックマークや再読み込み）。記録が無ければ 0 歩目
      const i = stateIndex();
      current = i == null ? 0 : i;
      if (i == null) history.replaceState({ webfiledirIndex: 0 }, "");
      maxIndex = current;
      window.addEventListener("popstate", apply);
      store.set({ location: parseHash(location.hash), canBack: current > 0, canForward: false });
    },
    /** 場所を移る。今と同じ場所なら履歴を増やさない。 */
    go(mount, path, { replace = false, trash = false } = {}) {
      const hash = formatHash(mount, path, trash);
      if (hash === location.hash) return false;
      const i = replace ? current : current + 1;
      history[replace ? "replaceState" : "pushState"]({ webfiledirIndex: i }, "", hash);
      current = i;
      maxIndex = i; // 新しく進んだら、その先の履歴は消える
      store.set({ location: parseHash(hash), canBack: current > 0, canForward: false });
      return true;
    },
    back() {
      if (current > 0) history.back();
    },
    forward() {
      if (current < maxIndex) history.forward();
    },
  };
}

/**
 * 画面の中だけで履歴を持つ（二画面モードの右の画面が使う）。使いかたは createRouter と同じ。
 * URL のハッシュは 1 つしかなく左の画面が使うので、右の画面は自分の戻る・進むを持ち、
 * 今の場所を sessionStorage に覚える（再読み込みで同じ場所に戻る。ブックマークには入らない）。
 * fallback() は覚えた場所が無いときの最初の場所を返す。initial があれば、覚えた場所より先にそこから始める
 * （フォルダを「隣の画面で開く」で、この画面を作ったとき）。
 */
export function createMemoryRouter(store, { storageKey, fallback, initial = null }) {
  const stack = [];
  let index = -1;
  const hashOf = (l) => formatHash(l.mount, l.path, l.trash);

  function publish() {
    const loc = stack[index] || null;
    store.set({ location: loc, canBack: index > 0, canForward: index < stack.length - 1 });
    try {
      if (loc) sessionStorage.setItem(storageKey, hashOf(loc));
    } catch {
      // 覚えられなくても動く
    }
  }

  return {
    start() {
      let saved = null;
      try {
        saved = parseHash(sessionStorage.getItem(storageKey) || "");
      } catch {
        saved = null;
      }
      const first = initial || saved || fallback();
      if (!first) return;
      stack.push(first);
      index = 0;
      publish();
    },
    go(mount, path, { replace = false, trash = false } = {}) {
      const next = parseHash(formatHash(mount, path, trash));
      if (stack[index] && hashOf(stack[index]) === hashOf(next)) return false;
      if (replace && index >= 0) {
        stack[index] = next;
      } else {
        stack.splice(index + 1); // 新しく進んだら、その先の履歴は消える
        stack.push(next);
        index = stack.length - 1;
      }
      publish();
      return true;
    },
    back() {
      if (index > 0) {
        index -= 1;
        publish();
      }
    },
    forward() {
      if (index < stack.length - 1) {
        index += 1;
        publish();
      }
    },
  };
}
