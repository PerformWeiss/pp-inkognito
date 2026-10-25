"""Einstellungen und Branding. Firmendaten aus dem öffentlichen Impressum von performplus.de; vor der Veröffentlichung bestätigen."""

APP_NAME = "PP-Inkognito"
ORG_NAME = "PerformPlus GmbH"
ORG_SLOGAN = "we empower people."
ORG_ADDRESS = "Im Birket 6, 82166 Gräfelfing/München"
ORG_WEB = "https://performplus.de"
ORG_LINKS = {
    "web": "https://performplus.de",
    "kontakt": "https://performplus.de/kontakt/",
    "impressum": "https://performplus.de/impressum/",
    "datenschutz": "https://performplus.de/datenschutz-2/",
}
# Persönliche Kontaktdaten stehen NICHT im Quelltext (öffentliches Repository). Sie liegen in der Datei kontakt_privat.json
# (in .gitignore), die beim Bauen der Installer aus einem GitHub-Geheimnis erzeugt wird. Fehlt die Datei, zeigt das Programm nur
# die Firmendaten und die Links.
import json as _json
from pathlib import Path as _Path

try:
    _priv = _json.loads((_Path(__file__).parent / "kontakt_privat.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    _priv = {}
ORG_PERSON = _priv.get("person", "")
ORG_EMAIL = _priv.get("email", "")
ORG_PHONE = _priv.get("phone", "")
ORG_CONTACT = " · ".join(x for x in (ORG_EMAIL, ORG_PHONE, ORG_WEB) if x) or ORG_WEB
LICENSE_NAME = "AGPL-3.0"
COPYRIGHT_YEAR = 2026
SPACY_MODEL = "de_core_news_md"
MAX_UPLOAD_MB = 25
DEFAULT_PORT = 8765  # feste Adresse, damit ein Lesezeichen im Browser immer funktioniert
