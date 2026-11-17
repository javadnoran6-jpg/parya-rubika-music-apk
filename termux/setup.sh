#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

while true; do
  clear || true
  echo "=================================================="
  echo "  Parya Rubika Music Bot | Termux & GitHub APK"
  echo "  Creator: پریا چش رنگی"
  echo "=================================================="
  echo "  1) Run Bot + Local APK Server (http://127.0.0.1:3000)"
  echo "  2) Push to GitHub & Build/Download APK"
  echo "  3) Change Rubika Bot Token"
  echo "  4) Test Rubika Token (getMe)"
  echo "  0) Exit"
  echo "=================================================="
  read -p "Select option [1-4, 0]: " CHOICE

  case "$CHOICE" in
    1)
      echo ""
      echo "[*] Enabling Termux wake-lock so Android keeps bot alive..."
      command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
      echo "[*] Starting Rubika Bot & APK Control Server on port ${PORT:-3000}..."
      echo "[*] Open the APK and select 'Termux Local (127.0.0.1:3000)'!"
      echo ""
      python3 bot/rubika_music_bot.py
      ;;
    2)
      bash termux/github-apk.sh
      read -p "Press Enter to return to menu..." _
      ;;
    3)
      read -p "Enter new Rubika Bot Token: " NEW_TOKEN
      if [ -n "$NEW_TOKEN" ]; then
        cat > .env << EOF
RUBIKA_BOT_TOKEN=${NEW_TOKEN}
RUBIKA_CREATOR_ID=u0_parya_creator
PORT=${PORT:-3000}
APP_URL=http://127.0.0.1:3000
EOF
        export RUBIKA_BOT_TOKEN="$NEW_TOKEN"
        echo "[OK] Token saved to .env!"
      fi
      sleep 1
      ;;
    4)
      python3 -c "import os,urllib.request,json; tok=os.getenv('RUBIKA_BOT_TOKEN',''); req=urllib.request.Request(f'https://botapi.rubika.ir/v3/{tok}/getMe', data=b'{}', headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(req, timeout=15).read().decode())" || echo "[!] Connection error"
      read -p "Press Enter to continue..." _
      ;;
    0)
      exit 0
      ;;
    *)
      echo "Invalid choice."
      sleep 1
      ;;
  esac
done
