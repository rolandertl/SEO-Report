#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

if [ -x "$PROJECT_DIR/.venv/bin/streamlit" ]; then
  STREAMLIT_BIN="$PROJECT_DIR/.venv/bin/streamlit"
elif [ -x "$PROJECT_DIR/venv/bin/streamlit" ]; then
  STREAMLIT_BIN="$PROJECT_DIR/venv/bin/streamlit"
elif command -v streamlit >/dev/null 2>&1; then
  STREAMLIT_BIN="$(command -v streamlit)"
else
  echo "Streamlit wurde nicht gefunden."
  echo "Bitte zuerst die Abhängigkeiten installieren."
  read -k 1 "?Taste drücken zum Beenden ..."
  exit 1
fi

echo "Starte SEO-Report aus: $PROJECT_DIR"
echo "Verwende: $STREAMLIT_BIN"
echo ""

"$STREAMLIT_BIN" run app.py
