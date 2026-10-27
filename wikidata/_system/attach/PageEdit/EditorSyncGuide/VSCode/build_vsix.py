#!/usr/bin/env python3
"""VS Code の拡張機能を、入れられる形（.vsix）に組み立てる（保守する人が使う。使う人は要らない）。

更新: 2026-10-07 23:43 +09:00

    ./build_vsix.py

このフォルダ（VSCode の添付）の package.json・extension.js から、wikiedit.vsix を作り直す。
.vsix は zip で、中に extension/ の下の拡張機能と、VS Code が読む目録（extension.vsixmanifest・
[Content_Types].xml）を入れる。目録は package.json から作るので、vsce（Node のツール）は要らない。

**中身が同じなら、毎回まったく同じ .vsix になる**（日付と順を固定する）。試験
（tests/test_editorsync_dist.py）が、添付の .vsix がこの結果と同じかを確かめる。元のファイルを
直したら、package.json の version を上げ（VS Code が新しい版として入れ直すように）、これを
実行して .vsix も一緒にコミットする。
"""
import io
import json
import os
import zipfile
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("package.json", "extension.js")
VSIX = "wikiedit.vsix"
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""


def manifest(pkg):
    """package.json から extension.vsixmanifest を作る。"""
    kinds = ",".join(pkg.get("extensionKind", []))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id={quoteattr(pkg["name"])} Version={quoteattr(pkg["version"])} Publisher={quoteattr(pkg["publisher"])}/>
    <DisplayName>{escape(pkg.get("displayName", pkg["name"]))}</DisplayName>
    <Description xml:space="preserve">{escape(pkg.get("description", ""))}</Description>
    <Categories>{escape(",".join(pkg.get("categories", [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value={quoteattr(pkg["engines"]["vscode"])}/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value={quoteattr(kinds)}/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def build(root=HERE):
    """組み立てた .vsix のバイト列を返す。"""
    with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    entries = [("extension.vsixmanifest", manifest(pkg).encode("utf-8")),
               ("[Content_Types].xml", CONTENT_TYPES.encode("utf-8"))]
    for name in FILES:
        with open(os.path.join(root, name), "rb") as f:
            entries.append(("extension/" + name, f.read()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, data in entries:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return buf.getvalue()


def main():
    with open(os.path.join(HERE, VSIX), "wb") as f:
        f.write(build())
    print(VSIX)


if __name__ == "__main__":
    main()
