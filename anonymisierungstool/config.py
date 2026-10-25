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
ORG_CONTACT = "%s · %s" % (ORG_NAME, ORG_WEB)  # bewusst keine persönliche E-Mail oder Telefonnummer: Kontakt über die Kontaktseite
LICENSE_NAME = "AGPL-3.0"
COPYRIGHT_YEAR = 2026
SPACY_MODEL = "de_core_news_md"
MAX_UPLOAD_MB = 25
DEFAULT_PORT = 8765  # feste Adresse, damit ein Lesezeichen im Browser immer funktioniert
