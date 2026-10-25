"""Rückspielen: Pseudonyme in einem (von einer KI überarbeiteten) Dokument wieder durch die Originalangaben ersetzen."""
import re

from .pseudonymize import FAKE_PLACES, FAKE_STREETS
from .textutil import count_occurrences, term_regex

# Muster der vom Tool erzeugten Pseudonyme; dient dazu, unbekannte oder veränderte Pseudonyme zu melden.
RX_GENERIC = re.compile(
    r"(?<!\w)(?:(?:Person|Firma|Musterfirma|Ort|Projekt) [A-Z]{1,3}(?:-\d+)?|Musterort \d+|"
    r"(?:" + "|".join(FAKE_PLACES) + r")(?:-\d+)?|"
    r"(?:" + "|".join(FAKE_STREETS) + r") \d+)(?!\w)"
    r"|\[(?:Telefon|Adresse|IBAN|Link|Angabe) \d+\]|(?:kontakt|muster)\d*@example\.(?:invalid|com)"
)


def build_reverse(payload):
    """Gibt (mapping, nicht_rückspielbar) zurück. mapping: Pseudonym -> Original."""
    mapping, lost = {}, 0
    entries = payload.get("entries", [])
    # Zuerst die vollen Namen; Kurzformen mit demselben Pseudonym werden dadurch zum vollen Namen
    for e in sorted(entries, key=lambda e: bool(e.get("variant"))):
        if not e.get("reversible"):
            lost += 1
        elif e["replacement"] not in mapping:
            mapping[e["replacement"]] = e["original"]
    return mapping, lost


def plan(text, mapping):
    """Bericht vor dem Ersetzen: was wird wie oft zurückgesetzt, was fehlt, was ist unbekannt."""
    restored, missing = [], []
    for repl, orig in mapping.items():
        n = count_occurrences(text, repl)
        (restored if n else missing).append({"replacement": repl, "original": orig, "count": n})
    known = [m.span() for m in term_regex(mapping.keys()).finditer(text)] if mapping else []  # "23456 Musterhausen" enthält "Musterhausen"
    unknown = sorted({m.group(0) for m in RX_GENERIC.finditer(text) if not any(a <= m.start() and m.end() <= b for a, b in known)} - set(mapping))
    return {"restored": restored, "missing": missing, "unknown": unknown}


def regex_for(mapping):
    return term_regex(mapping.keys())
