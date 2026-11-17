# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the HTML files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL: a remote image is skipped, never opened.

It only checks that local image files exist on disk. It never downloads an image, never loads a page, and never runs JavaScript.

If you find a case where the tool rewrites a file, opens a URL, or reports a pass for an HTML file with an `<img>` whose local file is missing, please open an issue describing the exact commands and input. Do not include any real secret in the report.
