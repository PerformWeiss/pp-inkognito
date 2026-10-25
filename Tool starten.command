#!/bin/bash
# Doppelklick zum Starten (macOS). Das Tool öffnet sich im Browser; Beenden mit dem Button "Beenden" oder Ctrl+C.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Die Python-Umgebung fehlt. Bitte zuerst die Installation aus der README durchführen."
  read -n 1 -s -r -p "Beliebige Taste zum Schließen ..."
  exit 1
fi
.venv/bin/python app.py
