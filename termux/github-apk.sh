#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo ""
echo "=================================================="
echo "  GitHub APK Builder from Termux"
echo "=================================================="

if ! command -v git >/dev/null 2>&1 || ! command -v gh >/dev/null 2>&1; then
  echo "[*] Installing git & GitHub CLI (gh) in Termux..."
  pkg install -y git gh
fi

if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "[*] Login to your GitHub account (choose HTTPS -> Login with web browser or Token):"
  gh auth login
fi

GH_USER="$(gh api user --jq '.login')"
echo "[OK] Logged into GitHub as: $GH_USER"

if [ -z "$(git config user.name || true)" ]; then
  git config user.name "$GH_USER"
fi
if [ -z "$(git config user.email || true)" ]; then
  git config user.email "${GH_USER}@users.noreply.github.com"
fi

if [ ! -d .git ]; then
  git init -b main
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "Rubika Music Bot + Android APK (Termux Push)"
fi

read -p "GitHub repository name [parya-rubika-music-apk]: " REPO_NAME
REPO_NAME="${REPO_NAME:-parya-rubika-music-apk}"

if ! git remote get-url origin >/dev/null 2>&1; then
  if gh repo view "$GH_USER/$REPO_NAME" >/dev/null 2>&1; then
    git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
    gh auth setup-git
    git push -u origin main --force
  else
    gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
  fi
else
  gh auth setup-git
  git push -u origin main --force
fi

echo ""
echo "[*] Triggering GitHub Actions APK build workflow..."
sleep 2
gh workflow run build-apk.yml || true

echo "[*] Waiting for GitHub Actions to start..."
sleep 5
RUN_ID="$(gh run list --workflow=build-apk.yml --limit=1 --json databaseId --jq '.[0].databaseId')"

if [ -n "$RUN_ID" ]; then
  echo "[*] Watching build run #$RUN_ID (Panel APK takes ~90 seconds)..."
  gh run watch "$RUN_ID" --exit-status || true

  OUT_DIR="/sdcard/Download/ParyaRubikaAPK"
  if [ ! -d "/sdcard/Download" ]; then
    termux-setup-storage || true
    sleep 2
  fi
  mkdir -p "$OUT_DIR" || OUT_DIR="$ROOT_DIR/apk_output"
  mkdir -p "$OUT_DIR"

  echo "[*] Downloading compiled APK(s) to: $OUT_DIR"
  gh run download "$RUN_ID" -D "$OUT_DIR" || true
  echo ""
  echo "[SUCCESS] Check your Download folder:"
  find "$OUT_DIR" -name "*.apk" 2>/dev/null || ls -la "$OUT_DIR"
else
  echo "[!] Open GitHub Actions tab to download your APK:"
  echo "    https://github.com/$GH_USER/$REPO_NAME/actions"
fi
