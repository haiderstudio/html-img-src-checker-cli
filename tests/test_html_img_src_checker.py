#!/usr/bin/env python3
"""Tests for html_img_src_checker — stdlib unittest only.

Every HTML document in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html_img_src_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/html_img_src_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text, tmp):
    return checker.check_text(text, base_dir=tmp, root_dir=tmp)


class TestLocalSrc(unittest.TestCase):
    def test_relative_path_is_local(self):
        self.assertTrue(checker.is_local_src("images/logo.png"))

    def test_dot_relative_path_is_local(self):
        self.assertTrue(checker.is_local_src("./images/logo.png"))

    def test_parent_path_is_local(self):
        self.assertTrue(checker.is_local_src("../shared/logo.png"))

    def test_root_relative_path_is_local(self):
        self.assertTrue(checker.is_local_src("/images/logo.png"))

    def test_http_url_is_not_local(self):
        self.assertFalse(checker.is_local_src("http://example.com/a.png"))

    def test_https_url_is_not_local(self):
        self.assertFalse(checker.is_local_src("https://example.com/a.png"))

    def test_protocol_relative_url_is_not_local(self):
        self.assertFalse(checker.is_local_src("//example.com/a.png"))

    def test_data_uri_is_not_local(self):
        self.assertFalse(checker.is_local_src("data:image/png;base64,AAAA"))

    def test_fragment_only_is_not_local(self):
        self.assertFalse(checker.is_local_src("#top"))

    def test_empty_src_is_not_local(self):
        self.assertFalse(checker.is_local_src(""))
        self.assertFalse(checker.is_local_src("   "))

    def test_other_scheme_is_not_local(self):
        self.assertFalse(checker.is_local_src("blob:https://x/y.png"))


class TestResolveSrc(unittest.TestCase):
    def test_relative_resolves_against_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = checker.resolve_src("images/logo.png", tmp, tmp)
            self.assertEqual(target, Path(tmp) / "images/logo.png")

    def test_query_string_and_fragment_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = checker.resolve_src("images/logo.png?v=2#frag",
                                         tmp, tmp)
            self.assertEqual(target, Path(tmp) / "images/logo.png")

    def test_percent_encoding_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = checker.resolve_src("images/my%20photo.png",
                                         tmp, tmp)
            self.assertEqual(target, Path(tmp) / "images/my photo.png")

    def test_root_relative_resolves_against_root_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = checker.resolve_src("/images/logo.png",
                                         tmp + "/pages", tmp)
            self.assertEqual(target, Path(tmp) / "images/logo.png")


class TestImgDetection(unittest.TestCase):
    def test_existing_image_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "fake png bytes")
            self.assertEqual(
                findings_of('<img src="images/logo.png" alt="Logo">',
                            tmp),
                [])

    def test_missing_image_fails_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of('<img src="images/missing.png" alt="x">',
                              tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["line"], 1)
            self.assertEqual(bad[0]["src"], "images/missing.png")
            self.assertEqual(bad[0]["reason"], "not found")

    def test_remote_url_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<img src="https://example.com/a.png">',
                            tmp),
                [])

    def test_data_uri_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<img src="data:image/png;base64,AAAA">',
                            tmp),
                [])

    def test_empty_src_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<img src="" alt="x">', tmp), [])

    def test_img_without_src_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<img alt="No src here">', tmp), [])

    def test_img_with_only_srcset_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<img srcset="images/missing.png 1x">',
                            tmp),
                [])

    def test_multiple_images_in_document_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/ok.png", "x")
            text = ('<img src="images/ok.png">\n'
                    '<img src="images/a.png">\n'
                    '<img src="images/b.png">\n')
            bad = findings_of(text, tmp)
            self.assertEqual([f["line"] for f in bad], [2, 3])
            self.assertEqual([f["src"] for f in bad],
                             ["images/a.png", "images/b.png"])

    def test_uppercase_img_and_src(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            self.assertEqual(
                findings_of('<IMG SRC="images/logo.png">', tmp), [])
            bad = findings_of('<IMG SRC="images/missing.png">', tmp)
            self.assertEqual(len(bad), 1)

    def test_multiline_img_reports_start_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ('<html>\n<body>\n'
                    '<img\n  src="images/missing.png"\n  alt="x">\n'
                    '</body>\n</html>\n')
            bad = findings_of(text, tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["line"], 3)

    def test_img_with_query_string_passes_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            self.assertEqual(
                findings_of('<img src="images/logo.png?v=2">', tmp),
                [])

    def test_img_with_fragment_passes_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            self.assertEqual(
                findings_of('<img src="images/logo.png#frag">', tmp),
                [])

    def test_percent_encoded_src_passes_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/my photo.png", "x")
            self.assertEqual(
                findings_of('<img src="images/my%20photo.png">', tmp),
                [])

    def test_root_relative_src_passes_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            self.assertEqual(
                findings_of('<img src="/images/logo.png">', tmp), [])

    def test_root_relative_src_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of('<img src="/images/missing.png">', tmp)
            self.assertEqual(len(bad), 1)

    def test_parent_folder_src_passes_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "shared/logo.png", "x")
            write(tmp, "pages/page.html", "x")
            bad = checker.check_text(
                '<img src="../shared/logo.png">',
                base_dir=tmp + "/pages", root_dir=tmp)
            self.assertEqual(bad, [])

    def test_unquoted_src(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of('<img src=images/missing.png>', tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["src"], "images/missing.png")

    def test_self_closing_img(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of('<img src="images/missing.png" />', tmp)
            self.assertEqual(len(bad), 1)

    def test_img_on_same_line_as_other_markup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of(
                '<div><img src="images/missing.png"></div>', tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["line"], 1)

    def test_file_with_no_images_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<html><body><p>Hello</p></body></html>',
                            tmp),
                [])

    def test_empty_document_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(findings_of("", tmp), [])

    def test_src_pointing_at_a_folder_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "images").mkdir()
            bad = findings_of('<img src="images">', tmp)
            self.assertEqual(len(bad), 1)


class TestSkipping(unittest.TestCase):
    def test_img_in_comment_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of('<!-- <img src="images/missing.png"> -->',
                            tmp),
                [])

    def test_img_in_script_string_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ('<script>\n'
                    "var markup = '<img src=\"images/missing.png\">';\n"
                    '</script>\n')
            self.assertEqual(findings_of(text, tmp), [])

    def test_img_in_style_block_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ('<style>\n'
                    '.fake { content: "<img src=\\"images/m.png\\">"; }\n'
                    '</style>\n')
            self.assertEqual(findings_of(text, tmp), [])

    def test_real_img_after_script_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ('<script>var x = 1;</script>\n'
                    '<img src="images/missing.png">\n')
            bad = findings_of(text, tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["line"], 2)


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            path = write(tmp, "page.html",
                         '<img src="images/logo.png" alt="Logo">\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("every local image file exists", out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "page.html",
                         '<img src="images/missing.png">\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 1", out)
            self.assertIn('src "images/missing.png" not found', out)
            self.assertIn(path, out)

    def test_folder_walk_finds_html_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            write(tmp, "a.html", '<img src="images/logo.png">\n')
            write(tmp, "b.htm", '<img src="images/missing.png">\n')
            write(tmp, "notes.txt", '<img src="images/missing.png">\n')
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("b.htm", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            write(tmp, "a.html", '<img src="images/logo.png">\n')
            write(tmp, "sub/b.html",
                  '<img src="images/missing.png">\n')
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            write(tmp, "a.html", '<img src="images/logo.png">\n')
            write(tmp, "b.html", '<img src="images/missing.png">\n')
            code, out, err = run_cli([tmp, "--exclude", "b.html"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            write(tmp, "a.html", '<img src="images/logo.png">\n')
            write(tmp, ".git/b.html",
                  '<img src="images/missing.png">\n')
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "template.txt",
                         '<img src="images/missing.png">\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("template.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            path = write(tmp, "a.html", '<img src="images/logo.png">\n')
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html",
                         '<img src="images/missing.png">\n')
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 1)
            self.assertEqual(
                data["files"][0]["findings"][0]["src"],
                "images/missing.png")
            self.assertEqual(
                data["files"][0]["findings"][0]["reason"], "not found")
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.png", "x")
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input='<img src="a.png">\n', cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every local image file exists",
                          result.stdout)

    def test_stdin_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input='<img src="missing.png">\n', cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL <stdin>: <img> line 1 src "missing.png"',
                          result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "page.html"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no HTML files found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("html_img_src_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html", b"\xff\xfe<img>\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html",
                         '<img src="images/missing.png">\n')
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            write(tmp, "a.html", '<img src="images/logo.png">\n')
            result = subprocess.run(
                [sys.executable, str(SRC), "a.html"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every local image file exists",
                          result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "images/logo.png", "x")
            path = write(tmp, "a.html",
                         '<img src="images/logo.png">\n')
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/html_img_src_checker.py",
             "examples/clean.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/html_img_src_checker.py",
             "examples/flagged.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/html_img_src_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 3 missing image file(s) "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 3 missing image file(s) "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/html_img_src_checker.py",
             "examples/edge.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/html_img_src_checker.py",
             "--json", "examples/flagged.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/html_img_src_checker.py",
                       REPO / "tests/test_html_img_src_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"html_img_src_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/html_img_src_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_html_img_src_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("html-img-attr-checker-cli", readme)
        self.assertIn("image-alt-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
