#!/usr/bin/env python3
"""
md_to_pdf.py — Convert Markdown files (with LaTeX math) to PDF.

Tries conversion methods in order of quality:
  1. pandoc + xelatex  (Unicode-native, handles box-drawing chars + $...$ equations)
  2. pandoc + lualatex (Unicode-native fallback)
  3. pandoc + pdflatex (ASCII-safe preprocessed copy — box-drawing chars replaced)
  4. pandoc + wkhtmltopdf / weasyprint  (HTML-based)
  5. HTML-only output  (always works, open in browser and File → Print → PDF)

Usage:
    python md_to_pdf.py                                 # convert all .md in this dir
    python md_to_pdf.py places365_coco80_context_pipeline.md
    python md_to_pdf.py *.md --output-dir ./pdf

Install (best quality):
    sudo apt install pandoc texlive-xetex texlive-latex-extra texlive-fonts-recommended fonts-dejavu
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _has(cmd):
    return shutil.which(cmd) is not None


# Box-drawing + other non-ASCII symbols that pdflatex can't handle.
# Maps to plain-ASCII replacements that preserve visual structure.
_BOX_REPLACEMENTS = {
    '┌': '+', '┐': '+', '└': '+', '┘': '+',
    '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+',
    '─': '-', '━': '-', '═': '=',
    '│': '|', '║': '|',
    '▼': 'v', '▲': '^', '◄': '<', '►': '>',
    '→': '->', '←': '<-', '↑': '^', '↓': 'v',
    '⊕': '+', '⊗': 'x', '∧': '^', '∨': 'v',
    '✓': 'OK', '✗': 'NO', '⚠': '(!)',
    '\u200b': '',  # zero-width space
}

def _ascii_safe(text: str) -> str:
    """Replace non-ASCII characters that pdflatex cannot handle."""
    for char, replacement in _BOX_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Replace any remaining non-ASCII outside math delimiters
    # (preserve content inside $...$ and $$...$$)
    parts = re.split(r'(\$\$.*?\$\$|\$[^$\n]+?\$)', text, flags=re.DOTALL)
    safe_parts = []
    for i, part in enumerate(parts):
        if part.startswith('$'):
            safe_parts.append(part)  # keep math as-is
        else:
            safe_parts.append(part.encode('ascii', errors='replace').decode('ascii').replace('?', ' '))
    return ''.join(safe_parts)


def _pandoc_common_args(src: Path, dst: Path, engine: str) -> list:
    args = [
        'pandoc', str(src),
        '--pdf-engine', engine,
        '-V', 'geometry:margin=2.5cm',
        '-V', 'fontsize=11pt',
        '-V', 'linestretch=1.3',
        '-V', 'colorlinks=true',
        '-V', 'linkcolor=NavyBlue',
        '-V', 'urlcolor=NavyBlue',
        '-V', 'toccolor=NavyBlue',
        '--highlight-style', 'tango',
        '-o', str(dst),
    ]
    return args


def _md_to_pdf_xelatex(src: Path, dst: Path) -> bool:
    """
    pandoc + xelatex — Unicode-native engine.
    Uses DejaVu fonts which include box-drawing characters.
    """
    if not _has('pandoc') or not _has('xelatex'):
        return False

    # Probe available monospace fonts in preference order
    mono_candidates  = ['DejaVu Sans Mono', 'FreeMono', 'Liberation Mono', 'Noto Mono', 'Courier New']
    main_candidates  = ['DejaVu Sans',      'FreeSans', 'Liberation Sans',  'Noto Sans']

    fc_out = _run(['fc-list', '--format=%{family}\\n']).stdout.lower() if _has('fc-list') else ''
    mono = next((f for f in mono_candidates if f.lower() in fc_out), None)
    main = next((f for f in main_candidates  if f.lower() in fc_out), None)

    cmd = _pandoc_common_args(src, dst, 'xelatex')
    if main:
        cmd += ['-V', f'mainfont={main}']
    if mono:
        cmd += ['-V', f'monofont={mono}']

    r = _run(cmd)
    if r.returncode == 0 and dst.exists():
        return True
    print(f'  [xelatex] failed: {r.stderr[-400:].strip()}')
    return False


def _md_to_pdf_lualatex(src: Path, dst: Path) -> bool:
    """pandoc + lualatex — Unicode-native, second option."""
    if not _has('pandoc') or not _has('lualatex'):
        return False
    cmd = _pandoc_common_args(src, dst, 'lualatex')
    r = _run(cmd)
    if r.returncode == 0 and dst.exists():
        return True
    print(f'  [lualatex] failed: {r.stderr[-400:].strip()}')
    return False


def _md_to_pdf_pdflatex(src: Path, dst: Path) -> bool:
    """
    pandoc + pdflatex — ASCII-only engine.
    Writes a temporary preprocessed copy with box-drawing chars replaced.
    """
    if not _has('pandoc') or not _has('pdflatex'):
        return False

    original = src.read_text(encoding='utf-8')
    safe     = _ascii_safe(original)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md',
                                     delete=False, encoding='utf-8') as tf:
        tf.write(safe)
        tmp_src = Path(tf.name)

    try:
        cmd = _pandoc_common_args(tmp_src, dst, 'pdflatex')
        r = _run(cmd)
        if r.returncode == 0 and dst.exists():
            return True
        print(f'  [pdflatex] failed: {r.stderr[-400:].strip()}')
    finally:
        tmp_src.unlink(missing_ok=True)
    return False


def _md_to_pdf_pandoc_html(src: Path, dst: Path) -> bool:
    """pandoc → HTML → wkhtmltopdf."""
    if not _has('pandoc') or not _has('wkhtmltopdf'):
        return False
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as tf:
        html_path = Path(tf.name)
    try:
        r1 = _run(['pandoc', str(src), '--standalone', '--mathjax', '-o', str(html_path)])
        if r1.returncode != 0:
            return False
        r2 = _run(['wkhtmltopdf', '--enable-local-file-access',
                   '--margin-top', '20mm', '--margin-bottom', '20mm',
                   '--margin-left', '20mm', '--margin-right', '20mm',
                   str(html_path), str(dst)])
        if r2.returncode == 0 and dst.exists():
            return True
        print(f'  [wkhtmltopdf] failed: {r2.stderr[:200]}')
    finally:
        html_path.unlink(missing_ok=True)
    return False


def _md_to_pdf_weasyprint(src: Path, dst: Path) -> bool:
    """markdown → HTML → weasyprint."""
    try:
        import markdown    # type: ignore
        import weasyprint  # type: ignore
    except ImportError:
        return False
    md_text  = src.read_text(encoding='utf-8')
    html_body = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc'],
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: 'DejaVu Sans', Georgia, serif; font-size: 11pt; line-height: 1.5;
          max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 6px; }}
  h2 {{ font-size: 14pt; color: #222; border-bottom: 1px solid #aaa; }}
  code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-size: 9pt;
          font-family: 'DejaVu Sans Mono', monospace; }}
  pre  {{ background: #f4f4f4; padding: 12px; border-radius: 5px; font-size: 9pt; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; }}
  th {{ background: #e8e8e8; }}
</style></head><body>{html_body}</body></html>"""
    weasyprint.HTML(string=html).write_pdf(str(dst))
    return dst.exists()


def _md_to_html_fallback(src: Path, dst_html: Path) -> bool:
    """Always-available HTML output. Open in browser → File → Print → Save as PDF."""
    try:
        import markdown  # type: ignore
        extensions = ['tables', 'fenced_code', 'toc']
        try:
            import pygments  # noqa
            extensions.append('codehilite')
        except ImportError:
            pass
        html_body = markdown.markdown(src.read_text(encoding='utf-8'), extensions=extensions)
    except ImportError:
        html_body = f'<pre>{src.read_text(encoding="utf-8")}</pre>'

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{src.stem}</title>
<script>
  window.MathJax = {{ tex: {{ inlineMath: [['$','$'],['\\\\(','\\\\)']] }},
                       svg: {{ fontCache: 'global' }} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
  body {{ font-family: 'DejaVu Serif', Georgia, serif; font-size: 11pt;
          line-height: 1.6; max-width: 820px; margin: 50px auto; padding: 0 30px; color: #111; }}
  h1 {{ font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ font-size: 15pt; color: #1a1a1a; border-bottom: 1px solid #bbb; margin-top: 28px; }}
  h3 {{ font-size: 12pt; color: #333; margin-top: 20px; }}
  code {{ background: #f5f5f5; padding: 2px 5px; border-radius: 3px; font-size: 9.5pt;
          font-family: 'DejaVu Sans Mono', 'Courier New', monospace; }}
  pre  {{ background: #f5f5f5; padding: 14px; border-radius: 5px; overflow-x: auto;
          font-size: 9pt; border-left: 3px solid #4a90d9;
          font-family: 'DejaVu Sans Mono', 'Courier New', monospace; }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 10pt; }}
  th, td {{ border: 1px solid #ccc; padding: 7px 11px; }}
  th {{ background: #eaeaea; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  blockquote {{ border-left: 4px solid #aaa; margin: 10px 0; padding: 4px 16px;
                color: #555; font-style: italic; }}
  @media print {{
    body {{ margin: 0; padding: 20px; }}
    a {{ color: #000; text-decoration: none; }}
  }}
</style>
</head><body>
{html_body}
</body></html>"""
    dst_html.write_text(html, encoding='utf-8')
    return True


# ─── Conversion pipeline ──────────────────────────────────────────────────────

_METHODS = [
    ('pandoc + xelatex',    _md_to_pdf_xelatex),
    ('pandoc + lualatex',   _md_to_pdf_lualatex),
    ('pandoc + pdflatex',   _md_to_pdf_pdflatex),   # ASCII-safe preprocessed copy
    ('pandoc + wkhtmltopdf', _md_to_pdf_pandoc_html),
    ('weasyprint',          _md_to_pdf_weasyprint),
]

def convert(src: Path, out_dir: Path) -> Path:
    src = src.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_pdf  = out_dir / (src.stem + '.pdf')
    dst_html = out_dir / (src.stem + '.html')

    # Remove stale output so we don't mistake an old file for success
    dst_pdf.unlink(missing_ok=True)

    print(f'\nConverting: {src.name}')
    for label, method in _METHODS:
        if method(src, dst_pdf):
            print(f'  ✓ PDF ({label}): {dst_pdf}')
            return dst_pdf

    # Final fallback — HTML
    _md_to_html_fallback(src, dst_html)
    print(f'  ⚠  All PDF methods failed — generated HTML: {dst_html}')
    print(f'     Open in browser → File → Print → Save as PDF')
    print(f'     (Equations render via MathJax)')
    return dst_html


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Convert Markdown to PDF')
    parser.add_argument('files', nargs='*',
                        help='.md files to convert (default: all .md in current dir)')
    parser.add_argument('--output-dir', '-o', default=None,
                        help='Output directory (default: same as source file)')
    args = parser.parse_args()

    here = Path(__file__).parent

    sources = [Path(f) for f in args.files] if args.files else sorted(here.glob('*.md'))
    if not sources:
        print('No .md files found.')
        sys.exit(1)

    # Tool availability summary
    print('=== md_to_pdf.py ===')
    tools = {
        'pandoc':      ('sudo apt install pandoc', _has('pandoc')),
        'xelatex':     ('sudo apt install texlive-xetex', _has('xelatex')),
        'lualatex':    ('sudo apt install texlive-luatex', _has('lualatex')),
        'pdflatex':    ('sudo apt install texlive-latex-recommended', _has('pdflatex')),
        'wkhtmltopdf': ('sudo apt install wkhtmltopdf', _has('wkhtmltopdf')),
    }
    for name, (install, found) in tools.items():
        status = '✓ found' if found else f'✗ not found  ({install})'
        print(f'  {name:<12}: {status}')
    try:
        import weasyprint  # noqa
        print(f'  {"weasyprint":<12}: ✓ found')
    except ImportError:
        print(f'  {"weasyprint":<12}: ✗ not found  (pip install weasyprint)')

    out_dir = Path(args.output_dir) if args.output_dir else None

    outputs = []
    for src in sources:
        if not src.exists():
            print(f'[WARN] File not found: {src}')
            continue
        dst = convert(src, out_dir or src.parent)
        outputs.append(dst)

    print(f'\nDone. {len(outputs)} file(s) converted.')
    for o in outputs:
        print(f'  {o}')


if __name__ == '__main__':
    main()
