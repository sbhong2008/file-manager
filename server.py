#!/usr/bin/env python3
"""로컬 파일 관리 서버 — 표준 라이브러리만 사용. 127.0.0.1 전용, 홈 폴더 안에서만 동작."""
import hashlib, json, os, secrets, shutil, sys, time, unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("FM_PORT", 8056))
HOME = Path.home().resolve()
TRASH = HOME / ".Trash"
APP = Path(__file__).resolve().parent
JOURNAL = APP / "data" / "journal.json"
TOKEN = secrets.token_urlsafe(24)
DENY = [HOME / n for n in ("Library", ".ssh", ".gnupg", "Applications", ".Trash")]
PACKAGE_EXT = {".app", ".photoslibrary", ".fcpbundle", ".xcodeproj", ".framework", ".bundle", ".musiclibrary", ".tvlibrary"}
CATS = {
    "이미지": {".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp", ".bmp", ".tiff", ".raw", ".cr2", ".nef", ".svg"},
    "영상": {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"},
    "오디오": {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg"},
    "문서": {".pdf", ".doc", ".docx", ".hwp", ".hwpx", ".txt", ".md", ".rtf", ".pages", ".key", ".ppt", ".pptx", ".odt"},
    "표·데이터": {".xls", ".xlsx", ".csv", ".numbers", ".json", ".xml", ".sqlite", ".db"},
    "압축": {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"},
    "설치·디스크": {".dmg", ".pkg", ".iso", ".exe", ".msi", ".apk"},
    "코드": {".py", ".js", ".ts", ".html", ".css", ".sh", ".ipynb", ".java", ".c", ".cpp", ".go", ".rs"},
}


class Err(Exception):
    pass


def under(p, base):
    return p == base or base in p.parents


def check(path, allow_root=False):
    """홈 안의 실경로만 허용. 시스템성 폴더는 거부."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise Err("절대 경로가 필요합니다")
    p = Path(os.path.abspath(p))  # 심볼릭 링크는 따라가지 않고 정규화만
    if not under(Path(os.path.realpath(p)), HOME):
        raise Err("홈 폴더 밖은 다룰 수 없습니다")
    if any(under(p, d) for d in DENY):
        raise Err("보호된 폴더입니다 (Library, .ssh, Applications, 휴지통)")
    if p == HOME and not allow_root:
        raise Err("홈 폴더 자체는 대상이 될 수 없습니다")
    return p


def walk(root, hidden=False, files_only=True):  # hidden=True여도 .DS_Store는 건너뜀
    """심볼릭 링크·패키지(.app 등) 건너뜀. (경로, stat) 생성."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError:
            continue
        for e in it:
            if e.name == ".DS_Store" or (not hidden and e.name.startswith(".")):
                continue
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if Path(e.name).suffix.lower() in PACKAGE_EXT or Path(e.path) in DENY:
                        continue
                    stack.append(e.path)
                    if not files_only:
                        yield e.path, e.stat(follow_symlinks=False), True
                elif e.is_file(follow_symlinks=False):
                    yield e.path, e.stat(follow_symlinks=False), False
            except OSError:
                continue


def digest(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if limit:
            h.update(f.read(limit))
        else:
            while chunk := f.read(1 << 20):
                h.update(chunk)
    return h.hexdigest()


def fmt(p, st):
    return {"path": str(p), "size": st.st_size, "mtime": int(st.st_mtime)}


# ---- 스캔 ----
def scan_dup(a):
    root = check(a["path"], True)
    refs = [check(r, True) for r in a.get("refs", []) if r]
    min_size = max(1, int(a.get("min_size", 1)))
    by_size, seen_inodes = {}, set()
    for p, st, _ in walk(root, a.get("hidden", False)):
        key = (st.st_dev, st.st_ino)
        if st.st_size < min_size or key in seen_inodes:  # 하드링크는 같은 파일로 취급
            continue
        seen_inodes.add(key)
        by_size.setdefault(st.st_size, []).append((p, st))
    groups = []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        part = {}
        for p, st in items:
            try:
                part.setdefault(digest(p, 65536), []).append((p, st))
            except OSError:
                pass
        for cand in part.values():
            if len(cand) < 2:
                continue
            full = {}
            for p, st in cand:
                try:
                    full.setdefault(digest(p), []).append((p, st))
                except OSError:
                    pass
            for h, g in full.items():
                if len(g) > 1:
                    files = [dict(fmt(p, st), ref=any(under(Path(p), r) for r in refs)) for p, st in sorted(g)]
                    groups.append({"hash": h[:12], "size": size, "files": files, "wasted": size * (len(g) - 1)})
    groups.sort(key=lambda g: -g["wasted"])
    return {"groups": groups[:500], "total_groups": len(groups), "wasted": sum(g["wasted"] for g in groups)}


def scan_big(a):
    root = check(a["path"], True)
    files = [fmt(p, st) for p, st, _ in walk(root, a.get("hidden", False))]
    files.sort(key=lambda f: -f["size"])
    return {"files": files[: int(a.get("limit", 200))]}


DEV_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "site-packages", ".idea", ".tox", "Pods"}
KEEP_FILES = {"Icon\r", "__init__.py", ".gitkeep", ".keep", "py.typed", ".nojekyll"}


def scan_empty(a):
    root = check(a["path"], True)
    hidden, dev = a.get("hidden", False), a.get("dev", False)
    zero = [fmt(p, st) for p, st, _ in walk(root, hidden) if st.st_size == 0]
    # 하위부터: 자식이 모두 빈 폴더(또는 .DS_Store만)면 빈 폴더
    alld = [p for p, _, isd in walk(root, True, False) if isd]
    empty = set()
    for d in sorted(alld, key=lambda p: -len(p)):
        try:
            kids = [k for k in os.listdir(d) if k != ".DS_Store"]
        except OSError:
            continue
        if all(os.path.join(d, k) in empty for k in kids):
            empty.add(d)
    # git 프로젝트·개발 폴더(.git, venv, node_modules …) 안의 항목은 기본 제외: 구조가 프로그램에 필요함
    projects = {d for d in alld if os.path.isdir(os.path.join(d, ".git"))}

    def in_dev(p):
        rel = Path(p).relative_to(root).parts
        return any(x in DEV_DIRS for x in rel) or any(under(Path(p), Path(pr)) for pr in projects)

    dirs = [{"path": d, "size": 0, "mtime": int(os.stat(d).st_mtime)} for d in sorted(empty) if os.path.dirname(d) not in empty]
    skipped = 0
    if not dev:
        n = len(dirs) + len(zero)
        dirs = [x for x in dirs if not in_dev(x["path"])]
        zero = [x for x in zero if not in_dev(x["path"]) and os.path.basename(x["path"]) not in KEEP_FILES]
        skipped = n - len(dirs) - len(zero)
    return {"zero": zero, "dirs": dirs, "skipped": skipped}


def unique(dst):
    dst = Path(dst)
    if not dst.exists():
        return dst
    n = 2
    while True:
        c = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        if not c.exists():
            return c
        n += 1


def plan_org(a):
    root = check(a["path"], True)
    mode = a.get("mode", "type")
    plan, taken = [], set()
    for e in sorted(os.scandir(root), key=lambda e: e.name):
        if e.name.startswith(".") or not e.is_file(follow_symlinks=False):
            continue
        st = e.stat()
        ext = Path(e.name).suffix.lower()
        cat = next((c for c, s in CATS.items() if ext in s), "기타")
        month = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m")
        sub = {"type": cat, "month": month, "type-month": f"{cat}/{month}"}[mode]
        dst = unique(root / sub / e.name)
        while str(dst) in taken:
            dst = unique(dst.with_name(dst.stem + " (x)" + dst.suffix))
        taken.add(str(dst))
        plan.append({"src": e.path, "dst": str(dst), "size": st.st_size})
    return {"plan": plan}


def plan_rename(a):
    root = check(a["path"], True)
    tpl = a.get("template") or "{name}"
    find, repl = a.get("find", ""), a.get("repl", "")
    case, nfc = a.get("case", ""), a.get("nfc", False)
    start, pad = int(a.get("start", 1)), int(a.get("pad", 2))
    names = [e for e in sorted(os.scandir(root), key=lambda e: e.name) if e.is_file(follow_symlinks=False) and not e.name.startswith(".")]
    if a.get("ext"):
        names = [e for e in names if Path(e.name).suffix.lower() == a["ext"].lower()]
    plan, targets = [], set()
    for i, e in enumerate(names):
        p = Path(e.name)
        stem = p.stem.replace(find, repl) if find else p.stem
        new = tpl.format(name=stem, ext=p.suffix.lstrip("."), n=str(start + i).zfill(pad),
                         date=datetime.fromtimestamp(e.stat().st_mtime).strftime("%Y%m%d"))
        if "{ext}" not in tpl:
            new += p.suffix
        if case == "lower": new = new.lower()
        elif case == "upper": new = new.upper()
        if nfc: new = unicodedata.normalize("NFC", new)
        new = new.replace("/", "_").strip()
        dst = str(root / new)
        conflict = (new == "" or new.startswith(".")
                    or dst in targets or (dst != e.path and os.path.lexists(dst) and unicodedata.normalize("NFC", dst) != unicodedata.normalize("NFC", e.path)))
        targets.add(dst)
        plan.append({"src": e.path, "dst": dst, "old": e.name, "new": new, "same": dst == e.path, "conflict": bool(conflict)})
    return {"plan": plan}


# ---- 실행 (모두 기록 → 되돌리기) ----
def jload():
    try:
        return json.loads(JOURNAL.read_text())
    except Exception:
        return []


def jsave(j):
    JOURNAL.parent.mkdir(exist_ok=True)
    JOURNAL.write_text(json.dumps(j[-200:], ensure_ascii=False, indent=1))


def disk():
    u = shutil.disk_usage(HOME)
    # ~/.Trash 목록은 macOS 권한(TCC)으로 못 읽을 수 있어, 이 앱이 보낸 항목 중 아직 휴지통에 있는 것만 합산한다
    mine = 0
    for e in jload():
        if e["label"] != "휴지통" or e["undone"]:
            continue
        for op in e["ops"]:
            try:
                mine += os.stat(op["dst"]).st_size if os.path.isfile(op["dst"]) else 0
            except OSError:
                pass
    return {"total": u.total, "free": u.free, "trash": mine}


def do_trash(a):
    before = disk()["free"]
    ops, errs, freed = [], [], 0
    for raw in a["paths"]:
        try:
            p = check(raw)
            if p.is_symlink() or not p.exists():
                raise Err("대상이 없습니다")
            if p.is_dir() and any(True for _ in walk(p, True)):
                raise Err("파일이 들어 있는 폴더는 휴지통으로 보내지 않습니다")
            size = p.stat().st_size if p.is_file() else 0
            dst = unique(TRASH / p.name)
            shutil.move(str(p), str(dst))
            ops.append({"src": str(p), "dst": str(dst)})
            freed += size
        except (Err, OSError) as e:
            errs.append({"path": raw, "error": str(e)})
    r = log("휴지통", ops, errs)
    r.update(freed=freed, disk=disk(), free_before=before)  # 휴지통에 넣은 용량 (비워야 실제 확보)
    return r


def do_move(a):
    ops, errs = [], []
    for m in a["moves"]:
        try:
            s, d = check(m["src"]), check(m["dst"])
            if not os.path.lexists(s):
                raise Err("원본이 없습니다")
            if os.path.lexists(d) and unicodedata.normalize("NFC", str(d)) != unicodedata.normalize("NFC", str(s)):
                raise Err("대상 이름이 이미 있습니다")
            if str(s) == str(d):
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            os.rename(s, d)
            ops.append({"src": str(s), "dst": str(d)})
        except (Err, OSError) as e:
            errs.append({"path": m.get("src"), "error": str(e)})
    return log(a.get("label", "이동"), ops, errs)


def log(label, ops, errs):
    entry = None
    if ops:
        entry = {"id": int(time.time() * 1000), "label": label, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ops": ops, "undone": False}
        j = jload(); j.append(entry); jsave(j)
    return {"done": len(ops), "errors": errs, "entry": entry}


def do_undo(a):
    j = jload()
    ent = next((e for e in reversed(j) if not e["undone"] and (a.get("id") is None or e["id"] == a["id"])), None)
    if not ent:
        raise Err("되돌릴 기록이 없습니다")
    ok, errs = 0, []
    for op in reversed(ent["ops"]):
        try:
            src, dst = Path(op["src"]), Path(op["dst"])
            if not os.path.lexists(dst):
                raise Err("이미 옮겨졌거나 사라짐")
            if os.path.lexists(src):
                raise Err("원래 위치에 같은 이름이 있음")
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            ok += 1
        except (Err, OSError) as e:
            errs.append({"path": op["dst"], "error": str(e)})
    if ok:
        ent["undone"] = True
        jsave(j)
    return {"restored": ok, "errors": errs}


def do_ls(q):
    p = Path(q.get("path", [str(HOME)])[0]).expanduser()
    p = Path(os.path.abspath(p))
    if not under(Path(os.path.realpath(p)), HOME):
        raise Err("홈 폴더 밖")
    dirs = sorted(e.name for e in os.scandir(p) if e.is_dir(follow_symlinks=False) and not e.name.startswith("."))
    return {"path": str(p), "parent": str(p.parent) if p != HOME else None, "dirs": dirs}


ROUTES = {"disk": lambda a: disk(), "dup": scan_dup, "big": scan_big, "empty": scan_empty, "org": plan_org, "rename": plan_rename,
          "trash": do_trash, "move": do_move, "undo": do_undo}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):  # DNS 리바인딩 방지
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        u = urlparse(self.path)
        if not self.host_ok():
            return self.send(403, {"error": "host"})
        try:
            if u.path == "/":
                html = (APP / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN).replace("__HOME__", str(HOME))
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if u.path == "/api/ls":
                return self.send(200, do_ls(parse_qs(u.query)))
            if u.path == "/api/journal":
                return self.send(200, {"journal": jload()[::-1]})
            self.send(404, {"error": "not found"})
        except (Err, OSError) as e:
            self.send(400, {"error": str(e)})

    def do_POST(self):
        if not self.host_ok() or self.headers.get("X-Token") != TOKEN:
            return self.send(403, {"error": "token"})
        fn = ROUTES.get(self.path.removeprefix("/api/"))
        if not fn:
            return self.send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            self.send(200, fn(json.loads(self.rfile.read(n) or b"{}")))
        except (Err, OSError, KeyError, ValueError) as e:
            self.send(400, {"error": f"{type(e).__name__}: {e}" if not isinstance(e, Err) else str(e)})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"파일 관리: http://127.0.0.1:{PORT}/  (종료: Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
