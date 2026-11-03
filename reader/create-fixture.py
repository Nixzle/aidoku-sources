import plistlib
from pathlib import Path
from datetime import datetime, timezone
f=Path("reader/test-fixtures")
f.mkdir(exist_ok=True,parents=True)
sample = {
"date":datetime(2026,11,1,11,30,),
"version":"0.9",
"library":[
{"mangaId":"x55j7","sourceId":"en.comix","dateAdded":datetime(2026,10,1,10,0,),"lastOpened":datetime(2026,10,31,12,0,),"lastRead":datetime(2026,10,31,12,0,)},
{"mangaId":"titleB","sourceId":"en.mangadex","dateAdded":datetime(2026,9,1,8,0,),"lastOpened":datetime(2026,9,3,8,0,)}
],
"manga":[
{"id":"x55j7","sourceId":"en.comix","title":"Second Half","url":"https://comix.to/title/x55j7-second-half","status":1,"nsfw":0,"viewer":1},
{"id":"titleB","sourceId":"en.mangadex","title":"A Manga – Café","url":"https://mangadex.org/title/something","status":1,"nsfw":0,"viewer":1}
],
"history":[{"sourceId":"en.comix","mangaId":"x55j7","chapterId":"8927229","dateRead":datetime(2026,10,31,12,0,),"progress":7,"total":32,"completed":False}],
"chapters":[{"sourceId":"en.comix","mangaId":"x55j7","id":"8927229","url":"https://comix.to/title/x55j7-second-half/8927229-chapter-1","chapter":1.0,"title":"Chapter 1","lang":"en","sourceOrder":1}],
"settings":{"ComixExamplePrivateToken":"SECRET_DO_NOT_EXPORT"}}
(f/"sample.aib").write_bytes(plistlib.dumps(sample,fmt=plistlib.FMT_BINARY))
(f/"sample.json").write_text(__import__("json").dumps({"library":[],"manga":[{"sourceId":"en.comix","id":"x55j7","title":"Second Half","url":"https://comix.to/title/x55j7-second-half"}]}),encoding="utf-8")
print((f/"sample.aib").stat().st_size)
