#!/usr/bin/env python3
"""Check <img> src attributes that point at local files exist on disk.

Run: python3 src/html_img_src_checker.py page.html
     python3 src/html_img_src_checker.py site/
     python3 src/html_img_src_checker.py --stdin < page.html

A broken local image shows as an empty box on the
live page — usually found by a visitor, not the
author — and it fails silently in every local
preview that does not load that page. This tool
reads each HTML file, finds every <img> src that
points at a local file, and reports each one whose
file does not exist on disk, relative to the HTML
file, with the file and the line number. It exits
1 when any local image file is missing, so it can
fail a CI run. A page whose local images all exist
exits 0.

Only local files are checked. A remote URL
(http://, https://, or //), a data: URI, a
fragment-only src (#...), and an empty src are
never flagged — those are different jobs. A query
string or fragment on a local path (photo.png?v=2)
is ignored when the file is looked up, and a
percent-encoded path (%20) is decoded first. A
src starting with / is looked up under the first
folder you give on the command line (or the HTML
file's own folder for a single file).

A file given directly on the command line is always
checked, whatever its name. A folder is walked for
files ending in .html or .htm only, recursively by
default (--no-recursive stops at the top level).
.git folders are never walked, and directory links
are never followed.

Images inside HTML comments are not images — the
parser skips them. Markup inside <script> and
<style> blocks is not parsed as HTML either, so an
"<img>" written in a JavaScript string or a
stylesheet is left alone. Tag and attribute names
are matched without regard to case, as HTML
requires — <IMG> and SRC= are checked exactly like
<img> and src=.

It never rewrites a file, never touches the network,
and reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

__version__ = "1.0.0"

HTML_SUFFIXES = (".html", ".htm")

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def is_local_src(src):
    """True when src points at a local file worth checking."""
    value = (src or "").strip()
    if value == "":
        return False
    if value.startswith("#"):
        return False
    if value.startswith("//"):
        return False
    if _SCHEME.match(value):
        return False
    return True


def resolve_src(src, base_dir, root_dir):
    """Turn a local src into a filesystem path to check.

    The query string and fragment are dropped, the
    path is percent-decoded, and it is resolved
    against the HTML file's folder — or against the
    walk root when it starts with /.
    """
    value = unquote(urlsplit(src.strip()).path)
    if value.startswith("/"):
        return Path(root_dir) / value.lstrip("/")
    return Path(base_dir) / value


class ImgSrcParser(HTMLParser):
    """Collect every <img> whose local file is missing.

    HTMLParser already treats <script> and <style>
    content as character data, so markup written
    inside those blocks never reaches handle_starttag.
    Comments never reach it either.
    """

    def __init__(self, base_dir, root_dir):
        super().__init__(convert_charrefs=True)
        self.base_dir = base_dir
        self.root_dir = root_dir
        self.findings = []

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        values = dict(attrs)
        src = values.get("src")
        if src is None or not is_local_src(src):
            return
        line, _offset = self.getpos()
        target = resolve_src(src, self.base_dir, self.root_dir)
        if not target.is_file():
            self.findings.append({
                "line": line,
                "src": src,
                "reason": "not found",
            })

    def close(self):
        super().close()
        self.findings.sort(key=lambda item: item["line"])


def check_text(text, base_dir=".", root_dir=None):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "src": str, "reason": str}, in document order.
    """
    parser = ImgSrcParser(base_dir, root_dir or base_dir)
    parser.feed(text)
    parser.close()
    return parser.findings


def check_file(path, root_dir=None):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    try:
        base_dir = str(Path(path).parent)
        return (check_text(text, base_dir, root_dir or base_dir),
                None)
    except Exception as exc:  # malformed markup the parser rejects
        return [], "could not be parsed: %s" % exc


def _is_html_file(path):
    return Path(path).name.lower().endswith(HTML_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of HTML files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .html
    or .htm only. .git folders are never walked, and
    directory links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_html_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def walk_root(paths):
    """The folder root-relative src values resolve against.

    The first folder given on the command line, or the
    parent folder of the first file when only files are
    given.
    """
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            return str(path)
    return str(Path(paths[0]).parent)


def format_finding(path, finding):
    """One human-readable line for one missing image file."""
    return ('FAIL %s: <img> line %d src "%s" %s'
            % (path, finding["line"], finding["src"],
               finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no HTML files found", file=sys.stderr)
        return 2
    root = walk_root(paths)
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path, root_dir=root)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d missing image file(s) "
                  "in %d file(s)." % (len(files), findings,
                                      files_with_findings))
        else:
            print("OK — %d file(s) checked, every local image "
                  "file exists." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one HTML document read from standard input.

    Local src values resolve against the current
    folder.
    """
    text = sys.stdin.read()
    bad = check_text(text, base_dir=".", root_dir=".")
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d missing image file(s) "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every local image "
                  "file exists.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html_img_src_checker",
        description="Check <img> src attributes that point at "
                    "local files exist on disk, fail CI when one "
                    "does not.")
    parser.add_argument("paths", nargs="*",
                        help="HTML files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one HTML document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one HTML file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
