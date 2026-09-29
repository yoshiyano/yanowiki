// 操作者の好み（表示形式・並べ替え・隠しファイル）を覚える。
// localStorage に触るのはここだけ。利用する側のページに組み込むとき、ぶつからないよう
// キーに接頭辞を付け、読み書きできない環境（プライベートウィンドウなど）では覚えずに動く。

const PREFIX = "webfiledir.";

/** localStorage のキー（storage イベントで、別のタブの書き込みを見分けるのに使う）。 */
export function prefKey(name) {
  return PREFIX + name;
}

export function loadPref(name, fallback, isValid = () => true) {
  try {
    const raw = localStorage.getItem(PREFIX + name);
    if (raw == null) return fallback;
    const value = JSON.parse(raw);
    return isValid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function savePref(name, value) {
  try {
    localStorage.setItem(PREFIX + name, JSON.stringify(value));
  } catch {
    // 覚えられなくても画面は動く
  }
}
