"""Pseudonyme erzeugen und die Zuordnungstabelle (Schlüssel) aufbauen."""
import random
import re
from dataclasses import dataclass

from .textutil import term_regex
from .vornamen import FEMALE, MALE

REDACTED = "[geschwärzt]"
MONTH_NAMES = "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split()
DATE_MODES = {
    "jahr": "Jahr behalten",
    "verschieben": "Jahr um 1–2 verschieben",
    "schwaerzen": "Entfernen",
}
RX_NUM_DATE = re.compile(r"(\d{1,2})\.\s?(\d{1,2})\.\s?((?:19|20)?\d{2})")
RX_TXT_DATE = re.compile(r"(\d{1,2})\.?\s+(%s|Maerz)\s+((?:19|20)\d{2})" % "|".join(MONTH_NAMES))
RX_ISO_DATE = re.compile(r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})")
RX_SLASH_DATE = re.compile(r"(\d{1,2})([/-])(\d{1,2})\2((?:19|20)\d{2})")


@dataclass
class Item:
    text: str
    category: str
    action: str = "pseudonym"  # oder "schwaerzen"
    mode: str = ""  # nur Geburtsdatum: eigener Modus aus DATE_MODES, sonst der allgemeine
    main: bool = False  # Hauptperson (Bewerber/in)
    gender: str = ""  # "f", "m" oder unbekannt
    override: str = ""  # vom Nutzer gewähltes Pseudonym


def _letters(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _shift_year(year_txt, shift):
    y = int(year_txt)
    if len(year_txt) == 2:
        return "%02d" % ((y + shift) % 100)
    return str(y + shift)


def _date_replacement(text, mode, shift):
    t = text.strip()
    for rx, ygroup in ((RX_ISO_DATE, 1), (RX_SLASH_DATE, 4)):  # Jahr-Monat-Tag und Tag/Monat/Jahr
        m = rx.fullmatch(t)
        if m and mode != "schwaerzen":
            if mode == "verschieben":
                return text[:m.start(ygroup)] + _shift_year(m.group(ygroup), shift) + text[m.end(ygroup):], True
            return m.group(ygroup), False
        if m:
            return REDACTED, False
    m = RX_NUM_DATE.fullmatch(text.strip())
    kind = "num"
    if not m:
        m = RX_TXT_DATE.fullmatch(text.strip())
        kind = "txt"
    if not m or mode == "schwaerzen":
        return REDACTED, False
    d, mo, y = m.groups()
    if mode == "verschieben":
        ny = _shift_year(y, shift)
        return text[:m.start(3)] + ny + text[m.end(3):], True
    year = y if len(y) == 4 else ("20" if int(y) < 40 else "19") + y
    if mode == "jahr":
        return year, False
    month = ("%02d" % int(mo)) if kind == "num" else mo
    return "%s/%s" % (month, year) if kind == "num" else "%s %s" % (month, year), False


# Alle Pseudonyme sollen eindeutig erfunden wirken ("Muster..."), nie wie echte Namen oder Orte.
FAKE_PLACES = ["Musterstadt", "Musterdorf", "Musterhausen", "Musterheim", "Musterbach", "Musterfeld", "Musterau"]
FAKE_STREETS = ["Musterstraße", "Musterweg", "Musterallee", "Musterplatz", "Mustergasse", "Musterring", "Musterdamm"]
FAKE_PHONES = ["123456", "234567", "345678", "456789", "567890", "678901", "789012", "890123", "901234"]
FAKE_PLZ = ["12345", "23456", "34567", "45678", "56789", "67890", "78901", "89012", "90123"]
RX_PLZ = re.compile(r"\b\d{5}\b")


# Erfundene Namen: Vornamen aus einer kleinen Liste (Länge möglichst ähnlich zum Original, damit das Layout passt), Nachnamen "Muster...".
# Ein Vorname, der im Dokument selbst vorkommt, wird nie als Pseudonym gewählt; so bleibt das Zurückspielen eindeutig.
FAKE_FIRST = {
    "f": ["Eva", "Ida", "Mia", "Lea", "Anna", "Lisa", "Nora", "Elke", "Julia", "Sarah", "Marta", "Silke", "Helga", "Monika", "Barbara",
          "Susanne", "Katharina", "Charlotte"],
    "m": ["Jan", "Tim", "Max", "Uwe", "Karl", "Paul", "Hans", "Horst", "Peter", "Martin", "Stefan", "Walter", "Rainer", "Michael",
          "Thomas", "Andreas", "Bernhard", "Christian", "Alexander"],
    "": ["Alex", "Kim", "Robin", "Sascha", "Toni", "Nico", "Eike", "Jule", "Charlie", "Dominique"],
}
FAKE_LAST = ["Muster", "Mustel", "Musterl", "Musterer", "Musterle", "Musterberg", "Musterwald", "Musterstein",
             "Mustermeier", "Musterhuber", "Musterländer", "Mustermüller", "Musterschmidt", "Musterbauer"]  # bewusst nicht Mustermann/Musterfrau (geschlechtsbezogen)
PARTICLES = {"von", "van", "vom", "zu", "zur", "de", "del", "della", "der", "den", "ten", "ter", "la", "le", "di", "da", "dos", "du", "bin", "ibn", "al", "el", "af"}


def _case(orig, fake):
    if len(orig) > 1 and orig.isupper():
        return fake.upper()
    return fake.lower() if len(orig) > 1 and orig.islower() else fake


class _Names:
    """Namen werden Teil für Teil ersetzt: gleicher Vorname -> gleicher erfundener Vorname, gleicher Nachname -> gleicher erfundener
    Nachname. So ergibt "Fritz Müller" -> "Max Mustermann", "Fritz" -> "Max" und "Müller" -> "Mustermann"."""

    def __init__(self, store, avoid=()):
        self.s = store
        for k, v in (("first", {}), ("last", {})):
            store.setdefault(k, v)
        # Wörter, die nicht als Pseudonym dienen dürfen: alles im Dokument und die bisherigen Originale dieses Titels
        self.avoid = {w.lower() for w in avoid} | set(store["first"]) | set(store["last"])

    def _pick(self, kind, token, gender):
        used = {v.lower() for v in self.s[kind].values()} | self.avoid
        tiers = [FAKE_FIRST[gender], FAKE_FIRST[""], FAKE_FIRST["f"] + FAKE_FIRST["m"]] if kind == "first" else [FAKE_LAST]
        for tier in tiers:  # erst die Liste zum Geschlecht, dann neutrale Namen
            cands = [c for c in tier if c.lower() not in used]
            if cands:  # möglichst gleich lang wie das Original, bei Gleichstand in Listenreihenfolge
                return min(cands, key=lambda c: abs(len(c) - len(token)))
        n = 0
        while ("%s%s" % ("Muster", _letters(n))).lower() in used:
            n += 1
        return "Muster%s" % _letters(n)

    def part(self, kind, token, gender):
        k = token.lower()
        if k not in self.s[kind]:
            self.s[kind][k] = self._pick(kind, token, gender)
        return _case(token, self.s[kind][k])

    def render(self, it):
        text, gender = it.text.strip(), (it.gender if it.gender in ("f", "m") else "")
        if "," in text:  # "Müller, Fritz"
            last, _, rest = text.partition(",")
            firsts, last = rest.split(), last.strip()
        else:
            toks = text.split()
            i = len(toks) - 1
            while i > 0 and toks[i - 1] in PARTICLES:
                i -= 1
            firsts, last = toks[:i], " ".join(toks[i:])
            if not firsts:  # einzelnes Wort: Vorname oder Nachname?
                low = last.lower()
                if low in self.s["first"] or (low not in self.s["last"] and low.split("-")[0] in (FEMALE | MALE)):
                    firsts, last = [last], ""
        out = []
        for t in firsts:
            g = gender or ("f" if t.lower().split("-")[0] in FEMALE else "m" if t.lower().split("-")[0] in MALE else "")
            out.append(self.part("first", t, g))
        if last:
            fl = self.part("last", last, gender)
            out = ["%s," % fl] + out if "," in text else out + [fl]
        return " ".join(out)


def _fake_place(n):
    return FAKE_PLACES[n] if n < len(FAKE_PLACES) else "Musterort %d" % (n + 1)


def _fake_street(n):
    return "%s %d" % (FAKE_STREETS[n % len(FAKE_STREETS)], n + 1)


def _fake_plz(n):
    return FAKE_PLZ[n] if n < len(FAKE_PLZ) else "%05d" % (10000 + (1111 * (n + 1)) % 89999)


def _counter_key(category, original):
    """Zählergruppe: Adressen zählen getrennt für Straßen und Postleitzahl+Ort, damit "Musterstraße 1" und "12345 Musterstadt" zusammenpassen."""
    if category == "adresse":
        return "adresse_plz" if RX_PLZ.search(original) and not original[:RX_PLZ.search(original).start()].strip(" ,-–|") else "adresse_str"
    return category


def build_mapping(items, date_mode="jahr", rng=None, key=None, avoid=()):
    """Gibt (mapping, key_entries) zurück. mapping: Originaltext -> Ersatztext.

    key: Schlüsseldaten eines Titels (dict mit "entries"). Schon vergebene Pseudonyme werden weiterverwendet, neue
    fortlaufend ergänzt und in key["entries"] eingetragen (key wird dabei verändert). key_entries enthält nur die
    Einträge, die in diesem Dokument vorkommen. avoid: Wörter des Dokuments, die nicht als Namens-Pseudonym dienen dürfen."""
    rng = rng or random.SystemRandom()
    key = key if key is not None else {}
    known = {e["original"]: e for e in key.get("entries", [])}
    shift = key.get("date_shift") or rng.choice([-2, -1, 1, 2])
    key["date_shift"] = shift
    counters, assigned, variant_counts = {}, [], {}  # assigned: (item, replacement) der Hauptbegriffe
    used, place_map = set(), {}
    own = {w.lower() for it in items if it.category == "name" for w in re.split(r"[\s,]+", it.text) if w}
    names = _Names(key.setdefault("name_parts", {}), set(avoid) | own)  # auch die eigenen Namen dürfen nicht als Pseudonym dienen
    for e in known.values():
        used.add(e["replacement"])
        if e["replacement"] == REDACTED or e["category"] == "name":
            continue
        if e.get("variant"):
            base, _, num = e["replacement"].rpartition("-")
            variant_counts[base] = max(variant_counts.get(base, 1), int(num) if num.isdigit() else 1)
        else:
            ck = _counter_key(e["category"], e["original"])
            counters[ck] = counters.get(ck, 0) + 1
            assigned.append((Item(e["original"], e["category"]), e["replacement"]))
            if e["category"] == "ort":
                place_map[e["original"]] = e["replacement"]
    mapping, entries = {}, []
    seen = set()

    def fresh(make, ck):
        """Nächstes noch nicht vergebenes Pseudonym der Gruppe ck."""
        while True:
            n = counters.get(ck, 0)
            counters[ck] = n + 1
            repl = make(n)
            if repl not in used:
                return repl

    def place_for(text):
        if text not in place_map:
            place_map[text] = fresh(_fake_place, "ort")
        return place_map[text]

    for it in sorted(items, key=lambda i: -len(i.text)):
        if not it.text or it.text in seen:
            continue
        seen.add(it.text)
        old = known.get(it.text)
        if old and old["replacement"] != REDACTED and it.action != "schwaerzen" and not it.override:
            mapping[it.text] = old["replacement"]
            entries.append(old)
            continue
        variant_of = None
        if it.action != "schwaerzen" and not it.override:
            for prim, repl in assigned:
                if prim.category == it.category and it.category in ("firma", "ort") and \
                        term_regex([it.text]).search(prim.text):
                    variant_of = repl
                    break
        if it.action == "schwaerzen":
            repl, reversible = REDACTED, False
        elif it.override:
            repl, reversible = it.override, True  # vom Nutzer überschrieben; Kurzformen folgen dem neuen Namen
            assigned.append((it, repl))
        elif variant_of:
            # Kurzform (z. B. nur der Nachname) bekommt dasselbe Pseudonym wie der volle Name; beim Zurückspielen
            # wird daraus der volle Name
            repl, reversible = variant_of, True
        else:
            reversible = True
            cat = it.category
            if cat == "name":
                repl = names.render(it)
            elif cat == "firma":
                repl = fresh(lambda n: "Musterfirma %s" % _letters(n), "firma")
            elif cat == "ort":
                repl = place_map.get(it.text) or fresh(_fake_place, "ort")
            elif cat == "projekt":
                repl = fresh(lambda n: "Projekt %s" % _letters(n), "projekt")
            elif cat == "email":
                repl = fresh(lambda n: "muster@example.com" if n == 0 else "muster%d@example.com" % (n + 1), "email")
            elif cat == "telefon":
                repl = fresh(lambda n: "0xxx %s" % (FAKE_PHONES[n] if n < len(FAKE_PHONES) else "%06d" % n), "telefon")
            elif cat == "adresse":
                m = RX_PLZ.search(it.text)
                street = it.text[:m.start()].strip(" ,-–|") if m else it.text
                if not m:
                    repl = fresh(_fake_street, "adresse_str")
                else:
                    rest = it.text[m.end():].strip(" ,")
                    repl = " ".join(x for x in (fresh(_fake_plz, "adresse_plz"), place_for(rest) if rest else "") if x)
                    if street:
                        repl = "%s, %s" % (fresh(_fake_street, "adresse_str"), repl)
            elif cat == "iban":
                repl = fresh(lambda n: "DE00 0000 0000 0000 %04d 00" % n, "iban")
            elif cat == "url":
                repl = fresh(lambda n: "www.example.com/profil" if n == 0 else "www.example.com/profil%d" % (n + 1), "url")
            elif cat == "geburtsdatum":
                repl, reversible = _date_replacement(it.text, it.mode if it.mode in DATE_MODES else date_mode, shift)
            else:
                repl = fresh(lambda n: "[Angabe %d]" % (n + 1), "sonstiges")
            assigned.append((it, repl))
        used.add(repl)
        if it.category == "ort" and repl != REDACTED:
            place_map.setdefault(it.text, repl)
        mapping[it.text] = repl
        entries.append({
            "original": it.text, "replacement": repl, "category": it.category,
            "reversible": reversible, "variant": variant_of is not None,
        })
    merged = {e["original"]: e for e in key.get("entries", [])}
    for e in entries:
        cur = merged.get(e["original"])
        if cur is None or (cur["replacement"] == REDACTED and e["replacement"] != REDACTED) or e["replacement"] != (cur or {}).get("replacement") and any(i.override and i.text == e["original"] for i in items):
            merged[e["original"]] = e
    key["entries"] = list(merged.values())
    return mapping, entries


_FN_SEP = r"[\s_.\-]*"


def anonymize_filename(stem, mapping, name_parts=None):
    """Dateiname ohne Endung: erkannte Begriffe (und einzelne Namensteile) werden durch ihr Pseudonym ersetzt, auch wenn sie mit
    _ - . oder ohne Trennzeichen geschrieben sind ("Max_Mustermann", "MaxMustermann"). Ergebnis ist ein sicherer Dateiname."""
    pairs = {k: v for k, v in mapping.items() if len(k.strip()) >= 3}
    for kind in ("first", "last"):
        for orig, fake in ((name_parts or {}).get(kind) or {}).items():
            if len(orig) >= 3:
                pairs.setdefault(orig, fake)
    out = stem
    for orig in sorted(pairs, key=len, reverse=True):
        toks = [t for t in re.split(r"[\s_.\-]+", orig.strip()) if t]
        if not toks:
            continue
        rx = re.compile(_FN_SEP.join(re.escape(t) for t in toks), re.I)  # bewusst ohne Wortgrenzen: im Dateinamen lieber zu viel ersetzen
        fake = re.sub(r"\s+", "_", pairs[orig].strip())
        out = rx.sub(lambda m: fake, out)
    out = re.sub(r"[\x00-\x1f/\\:*?\"<>|]", "", out).strip(" .")
    return out or "Dokument"
