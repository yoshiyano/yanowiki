#!/usr/bin/env python3
"""ブラウザ拡張機能を、ブラウザごとの zip に組み立てる（保守する人が使う。使う人は要らない）。

更新: 2026-10-07 23:20 +09:00

    ./build_zip.py

このフォルダ（BrowserExt の添付）の元のファイルから、次の2つを作り直す。zip は、それぞれの
ブラウザのページ（Chrome・Firefox）の添付に置く。

    ../Chrome/wikiedit-chrome.zip    manifest.json（Chrome 用）・background.js・relay.js
    ../Firefox/wikiedit-firefox.zip  manifest.firefox.json を manifest.json という名前にしたもの・同じ JS

Chrome は MV3 で `background.scripts` があるとエラーにし、Firefox は `background.service_worker`
で動かないので、設定だけを入れ替える。

**中身が同じなら、毎回まったく同じ zip になる**（日付と順を固定する）。試験
（tests/test_editorsync_dist.py）が、添付の zip がこの結果と同じかを確かめる。元のファイルを
直したら、これを実行して zip も一緒にコミットする。元のファイルを直したら、manifest の
version も上げる（ブラウザが新しい版として扱えるように）。
"""
import io
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ("background.js", "relay.js")
SETS = {
    "../Chrome/wikiedit-chrome.zip": "manifest.json",
    "../Firefox/wikiedit-firefox.zip": "manifest.firefox.json",
}
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def build(manifest_name, root=HERE):
    """組み立てた zip のバイト列を返す。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, src in [("manifest.json", manifest_name)] + [(s, s) for s in SCRIPTS]:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(root, src), "rb") as f:
                z.writestr(info, f.read())
    return buf.getvalue()


def main():
    for zip_name, manifest_name in SETS.items():
        path = os.path.normpath(os.path.join(HERE, zip_name))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(build(manifest_name))
        print(zip_name)


if __name__ == "__main__":
    main()
