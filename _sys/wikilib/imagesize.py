"""画像ファイルの幅・高さを、デコードせずヘッダだけ読んで求める。

添付ファイル一覧に解像度を添えるためのもの（Pillow等の外部ライブラリを
入れずに済ませたい）。対応するのはPNG/JPEG/GIF/WebP/BMP/SVG。ico・avifは
構造が複雑なため対応しない（そのぶん image_dimensions は None を返す。
呼び出し側は解像度を出せないだけで、大きさの表示自体は続けられる）。

SVGは画素を持たないので、ブラウザで等倍に出したときの大きさを返す。
ルート要素の width・height（絶対単位はpxに直す）を使い、無いものは
viewBox の縦横比で補う。どちらからも決まらなければ None。
"""
import math
import re
import struct

# SVGのルート要素の開始タグ（<svg ...>）。前にXML宣言・DOCTYPE・コメントが
# 来ることがあるので、先頭の決まった位置ではなく最初に現れるものを探す。
# 属性値の中に ">" があってもタグが切れないよう、引用符の中は丸ごと読み飛ばす
_SVG_ROOT_RE = re.compile(rb'<(?:[\w.-]+:)?svg(?=[\s/>])((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
_SVG_COMMENT_RE = re.compile(rb'<!--.*?-->', re.S)
# 開始タグ中の属性。名前は完全一致で見る（以前は \b(width|height) で探して
# いたため、stroke-width の "width" や、中の <rect> の width まで拾っていた）
_SVG_ATTR_RE = re.compile(rb'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
# width・height の値（数値＋単位）。数値は ".5" や "1e3" の書きかたもある
_SVG_LENGTH_RE = re.compile(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z%]*)')
# 絶対単位をpxに直す係数（CSSの定義で 1in = 96px）。% や em などの相対単位は
# 置く場所が決まるまで大きさが決まらないので載せない（None扱いにして viewBox に回す）
_SVG_UNIT_PX = {"": 1.0, "px": 1.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4,
                "q": 96 / 101.6, "pt": 96 / 72, "pc": 16.0}
# ルート要素を探すのに読む量。DOCTYPEに実体宣言を長々と書く
# ソフト（Illustrator等）があるため、少し余裕を持たせる
_SVG_READ_BYTES = 64 * 1024


def image_dimensions(path):
    """画像ファイルの (幅, 高さ) をピクセル単位で返す。読み取れなければNone。"""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head.startswith(b"\x89PNG\r\n\x1a\n"):
                return _png_dimensions(head)
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return _gif_dimensions(head)
            if head[:2] == b"BM":
                return _bmp_dimensions(head)
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                return _webp_dimensions(f)
            if head[:2] == b"\xff\xd8":
                return _jpeg_dimensions(f)
            # SVG（XML）は "<" で始まる。BOMや空白が先に来ることがある
            if head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
                f.seek(0)
                return _svg_dimensions(f.read(_SVG_READ_BYTES))
    except OSError:
        return None
    return None


def _png_dimensions(head):
    # シグネチャ(8B) + IHDRチャンクの長さ(4B) + "IHDR"(4B) の直後に
    # 幅・高さが4バイトずつビッグエンディアンで入っている
    if len(head) < 24:
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def _gif_dimensions(head):
    # シグネチャ(6B)の直後、Logical Screen Descriptorに幅・高さが
    # 2バイトずつリトルエンディアンで入っている
    if len(head) < 10:
        return None
    w, h = struct.unpack("<HH", head[6:10])
    return w, h


def _bmp_dimensions(head):
    # ファイルヘッダ(14B)の直後のDIBヘッダ（BITMAPINFOHEADER想定）に
    # 幅・高さが4バイトずつリトルエンディアン（符号付き）で入っている。
    # 高さが負なら「上から下」方向を表すだけなので絶対値にする
    if len(head) < 26:
        return None
    w, h = struct.unpack("<ii", head[18:26])
    return abs(w), abs(h)


def _webp_dimensions(f):
    # RIFFヘッダ(12B)の直後のチャンクの種類で構造が変わる
    f.seek(12)
    fourcc = f.read(4)
    if fourcc == b"VP8 ":
        # ロッシー版。チャンク長(4B)の後、開始コード(3B: 9d 01 2a)の直後に
        # 幅・高さが14ビットずつ（上位2ビットはスケール指定なので捨てる）
        data = f.read(14)
        if len(data) < 14 or data[7:10] != b"\x9d\x01\x2a":
            return None
        w, h = struct.unpack("<HH", data[10:14])
        return w & 0x3FFF, h & 0x3FFF
    if fourcc == b"VP8L":
        # ロスレス版。チャンク長(4B)の後、シグネチャ(1B: 0x2f)の直後の
        # 4バイトに、幅14ビット・高さ14ビットが詰まっている（+1して使う）
        data = f.read(9)
        if len(data) < 9 or data[4] != 0x2F:
            return None
        bits = int.from_bytes(data[5:9], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if fourcc == b"VP8X":
        # 拡張版。チャンク長(4B) + フラグ(4B)の後、幅-1・高さ-1が
        # 3バイトずつリトルエンディアンで入っている
        data = f.read(14)
        if len(data) < 14:
            return None
        w = int.from_bytes(data[8:11], "little") + 1
        h = int.from_bytes(data[11:14], "little") + 1
        return w, h
    return None


def _jpeg_dimensions(f):
    # SOI(0xFFD8)の後に続くマーカー列から、SOFマーカー（フレーム開始。
    # DHT/JPG/DACにあたる 0xC4/0xC8/0xCC は「SOFではない」ため除く）を探す。
    # SOFのデータは 精度(1B) + 高さ(2B) + 幅(2B)
    f.seek(2)
    sof_codes = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        code = marker[1]
        if code == 0xD8 or code == 0x01 or 0xD0 <= code <= 0xD7:
            continue  # 長さを持たないマーカー
        if code == 0xD9:  # EOI。SOFに出会わないまま終わった
            return None
        length_bytes = f.read(2)
        if len(length_bytes) < 2:
            return None
        length = struct.unpack(">H", length_bytes)[0]
        if code in sof_codes:
            data = f.read(5)
            if len(data) < 5:
                return None
            h, w = struct.unpack(">HH", data[1:5])
            return w, h
        if length < 2:
            return None
        f.seek(length - 2, 1)


def _svg_dimensions(data):
    # コメントの中に書かれた <svg ...> をルート要素と取り違えないよう、先に消す
    m = _SVG_ROOT_RE.search(_SVG_COMMENT_RE.sub(b"", data))
    if not m:
        return None
    attrs = {}
    for a in _SVG_ATTR_RE.finditer(m.group(1)):
        value = a.group(2) if a.group(2) is not None else a.group(3)
        attrs[a.group(1).decode("ascii", "replace")] = value.decode("utf-8", "replace")
    width = _svg_length(attrs.get("width"))
    height = _svg_length(attrs.get("height"))
    if width is None or height is None:
        # 決まらなかった側は viewBox の縦横比で補う。両方とも無ければ
        # viewBox の大きさそのもの（ブラウザが <img> で出すときと同じ考えかた）
        box = _svg_viewbox(attrs.get("viewBox"))
        if box is None:
            return None
        box_w, box_h = box
        if width is not None:
            height = width * box_h / box_w
        elif height is not None:
            width = height * box_w / box_h
        else:
            width, height = box_w, box_h
    w, h = round(width), round(height)
    if w <= 0 or h <= 0:
        return None
    return w, h


def _svg_length(text):
    """SVGの width・height の値をpxの数にする。相対単位・読めない値・0以下はNone。"""
    if text is None:
        return None
    m = _SVG_LENGTH_RE.fullmatch(text.strip())
    if not m:
        return None
    factor = _SVG_UNIT_PX.get(m.group(2).lower())
    if factor is None:
        return None
    value = float(m.group(1)) * factor
    return value if math.isfinite(value) and value > 0 else None


def _svg_viewbox(text):
    """viewBox（"min-x min-y 幅 高さ"。区切りは空白かカンマ）の (幅, 高さ)。
    読めない・幅や高さが0以下ならNone。"""
    if text is None:
        return None
    parts = re.split(r'[\s,]+', text.strip())
    if len(parts) != 4:
        return None
    try:
        w, h = float(parts[2]), float(parts[3])
    except ValueError:
        return None
    if not (math.isfinite(w) and math.isfinite(h) and w > 0 and h > 0):
        return None
    return w, h
