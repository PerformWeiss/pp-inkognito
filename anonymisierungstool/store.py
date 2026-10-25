"""Lokales Wörterbuch: Begriffe, die das Tool aus Korrekturen gelernt hat (nur auf diesem Rechner)."""
import json
import os
from pathlib import Path


def data_dir():
    base = os.environ.get("ANONYMISIERUNGSTOOL_HOME") or str(Path.home() / ".anonymisierungstool")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings():
    try:
        data = json.loads((data_dir() / "einstellungen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings):
    (data_dir() / "einstellungen.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def _file():
    return data_dir() / "woerterbuch.json"


def load_dictionary():
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("text") and e.get("category")]


def _save(entries):
    _file().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def add_entry(text, category):
    text = text.strip()
    entries = load_dictionary()
    if text and not any(e["text"] == text and e["category"] == category for e in entries):
        entries.append({"text": text, "category": category})
        _save(entries)
    return entries


def remove_entry(text, category):
    entries = [e for e in load_dictionary() if not (e["text"] == text and e["category"] == category)]
    _save(entries)
    return entries
