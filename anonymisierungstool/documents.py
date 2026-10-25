"""Dateien einlesen (Word, PDF, Text) und anonymisiert wieder ausgeben (Word, PDF, HTML, Text)."""
import io
import re

from lxml import etree

from .textutil import replace_in_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def _placeholder_png(w, h):
    """Grauer Kasten mit "Foto entfernt" (Pixelmaße) als Ersatz für ein entferntes Bild."""
    import fitz

    w, h = max(int(w), 60), max(int(h), 40)
    page = fitz.open().new_page(width=w, height=h)
    page.draw_rect(page.rect, color=(0.6, 0.6, 0.6), fill=(0.93, 0.93, 0.93), width=2)
    page.insert_textbox(fitz.Rect(2, h / 2 - 10, w - 2, h / 2 + 14), "Foto entfernt", fontname="helv", fontsize=min(12, max(6, w / 9)), align=1, color=(0.35, 0.35, 0.35))
    return page.get_pixmap(dpi=72).tobytes("png")


def _image_holes(page, keep):
    """Stellen kleiner Bilder (Fotos, Logos), die entfernt werden; große Hintergrundbilder bekommen keinen Platzhalter."""
    import fitz

    out = []
    try:
        for inf in page.get_image_info(xrefs=True):
            r = fitz.Rect(inf["bbox"])
            if inf.get("xref") in keep or r.width < 30 or r.height < 30 or r.width * r.height > 0.4 * page.rect.width * page.rect.height:
                continue
            out.append(r)
    except Exception:
        pass
    return out


def _draw_holes(page, holes):
    import fitz

    words = [fitz.Rect(w[:4]) for w in page.get_text("words")]
    for r in holes:
        over = not any(r.intersects(w) for w in words)  # liegt Text im Bildbereich, kommt der Kasten darunter, damit nie Text verdeckt wird
        page.draw_rect(r, color=(0.6, 0.6, 0.6), fill=(0.93, 0.93, 0.93), width=1, overlay=over)
        page.insert_textbox(fitz.Rect(r.x0 + 2, (r.y0 + r.y1) / 2 - 8, r.x1 - 2, (r.y0 + r.y1) / 2 + 12), "Foto entfernt", fontname="helv",
                            fontsize=min(10, max(5, r.width / 9)), align=1, color=(0.35, 0.35, 0.35), overlay=over)


def _w(tag):
    return "{%s}%s" % (W, tag)


TEXT_TAGS = {_w("t"), _w("delText")}
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PART_RX = re.compile(r"^/word/(document|header\d*|footer\d*|footnotes|endnotes|comments\w*)\.xml$")


# Fremde Dateien: keine externen Entitäten auflösen, kein Netzwerkzugriff (Schutz vor XXE)
_SAFE_XML = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


class UnsupportedFile(Exception):
    pass


def _nearest_p(el):
    a = el.getparent()
    while a is not None and a.tag != _w("p"):
        a = a.getparent()
    return a


def _in_fallback(el):
    return any(a.tag == "{%s}Fallback" % MC for a in el.iterancestors())


def _segments(p):
    """Textknoten eines Absatzes in Dokumentreihenfolge: [(knoten|None, text)]."""
    segs = []
    for el in p.iter():
        if el.tag in TEXT_TAGS:
            if _nearest_p(el) is p:
                segs.append((el, el.text or ""))
        elif el.tag in (_w("tab"), _w("br"), _w("cr")) and el.getparent() is not None \
                and el.getparent().tag == _w("r") and _nearest_p(el) is p:
            segs.append((None, "\t" if el.tag == _w("tab") else "\n"))
    return segs


def _replace_in_paragraph(p, regex, mapping):
    segs = _segments(p)
    full = "".join(t for _, t in segs)
    matches = list(regex.finditer(full))
    if not matches:
        return 0
    pos = 0
    for node, t in segs:
        s, e = pos, pos + len(t)
        pos = e
        if node is None:
            continue
        out, cur = [], s
        for m in matches:
            ms, me = m.span()
            if me <= s or ms >= e:
                continue
            if ms > cur:
                out.append(full[cur:ms])
            if ms >= s:
                out.append(mapping[m.group(0)])
            cur = min(me, e)
        out.append(full[cur:e])
        node.text = "".join(out)
        node.set(SPACE, "preserve")
    return len(matches)


class BaseDoc:
    kind = "txt"
    ext = "txt"

    image_count = 0

    def __init__(self):
        self.warnings = []

    def text(self):
        raise NotImplementedError

    def alt_texts(self):
        """Weitere Lesereihenfolgen desselben Dokuments, die zusätzlich nach Funden durchsucht werden."""
        return []

    def export(self, regex, mapping, remove_images=True, scrub=True, blackouts=None):
        """Gibt (bytes, endung, mimetype) im Format der Eingabe zurück. blackouts: nur für PDF (von Hand geschwärzte Stellen)."""
        new_text = replace_in_text(self.text(), regex, mapping)
        return new_text.encode("utf-8"), "txt", "text/plain; charset=utf-8"

    def leftover_check(self, data, ext, terms):
        """Prüft die fertige Ausgabe noch einmal auf Originalbegriffe."""
        return []


class TxtDoc(BaseDoc):
    def __init__(self, data):
        super().__init__()
        for enc in ("utf-8-sig", "cp1252"):
            try:
                self._text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue

    def text(self):
        return self._text


class PdfDoc(BaseDoc):
    """PDF wird direkt im Original bearbeitet: Text wird entfernt und der Ersatz an dieselbe Stelle gesetzt."""
    kind = "pdf"
    ext = "pdf"

    def __init__(self, data):
        super().__init__()
        import fitz

        self._data = data
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise UnsupportedFile("Die PDF-Datei konnte nicht gelesen werden: %s" % exc)
        if doc.needs_pass:
            raise UnsupportedFile("Die PDF-Datei ist passwortgeschützt. Bitte zuerst entsperren.")
        self.page_sizes = [(p.rect.width, p.rect.height) for p in doc]
        page_texts = [_page_text(p) for p in doc]
        self._text = _clean("\n\n".join(page_texts)).strip()
        self._stream_text = _clean("\n\n".join(p.get_text("text").strip() for p in doc)).strip()
        # Scan-Seite: Bild, aber kein lesbarer Text
        self.scan_pages = [i + 1 for i, p in enumerate(doc) if not page_texts[i] and (p.get_images() or p.get_image_info())]
        self.image_count = sum(max(len(p.get_images()), len(p.get_image_info()))
                               for i, p in enumerate(doc) if i + 1 not in self.scan_pages)
        doc.close()
        if self.scan_pages:
            if len(self.scan_pages) == len(page_texts):
                where = "Alle Seiten dieser PDF sind Scans"
            elif len(self.scan_pages) == 1:
                where = "Seite %d dieser PDF ist ein Scan" % self.scan_pages[0]
            else:
                where = "Die Seiten %s dieser PDF sind Scans" % ", ".join(map(str, self.scan_pages))
            self.warnings.append("%s (Bild ohne lesbaren Text). Dort wurde nichts automatisch erkannt: Namen, Adressen, "
                                 "Unterschriften und Stempel bleiben sichtbar. Bitte diese Stellen links in der Originalansicht mit "
                                 "Rechteck, Kreis oder Stift schwärzen. Das Tool arbeitet am besten mit Word und textbasierten PDFs." % where)
        elif not self._text:
            self.warnings.append("In dieser PDF wurde kein Text gefunden. Bitte prüfen, ob sie leer ist.")

    def text(self):
        return self._text

    def alt_texts(self):
        # Reihenfolge im PDF selbst: bei Word-PDFs oft besser für das Sprachmodell, bei Online-Lebensläufen die sortierte
        return [self._stream_text] if self._stream_text and self._stream_text != self._text else []

    # ---- Originalansicht
    def render_page(self, n, dpi=110):
        import fitz

        doc = fitz.open(stream=self._data, filetype="pdf")
        try:
            return doc[n].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
        finally:
            doc.close()

    def marks(self, terms):
        """Positionen der Fundstellen als Anteile der Seitengröße: [{page, term, x, y, w, h}]. Gleiche Suche wie beim Export."""
        import fitz

        terms = sorted({t for t in terms if t and t.strip()})
        if not terms:
            return []
        cached = getattr(self, "_marks_cache", None)
        if cached and cached[0] == terms:
            return cached[1]
        out = []
        doc = fitz.open(stream=self._data, filetype="pdf")
        try:
            for i, page in enumerate(doc):
                R = page.rect
                for r, term, _sp in _find_jobs(page, terms):
                    out.append({"page": i, "term": term, "x": (r.x0 - R.x0) / R.width, "y": (r.y0 - R.y0) / R.height,
                                "w": r.width / R.width, "h": r.height / R.height})
        finally:
            doc.close()
        self._marks_cache = (terms, out)
        return out

    def text_in_rect(self, n, x0, y0, x1, y1, touch=False):
        """Text der Wörter im Rahmen (Rahmen als Anteile der Seitengröße). Ein Wort zählt, wenn mindestens 40 % davon im Rahmen liegen.
        touch=True: Klick auf ein Wort; gibt nur das Wort zurück, das dem Klickpunkt am nächsten liegt."""
        import fitz

        doc = fitz.open(stream=self._data, filetype="pdf")
        try:
            page = doc[n]
            R = page.rect
            box = fitz.Rect(R.x0 + min(x0, x1) * R.width, R.y0 + min(y0, y1) * R.height,
                            R.x0 + max(x0, x1) * R.width, R.y0 + max(y0, y1) * R.height)
            if touch:
                c = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
                near = [w for w in page.get_text("words") if (fitz.Rect(w[:4]) + (-2, -2, 2, 2)).contains(c)]
                near.sort(key=lambda w: abs((w[0] + w[2]) / 2 - c.x) + abs((w[1] + w[3]) / 2 - c.y))
                return _clean(near[0][4]).strip(_EDGE) if near else ""
            words = [w for w in page.get_text("words") if _area(fitz.Rect(w[:4]) & box) >= 0.4 * _area(fitz.Rect(w[:4]))]
            words.sort(key=lambda w: (w[5], w[6], w[7]))
            return _clean(" ".join(w[4] for w in words)).strip(_EDGE)
        finally:
            doc.close()

    def export(self, regex, mapping, remove_images=True, scrub=True, blackouts=None):
        import fitz

        doc = fitz.open(stream=self._data, filetype="pdf")
        terms = list(mapping)
        # Auf Scan-Seiten ist das Bild der Inhalt selbst; es wird nie entfernt (sonst bliebe eine leere Seite).
        keep = {img[0] for n in self.scan_pages for img in doc[n - 1].get_images()}
        for page in doc:
            _redact_page(page, terms, mapping)
            if remove_images and page.number + 1 not in self.scan_pages:
                holes = _image_holes(page, keep)
                for img in page.get_images():
                    if img[0] in keep:
                        continue
                    try:
                        page.delete_image(img[0])
                    except Exception:
                        pass
                # Direkt in den Seiteninhalt eingebettete Bilder (keine Bildobjekte) per Schwärzung entfernen
                try:
                    infos = page.get_image_info()
                except Exception:
                    infos = []
                if infos:
                    for inf in infos:
                        page.add_redact_annot(fitz.Rect(inf["bbox"]), fill=False)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE, text=fitz.PDF_REDACT_TEXT_NONE)
                _draw_holes(page, holes)
            try:
                links = page.get_links() if scrub else []
            except Exception:  # beschädigte PDF-Struktur: Links lassen sich nicht lesen
                links = []
            for link in links:
                uri = link.get("uri") or ""
                if uri.lower().startswith(("mailto:", "tel:")) or any(t.lower() in uri.lower() for t in terms):
                    page.delete_link(link)
        if remove_images:
            # Auch Bilder, die nur als Füllmuster oder in Unterobjekten eingebunden sind (z. B. Fotos aus Word-Exporten)
            for xref in range(1, doc.xref_length()):
                try:
                    if xref not in keep and doc.xref_get_key(xref, "Subtype")[1] == "/Image" and doc.xref_get_key(xref, "Width")[1] != "1":
                        doc[0].delete_image(xref)
                except Exception:
                    pass
        _burn_blackouts(doc, blackouts or [])
        if scrub:
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
                doc.set_toc([])
            except Exception:
                pass
        data = doc.tobytes(garbage=4, deflate=True, clean=True)
        doc.close()
        return data, "pdf", "application/pdf"

    def leftover_check(self, data, ext, terms):
        import fitz
        from .textutil import term_regex

        doc = fitz.open(stream=data, filetype="pdf")
        text = _clean("\n\n".join(p.get_text("text") for p in doc))
        doc.close()
        rx = term_regex(terms)
        return sorted(set(rx.findall(text))) if rx else []


_EDGE = " ,;:.()[]•-–|\"'„“"
_PUA = re.compile("[\ue000-\uf8ff\u00ad\u200b]")


def _burn_blackouts(doc, blackouts):
    """Von Hand geschwärzte Stellen (Rechteck, Kreis, Stift; Koordinaten als Anteile der Seitengröße) fest einbrennen:
    Die ganze Seite wird zu einem Bild mit schwarzen Flächen, darunter bleibt weder Text noch eine Ebene."""
    import fitz

    by_page = {}
    for b in blackouts:
        try:
            by_page.setdefault(int(b["page"]), []).append(b)
        except (KeyError, TypeError, ValueError):
            continue
    for pno in sorted(by_page):
        if not 0 <= pno < len(doc):
            continue
        page = doc[pno]
        R = page.rect
        pt = lambda x, y: fitz.Point(R.x0 + float(x) * R.width, R.y0 + float(y) * R.height)
        for b in by_page[pno]:
            try:
                if b.get("shape") in ("rect", "ellipse"):
                    a, c = pt(b["x0"], b["y0"]), pt(b["x1"], b["y1"])
                    r = fitz.Rect(min(a.x, c.x), min(a.y, c.y), max(a.x, c.x), max(a.y, c.y))
                    (page.draw_rect if b["shape"] == "rect" else page.draw_oval)(r, color=None, fill=(0, 0, 0))
                elif b.get("shape") == "pen":
                    pts = [pt(x, y) for x, y in b["pts"][:5000]]
                    width = max(2.0, min(float(b.get("w", 0.02)), 0.2) * R.width)
                    if len(pts) == 1:
                        page.draw_circle(pts[0], width / 2, color=None, fill=(0, 0, 0))
                    elif len(pts) > 1:
                        page.draw_polyline(pts, color=(0, 0, 0), width=width, lineCap=1, lineJoin=1, closePath=False)
            except (KeyError, TypeError, ValueError):
                continue
        pix = page.get_pixmap(dpi=200, alpha=False)
        flat = fitz.open()
        flat.new_page(width=R.width, height=R.height).insert_image(fitz.Rect(0, 0, R.width, R.height), stream=pix.tobytes("jpg", jpg_quality=88))
        doc.insert_pdf(flat, start_at=pno)
        doc.delete_page(pno + 1)
        flat.close()


def _page_text(page):
    """Seitentext in Leserichtung: Zeilen nach Position geordnet, nebeneinanderstehende Spalten per Tab getrennt.
    (Online erstellte Lebensläufe legen ihre Textblöcke oft in beliebiger Reihenfolge ab.)"""
    lines = {}
    for x0, y0, x1, y1, word, block, line, _n in page.get_text("words"):
        e = lines.setdefault((block, line), [x0, y0, x1, y1, []])
        e[0], e[1], e[2], e[3] = min(e[0], x0), min(e[1], y0), max(e[2], x1), max(e[3], y1)
        e[4].append((x0, word))
    items = sorted(((e[0], e[1], e[2], e[3], " ".join(w for _, w in sorted(e[4]))) for e in lines.values()),
                   key=lambda i: ((i[1] + i[3]) / 2, i[0]))
    rows = []
    for it in items:
        mid, h = (it[1] + it[3]) / 2, it[3] - it[1]
        if rows and abs(mid - rows[-1][0]) <= 0.5 * min(h, rows[-1][1]):
            rows[-1][2].append(it)
        else:
            rows.append([mid, h, [it]])
    out = []
    for _mid, _h, row in rows:
        row.sort(key=lambda i: i[0])
        txt = row[0][4]
        for prev, cur in zip(row, row[1:]):
            txt += ("\t" if cur[0] - prev[2] > 10 else " ") + cur[4]
        out.append(txt)
    return "\n".join(out).strip()


def _clean(text):
    """Icon-Zeichen (Private Use Area, z. B. Symbole vor Telefonnummern) und weiche Trennstriche entfernen."""
    return _PUA.sub("", text)


def _tok_eq(word, tok, first, last):
    w = _clean(word)
    if w == tok:
        return True
    if first and w.lstrip(_EDGE) == tok.lstrip(_EDGE):
        return True
    if last and w.rstrip(_EDGE) == tok.rstrip(_EDGE):
        return True
    if first and w.endswith(tok) and not w[-len(tok) - 1:-len(tok)].isalnum():
        return True  # z. B. "D-53117" für "53117"
    if last and w.startswith(tok) and not w[len(tok):len(tok) + 1].isalnum():
        return True
    if first and last:
        # Einzelbegriff innerhalb eines Worts, getrennt durch Sonderzeichen ("Zahnpraxis/Frechen", "USA-basiert")
        return w.strip(_EDGE) == tok.strip(_EDGE) or bool(re.search(r"(?<!\w)%s(?!\w)" % re.escape(tok), w))
    return False


def _word_matches(words, tokens):
    """Fundstellen einer Wortfolge in der Wortliste einer Seite (ganze Wörter, groß/klein beachten)."""
    n, hits = len(tokens), []
    for i in range(len(words) - n + 1):
        ok = True
        for k, tok in enumerate(tokens):
            if not _tok_eq(words[i + k][4], tok, k == 0, k == n - 1):
                ok = False
                break
            if k and words[i + k][5:7] != words[i + k - 1][5:7]:
                ok = False  # Block oder Zeile wechselt: kein zusammenhängender Fund
                break
        if ok:
            hits.append(words[i:i + n])
    return hits


def _find_jobs(page, terms):
    """Fundstellen der Begriffe auf einer Seite: [(Rechteck, Begriff, Schrift-Span)].
    Dieselbe Suche dient der Anzeige (Markierungen) und der Ersetzung, damit beides übereinstimmt."""
    import fitz

    words = page.get_text("words")
    if not words or not terms:
        return []
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                spans.append(sp)
    jobs = []
    for term in sorted(terms, key=len, reverse=True):
        tokens = term.split()
        if not tokens:
            continue
        hits = _word_matches(words, tokens)
        if len(tokens) >= 2 and len(re.sub(r"\s", "", term)) >= 8:
            for r in _squeezed_hits(page, term):
                if not any(_area(r & j[0]) > 0.5 * _area(r) for j in jobs) and \
                        not any(_area(r & fitz.Rect(h[0][:4])) > 0.5 * _area(r) for h in hits):
                    span = next((sp for sp in spans if fitz.Rect(sp["bbox"]).contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))), None)
                    jobs.append((r, term, span))
        if len(tokens) == 1 and len(term) >= 6:
            # Fallback für gesperrt gesetzte Schrift ("L i u d m y l a"): Zeichensuche, nur bei exakt gleichem Textinhalt
            for r in page.search_for(term):
                near = [w for w in words if _area(fitz.Rect(w[:4]) & r) > 0]
                inside = fitz.Rect(r.x0 - 1.5, r.y0 - 3, r.x1 + 1.5, r.y1 + 3)
                # nur akzeptieren, wenn alle berührten Wörter vollständig im Fund liegen (kein Teil eines längeren Worts)
                if near and all(inside.contains(fitz.Rect(w[:4])) for w in near) \
                        and re.sub(r"\s", "", _clean("".join(w[4] for w in near))).strip(_EDGE) == re.sub(r"\s", "", term).strip(_EDGE) \
                        and not any(_area(r & j[0]) > 0.5 * _area(r) for j in jobs):
                    span = next((sp for sp in spans if fitz.Rect(sp["bbox"]).contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))), None)
                    jobs.append((r, term, span))
        for hit in hits:
            union = fitz.Rect(hit[0][:4])
            for w in hit[1:]:
                union |= fitz.Rect(w[:4])
            exact = page.search_for(term, clip=union + (-2, -2, 2, 2))
            rect = max(exact, key=lambda e: _area(e & union)) if exact else union
            if any(_area(rect & j[0]) > 0.5 * _area(rect) for j in jobs):
                continue  # bereits durch längeren Begriff erfasst
            span = next((sp for sp in spans if fitz.Rect(sp["bbox"]).contains(fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2))), None)
            jobs.append((rect, term, span))
    return jobs


def _redact_page(page, terms, mapping):
    import fitz

    from .pseudonymize import REDACTED

    jobs = [(r, mapping[t], sp) for r, t, sp in _find_jobs(page, terms)]
    if not jobs:
        return
    pix = page.get_pixmap(dpi=72, alpha=False)
    for rect, repl, span in jobs:
        fill = (0, 0, 0) if repl == REDACTED else _background(pix, rect)
        # Nur den Schriftkern der Zeile entfernen (Oberlänge bis Unterlänge), damit enge Nachbarzeilen unberührt bleiben
        if span:
            y0, y1 = span["origin"][1] - 0.8 * span["size"], span["origin"][1] + 0.25 * span["size"]
            core = fitz.Rect(rect.x0, max(rect.y0, y0), rect.x1, min(rect.y1, y1))
        else:
            core = fitz.Rect(rect.x0, rect.y0 + rect.height * 0.2, rect.x1, rect.y1 - rect.height * 0.2)
        page.add_redact_annot(core, fill=fill)
    before = _page_chars(page)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    _repair_collateral(page, before, [j[0] for j in jobs])
    for rect, repl, span in jobs:
        if repl == REDACTED:
            continue
        size = span["size"] if span else rect.height * 0.8
        color = fitz.sRGB_to_pdf(span["color"]) if span else (0, 0, 0)
        origin = span["origin"][1] if span else rect.y1 - rect.height * 0.2
        flags = span["flags"] if span else 0
        font = "hebo" if flags & 16 else ("heit" if flags & 2 else "helv")
        width = fitz.get_text_length(repl, fontname=font, fontsize=size)
        if width > rect.width:
            size = max(size * rect.width / width, size * 0.85)
        page.insert_text((rect.x0, origin), repl, fontname=font, fontsize=size, color=color)


def _page_chars(page):
    """Alle sichtbaren Zeichen einer Seite: (x, y, Zeichen) -> (Span, Zeichen)."""
    out = {}
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                for ch in sp["chars"]:
                    if not ch["c"].isspace():
                        out[(round(ch["origin"][0], 1), round(ch["origin"][1], 1), ch["c"])] = (sp, ch)
    return out


def _repair_collateral(page, before, rects):
    """Die Schwärzung kann Zeichen in engen Nachbarzeilen mit entfernen. Diese werden hier wieder eingesetzt."""
    import fitz

    after = _page_chars(page)
    lost = []
    for key, (sp, ch) in before.items():
        if key in after:
            continue
        cx, cy = (ch["bbox"][0] + ch["bbox"][2]) / 2, (ch["bbox"][1] + ch["bbox"][3]) / 2
        if any(fitz.Rect(r.x0 - 0.5, r.y0 - 1, r.x1 + 0.5, r.y1 + 1).contains(fitz.Point(cx, cy)) for r in rects):
            continue  # gewollt entfernt
        lost.append((key[1], key[0], key[2], sp))
    lost.sort(key=lambda t: (t[0], t[1]))
    run, last = [], None
    runs = []
    for y, x, c, sp in lost:
        if run and (y != last[0] or x - last[1] > sp["size"] * 0.9):
            runs.append(run)
            run = []
        run.append((y, x, c, sp))
        last = (y, x)
    if run:
        runs.append(run)
    for r in runs:
        y, x0, _, sp = r[0]
        text = "".join(c for _, _, c, _ in r)
        flags = sp["flags"]
        font = "hebo" if flags & 16 else ("heit" if flags & 2 else "helv")
        try:
            page.insert_text((x0, y), text.encode("cp1252", errors="ignore").decode("cp1252"), fontname=font,
                             fontsize=sp["size"], color=fitz.sRGB_to_pdf(sp["color"]))
        except Exception:
            pass


def _squeezed_hits(page, term):
    """Mehrwort-Begriffe auch in gesperrt gesetzter Schrift finden: pro Zeile Leerräume ignorieren."""
    import fitz

    want = re.sub(r"\s", "", term)
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            chars = [c for sp in ln["spans"] for c in sp["chars"] if not c["c"].isspace()]
            squeezed = _clean("".join(c["c"] for c in chars))
            if len(squeezed) != len(chars):
                continue  # Ersetzungen verschieben die Zuordnung: lieber überspringen
            i = squeezed.find(want)
            while i >= 0:
                r = fitz.Rect(chars[i]["bbox"])
                for c in chars[i + 1:i + len(want)]:
                    r |= fitz.Rect(c["bbox"])
                out.append(r)
                i = squeezed.find(want, i + len(want))
    return out


def _area(r):
    return max(r.width, 0) * max(r.height, 0) if not r.is_empty else 0


def _background(pix, rect):
    """Hintergrundfarbe um die Fundstelle: häufigste Farbe an mehreren Punkten knapp außerhalb des Rechtecks."""
    from collections import Counter

    pts = []
    ym = (rect.y0 + rect.y1) / 2
    for x in (rect.x0 - 2, rect.x1 + 2):
        for y in (rect.y0 + 1, ym, rect.y1 - 1):
            pts.append((x, y))
    for x in (rect.x0 + 1, (rect.x0 + rect.x1) / 2, rect.x1 - 1):
        pts.append((x, rect.y0 - 1.5))
        pts.append((x, rect.y1 + 1.5))
    votes, sample = Counter(), {}
    for x, y in pts:
        try:
            px = pix.pixel(int(x), int(y))[:3]
        except Exception:
            continue
        key = tuple(v // 16 for v in px)
        votes[key] += 1
        sample.setdefault(key, px)
    if not votes:
        return (1, 1, 1)
    return tuple(v / 255 for v in sample[votes.most_common(1)[0][0]])


class DocxDoc(BaseDoc):
    kind = "docx"
    ext = "docx"

    def __init__(self, data):
        super().__init__()
        import docx
        from docx.opc.part import XmlPart

        self._data = data
        try:
            self.doc = docx.Document(io.BytesIO(data))
        except Exception:
            raise UnsupportedFile("Die Word-Datei konnte nicht gelesen werden (nur .docx wird unterstützt).")
        self._roots = []  # (part, root, ist_generisch)
        for part in self.doc.part.package.iter_parts():
            if PART_RX.match(str(part.partname)):
                if isinstance(part, XmlPart):
                    self._roots.append((part, part.element, False))
                else:
                    self._roots.append((part, etree.fromstring(part.blob, _SAFE_XML), True))
        self._collect_warnings()

    def _paragraphs(self, skip_fallback):
        for part, root, _ in self._roots:
            for p in root.iter(_w("p")):
                if skip_fallback and _in_fallback(p):
                    continue
                yield p

    def _collect_warnings(self):
        has_changes = has_box = False
        self.image_count = 0
        for _, root, _g in self._roots:
            for el in root.iter():
                if el.tag == "{%s}blip" % A or el.tag == "{%s}imagedata" % V:
                    self.image_count += 1
                elif el.tag in (_w("ins"), _w("del")):
                    has_changes = True
                elif el.tag == _w("txbxContent"):
                    has_box = True
        if has_changes:
            self.warnings.append("Das Dokument enthält nachverfolgte Änderungen. Gelöschter Text kann Namen enthalten. "
                                 "Bitte vorher in Word alle Änderungen annehmen oder ablehnen.")
        if has_box:
            self.warnings.append("Das Dokument enthält Textfelder. Sie werden mitbearbeitet; bitte das Ergebnis besonders prüfen.")

    def text(self):
        lines = []
        for p in self._paragraphs(skip_fallback=True):
            lines.append("".join(t for n, t in _segments(p) if n is None or n.tag == _w("t")))
        return "\n".join(lines).strip("\n")

    def all_text(self):
        """Gesamter Text inklusive gelöschter Änderungen, für die Abschlusskontrolle."""
        return "\n".join("".join(t for _, t in _segments(p)) for p in self._paragraphs(skip_fallback=False))

    def apply(self, regex, mapping):
        if regex is None:
            return
        for p in self._paragraphs(skip_fallback=False):
            _replace_in_paragraph(p, regex, mapping)

    def remove_images(self):
        """Bilder werden durch einen gleich großen grauen Kasten "Foto entfernt" ersetzt, damit das Layout stehen bleibt."""
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        for part, root, _g in self._roots:
            can = hasattr(part, "get_or_add_image")
            for d in list(root.iter(_w("drawing"))):
                blips = d.findall(".//{%s}blip" % A)
                if not blips or d.find(".//" + _w("txbxContent")) is not None:
                    continue
                ext = d.find(".//{%s}extent" % WP)
                w, h = (int(ext.get("cx")) // 9525, int(ext.get("cy")) // 9525) if ext is not None else (120, 160)
                if can:
                    rid, _img = part.get_or_add_image(io.BytesIO(_placeholder_png(w, h)))
                    for b in blips:
                        b.set("{%s}embed" % R, rid)
                        b.attrib.pop("{%s}link" % R, None)
                else:
                    d.getparent().remove(d)
            for pic in list(root.iter(_w("pict"))):
                im = pic.find(".//{%s}imagedata" % V)
                if im is None or pic.find(".//" + _w("txbxContent")) is not None:
                    continue
                if can:
                    st = (pic.find(".//{%s}shape" % V).get("style") or "") if pic.find(".//{%s}shape" % V) is not None else ""
                    dims = {k: float(re.match(r"[\d.]+", v).group(0)) * (1.333 if v.endswith("pt") else 1) for k, v in
                            (x.split(":", 1) for x in st.split(";") if ":" in x and x.split(":", 1)[0] in ("width", "height")) if re.match(r"[\d.]+", v)}
                    rid, _img = part.get_or_add_image(io.BytesIO(_placeholder_png(dims.get("width", 120), dims.get("height", 160))))
                    im.set("{%s}id" % R, rid)
                else:
                    pic.getparent().remove(pic)
            used = {v for el in root.iter() for k, v in el.attrib.items() if k.startswith("{%s}" % R)}
            for rid, rel in list(part.rels.items()):
                if rel.reltype == RT.IMAGE and rid not in used:
                    part.rels.pop(rid)

    def scrub_metadata(self):
        cp = self.doc.core_properties
        for attr in ("author", "last_modified_by", "title", "subject", "keywords", "comments", "category"):
            try:
                setattr(cp, attr, "")
            except Exception:
                pass
        pkg = self.doc.part.package
        for rid, rel in list(pkg.rels.items()):
            # Vorschaubild, Anwendungs-Eigenschaften (Firma, Manager ...) und benutzerdefinierte Eigenschaften entfernen
            if rel.reltype.endswith(("/thumbnail", "/extended-properties", "/custom-properties")):
                pkg.rels.pop(rid)

    def to_bytes(self):
        for part, root, generic in self._roots:
            if generic:
                part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()

    def export(self, regex, mapping, remove_images=True, scrub=True, blackouts=None):
        work = DocxDoc(self._data)   # frische Kopie: mehrfaches Erstellen oder Vorschau ändert das geladene Dokument nicht
        work.apply(regex, mapping)
        if remove_images:
            work.remove_images()
        if scrub:
            work.scrub_metadata()
        return work.to_bytes(), "docx", \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def leftover_check(self, data, ext, terms):
        from .textutil import term_regex

        if ext != "docx":
            return []
        out = DocxDoc(data)
        rx = term_regex(terms)
        return sorted(set(rx.findall(out.all_text()))) if rx else []


def open_document(filename, data):
    name = filename.lower()
    if name.endswith(".docx"):
        return DocxDoc(data)
    if name.endswith(".pdf"):
        return PdfDoc(data)
    if name.endswith((".txt", ".md")):
        return TxtDoc(data)
    if name.endswith(".doc"):
        raise UnsupportedFile("Das alte Word-Format (.doc) wird nicht unterstützt. Bitte in Word als .docx speichern.")
    raise UnsupportedFile("Dieses Dateiformat wird noch nicht unterstützt. Möglich sind: .docx, .pdf, .txt")
