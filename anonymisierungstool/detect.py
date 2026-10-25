"""Erkennung personenbezogener Daten: Wörterbuch, feste Muster, Lebenslauf-Muster, lokales Sprachmodell (spaCy)."""
import re
from datetime import datetime
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from . import store
from .config import SPACY_MODEL
from .gazetteer import PLACE_SET, RX_PLACES, RX_PLACES_UPPER
from .vornamen import FEMALE, MALE
from .textutil import count_occurrences, term_regex

CATEGORIES = {
    "name": "Name",
    "geburtsdatum": "Geburtsdatum",
    "adresse": "Adresse",
    "email": "E-Mail",
    "telefon": "Telefon",
    "iban": "IBAN",
    "url": "Link / Profil",
    "firma": "Firma / Institution",
    "projekt": "Projekt",
    "ort": "Ort",
    "sonstiges": "Sonstiges",
}
# Reihenfolge in den Auswahlmenüs: Häufiges zuerst, einmalige Angaben (Name, Geburtsdatum ...) weiter unten.
DROPDOWN_ORDER = ["firma", "projekt", "ort", "name", "geburtsdatum", "adresse", "email", "telefon", "iban", "url", "sonstiges"]
# Diese Kategorien sind vorausgewählt; Firmen und Orte bewusst nicht.
DEFAULT_ON = {"name", "geburtsdatum", "adresse", "email", "telefon", "iban", "url"}

SOURCE_LABELS = {
    "woerterbuch": "Wörterbuch",
    "muster": "Muster",
    "lebenslauf": "Lebenslauf-Muster",
    "modell": "Sprachmodell",
    "wohnort": "Wohnort aus der Adresse",
}

PRIO = {"woerterbuch": 0, "wohnort": 1, "muster": 1, "lebenslauf": 2, "modell": 3}


@dataclass
class Cand:
    start: int
    end: int
    category: str
    source: str
    confident: bool = True


# ---------------------------------------------------------------- feste Muster
MONTHS = "Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
RX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RX_URL = re.compile(r"(?i)\b(?:https?://|www\.|(?:[\w-]+\.)?(?:linkedin|xing|github|instagram|facebook)\.[a-z]{2,}/)[^\s<>\"']+")
RX_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[\dA-Z]{4}){3,7}(?:\s?[\dA-Z]{1,4})?\b")
RX_PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}|\(?0\d)[\d \t/()\-]{5,}\d")
RX_PHONE_NOT = re.compile(r"\b(?:0?[1-9]|1[0-2])\s*/\s*(?:19|20)\d\d")
# "09/77 - 07/85", "06/23-09/24", "01.2010 - 05.2012": Zeiträume mit Monat/Jahr, keine Telefonnummern
RX_PHONE_DATERANGE = re.compile(r"^\(?\s*(?:0?[1-9]|1[0-2])\s*[/.]\s*(?:\d{2}|\d{4})\s*(?:[-–—]|bis)\s*(?:0?[1-9]|1[0-2])\s*[/.]\s*(?:\d{2}|\d{4})\s*\)?$")
RX_DATE = re.compile(
    r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19|20)?\d{2}\b|\b\d{1,2}\.?\s+(?:%s)\s+(?:19|20)\d{2}\b"
    r"|\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}([/-])\d{1,2}\1(?:19|20)\d{2}\b" % MONTHS
)
RX_BIRTH_CTX = re.compile(r"(?i)geb(?:oren|urt|\.)|\bborn\b|\bdob\b|\*\s*$")
STREET_WORDS = r"(?i:stra(?:ß|ss)e|str\.?|weg|allee|platz|gasse|ring|damm|ufer|chaussee|steig|pfad|hof|markt|anlage|anger|garten|park|promenade|wall|zeile|kai|siedlung|bogen)"
RX_STREET = re.compile(
    r"\b[A-ZÄÖÜ][\wäöüß\-]*(?:[ \-][A-ZÄÖÜ][\wäöüß\-]*)?[ \t]?" + STREET_WORDS + r"[ \t]*(?:\d{1,4}(?![\d.,]\d)(?:[ ]?[a-zA-Z]\b)?|\d{6,8}\b)"
)
RX_STREET_PREFIX = re.compile(r"\b(?:Am|An der|An den|Auf dem|Im|In der|Zum|Zur)[ \t]+[A-ZÄÖÜ][\wäöüß\-]+[ \t]+\d{1,4}(?![\d.,]\d)(?:[ ]?[a-z]\b)?")
# Straße ohne typische Endung (z. B. "Obere Wiesen 5a"), erkannt an der folgenden Postleitzahl
RX_STREET_PLZ = re.compile(
    r"(?<![\wäöüß])[A-ZÄÖÜ][\wäöüß\-]+(?:[ \t][A-ZÄÖÜ][\wäöüß\-]+){0,2}[ \t]\d{1,4}(?:[ ]?[a-z]\b)?(?=[ \t]*[-–,|]?[ \t]*\d{5}\b)"
)
_OT = r"[A-ZÄÖÜ][\wäöüß\-]+"
RX_PLACE_AFTER_STREET = re.compile(r"[ \t]*[,|–-]?[ \t]*([A-ZÄÖÜ][\wäöüß\-]+)")
RX_PLZ_ORT = re.compile(r"\b\d{5}[ \t]+(?:%s[ \t](?:am|im|an der|ob der|in der)[ \t]+(?!(?:%s)\b)%s|%s(?:[ ]%s)?)" % (_OT, MONTHS, _OT, _OT, _OT))  # Tabulator trennt Spalten: kein zweites Ortswort über den Tab hinweg
LEGAL = (r"(?:GmbH\s*&\s*Co\.\s*KG|GMBH\s*&\s*CO\.\s*KG|gGmbH|GmbH|GMBH|mbH|MBH|GBR|AG|SE|UG(?:\s*\(haftungsbeschränkt\))?|KG|OHG|GbR|eG|e\.\s?K\.|e\.\s?V\.|"
         r"LLC|LLP|PLC|Ltd\.?|Limited|Inc\.?|Corp\.?|Corporation|S\.A\.|S\.L\.|S\.p\.A\.|S\.r\.l\.|B\.V\.|N\.V\.|d\.o\.o\.|s\.r\.o\.|"
         r"Sp\. z o\.o\.|OOO|TOV|ТОВ|ПП)")
_CW = r"[A-ZÄÖÜ][\wäöüß\-.]*"
RX_COMPANY = re.compile(_CW + r"[ \t](?:(?:" + _CW + r"|&)[ \t]){0,3}" + LEGAL + r"(?!\w)")
_ORG_WORDS = ("Universität|Universitaet|Hochschule|Fachhochschule|Akademie|Institut|Klinikum|Krankenhaus|Gymnasium|Lyzeum|Berufsfachschule|"
              "Berufskolleg|Sparkasse|Verlag|Stiftung|Ministerium|Kindergarten|Polytechnikum|Konservatorium|Lyceum|University|College|Institute|Academy")
RX_ORG_KEY = re.compile(
    r"(?:[A-ZÄÖÜ][\wäöüß\-.]*[ \t]){0,3}(?:%s)(?:[ \t](?:für|der|des|zu|von|in|am|an|und|&|of)?[ \t]?[A-ZÄÖÜ][\wäöüß\-.]*){0,4}" % _ORG_WORDS
)
RX_ORG_COMPOUND = re.compile(r"\b[A-ZÄÖÜ][\wäöüß\-]*(?:schule|universität|hochschule|klinik|akademie|institut|krankenhaus)(?:[ \t][A-ZÄÖÜ][\wäöüß\-]*){0,2}")
RX_EMAIL_NAME = re.compile(r"^([a-zäöüß]{2,})[._-]([a-zäöüß]{2,})$", re.IGNORECASE)
COMPANY_STOP_FIRST = {"bei", "die", "der", "das", "firma", "ich", "als", "und", "von", "in", "im", "für", "mit", "zu", "den", "dem", "unser", "unsere", "ihre", "ihr"}


def _pattern_cands(text):
    out = []
    for m in RX_EMAIL.finditer(text):
        out.append(Cand(m.start(), m.end(), "email", "muster"))
    for m in RX_URL.finditer(text):
        end = m.end() - len(m.group(0)) + len(m.group(0).rstrip(".,;:)"))
        out.append(Cand(m.start(), end, "url", "muster"))
    for m in RX_IBAN.finditer(text):
        if len(re.sub(r"\s", "", m.group(0))) >= 15:
            out.append(Cand(m.start(), m.end(), "iban", "muster"))
    for m in RX_PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 7 <= len(digits) <= 15 and not RX_PHONE_NOT.search(m.group(0)) and not RX_PHONE_DATERANGE.match(m.group(0).strip()):
            s, e = m.start(), m.end()
            out.append(Cand(s, e, "telefon", "muster"))
    for m in RX_DATE.finditer(text):
        before = text[max(0, m.start() - 60):m.start()]
        if RX_BIRTH_CTX.search(before) or _lonely_header_date(text, m):
            out.append(Cand(m.start(), m.end(), "geburtsdatum", "muster"))
    home_places = set()
    for rx in (RX_STREET, RX_STREET_PREFIX, RX_STREET_PLZ):
        for m in rx.finditer(text):
            out.append(Cand(m.start(), m.end(), "adresse", "muster"))
            # Ort direkt hinter der Straße ("Musterweg 5, Nürnberg"): gehört zur Adresse, auch ohne Postleitzahl
            after = RX_PLACE_AFTER_STREET.match(text, m.end())
            if after and after.group(1) in PLACE_SET:
                out.append(Cand(after.start(1), after.end(1), "adresse", "muster"))
                home_places.add(after.group(1))
    for m in RX_PLZ_ORT.finditer(text):
        out.append(Cand(m.start(), m.end(), "adresse", "muster"))
        home_places.add(m.group(0).split(None, 1)[1].strip())
    # Der Wohnort aus der Adresse taucht oft noch einmal auf (auch in Versalien, z. B. als Überschrift)
    for place in home_places:
        for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(place), text, re.IGNORECASE):
            out.append(Cand(m.start(), m.end(), "ort", "wohnort"))
    for m in RX_COMPANY.finditer(text):
        s, e = m.start(), m.end()
        words = re.split(r"[ \t]", text[s:e])
        while len(words) > 2 and words[0].lower() in COMPANY_STOP_FIRST:
            s += len(words[0]) + 1
            words = words[1:]
        if len(words) >= 2 and words[0].lower() not in COMPANY_STOP_FIRST:
            out.append(Cand(s, e, "firma", "muster"))
    out += _email_name_cands(text)
    out += _header_name_cands(text)
    for rx in (RX_ORG_KEY, RX_ORG_COMPOUND):
        for m in rx.finditer(text):
            frag = m.group(0).rstrip(" \t-.")
            if len(frag.split()) >= 2 or rx is RX_ORG_COMPOUND:
                out.append(Cand(m.start(), m.start() + len(frag), "firma", "muster", confident=False))
    for m in RX_PLACES.finditer(text):
        out.append(Cand(m.start(), m.end(), "ort", "muster"))
    for m in RX_PLACES_UPPER.finditer(text):
        out.append(Cand(m.start(), m.end(), "ort", "muster"))
    return out


def _lonely_header_date(text, m):
    """Ein vollständiges Datum allein in einer Zeile im Kopf des Dokuments ist meist das Geburtsdatum (z. B. '1972-08-18')."""
    if text.count("\n", 0, m.start()) >= 15:
        return False
    ls = text.rfind("\n", 0, m.start()) + 1
    le = text.find("\n", m.end())
    if text[ls:len(text) if le < 0 else le].strip() != m.group(0):
        return False
    year = re.search(r"(?:19|20)\d{2}", m.group(0))
    return bool(year) and 1930 <= int(year.group(0)) <= datetime.now().year - 14


HEADING_WORDS = set(
    """lebenslauf curriculum vitae cv kontakt profil berufserfahrung ausbildung kenntnisse fähigkeiten sprachen
    persönliche persönlicher daten angaben hobbys interessen was ich suche über mich bewerbung anschreiben zeugnis
    kompetenzen skills erfahrung bildung werdegang weiterbildung stationen praktika zertifikate qualifikationen
    studium schule personalien adresse mobil telefon email geburtsdatum berufliche beruflicher deutsch englisch
    ukrainisch russisch fertigkeiten it-kenntnisse ehrenamt zusatzqualifikationen berufsausbildung schulbildung
    arbeitserfahrung praktikum projekte referenzen stärken ziele zielsetzung kurzprofil übersicht aktuell heute seit bis
    mittlere reife grundkenntnisse fortgeschritten muttersprache verhandlungssicher zertifizierungen kurse sprachkenntnisse
    jan feb mär mrz mar apr mai jun jul aug sep sept okt nov dez januar februar märz april juni juli august september
    oktober november dezember gesellschafter meine meiner weiteres weitere schulung schulungen weiterbildungen""".split()
)
RX_NAME_WORD = re.compile(r"^[A-Za-zÄÖÜäöüßÀ-ÿ][A-Za-zÄÖÜäöüßÀ-ÿ'\-]+$")


def _fold(s):
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b).replace(a.upper(), b)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _header_name_cands(text):
    """Namenszeile am Dokumentanfang (z. B. 'ANNA MUSTERFRAU'), die das Sprachmodell oft übersieht.
    Auch weiter hinten (Fußzeile, Briefkopf am Ende): eine Zeile, die wie ein Name aussieht und direkt neben Kontaktdaten steht."""
    evidence = _fold(" ".join(m.group(0) for m in RX_EMAIL.finditer(text)) + " " + " ".join(m.group(0) for m in RX_URL.finditer(text)))
    lines = text.split("\n")
    contact = [bool(RX_EMAIL.search(l) or RX_PHONE.search(l) or re.search(r"\b\d{5}\b", l)) for l in lines]
    out, pos = [], 0
    for idx, line in enumerate(lines):
        start = pos
        pos += len(line) + 1
        near = any(contact[j] for j in range(max(0, idx - 2), min(len(lines), idx + 3)) if j != idx)
        if idx >= 12 and not near:
            continue
        words = line.split()
        if not (2 <= len(words) <= 4) or not all(RX_NAME_WORD.match(w) for w in words):
            continue
        if any(w.lower().strip("-") in HEADING_WORDS for w in words):
            continue
        if idx >= 12 and (RX_JOB.search(line) or any(w in PLACE_SET for w in words) or not (line.isupper() or all(w[0].isupper() and w[1:].islower() for w in words))):
            continue
        confident = any(len(p) >= 4 and _fold(p) in evidence for w in words for p in w.split("-")) or idx >= 12
        if not confident and not (line.isupper() or all(w[0].isupper() and w[1:].islower() for w in words)):
            continue
        off = start + (len(line) - len(line.lstrip()))
        out.append(Cand(off, off + len(line.strip()), "name", "muster", confident=confident))
        if confident:  # Schreibweisen des Namens im restlichen Dokument (Unterschrift, Fließtext)
            for part in [line.strip()] + [p for w in words for p in [w] + w.split("-") if len(p) >= 3]:
                for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(part), text, re.IGNORECASE):
                    out.append(Cand(m.start(), m.end(), "name", "muster", confident=True))
    return out


def _email_name_cands(text):
    """Aus 'vorname.nachname@…' den Namen ableiten und im Text suchen."""
    out = []
    for em in RX_EMAIL.finditer(text):
        m = RX_EMAIL_NAME.match(em.group(0).split("@")[0])
        if not m:
            continue
        first, last = m.group(1), m.group(2)
        full = re.compile(r"(?<!\w)(%s[ \t]+%s|%s,[ \t]*%s)(?!\w)" % (first, last, last, first), re.IGNORECASE)
        found = list(full.finditer(text))
        for f in found:
            out.append(Cand(f.start(1), f.end(1), "name", "muster"))
        if found:
            for part in (first, last):
                for t in re.finditer(r"(?<!\w)%s(?!\w)" % part, text, re.IGNORECASE):
                    out.append(Cand(t.start(), t.end(), "name", "muster"))
    return out


# ---------------------------------------------------------------- Lebenslauf-Muster
_D = r"(?:\d{1,2}[./]\s?)?(?:19|20)\d{2}"
RX_CV_LINE = re.compile(
    r"^(\s*(?:seit\s+)?%s\s*(?:[-–—]|bis)\s*(?:%s|heute|jetzt|aktuell|present|today|laufend|dato)\s*[:|,]?\s*)(.*)$" % (_D, _D),
    re.IGNORECASE,
)
JOB_WORDS = (
    "manager leiter leitung entwickler berater assistent sachbearbeiter mitarbeiter praktik ausbildung studium trainee "
    "engineer developer consultant techniker fachkraft kaufmann kauffrau verkäufer fahrer helfer koch pfleger lehrer "
    "designer analyst architekt werkstudent volontariat referent spezialist student schüler abitur bachelor master "
    "diplom promotion projekt tätigkeit aufgaben elternzeit arbeitslos selbstständig selbststaendig freiberuf "
    "vertrieb sachbearbeitung teamleiter produktion lager buchhalt"
).split()
RX_SEP = re.compile(r"\s*(?:\||,|;|\t|–|—|\s-\s|\bbei\b|\bat\b|@)\s*", re.IGNORECASE)


def _segments(line, offset):
    segs, pos = [], 0
    for m in RX_SEP.finditer(line):
        segs.append((pos, m.start()))
        pos = m.end()
    segs.append((pos, len(line)))
    return [(offset + a, offset + b) for a, b in segs if b > a and line[a:b].strip()]


NOT_ORG_WORDS = (
    "kurs kurse weiterbildung praktikum umschulung abschluss abschlussarbeit orientierung qualifizierung fortbildung "
    "familienzeit auszeit arbeitssuchend arbeitsuchend integration sprachkurs deutschkurs beratung betreuung grundschule "
    "hauptschule realschule berufsschule oberstufe kenntnisse erfahrung ehrenamt"
).split()
RX_JOB = re.compile(
    r"(?i)\w*(?:erin|helfer|assistent|angestellte|techniker|ingenieur|pfleger|schwester|verkäufer|kauffrau|kaufmann|köchin|koch|fahrer|"
    r"leiter|manager|berater|entwickler|sachbearbeiter|mitarbeiter|disponent|erzieher|apotheker|arzt|ärztin|lehrer|buchhalter|controller|"
    r"analyst|designer|specialist|consultant|developer|engineer|administrator|coordinator|director|officer|praktikant|referent|therapeut|akteure|coach|dozent|trainer|psycholog|pädagog)\w*"
)


def _looks_like_job(seg):
    low = seg.lower()
    return any(w in low for w in JOB_WORDS) or any(w in low for w in NOT_ORG_WORDS) or bool(RX_JOB.search(seg)) \
        or low.startswith("head of")


def _cv_from_text(line, offset):
    cands = []
    for a, b in _segments(line, offset):
        raw = line[a - offset:b - offset]
        seg = raw.strip(" •-–")
        if not seg or _looks_like_job(seg):
            continue
        if re.search(r"\d", seg) or len(seg.split()) > 6 or not seg[0].isupper():
            continue
        a2 = a + (len(raw) - len(raw.lstrip(" •-–")))
        cands.append((a2, a2 + len(seg), seg))
    out, firm = [], False
    for a, b, seg in cands:
        if seg in PLACE_SET:
            out.append(Cand(a, b, "ort", "lebenslauf"))
        elif not firm:
            out.append(Cand(a, b, "firma", "lebenslauf", confident=False))
            firm = True
        elif len(seg.split()) <= 3 and not any(c.category == "ort" for c in out):
            out.append(Cand(a, b, "ort", "lebenslauf", confident=False))
    return out


def _cv_cands(text):
    out, lines, pos = [], text.split("\n"), 0
    starts = []
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    for i, ln in enumerate(lines):
        m = RX_CV_LINE.match(ln)
        if not m:
            continue
        rest = m.group(2)
        if rest.strip():
            out += _cv_from_text(rest, starts[i] + m.start(2))
        else:
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].strip():
                    if not RX_CV_LINE.match(lines[j]) and len(lines[j]) < 120:
                        out += _cv_from_text(lines[j], starts[j])
                    break
    return out


# ---------------------------------------------------------------- Sprachmodell
@lru_cache(maxsize=1)
def _nlp():
    import spacy

    return spacy.load(SPACY_MODEL, exclude=["lemmatizer"])


TITLE_WORDS = {"herr", "frau", "dr.", "dr", "prof.", "prof", "dipl.-ing.", "dipl.-kfm.", "mag.", "herrn"}
LABEL_MAP = {"PER": "name", "ORG": "firma", "LOC": "ort"}
EDGE = " ,;:.()[]•-–|\"'„“"
ACRO_STOP = set(
    """ERP KPI CRM CMS SEO SEM PDF API IT HR DIN ISO EDV MS SQL AWS GCP NFT HTML CSS PHP UI UX AI KI BWL VWL MBA EU PC TV CV PM PO QA
    ESG DSGVO GDPR EDI ATEX SCM WMS BI DATEV P&L SAP GL GLT CAD CNC SPS HACCP TÜV HIV AIDS TB STI NGO BIM TGA QMB PMO BSC TDD IFS SES SIS CPA
    TQM FMEA OEE LEAN SCRUM""".split()
)
# Werkzeuge, Programme und Methoden sind keine Firmen oder Orte
TECH_WORDS = set(
    """bitrix qdrant golang junit rspec strapi toad safe docker kubernetes jenkins jira confluence python java javascript typescript react
    angular vue django flask laravel symfony postgresql mysql mongodb redis kafka terraform ansible git github gitlab bootstrap scrum kanban
    excel word powerpoint outlook sap datev autocad revit sketchup photoshop wordpress linux windows android ios""".split()
)
RX_NOUN_END = re.compile(r"(?i)(?:ung|keit|heit|schaft|tion|ität|ismus|ing|ment|erin|ent|ist|ik|nis|ei|ur|ium|age|en|es)$")
RX_PLACE_CTX_BEFORE = re.compile(r"(?:\bin|\bnach|\baus|\bbei|\bnear|\bin der|,|\(|/|-|–|—|:)\s*$", re.IGNORECASE)


ORG_WORDS = set(
    """school schule university universität universitaet college academy akademie institute institut bank banking hospital klinik
    ministry ministerium department abteilung foundation stiftung agency agentur group gruppe center centre zentrum""".split()
)


def _heading(frag):
    return any(w.lower().strip("-") in HEADING_WORDS for w in re.split(r"[\s\-]+", frag) if w)


def _org_like(frag):
    return any(w.lower() in ORG_WORDS for w in re.split(r"[\s\-]+", frag) if w)


def _keep_org(frag):
    words = frag.split()
    if _heading(frag) or frag[0].islower() or frag.lower() in TECH_WORDS:
        return False
    if len(words) == 1:
        if frag.isupper():
            return 3 <= len(frag) <= 8 and frag not in ACRO_STOP
        return len(frag) >= 4 and not RX_NOUN_END.search(frag) and not _looks_like_job(frag)
    return not _looks_like_job(frag) or bool(re.search(LEGAL, frag))


def _keep_loc(frag, before, after):
    if frag in PLACE_SET:
        return True
    if frag.isupper() or frag[0].islower() or len(frag) < 4 or _heading(frag) or RX_NOUN_END.search(frag) or frag.lower() in TECH_WORDS:
        return False
    return bool(RX_PLACE_CTX_BEFORE.search(before)) or after.lstrip()[:1] in (")", ",")


CONNECTORS = {"für", "der", "des", "von", "und", "of", "in", "am", "an", "zu", "&", "the"}


def _model_confidence(cat, frag):
    words = frag.split()
    if cat == "name":
        return len(words) > 1
    if cat == "ort":
        return frag in PLACE_SET
    if cat == "firma":
        if re.search(LEGAL + r"$", frag) or re.search(_ORG_WORDS, frag):
            return True
        return 2 <= len(words) <= 4 and all(w[0].isupper() or w.lower() in CONNECTORS for w in words)
    return True


NAME_PARTICLES = {"von", "van", "vom", "zu", "zur", "de", "del", "della", "der", "den", "ten", "ter", "la", "le", "di", "da", "dos", "du", "bin", "ibn", "al", "el", "af"}


def _sentence_start_word(text, s, e):
    """Einzelnes Wort am Zeilenanfang (ggf. nach Aufzählungszeichen), dem Kleingeschriebenes oder eine Zahl folgt: ein Satzanfang
    wie 'Leitete 50 Mitarbeiter', kein Name."""
    if " " in text[s:e]:
        return False
    lead = text[text.rfind("\n", 0, s) + 1:s]
    if lead.strip(" \t•·▪-–*"):
        return False
    if any(c in lead for c in "•·▪"):  # Aufzählungspunkt: das erste Wort ist der Beginn eines Satzes
        return True
    after = text[e:e + 25].lstrip(" \t")
    return bool(after) and (after[0].islower() or after[0].isdigit())


def _model_cands(text):
    try:
        doc = _nlp()(text)
    except OSError:
        return [], "Das Sprachmodell (%s) ist nicht installiert. Nur Muster und Wörterbuch werden verwendet." % SPACY_MODEL
    out = []
    for ent in doc.ents:
        cat = LABEL_MAP.get(ent.label_)
        if not cat:
            continue
        for part in re.finditer(r"[^\n\t|]+", ent.text):
            s, e = ent.start_char + part.start(), ent.start_char + part.end()
            while s < e and text[s] in EDGE:
                s += 1
            while e > s and text[e - 1] in EDGE:
                e -= 1
            if cat == "name":
                words = text[s:e].split(" ")
                while words and words[0].lower() in TITLE_WORDS:
                    s += len(words[0]) + 1
                    words = words[1:]
            frag = text[s:e]
            if len(frag) < 3 or re.search(r"\d", frag):
                continue
            if cat != "name" and frag in PLACE_SET:
                cat = "ort"
            if cat in ("name", "firma") and _sentence_start_word(text, s, e):
                continue
            if cat == "name" and any(w[0].islower() and w not in NAME_PARTICLES for w in frag.split()):
                continue  # ein Name besteht aus großgeschriebenen Wörtern (außer Namenszusätzen wie "von")
            if cat == "name" and RX_JOB.search(frag) and " " not in frag:
                continue
            if cat == "name" and (_heading(frag) or _org_like(frag)):
                continue  # "Banking School-September" ist kein Name
            if cat == "firma" and not _keep_org(frag):
                continue
            if cat == "ort" and not _keep_loc(frag, text[max(0, s - 14):s], text[e:e + 3]):
                continue
            conf = _model_confidence(cat, frag)
            out.append(Cand(s, e, cat, "modell", confident=conf))
            cat = LABEL_MAP.get(ent.label_)
    return out, None


# ---------------------------------------------------------------- Zusammenführen
def _dictionary_cands(text):
    out = []
    for entry in store.load_dictionary():
        rx = term_regex([entry["text"]], re.IGNORECASE)
        for m in rx.finditer(text):
            out.append(Cand(m.start(), m.end(), entry["category"], "woerterbuch"))
    return out


def find_candidates(text):
    cands = _dictionary_cands(text) + _pattern_cands(text) + _cv_cands(text)
    model, warn = _model_cands(text)
    cands += model
    cands.sort(key=lambda c: (PRIO[c.source], -(c.end - c.start), c.start))
    accepted = []
    for c in cands:
        if c.end <= c.start:
            continue
        clash = [a for a in accepted if c.start < a.end and a.start < c.end]
        if clash:
            for a in clash:  # gleiche Stelle und Kategorie: Sicherheit zusammenführen
                if (a.start, a.end, a.category) == (c.start, c.end, c.category):
                    a.confident = a.confident or c.confident
            continue
        accepted.append(c)
    return accepted, warn


def analyze_all(text, alt_texts=()):
    """Wie analyze, durchsucht aber zusätzlich andere Lesereihenfolgen desselben Dokuments und führt die Funde zusammen."""
    findings, warn = analyze(text) if text.strip() else ([], None)
    order = list(CATEGORIES)
    for alt in alt_texts:
        more, _ = analyze(alt)
        for f in more:
            same = [x for x in findings if x["text"] == f["text"]]
            if same:
                for x in same:
                    if x["category"] == f["category"]:
                        x["checked"], x["confident"] = x["checked"] or f["checked"], x["confident"] or f["confident"]
                continue
            f["count"] = max(1, count_occurrences(text, f["text"]))
            findings.append(f)
    _add_case_variants(findings, text, alt_texts)
    findings.sort(key=lambda f: (order.index(f["category"]), text.find(f["text"]) if f["text"] in text else len(text), -len(f["text"]), f["text"]))
    _mark_main_person(findings, text)
    return findings, warn


_NAME_PARTICLES = {"von", "van", "vom", "zu", "zur", "de", "del", "della", "der", "den", "ten", "ter", "la", "le", "di", "da", "dos", "du",
                   "bin", "ibn", "al", "el", "af", "herr", "frau", "dr", "prof", "mag"}


# Wort ohne Anschluss an Buchstaben, @ oder Punkt+Buchstabe: "anna" in "anna.beispiel@example.org" ist kein eigener Fund
_VARIANT_L = r"(?<![\w@])(?<!\w\.)"
_VARIANT_R = r"(?![\w@])(?!\.\w)"


def name_variants(name, haystacks):
    """Weitere Schreibweisen eines Namens, die in den Texten vorkommen: [(Text, Anzahl)].
    Vollname: GROSS, klein oder gemischt wie im Text. Namensteile (Vor-/Nachname einzeln): jede Schreibweise, auch die normale,
    damit jedes "Amir" und jedes "DEGAN" im Dokument gleich ersetzt wird. Teile von E-Mail-Adressen und Links zählen nicht."""
    parts = [p for p in re.split(r"[\s,]+", name) if len(p) >= 3 and p.strip(".").lower() not in _NAME_PARTICLES]
    out = {}
    for base in dict.fromkeys([name] + parts):
        is_part = base != name
        cands = {base.upper(), base.lower()} | ({base} if is_part else set())
        for h in haystacks:
            cands |= {m.group(0) for m in re.finditer(_VARIANT_L + r"\s+".join(map(re.escape, base.split())) + _VARIANT_R, h, re.I)}
        for v in cands:
            if v == name or v in out or "\n" in v or not (is_part or v.isupper() or v.islower()):
                continue
            rx = re.compile(_VARIANT_L + re.escape(v) + _VARIANT_R)
            n = max(len(rx.findall(h)) for h in haystacks)
            if n:
                out[v] = n
    return list(out.items())


def _add_case_variants(findings, text, alt_texts=()):
    """Taucht ein erkannter Name in GROSSBUCHSTABEN oder ganz klein auf, wird auch diese Schreibweise ein eigener Fund
    (Vollname und einzelne Namensteile). Das Pseudonym übernimmt die Schreibweise (siehe pseudonymize._case).
    Hat das Sprachmodell dieselbe Schreibweise schon anders eingeordnet (z. B. "AMIR" als Firma), wird sie zum Namen."""
    haystacks = [text] + [a for a in alt_texts if a]
    by_text = {f["text"]: f for f in findings}
    for f in [f for f in findings if f["category"] == "name"]:
        for v, n in name_variants(f["text"], haystacks):
            old = by_text.get(v)
            if old is None:
                new = {**f, "text": v, "count": n, "context": v, "main": False}
                findings.append(new)
                by_text[v] = new
            elif old["category"] != "name" and old["source"] == "modell":
                old.update(category="name", checked=f["checked"], confident=f["confident"], source=f["source"], gender=f.get("gender", ""))


_TITLES = {"herr", "frau", "dr", "dr.", "prof", "prof.", "dipl.-ing.", "mag."}


def guess_gender(full_name, text):
    """'f', 'm' oder '' (unbekannt): aus der Anrede im Text, sonst aus einer kleinen Vornamenliste."""
    parts = [w for w in full_name.replace(",", " ").split() if w.lower() not in _TITLES]
    if len(parts) < 2:
        return ""
    first, last = re.escape(parts[0]), re.escape(parts[-1])
    for pat, g in ((r"\bFrau\s+", "f"), (r"\bHerr(?:n)?\s+", "m")):
        if re.search(pat + r"(?:(?:Dr|Prof)\.?\s*)*(?:%s\s+)?%s\b" % (first, last), text):
            return g
    f = parts[0].split("-")[0].lower()
    return "f" if f in FEMALE else "m" if f in MALE else ""


def _mark_main_person(findings, text):
    """Die Hauptperson (Bewerber/in) ist der erste volle Name aus der Namenszeile oder der E-Mail-Adresse."""
    for f in findings:
        f["main"] = False
        f["gender"] = guess_gender(f["text"], text) if f["category"] == "name" and " " in f["text"] else ""
    for f in findings:
        if f["category"] == "name" and f["source"] == "muster" and " " in f["text"] and f["text"] in text:
            f["main"] = True
            break


def analyze(text):
    """Liefert (Fundliste, Hinweis). Jeder Fund = ein einzigartiger Text mit Kategorie."""
    cands, warn = find_candidates(text)
    found = {}
    for c in sorted(cands, key=lambda c: c.start):
        frag = text[c.start:c.end]
        key = (frag, c.category)
        f = found.get(key)
        if f is None:
            line_start = text.rfind("\n", 0, c.start) + 1
            line_end = text.find("\n", c.end)
            line_end = len(text) if line_end < 0 else line_end
            ctx = text[max(line_start, c.start - 40):min(line_end, c.end + 40)]
            f = found[key] = {
                "text": frag, "category": c.category, "source": c.source,
                "confident": c.confident, "context": ctx,
            }
        else:
            f["confident"] = f["confident"] or c.confident
            if PRIO[c.source] < PRIO[f["source"]]:
                f["source"] = c.source
    # gleicher Text in mehreren Kategorien: höchste Priorität gewinnt
    by_text = {}
    for (frag, cat), f in found.items():
        cur = by_text.get(frag)
        if cur is None or PRIO[f["source"]] < PRIO[cur["source"]]:
            by_text[frag] = f
    findings = list(by_text.values())
    # Einzelne Nachnamen gelten als sicher, wenn sie Teil eines vollen Namens sind
    full_names = [f["text"] for f in findings if f["category"] == "name" and " " in f["text"]]
    for f in findings:
        if f["category"] == "name" and " " not in f["text"] and any(f["text"] in n.split() for n in full_names):
            f["confident"] = True
    out = []
    for f in findings:
        f["count"] = max(1, count_occurrences(text, f["text"]))
        f["source_label"] = SOURCE_LABELS[f["source"]]
        f["checked"] = (f["category"] in DEFAULT_ON and f["confident"]) or f["source"] in ("woerterbuch", "wohnort")
        out.append(f)
    order = list(CATEGORIES)
    out.sort(key=lambda f: (order.index(f["category"]), text.find(f["text"]), -len(f["text"]), f["text"]))
    return out, warn
