#!/usr/bin/env bash
# Launches the local button-driven UI at http://localhost:8501
set -e
cd "$(dirname "$0")"
if [ -d .venv ]; then
  source .venv/bin/activate
fi
streamlit run gui/app.py
