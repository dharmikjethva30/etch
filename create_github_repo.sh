#!/bin/bash
# Creates a private GitHub repo for Etch and pushes the code.
# Requires: gh CLI (GitHub CLI) — install via: brew install gh

set -e

BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
CYAN="\033[36m"
RESET="\033[0m"

REPO_NAME="etch"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BOLD}Pushing Etch to GitHub...${RESET}"
echo ""

# ── Check gh CLI ──────────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
    echo -e "${RED}✗ GitHub CLI (gh) not found${RESET}"
    echo ""
    echo "  Install it with:  brew install gh"
    echo "  Then run:         gh auth login"
    echo "  Then re-run this script."
    exit 1
fi

# ── Check auth ───────────────────────────────────────────────────────────────
if ! gh auth status &>/dev/null; then
    echo -e "${RED}✗ Not logged into GitHub${RESET}"
    echo ""
    echo "  Run:  gh auth login"
    echo "  Then re-run this script."
    exit 1
fi

GH_USER=$(gh api user --jq .login)
echo -e "  ${GREEN}✓${RESET} Logged in as: $GH_USER"

# ── Create private repo ───────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

if gh repo view "$GH_USER/$REPO_NAME" &>/dev/null; then
    echo -e "  ${GREEN}✓${RESET} Repo $GH_USER/$REPO_NAME already exists"
    REPO_URL="git@github.com:$GH_USER/$REPO_NAME.git"
else
    echo -e "  Creating private repo: $GH_USER/$REPO_NAME..."
    gh repo create "$REPO_NAME" \
        --private \
        --description "Passive memory layer for AI coding tools" \
        --source=. \
        --remote=origin \
        --push
    echo -e "  ${GREEN}✓${RESET} Repo created and code pushed!"
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║  Done! Etch is on GitHub ✓                          ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ${CYAN}Repo:${RESET}    https://github.com/$GH_USER/$REPO_NAME"
    echo ""
    echo -e "  ${CYAN}Clone on any machine:${RESET}"
    echo -e "    git clone git@github.com:$GH_USER/$REPO_NAME.git"
    echo -e "    cd $REPO_NAME && bash install.sh"
    echo ""
    exit 0
fi

# ── Repo already existed — just push ─────────────────────────────────────────
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
git push -u origin main

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║  Done! Etch is on GitHub ✓                          ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${CYAN}Repo:${RESET}    https://github.com/$GH_USER/$REPO_NAME"
echo ""
echo -e "  ${CYAN}Clone & run on any machine:${RESET}"
echo -e "    git clone git@github.com:$GH_USER/$REPO_NAME.git"
echo -e "    cd $REPO_NAME && bash install.sh"
echo ""
