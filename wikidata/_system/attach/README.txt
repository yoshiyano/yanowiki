このディレクトリには、wiki/ 配下の各ページに添付されたファイルが保存されます。
配置場所はページのパスをそのままミラーします。

（例）
  wiki/data/file.md   に添付するファイルは  attach/data/file/  以下に配置
  wiki/index.md       に添付するファイルは  attach/index/      以下に配置

URLは /.attach/<配置場所> で配信されます（例: /.attach/index/logo.png）。
別farmを明示している場合は /=<farm名>/.attach/... になります。

ページ本文からは、他のページへのリンクと同様にルート相対パスで参照します。

    ![説明](/.attach/index/logo.png)

