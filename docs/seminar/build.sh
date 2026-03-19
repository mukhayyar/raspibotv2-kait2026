#!/usr/bin/env bash
# ============================================================
# build.sh — Build PENS-KAIT 2026 seminar LaTeX PDF
#
# Requirements:
#   - pdflatex  (texlive-full or texlive-latex-extra)
#   - mmdc      (optional) mermaid-cli: npm install -g @mermaid-js/mermaid-cli
#
# Usage:
#   cd docs/seminar && ./build.sh
# ============================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Checking LaTeX dependencies..."
if ! command -v pdflatex &>/dev/null; then
    echo "  [!] pdflatex not found."
    echo "      Install: sudo apt install texlive-latex-extra texlive-fonts-recommended"
    echo "      Or full: sudo apt install texlive-full"
    exit 1
fi

# ── Optional: render Mermaid diagrams to PNG ─────────────────
echo "==> Rendering Mermaid diagrams..."
mkdir -p figures
if command -v mmdc &>/dev/null; then
    for mmd_file in diagrams/*.mmd; do
        base=$(basename "$mmd_file" .mmd)
        echo "  Rendering: $mmd_file -> figures/${base}.png"
        mmdc -i "$mmd_file" -o "figures/${base}.png" \
             -w 1200 -H 800 --backgroundColor white 2>/dev/null || \
        echo "  [warn] Failed to render $mmd_file — skipping"
    done
else
    echo "  [warn] mmdc not found — skipping Mermaid PNG generation."
    echo "         Install: npm install -g @mermaid-js/mermaid-cli"
    echo "         Or view diagrams online at https://mermaid.live"
    echo "         The LaTeX document uses TikZ diagrams and will compile without PNGs."
fi

# ── Compile LaTeX (run twice for references/TOC) ─────────────
echo "==> Compiling main.tex (pass 1)..."
pdflatex -interaction=nonstopmode -halt-on-error main.tex

echo "==> Compiling main.tex (pass 2, for TOC & cross-refs)..."
pdflatex -interaction=nonstopmode -halt-on-error main.tex

# ── Clean auxiliary files ─────────────────────────────────────
echo "==> Cleaning auxiliary files..."
rm -f main.aux main.log main.out main.toc main.lof main.lot

echo ""
echo "✓ Done! Output: docs/seminar/main.pdf"
echo ""
echo "To view Mermaid diagrams interactively:"
echo "  - Open any .mmd file in VS Code with the Mermaid extension"
echo "  - Or paste contents at https://mermaid.live"
