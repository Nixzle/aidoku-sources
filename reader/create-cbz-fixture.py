import zipfile, base64
from pathlib import Path
root=Path("reader/test-fixtures")
pixel=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y/o9O8AAAAASUVORK5CYII=")
with zipfile.ZipFile(root/"sample.cbz","w",compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr("chapter/page10.png",pixel)
    z.writestr("chapter/page2.png",pixel)
    z.writestr("ComicInfo.xml","<ComicInfo/>")
print((root/"sample.cbz").stat().st_size)
