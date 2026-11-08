"""Build docs/ContractGuard_Documentation.pdf from the Markdown documentation.

Markdown -> one HTML file (python-markdown) -> PDF with headless Chromium (Playwright for Node),
with a linked table of contents and PDF bookmarks.

Usage:
    pip install markdown            # plus Node.js with the playwright package and Chromium
    python docs/build/build_docs_pdf.py
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = DOCS / "ContractGuard_Documentation.pdf"

PARTS: list[tuple[str, Path]] = [
    ("Architecture", DOCS / "ARCHITECTURE.md"),
    ("Module guide", DOCS / "modules" / "README.md"),
    *[(None, p) for p in sorted((DOCS / "modules").glob("[0-9][0-9]_*.md"))],
    ("Testing strategy", DOCS / "TESTING.md"),
    ("Deployment", DOCS / "DEPLOYMENT.md"),
    ("Demo script", DOCS / "DEMO.md"),
    ("Decision log", DOCS / "DECISIONS.md"),
]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9.6pt; line-height: 1.45;
       color: #1f2933; }
h1 { font-size: 19pt; color: #1d4ed8; border-bottom: 2px solid #c7d2fe; padding-bottom: 4px;
     margin-top: 0; }
h2 { font-size: 13pt; color: #1e3a8a; margin-top: 18px; }
h3 { font-size: 11pt; color: #1e3a8a; margin-top: 14px; }
section.part { page-break-before: always; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 8.4pt;
        page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #cbd2d9; padding: 4px 6px; vertical-align: top; text-align: left; }
th { background: #eef2ff; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.4pt; background: #f1f5f9;
       padding: 0 2px; border-radius: 2px; overflow-wrap: anywhere; }
pre { background: #f1f5f9; border: 1px solid #e2e8f0; padding: 8px; font-size: 8pt;
      white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
td code, th code { overflow-wrap: normal; word-break: normal; }
a { color: #1d4ed8; text-decoration: none; }
.cover { text-align: center; padding-top: 70mm; }
.cover h1 { border: none; font-size: 30pt; }
.cover p { font-size: 12pt; color: #52606d; }
.toc ol { font-size: 10.5pt; line-height: 1.9; }
blockquote { border-left: 3px solid #c7d2fe; margin-left: 0; padding-left: 10px; color: #52606d; }
"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fix_links(body: str) -> str:
    """Links to other Markdown files cannot work inside one PDF: keep their text only."""
    return re.sub(r'<a href="(?!https?:)[^"]*">(.*?)</a>', r"\1", body)


def main() -> int:
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    sections, toc = [], []
    for n, (title, path) in enumerate(PARTS, start=1):
        text = path.read_text(encoding="utf-8")
        first = re.search(r"^# (.+)$", text, re.M)
        heading = title or (first.group(1) if first else path.stem)
        if first:
            text = text.replace(first.group(0), f"# {heading}", 1)
        anchor = f"part-{n}-{slug(heading)}"
        body = fix_links(md.reset().convert(text))
        body = body.replace("<h1>", f'<h1 id="{anchor}">', 1)
        sections.append(f'<section class="part">{body}</section>')
        toc.append(f'<li><a href="#{anchor}">{html.escape(heading)}</a></li>')

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>ContractGuard documentation</title><style>{CSS}</style></head><body>
<div class="cover"><h1>ContractGuard</h1>
<p>Technical documentation</p>
<p>Architecture, module guides, testing, deployment, demo and decision log</p>
<p>Generated {date.today():%d %B %Y} from the Markdown files in <code>docs/</code></p></div>
<section class="part toc"><h1>Contents</h1><ol>{"".join(toc)}</ol></section>
{"".join(sections)}
</body></html>"""
    html_path = DOCS / "build" / "documentation.html"
    html_path.write_text(page, encoding="utf-8")

    script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://{html_path}');
  await page.pdf({{ path: '{OUT}', format: 'A4', printBackground: true, outline: true,
    tagged: true, displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:7pt;width:100%;padding:0 16mm;color:#52606d;' +
      'display:flex;justify-content:space-between"><span>ContractGuard documentation</span>' +
      '<span>Page <span class="pageNumber"></span> of ' +
      '<span class="totalPages"></span></span></div>',
    margin: {{ top: '16mm', bottom: '18mm', left: '16mm', right: '16mm' }} }});
  await browser.close();
}})();
"""
    subprocess.run(["node", "-e", script], check=True)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
