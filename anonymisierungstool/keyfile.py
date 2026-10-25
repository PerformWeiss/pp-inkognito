"""Schlüsseldatei (Zuordnung Original <-> Pseudonym) als einfache JSON-Datei, bewusst ohne Passwort."""
import json

KEY_NAME = "SCHLUESSEL_nicht_in_die_KI_laden.anonkey"


def dump_key(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def load_key(blob):
    if blob.startswith(b"ANK1"):
        raise ValueError("Diese Schlüsseldatei stammt aus einer früheren, verschlüsselten Version und wird nicht mehr unterstützt.")
    try:
        payload = json.loads(blob.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("Keine gültige Schlüsseldatei.")
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("Keine gültige Schlüsseldatei.")
    return payload
