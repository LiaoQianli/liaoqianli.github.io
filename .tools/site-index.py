#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
site-index.py —— 扫描站点目录，自动生成"文件夹 / 音乐"列表。

只处理 index.html 里用 fetchData('X') 加载、且 X 属于 LIST_TARGETS 的页面：
  folders.html   文件树的目录列表
  files.html     科目目录的列表（原有命名，保留）
  songs.html     音乐屋的歌曲列表
绝不碰 lyrics.html（歌词）和任何其它文件名。

显示名优先级：
  1. 旧列表里已有的自定义文字（例如 href="CommonHazardWarningLabels.jpeg">Common Hazard Warning Labels<）
  2. 目录内 index.html 的 <title>
  3. 目录名（下划线换空格）/ 文件名

跳过：index.html、folders.html、files.html、songs.html、*.md、点或下划线开头的项。

用法：
  python3 site-index.py                      # 扫 /var/www/html 并写入
  python3 site-index.py --root . --dry-run   # 只看会生成什么
"""

import argparse
import html
import os
import re
import sys
from pathlib import Path

try:  # 仅 Linux 有
    import grp
    import pwd
except ImportError:  # Windows 开发机
    grp = pwd = None

LIST_TARGETS = {"folders.html", "files.html", "songs.html"}
GENERIC_TITLES = {"文件夹", "星辰音乐库", "千里的小屋", "音乐"}
SKIP_FILES = {"index.html", "folders.html", "files.html", "songs.html"}
SKIP_SUFFIXES = {".md"}

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
FETCH_RE = re.compile(r"fetchData\(\s*['\"]([^'\"]+)['\"]")
HREF_RE = re.compile(r'href="([^"]+)"[^>]*>([^<]*)<')


def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def read_title(index_file: Path):
    text = read_text(index_file)
    if not text:
        return None
    m = TITLE_RE.search(text)
    if not m:
        return None
    title = html.unescape(m.group(1)).strip()
    return title or None


def display_name(d: Path) -> str:
    title = read_title(d / "index.html")
    if title and title not in GENERIC_TITLES:
        return title
    return d.name.replace("_", " ")


def list_target(index_file: Path):
    text = read_text(index_file)
    if not text:
        return None
    m = FETCH_RE.search(text)
    return m.group(1) if m else None


def load_labels(list_file: Path):
    text = read_text(list_file)
    if not text:
        return {}
    return {href: html.unescape(label).strip() for href, label in HREF_RE.findall(text)}


def is_hidden(name: str) -> bool:
    return name.startswith(".") or name.startswith("_")


def render(entries) -> str:
    lines = []
    for href, label in entries:
        lines.append(
            '<a target="_blank" href="{}">{}</a><br>'.format(
                html.escape(href, quote=True), html.escape(label)
            )
        )
    return ("\n".join(lines) + "\n") if lines else ""


def list_entries(d: Path, labels):
    dirs, files = [], []
    try:
        items = list(d.iterdir())
    except OSError:
        return []
    for p in items:
        if is_hidden(p.name):
            continue
        if p.is_dir():
            href = p.name + "/"
            dirs.append((href, labels.get(href) or display_name(p)))
        else:
            if p.name in SKIP_FILES or p.suffix.lower() in SKIP_SUFFIXES:
                continue
            files.append((p.name, labels.get(p.name) or p.name))
    dirs.sort(key=lambda x: x[0].lower())
    files.sort(key=lambda x: x[0].lower())
    return dirs + files


def fix_owner(path: Path):
    """让生成的列表跟站点其它文件同属 www-data:www-data，方便 vpnadmin 在组内改。"""
    if pwd is None or grp is None:
        return
    try:
        uid = pwd.getpwnam("www-data").pw_uid
        gid = grp.getgrnam("www-data").gr_gid
    except KeyError:
        return
    try:
        os.chown(path, uid, gid)
        os.chmod(path, 0o775)
    except OSError:
        pass


def write_if_changed(path: Path, content: str, dry: bool) -> bool:
    old = read_text(path)
    if old == content:
        if not dry:  # 内容没变也纠正一次属主，避免拖拽/解压带进来的奇怪 UID
            fix_owner(path)
        return False
    if dry:
        print("[dry] {} ({} bytes)".format(path, len(content.encode("utf-8"))))
    else:
        path.write_text(content, encoding="utf-8", newline="\n")
        fix_owner(path)
        print("[write] {}".format(path))
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/var/www/html", help="站点根目录")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print("root not found: {}".format(root), file=sys.stderr)
        return 2

    changed = 0

    musics = root / "musics"
    if musics.is_dir():
        target = list_target(musics / "index.html")
        if target in LIST_TARGETS:
            list_file = musics / target
            labels = load_labels(list_file)
            entries = []
            for p in sorted(musics.iterdir()):
                if p.is_dir() and not is_hidden(p.name) and (p / "index.html").exists():
                    href = p.name + "/"
                    entries.append((href, labels.get(href) or display_name(p)))
            entries.sort(key=lambda x: x[0].lower())
            if write_if_changed(list_file, render(entries), args.dry_run):
                changed += 1

    files_root = root / "files"
    if files_root.is_dir():
        targets = [files_root] + [
            p for p in sorted(files_root.rglob("*")) if p.is_dir() and not is_hidden(p.name)
        ]
        for d in targets:
            index_file = d / "index.html"
            if not index_file.exists():
                continue
            target = list_target(index_file)
            if target not in LIST_TARGETS:
                continue
            list_file = d / target
            entries = list_entries(d, load_labels(list_file))
            if write_if_changed(list_file, render(entries), args.dry_run):
                changed += 1

    print("done, {} file(s) {}".format(changed, "would change" if args.dry_run else "updated"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
