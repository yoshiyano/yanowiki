// フォルダの一覧の先読み（Wiki「画面設計 > 先読み」）。
// 2026-09-29 設計者の指示: 開いたフォルダを中心に、近い親子フォルダを裏で順に読んでおく。応答性のため親を先に、
// 子は更新日時の新しいものから。子フォルダから親へ移ったときは、名前の並びで遷移元に隣接する子を先に読む。先に読んだフォルダへ移ったら、すぐ出して裏で読み直す（main.js の loadList）。
// 見張り（自動更新）は増やさず、移ったときに読み直して合わせる。
// 範囲（親は根まで・子は 1 段）も設計者が選んだ。個数の上限・60 秒・画面どうしで共有する、はクロコの実装例。

import { api } from "./api.js";
import { splitPath, joinPath } from "./location.js";
import { allows } from "./model.js";
import { compareNames } from "./sort.js";

export const CACHE_MAX = 200;       // 覚えておくフォルダの数（最近使った順に残す）
export const CHILDREN_MAX = 50;     // 先読みする子フォルダの数（更新日時の新しい順に先頭から）
export const FRESH_MS = 60 * 1000;  // 読んでからこの時間の内なら、先読みで読み直さない

const key = (mount, path) => `${mount}\n${path}`;

/**
 * 一覧（GET list の応答）の覚え。最近使った順に max まで持ち、あふれたら古いものから捨てる。
 * get は使ったことにし（順を先頭へ）、peek は順を変えない（先読みが新しさを見るとき）。
 */
export function createListCache(max = CACHE_MAX) {
  const map = new Map(); // key → {res, at}（Map は入れた順なので、末尾が最近）
  return {
    get(mount, path) {
      const k = key(mount, path);
      const v = map.get(k);
      if (!v) return null;
      map.delete(k);
      map.set(k, v);
      return v;
    },
    peek: (mount, path) => map.get(key(mount, path)) || null,
    put(mount, path, res, at = Date.now()) {
      const k = key(mount, path);
      map.delete(k);
      map.set(k, { res, at });
      while (map.size > max) map.delete(map.keys().next().value);
    },
    delete: (mount, path) => map.delete(key(mount, path)),
    clear: () => map.clear(),
    get size() {
      return map.size;
    },
  };
}

// 同じページの画面（二画面の左右）で共有する覚え
export const listCache = createListCache();

const mtimeOf = (e) => (e.attrs && typeof e.attrs.mtime === "number" ? e.attrs.mtime : null);

/**
 * 先読みする順（フォルダのパスの配列）。path は今いるフォルダ、entries はその一覧。
 * 親を近い順に根まで、次に子フォルダを更新日時の新しい順に最大 CHILDREN_MAX 個（更新日時の無いものは後ろ）。
 * from は、子フォルダ from から上へ移ってきたときのその名前。**名前の並びで from に隣接する子（すぐ次・すぐ前）を
 * 先に読み、そのあと更新日時の順**にする（2026-09-29 設計者の指示）。from 自身は読んだばかりなので読まない。
 * 入る・中身を見る権限の無いフォルダと、開けないリンクは読まない（読んでも失敗する）。
 */
export function prefetchOrder(path, entries, childrenMax = CHILDREN_MAX, from = null) {
  const parts = splitPath(path) || [];
  const parents = [];
  for (let i = parts.length - 1; i >= 0; i--) parents.push(joinPath(parts.slice(0, i)));
  const dirs = entries.filter((e) => e.kind === "dir");
  // 隣接は、読めるかに関わらず名前の並びで決める（読めない隣は飛ばすだけで、その向こうへは広げない）
  const byName = [...dirs].sort((a, b) => compareNames(a.name, b.name));
  const at = from == null ? -1 : byName.findIndex((e) => e.name === from);
  const adjacent = at < 0 ? [] : [byName[at + 1], byName[at - 1]].filter(Boolean);
  const readable = (e) => !(e.extra && e.extra.unreachable) && allows(e, "exec") && allows(e, "read");
  const byTime = dirs
    .map((e, i) => ({ e, i, t: mtimeOf(e) }))
    .sort((a, b) => (a.t == null) - (b.t == null) || (b.t ?? 0) - (a.t ?? 0) || a.i - b.i)
    .map(({ e }) => e);
  const children = [...new Set([...adjacent, ...byTime])]
    .filter((e) => e.name !== from && readable(e))
    .slice(0, childrenMax)
    .map((e) => joinPath([...parts, e.name]));
  return [...parents, ...children];
}

/**
 * 上へ移ったときの遷移元の子の名前（prefetchOrder の from）。to が from の祖先なら、from へ続く to の子の名前。
 * 親へ移ったとき（設計者の指示）に加え、パンくずなどで祖先へ一気に移ったときも同じに扱う（クロコの実装例）。
 */
export function cameFromChild(from, to) {
  if (!from || !to || from.trash || to.trash || from.mount !== to.mount) return null;
  const f = splitPath(from.path);
  const t = splitPath(to.path);
  if (!f || !t || f.length <= t.length || t.some((p, i) => p !== f[i])) return null;
  return f[t.length];
}

/**
 * 画面ごとの先読みの係。start で中心を決めると、prefetchOrder の順に 1 つずつ読んで覚えに入れる。
 * 新しく start する（別のフォルダへ移る）か stop すると、残りを捨てる（読んでいる途中のものは覚えに入れる）。
 * 読めなかったフォルダは飛ばす（知らせない。移ったときに loadList が読み直して知らせる）。
 */
export function createPrefetcher({ cache = listCache, list = api.list, now = () => Date.now(), fresh = FRESH_MS } = {}) {
  let gen = 0;
  return {
    /** from は上へ移ってきたときの遷移元の子の名前（cameFromChild）。無ければ null。 */
    async start(mount, path, entries, from = null) {
      const mine = ++gen;
      for (const p of prefetchOrder(path, entries, CHILDREN_MAX, from)) {
        if (mine !== gen) return;
        const had = cache.peek(mount, p);
        if (had && now() - had.at < fresh) continue;
        try {
          cache.put(mount, p, await list(mount, p), now());
        } catch {
          // 読めないフォルダは飛ばす
        }
      }
    },
    stop() {
      gen++;
    },
  };
}
