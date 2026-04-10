#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif [ -x "$PROJECT_DIR/venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Python wurde nicht gefunden."
  read -k 1 "?Taste drücken zum Beenden ..."
  exit 1
fi

echo "Starte SEO-Report aus: $PROJECT_DIR"
echo "Verwende Python: $PYTHON_BIN"
echo ""

"$PYTHON_BIN" -m streamlit run app.py
