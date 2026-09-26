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

streamlit run gui/app.py
