# html-img-src-checker-cli

Check every `<img>` src that points at a local file actually exists on disk — fail CI when one does not.

[![CI](https://github.com/haiderstudio/html-img-src-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/html-img-src-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`html_img_src_checker` reads each HTML file,
finds every `<img>` src that points at a local
file, and reports each one whose file does not
exist on disk, relative to the HTML file, with the
file and the line number. It exits 1 when any
local image file is missing, so it can fail a CI
run. A page whose local images all exist exits 0.

- A broken local image shows as an empty box on
  the live page — usually found by a visitor, not
  the author — and it fails silently in every local
  preview that does not load that page. This names
  the exact line, and the fix is one path per
  image once found.
- Only local files are checked. A remote URL
  (`http://`, `https://`, or `//`), a `data:` URI,
  a fragment-only src (`#...`), and an empty src
  are never flagged — those are different jobs. A
  query string or fragment on a local path
  (`photo.png?v=2`) is ignored when the file is
  looked up, and a percent-encoded path (`%20`) is
  decoded first. A src starting with `/` is looked
  up under the first folder you give on the command
  line (or the HTML file's own folder for a single
  file).
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.html` or `.htm` only, recursively
  by default (`--no-recursive` stops at the top
  level). `.git` folders are never walked, and
  directory links are never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one HTML document read from standard input
  (local src values resolve against the current
  folder).
- Images inside HTML comments are not images — the
  parser skips them. Markup inside `<script>` and
  `<style>` blocks is not parsed as HTML either, so
  an `"<img>"` written in a JavaScript string or a
  stylesheet is left alone. Tag and attribute names
  are matched without regard to case, as HTML
  requires — `<IMG>` and `SRC=` are checked exactly
  like `<img>` and `src=`.

## Who it is for

Every site owner with local images — a logo, a
photo, a product shot. One renamed or moved file
and the page shows an empty box, found by a
visitor, not the author. This is the gate that
stops it at the pull request.

## What it does NOT do

- It does not check `srcset` — only the `src`
  attribute is checked. A picture that relies on
  `srcset` alone is a different check.
- It does not check alt text on images. That is repo
  #30, image-alt-checker-cli — the same
  accessibility family, a different element
  property.
- It does not check other attributes on `<img>`.
  That is repo #83, html-img-attr-checker-cli —
  whether the file exists is a different check on
  the same tags.
- It does not download or open remote images — a
  remote URL is skipped, never fetched.
- It never rewrites a file, and it never touches the
  network.

## How this differs

- A fresh search of GitHub on Nov 16, 2026 found 0
  results for `"html-img-src-checker-cli"` and 1
  result for `html img src checker` — mfright/
  imgDeletedChecker, 0 stars, which compares
  `<img>` src tags between two versions of a page
  to find accidentally deleted images. That is a
  version-diff job, not an existence check.
- No rival checks whether the local file behind an
  `<img>` src exists, offline, with a CI exit code.

## Install

```sh
git clone https://github.com/haiderstudio/html-img-src-checker-cli.git
cd html-img-src-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one HTML file:

```sh
python3 src/html_img_src_checker.py page.html
```

A file whose local images all exist passes:

```sh
$ python3 src/html_img_src_checker.py examples/clean.html
OK — 1 file(s) checked, every local image file exists.
```

A file with missing local images fails, with the
file and line for each one:

```sh
$ python3 src/html_img_src_checker.py examples/flagged.html
FAIL examples/flagged.html: <img> line 5 src "images/missing.png" not found
FAIL examples/flagged.html: <img> line 6 src "images/gone.jpg" not found
FAIL examples/flagged.html: <img> line 7 src "../shared/absent.png" not found
Checked 1 file(s), 3 missing image file(s) in 1 file(s).
```

Check a whole folder (`.html` / `.htm` files only):

```sh
$ python3 src/html_img_src_checker.py examples/
FAIL examples/flagged.html: <img> line 5 src "images/missing.png" not found
FAIL examples/flagged.html: <img> line 6 src "images/gone.jpg" not found
FAIL examples/flagged.html: <img> line 7 src "../shared/absent.png" not found
Checked 3 file(s), 3 missing image file(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ printf '<img src="missing.png">\n' | python3 src/html_img_src_checker.py --stdin
FAIL <stdin>: <img> line 1 src "missing.png" not found
Checked 1 file(s), 1 missing image file(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/html_img_src_checker.py --json examples/flagged.html
{
  "files": [
    {
      "path": "examples/flagged.html",
      "findings": [
        {
          "line": 5,
          "src": "images/missing.png",
          "reason": "not found"
        },
        {
          "line": 6,
          "src": "images/gone.jpg",
          "reason": "not found"
        },
        {
          "line": 7,
          "src": "../shared/absent.png",
          "reason": "not found"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 3
}
```

Exit codes: 0 when every local image file exists, 1
when any local image file is missing or a file cannot
be read, 2 for a usage error (a missing path, a bad
flag, or no HTML files found).

## Examples

A remote URL, a data URI, and an empty src are not
flagged, and an image in a comment or a script
string is not an image — `examples/clean.html`
holds all of them, and it passes:

```sh
$ python3 src/html_img_src_checker.py examples/clean.html
OK — 1 file(s) checked, every local image file exists.
```

Uppercase tags, a query string, a root-relative
path, a fragment, and a percent-encoded name are
all handled — `examples/edge.html` has all of
them, and it passes:

```sh
$ python3 src/html_img_src_checker.py examples/edge.html
OK — 1 file(s) checked, every local image file exists.
```

An image that points at a folder, not a file, still
fails — a folder is not an image file:

```sh
$ printf '<img src="images">\n' | python3 src/html_img_src_checker.py --stdin
FAIL <stdin>: <img> line 1 src "images" not found
Checked 1 file(s), 1 missing image file(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_html_img_src_checker.py
```

The tests cover local-vs-remote detection (a
relative path is local, a `./` path is local, a
`../` path is local, a root-relative path is local,
an `http://` URL is not, an `https://` URL is not,
a protocol-relative `//` URL is not, a `data:` URI
is not, a fragment-only src is not, an empty src is
not, another scheme such as `blob:` is not),
resolving a src (relative against the HTML file's
folder, query string and fragment dropped,
percent-encoding decoded, root-relative against the
walk root), detection (an existing image passes, a
missing image fails with line, src and reason,
remote URLs pass, data URIs pass, an empty src
passes, an `<img>` with no src passes, an `<img>`
with only `srcset` passes, several images in one
file in document order, an uppercase `<IMG>` and
`SRC=`, a multiline `<img>` reports the line the
tag starts on, a query string passes when the file
exists, a fragment passes when the file exists, a
percent-encoded src passes when the file exists, a
root-relative src passes when the file exists and
fails when it does not, a parent-folder src passes
when the file exists, an unquoted src, a
self-closing `<img>`, an image on the same line as
other markup, a file with no images passes, an
empty document passes, a src pointing at a folder
fails), skipping (an image in a comment, an image
in a script string, an image in a style block, a
real image after a script checked), the CLI (exit
0/1/2, folder walking for several HTML files
including `.htm`, nested folders, `--no-recursive`,
`--exclude`, `.git` skipped, a direct file checked
whatever its name, duplicate paths checked once,
`--json` output, `--stdin` clean and dirty, bad
flags, missing paths, empty folders, `--version`, a
non-UTF-8 file reported, input files left
unchanged, the tool run from another folder and
under a changed HOME), the bundled examples (sample
output compared byte-for-byte against a fresh run,
and the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no
absolute paths, no real secrets outside the tests
and examples, stdlib imports only, no network use
in the source, `.env` first in `.gitignore`, CI
file runs the test file, README names the
neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking image links is not new, and the
parsing follows Python's own standard-library HTML
parser — but no existing tool does this one job,
checking that the local file behind every `<img>`
src exists on disk, as a tested command-line gate
with a CI exit code, as the search above shows —
and every line of code here is original, built on
nothing but Python's standard library.
