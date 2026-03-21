#!/bin/bash
# Etch — Global Install Script
# Run this once from your terminal to install the `etch` CLI globally

set -e

ETCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}Installing Etch...${RESET}"
echo ""

# ── 1. Check Python version ───────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null)
        if [ "$VERSION" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}✗ Python 3.10+ not found${RESET}"
    echo ""
    echo "  Install Python from: https://python.org/downloads"
    echo "  Or via Homebrew:  brew install python"
    exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  ${GREEN}✓${RESET} Python $PY_VERSION found"

# ── 2. Install etch package ───────────────────────────────────────────────────
echo -e "  Installing package from: $ETCH_DIR"
"$PYTHON" -m pip install -e "$ETCH_DIR" --quiet 2>&1 | tail -2

echo -e "  ${GREEN}✓${RESET} Package installed"

# ── 3. Find where etch binary landed ─────────────────────────────────────────
ETCH_BIN=$("$PYTHON" -m pip show -f etch 2>/dev/null | grep "etch$" | awk '{print $1}')
SCRIPTS_DIR=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('scripts'))")
ETCH_PATH="$SCRIPTS_DIR/etch"

# ── 4. Check if scripts dir is on PATH ───────────────────────────────────────
SHELL_RC=""
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ "$SHELL" == *"bash"* ]]; then
    SHELL_RC="$HOME/.bash_profile"
fi

if ! echo "$PATH" | grep -q "$SCRIPTS_DIR"; then
    echo ""
    echo -e "  ${YELLOW}⚠ $SCRIPTS_DIR is not on your PATH${RESET}"
    if [ -n "$SHELL_RC" ]; then
        echo ""
        echo -e "  Adding to $SHELL_RC..."
        echo "" >> "$SHELL_RC"
        echo "# Etch CLI" >> "$SHELL_RC"
        echo "export PATH=\"$SCRIPTS_DIR:\$PATH\"" >> "$SHELL_RC"
        echo -e "  ${GREEN}✓${RESET} PATH updated in $SHELL_RC"
        export PATH="$SCRIPTS_DIR:$PATH"
    else
        echo -e "  Add this to your shell config manually:"
        echo -e "  ${CYAN}export PATH=\"$SCRIPTS_DIR:\$PATH\"${RESET}"
    fi
fi

echo ""

# ── 5. Verify ────────────────────────────────────────────────────────────────
if command -v etch &>/dev/null; then
    echo -e "  ${GREEN}✓${RESET} etch is available globally"
else
    # Try direct path
    if [ -f "$ETCH_PATH" ]; then
        echo -e "  ${GREEN}✓${RESET} etch installed at: $ETCH_PATH"
        echo ""
        echo -e "  ${YELLOW}Restart your terminal or run:${RESET}"
        echo -e "  ${CYAN}source $SHELL_RC${RESET}"
    fi
fi

# ── 6. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Etch installed successfully ✓      ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${CYAN}Quick start:${RESET}"
echo ""
echo -e "    cd ~/your-project"
echo -e "    etch init          # set up project memory"
echo -e "    etch start         # start background watcher"
echo -e "    etch status        # see live activity"
echo -e "    etch projects      # see all tracked projects"
echo ""
echo -e "  ${CYAN}For Claude Code / Cursor:${RESET}"
echo ""
echo -e "    etch mcp           # get config to paste into your AI tool"
echo ""
