#!/usr/bin/env bash
# build.sh — Compile paper.tex to paper.pdf (IEEE format)
# Usage:
#   ./build.sh            # full build (pdflatex → bibtex → pdflatex × 2)
#   ./build.sh --clean    # remove all auxiliary files
#   ./build.sh --watch    # rebuild on file change (requires inotifywait)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEX_FILE="paper.tex"
BASE="paper"
cd "$SCRIPT_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[build]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn] ${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

# ── Clean mode ───────────────────────────────────────────────────────────────
clean() {
    info "Removing auxiliary files..."
    rm -f "${BASE}.aux" "${BASE}.bbl" "${BASE}.blg" "${BASE}.log" \
          "${BASE}.out" "${BASE}.toc" "${BASE}.fls" "${BASE}.fdb_latexmk" \
          "${BASE}.synctex.gz" "${BASE}.run.xml" "${BASE}-blx.bib" \
          texput.log missfont.log
    info "Done. PDF kept (${BASE}.pdf)."
}

if [[ "${1:-}" == "--clean" ]]; then clean; exit 0; fi

# ── Dependency check ─────────────────────────────────────────────────────────
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        error "'$1' not found. Install with: sudo apt-get install $2"
        exit 1
    fi
}

check_dep pdflatex "texlive-latex-base"
check_dep bibtex   "texlive-bibtex-extra"

# ── Build function ────────────────────────────────────────────────────────────
build() {
    info "Pass 1/4 — pdflatex (initial)"
    pdflatex -interaction=nonstopmode -halt-on-error "${TEX_FILE}" \
        | grep -E "(^!|Warning|Error|Overfull|Underfull)" || true

    info "Pass 2/4 — bibtex (bibliography)"
    bibtex "${BASE}" 2>&1 | grep -v "^This is BibTeX" || true

    info "Pass 3/4 — pdflatex (resolve citations)"
    pdflatex -interaction=nonstopmode -halt-on-error "${TEX_FILE}" \
        | grep -E "(^!|Warning|Error|Overfull|Underfull)" || true

    info "Pass 4/4 — pdflatex (finalise cross-refs)"
    pdflatex -interaction=nonstopmode -halt-on-error "${TEX_FILE}" \
        | grep -E "(^!|Warning|Error|Overfull|Underfull)" || true

    if [[ -f "${BASE}.pdf" ]]; then
        SIZE=$(du -sh "${BASE}.pdf" | cut -f1)
        info "Build successful → ${SCRIPT_DIR}/${BASE}.pdf  (${SIZE})"
    else
        error "PDF was not produced. Check ${BASE}.log for details."
        exit 1
    fi
}

# ── Watch mode ────────────────────────────────────────────────────────────────
watch() {
    if ! command -v inotifywait &>/dev/null; then
        warn "'inotifywait' not found. Install: sudo apt-get install inotify-tools"
        warn "Falling back to single build."
        build; exit 0
    fi
    info "Watch mode active. Monitoring ${TEX_FILE} and references.bib ..."
    info "Press Ctrl+C to stop."
    build
    while inotifywait -e close_write -q "${TEX_FILE}" references.bib; do
        info "Change detected — rebuilding..."
        build
    done
}

if [[ "${1:-}" == "--watch" ]]; then watch; exit 0; fi

# ── Default: full build ───────────────────────────────────────────────────────
build
