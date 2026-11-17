#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
site-list-api.py —— 只读目录列表 API，供 files / musics 页面打开时实时渲染。

GET /api/list?path=files/middle_school[&dirs=1]
  -> {"ok": true, "path": "...", "items": [{"href": "chem/", "label": "Chemistry 化学", "type": "dir"}]}

规则与 .tools/site-index.py 一致：显示名优先继承旧列表里的文字，其次读目录
index.html 的 <title>，最后用目录名（下划线换空格）/ 文件名。
只允许 files/ 与 musics/ 两棵子树，纯只读，不写任何文件。
"""

import html
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path("/var/www/html").resolve()
ALLOWED_ROOTS = ("files", "musics")
SKIP_FILES = {"index.html", "folders.html", "files.html", "songs.html"}
SKIP_SUFFIXES = {".md"}
LIST_TARGETS = {"folders.html", "files.html", "songs.html"}
GENERIC_TITLES = {"文件夹", "星辰音乐库", "千里的小屋", "音乐"}

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
FETCH_RE = re.compile(r"fetchData\(\s*['\"]([^'\"]+)['\"]")
HREF_RE = re.compile(r'href="([^"]+)"[^>]*>([^<]*)<')


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def display_name(d):
    text = read_text(d / "index.html")
    if text:
        m = TITLE_RE.search(text)
        if m:
            title = html.unescape(m.group(1)).strip()
            if title and title not in GENERIC_TITLES:
                return title
    return d.name.replace("_", " ")


def load_labels(d):
    """从旧列表文件里继承手写的显示名。"""
    text = read_text(d / "index.html")
    if not text:
        return {}
    m = FETCH_RE.search(text)
    if not m or m.group(1) not in LIST_TARGETS:
        return {}
    listing = read_text(d / m.group(1))
    if not listing:
        return {}
    return {href: html.unescape(label).strip() for href, label in HREF_RE.findall(listing)}


def resolve(rel):
    rel = (rel or "").strip().strip("/")
    if not rel:
        return None
    parts = [p for p in rel.split("/") if p and p not in (".", "..")]
    if not parts or parts[0] not in ALLOWED_ROOTS:
        return None
    target = (BASE.joinpath(*parts)).resolve()
    try:
        target.relative_to(BASE)
    except ValueError:
        return None
    return target


def list_dir(d, dirs_only):
    labels = load_labels(d)
    dirs, files = [], []
    try:
        items = list(d.iterdir())
    except OSError:
        return []
    for p in items:
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        if p.is_dir():
            href = p.name + "/"
            dirs.append({"href": href, "label": labels.get(href) or display_name(p), "type": "dir"})
        elif not dirs_only:
            if p.name in SKIP_FILES or p.suffix.lower() in SKIP_SUFFIXES:
                continue
            files.append({"href": p.name, "label": labels.get(p.name) or p.name, "type": "file"})
    dirs.sort(key=lambda x: x["href"].lower())
    files.sort(key=lambda x: x["href"].lower())
    return dirs + files


class Handler(BaseHTTPRequestHandler):
    server_version = "site-list/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        u = urlparse(self.path)
        if u.path != "/api/list":
            return self.reply(404, {"ok": False, "error": "not found"})
        q = parse_qs(u.query)
        rel = (q.get("path") or [""])[0]
        dirs_only = (q.get("dirs") or ["0"])[0] in ("1", "true", "yes")
        target = resolve(rel)
        if target is None:
            return self.reply(400, {"ok": False, "error": "path not allowed"})
        if not target.is_dir():
            return self.reply(404, {"ok": False, "error": "no such dir"})
        self.reply(200, {"ok": True, "path": rel.strip("/"), "items": list_dir(target, dirs_only)})

    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("site-list-api listening on 127.0.0.1:%d" % port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
