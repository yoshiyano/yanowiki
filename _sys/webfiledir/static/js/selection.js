// 選択の規則（Wiki「画面設計 > 選択」）。画面の部品から切り離してテストページで確かめる。
// 項目は key（ふだんは名前、ごみ箱では ID）で指す。order は表示の並び順の key の配列。
// **Shift の範囲選択と矢印キーは表示の並び順に従う**（API から返った順ではない）。
//
// 状態は {selection: Set<key>, anchor: key|null, focus: key|null}。
//   anchor … Shift で範囲を選ぶときの起点（最後にクリックしたもの）
//   focus  … キー操作で動く「いまの項目」

export function emptySelection() {
  return { selection: new Set(), anchor: null, focus: null };
}

/** order の中の a から b まで（両端を含む）。どちらかが無ければ b だけ。 */
export function rangeKeys(order, a, b) {
  const i = order.indexOf(a);
  const j = order.indexOf(b);
  if (j < 0) return [];
  if (i < 0) return [b];
  const [lo, hi] = i < j ? [i, j] : [j, i];
  return order.slice(lo, hi + 1);
}

/** クリック。Ctrl で足す・外す、Shift で起点から範囲、Ctrl+Shift で今の選択に範囲を足す。 */
export function clickSelect(state, order, key, { ctrl = false, shift = false } = {}) {
  if (shift) {
    const range = rangeKeys(order, state.anchor, key);
    const selection = ctrl ? new Set([...state.selection, ...range]) : new Set(range);
    // 起点は動かさない（続けて Shift+クリックすると、同じ起点から範囲を選び直す）
    return { selection, anchor: state.anchor ?? key, focus: key };
  }
  if (ctrl) {
    const selection = new Set(state.selection);
    if (selection.has(key)) selection.delete(key);
    else selection.add(key);
    return { selection, anchor: key, focus: key };
  }
  return { selection: new Set([key]), anchor: key, focus: key };
}

/** 矢印キーなどで focus を delta だけ動かす（端で止まる）。Shift なら起点から範囲を選ぶ。 */
export function moveSelect(state, order, delta, { shift = false } = {}) {
  if (order.length === 0) return state;
  const i = order.indexOf(state.focus);
  let j;
  if (i < 0) j = delta >= 0 ? 0 : order.length - 1; // まだ何も無ければ端から始める
  else j = Math.max(0, Math.min(order.length - 1, i + delta));
  return jumpSelect(state, order, order[j], { shift });
}

/** focus を key へ（Home / End など）。 */
export function jumpSelect(state, order, key, { shift = false } = {}) {
  if (shift) {
    const anchor = state.anchor ?? state.focus ?? key;
    return { selection: new Set(rangeKeys(order, anchor, key)), anchor, focus: key };
  }
  return { selection: new Set([key]), anchor: key, focus: key };
}

export function selectAll(state, order) {
  return { selection: new Set(order), anchor: state.anchor, focus: state.focus };
}

/** ラバーバンド。hits は四角に入った key。Ctrl なら始める前の選択に足す（入ったものは反転）。 */
export function rectSelect(before, hits, { ctrl = false } = {}) {
  if (!ctrl) return { selection: new Set(hits), anchor: hits[0] ?? null, focus: hits[hits.length - 1] ?? null };
  const selection = new Set(before.selection);
  for (const k of hits) {
    if (before.selection.has(k)) selection.delete(k);
    else selection.add(k);
  }
  return { selection, anchor: before.anchor, focus: before.focus };
}

/** 一覧が変わったあと、無くなった項目を選択から外す。 */
export function pruneSelection(state, order) {
  const alive = new Set(order);
  const selection = new Set([...state.selection].filter((k) => alive.has(k)));
  return {
    selection,
    anchor: alive.has(state.anchor) ? state.anchor : null,
    focus: alive.has(state.focus) ? state.focus : null,
  };
}
