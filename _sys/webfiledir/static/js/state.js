// 画面の状態と、変わったことの通知。
// **部品どうしは直接呼び合わず、ここの状態を書き換えて通知を受ける**（Wiki「画面設計 > JS の部品分け」）。

export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();
  return {
    get: () => state,
    /** 変えたいところだけ渡す。値が変わったキーの一覧を添えて通知する。 */
    set(patch) {
      const changed = Object.keys(patch).filter((k) => state[k] !== patch[k]);
      if (changed.length === 0) return;
      state = { ...state, ...patch };
      for (const fn of listeners) fn(state, new Set(changed));
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
