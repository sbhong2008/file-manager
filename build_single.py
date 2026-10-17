#!/usr/bin/env python3
"""모든 OS(Windows·Linux·macOS·Android Termux)에서 `python3 filemanager.py` 하나로 실행되는 단일 파일을 만든다.
index.html을 server.py에 base64로 내장한다. 결과: dist/filemanager.py"""
import base64, pathlib
root = pathlib.Path(__file__).resolve().parent
src = (root / "server.py").read_text(encoding="utf-8")
ui = base64.b64encode((root / "index.html").read_bytes()).decode()
import re
line = re.search(r"^EMBEDDED_UI = None  # __EMBED__.*$", src, re.M)
assert line
out = root / "dist"
out.mkdir(exist_ok=True)
(out / "filemanager.py").write_text(src[:line.start()] + f'EMBEDDED_UI = "{ui}"' + src[line.end():], encoding="utf-8")
print("만듦:", out / "filemanager.py")
