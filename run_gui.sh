#!/usr/bin/env bash
# Launches the local button-driven UI at http://localhost:8501
#
# Safe to run every time: sets up the virtualenv on the very first run,
# reuses it afterwards, and permanently silences Streamlit's one-time
# "enter your email" onboarding prompt so it never blocks a double-click
# launch again.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Первый запуск — создаю окружение и ставлю зависимости (пару минут)..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
else
  source .venv/bin/activate
fi

mkdir -p "$HOME/.streamlit"
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

URL="http://localhost:8501"

# Ищем Chrome/Chromium вместо системного браузера по умолчанию. Проверяем
# только что нужный бинарь/flatpak вообще есть в PATH — без строгой
# проверки "приложение точно установлено" (flatpak info), которая на
# некоторых системах не проходит даже когда `flatpak run` работает.
CHROME_CMD=""
for c in "flatpak run com.google.Chrome" "flatpak run org.chromium.Chromium" \
         google-chrome google-chrome-stable chromium chromium-browser; do
  set -- $c
  if command -v "$1" >/dev/null 2>&1; then
    CHROME_CMD="$c"
    break
  fi
done

if [ -n "$CHROME_CMD" ]; then
  echo "Открою в Chrome: $CHROME_CMD"
  ( sleep 3 && $CHROME_CMD --new-window "$URL" >/dev/null 2>&1 & )
  streamlit run gui/app.py --server.headless true
else
  echo "Chrome не найден на этой системе — открываю в браузере по умолчанию."
  streamlit run gui/app.py
fi
