"""Word-Dokument als seitenähnliches HTML für die Ansicht im Tool (Tabellen, Spalten, Schrift, Bilder, Textfelder).

Das ist eine Annäherung an Word, kein genaues Abbild: Seitenumbrüche, Schriftarten und frei schwebende Objekte weichen ab.
Die Datei selbst wird dafür nie verändert; die Ansicht dient nur dem Prüfen der Markierungen."""
import base64
import html

from .documents import MC, R, A, _w

WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V = "urn:schemas-microsoft-com:vml"
HIGHLIGHT = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff", "blue": "#0000ff", "red": "#ff0000",
             "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000", "darkMagenta": "#800080", "darkRed": "#800000",
             "darkYellow": "#808000", "darkGray": "#808080", "lightGray": "#c0c0c0", "black": "#000000", "white": "#ffffff"}
SERIF = {"times new roman", "cambria", "georgia", "garamond", "book antiqua", "palatino linotype", "constantia", "baskerville"}


def _on(el):
    return el is not None and el.get(_w("val")) not in ("0", "false", "off", "none")


def _num(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _color(v):
    return "#" + v if v and v != "auto" and len(v) in (3, 6) else ""


def _border(el):
    if el is None or el.get(_w("val")) in (None, "nil", "none"):
        return ""
    px = max(1, round(_num(el.get(_w("sz")), 4) / 8 * 1.33))
    return "%dpx solid %s" % (px, _color(el.get(_w("color"))) or "#000")


class _Styles:
    def __init__(self, root):
        self.by = {s.get(_w("styleId")): s for s in root.iter(_w("style"))} if root is not None else {}
        dd = root.find(_w("docDefaults")) if root is not None else None
        self.def_r = dd.find("%s/%s" % (_w("rPrDefault"), _w("rPr"))) if dd is not None else None
        self.def_p = dd.find("%s/%s" % (_w("pPrDefault"), _w("pPr"))) if dd is not None else None
        # Standardabsatzformat (Normal), falls der Absatz keins nennt
        self.default_p = next((i for i, s in self.by.items() if s.get(_w("type")) == "paragraph" and s.get(_w("default")) in ("1", "true")), None)

    def chain(self, sid):
        out, seen = [], set()
        while sid and sid in self.by and sid not in seen:
            seen.add(sid)
            out.append(self.by[sid])
            b = self.by[sid].find(_w("basedOn"))
            sid = b.get(_w("val")) if b is not None else None
        return out[::-1]


def _merge_r(d, rpr):
    if rpr is None:
        return
    for c in rpr:
        t = c.tag.rpartition("}")[2]
        if t in ("b", "i", "strike", "caps", "smallCaps"):
            d[t] = _on(c)
        elif t == "u":
            d["u"] = c.get(_w("val")) not in (None, "none")
        elif t == "color":
            d["color"] = _color(c.get(_w("val"))) or d.get("color", "")
        elif t == "sz":
            d["sz"] = _num(c.get(_w("val")), 22) / 2
        elif t == "rFonts":
            f = c.get(_w("ascii")) or c.get(_w("hAnsi"))
            if f:
                d["font"] = f
        elif t == "highlight":
            d["bg"] = HIGHLIGHT.get(c.get(_w("val")), "")
        elif t == "shd":
            d["bg"] = _color(c.get(_w("fill")))
        elif t == "vertAlign":
            d["va"] = c.get(_w("val"))
        elif t == "vanish":
            d["hidden"] = _on(c)


def _merge_p(d, ppr):
    if ppr is None:
        return
    for c in ppr:
        t = c.tag.rpartition("}")[2]
        if t == "jc":
            d["jc"] = {"both": "justify", "center": "center", "right": "right", "end": "right"}.get(c.get(_w("val")), "left")
        elif t == "spacing":
            for k in ("before", "after", "line", "lineRule"):
                if c.get(_w(k)) is not None:
                    d[k] = c.get(_w(k))
        elif t == "ind":
            for k, names in (("left", ("left", "start")), ("right", ("right", "end")), ("firstLine", ("firstLine",)), ("hanging", ("hanging",))):
                for n in names:
                    if c.get(_w(n)) is not None:
                        d[k] = c.get(_w(n))
            if c.get(_w("hanging")) is not None:
                d.pop("firstLine", None)
        elif t == "shd":
            d["bg"] = _color(c.get(_w("fill")))
        elif t == "pBdr":
            for side in c:
                b = _border(side)
                if b:
                    d["bd_" + side.tag.rpartition("}")[2]] = b
        elif t == "numPr":
            n, lv = c.find(_w("numId")), c.find(_w("ilvl"))
            if n is not None:
                d["numId"] = n.get(_w("val"))
            if lv is not None:
                d["ilvl"] = _num(lv.get(_w("val")))


class Renderer:
    def __init__(self, docx_doc):
        self.d = docx_doc.doc
        self.styles = _Styles(self.d.styles.element)
        self.counters = {}
        self.part = self.d.part
        self.nums = self._numbering()
        self.default_r = {}
        _merge_r(self.default_r, self.styles.def_r)

    # ---- Nummerierung
    def _numbering(self):
        try:
            root = self.d.part.numbering_part.element
        except Exception:
            return {}
        abstract = {a.get(_w("abstractNumId")): a for a in root.iter(_w("abstractNum"))}
        out = {}
        for n in root.iter(_w("num")):
            a = n.find(_w("abstractNumId"))
            if a is not None and a.get(_w("val")) in abstract:
                lv = {}
                for l in abstract[a.get(_w("val"))].iter(_w("lvl")):
                    f, t, s = l.find(_w("numFmt")), l.find(_w("lvlText")), l.find(_w("start"))
                    lv[_num(l.get(_w("ilvl")))] = (f.get(_w("val")) if f is not None else "decimal", t.get(_w("val")) if t is not None else "%1.",
                                                   _num(s.get(_w("val")), 1) if s is not None else 1)
                out[n.get(_w("numId"))] = lv
        return out

    def _label(self, num_id, ilvl):
        lv = self.nums.get(num_id, {})
        fmt, text, start = lv.get(ilvl, ("bullet", "•", 1))
        if fmt == "bullet" or num_id == "0":
            return "•"
        key = (num_id, ilvl)
        self.counters[key] = self.counters.get(key, start - 1) + 1
        for k in [k for k in self.counters if k[0] == num_id and k[1] > ilvl]:
            del self.counters[k]
        out = text
        for i in range(ilvl + 1):
            out = out.replace("%%%d" % (i + 1), self._fmt(self.counters.get((num_id, i), lv.get(i, (0, 0, 1))[2]), lv.get(i, ("decimal",))[0]))
        return out

    @staticmethod
    def _fmt(n, fmt):
        if fmt in ("lowerLetter", "upperLetter"):
            s = chr(96 + (n - 1) % 26 + 1) * (1 + (n - 1) // 26)
            return s.upper() if fmt == "upperLetter" else s
        return str(n)

    # ---- Bilder
    def _image(self, rid, part, w=0, h=0):
        try:
            p = part.related_parts[rid]
            ct = p.content_type
            if not ct.startswith("image/") or "emf" in ct or "wmf" in ct:
                return ""
            size = ""
            if w and h:
                size = ' style="width:%dpx;height:auto;max-width:100%%"' % w
            return '<img alt=""%s src="data:%s;base64,%s">' % (size, ct, base64.b64encode(p.blob).decode())
        except Exception:
            return ""

    def _drawing(self, el, part):
        tb = next(el.iter(_w("txbxContent")), None)
        if tb is not None:
            out = []
            self.blocks(tb, out, part)
            return '<div class="tbx">%s</div>' % "".join(out)
        blip = next(el.iter("{%s}blip" % A), None)
        if blip is None:
            return ""
        ext = next(el.iter("{%s}extent" % WP), None)
        w = _num(ext.get("cx")) // 9525 if ext is not None else 0
        h = _num(ext.get("cy")) // 9525 if ext is not None else 0
        return self._image(blip.get("{%s}embed" % R), part, w, h)

    def _pict(self, el, part):
        tb = next(el.iter(_w("txbxContent")), None)
        if tb is not None:
            out = []
            self.blocks(tb, out, part)
            return '<div class="tbx">%s</div>' % "".join(out)
        im = next(el.iter("{%s}imagedata" % V), None)
        return self._image(im.get("{%s}id" % R), part) if im is not None else ""

    # ---- Text
    def _run(self, r, base, part):
        props = dict(base)
        rst = r.find("%s/%s" % (_w("rPr"), _w("rStyle")))
        if rst is not None:
            for s in self.styles.chain(rst.get(_w("val"))):
                _merge_r(props, s.find(_w("rPr")))
        _merge_r(props, r.find(_w("rPr")))
        if props.get("hidden"):
            return ""
        parts = []

        def walk(el):
            for c in el:
                t = c.tag.rpartition("}")[2]
                if t == "t":
                    parts.append(html.escape(c.text or "", quote=False))
                elif t == "tab":
                    parts.append("\t")
                elif t == "br":
                    parts.append('<hr class="pb">' if c.get(_w("type")) == "page" else "<br>")
                elif t == "cr":
                    parts.append("<br>")
                elif t == "noBreakHyphen":
                    parts.append("‑")
                elif t == "drawing":
                    parts.append(self._drawing(c, part))
                elif t == "pict":
                    parts.append(self._pict(c, part))
                elif c.tag == "{%s}AlternateContent" % MC:
                    ch = c.find("{%s}Choice" % MC)
                    if ch is not None:
                        walk(ch)

        walk(r)
        body = "".join(parts)
        if not body:
            return ""
        css = []
        if props.get("b"):
            css.append("font-weight:700")
        if props.get("i"):
            css.append("font-style:italic")
        deco = [x for x, k in (("underline", "u"), ("line-through", "strike")) if props.get(k)]
        if deco:
            css.append("text-decoration:" + " ".join(deco))
        if props.get("caps"):
            css.append("text-transform:uppercase")
        if props.get("smallCaps"):
            css.append("font-variant:small-caps")
        if props.get("color"):
            css.append("color:" + props["color"])
        if props.get("bg"):
            css.append("background:" + props["bg"])
        if props.get("sz") and props["sz"] != self.default_r.get("sz"):
            css.append("font-size:%gpt" % props["sz"])
        if props.get("font") and props["font"] != self.default_r.get("font"):
            css.append("font-family:" + self._family(props["font"]))
        if props.get("va") in ("superscript", "subscript"):
            css.append("vertical-align:%s;font-size:smaller" % ("super" if props["va"] == "superscript" else "sub"))
        return '<span style="%s">%s</span>' % (";".join(css), body) if css else body

    def _runs(self, el, base, part):
        out = []
        for c in el:
            t = c.tag.rpartition("}")[2]
            if t == "r":
                out.append(self._run(c, base, part))
            elif t in ("hyperlink", "ins", "smartTag", "fldSimple", "customXml", "sdtContent", "sdt", "bdo", "dir"):
                out.append(self._runs(c, base, part))
        return "".join(out)

    @staticmethod
    def _family(name):
        return "'%s',%s" % (name.replace('"', "").replace("'", ""), "serif" if name.lower() in SERIF else "sans-serif")  # einfache Anführungszeichen: steht in style="..."

    # ---- Absätze und Tabellen
    def _para(self, p, out, part):
        ppr = p.find(_w("pPr"))
        pst = ppr.find(_w("pStyle")).get(_w("val")) if ppr is not None and ppr.find(_w("pStyle")) is not None else self.styles.default_p
        props, base = {}, dict(self.default_r)
        _merge_p(props, self.styles.def_p)
        for s in self.styles.chain(pst):
            _merge_p(props, s.find(_w("pPr")))
            _merge_r(base, s.find(_w("rPr")))
        _merge_p(props, ppr)
        css = []
        if props.get("jc"):
            css.append("text-align:" + props["jc"])
        css.append("margin:%gpt %gpx %gpt %gpx" % (_num(props.get("before")) / 20, _num(props.get("right")) / 15, _num(props.get("after")) / 20, _num(props.get("left")) / 15))
        if props.get("hanging"):
            css.append("text-indent:-%gpx" % (_num(props["hanging"]) / 15))
        elif props.get("firstLine"):
            css.append("text-indent:%gpx" % (_num(props["firstLine"]) / 15))
        line = _num(props.get("line"))
        if line:
            css.append("line-height:%s" % (("%.2f" % (line / 240)) if props.get("lineRule", "auto") == "auto" else "%gpt" % (line / 20)))
        if props.get("bg"):
            css.append("background:" + props["bg"])
        for side in ("top", "bottom", "left", "right"):
            if props.get("bd_" + side):
                css.append("border-%s:%s" % (side, props["bd_" + side]))
        label = ""
        if props.get("numId") and props["numId"] != "0":
            label = '<span class="num">%s </span>' % html.escape(self._label(props["numId"], props.get("ilvl", 0)), quote=False)
        # Absatzmarke selbst (Größe leerer Absätze)
        mark = {}
        _merge_r(mark, ppr.find(_w("rPr")) if ppr is not None else None)
        if mark.get("sz") and not self._runs(p, base, part):
            css.append("font-size:%gpt" % mark["sz"])
        inner = self._runs(p, base, part)
        out.append('<p style="%s">%s%s</p>' % (";".join(css), label, inner or "<br>"))

    def _table(self, tbl, out, part):
        grid = [_num(g.get(_w("w"))) for g in (tbl.find(_w("tblGrid")) if tbl.find(_w("tblGrid")) is not None else [])]
        tpr = tbl.find(_w("tblPr"))
        borders = {}
        tst = tpr.find(_w("tblStyle")) if tpr is not None else None
        for s in self.styles.chain(tst.get(_w("val")) if tst is not None else None):
            tb = s.find("%s/%s" % (_w("tblPr"), _w("tblBorders")))
            for b in (tb if tb is not None else []):
                borders[b.tag.rpartition("}")[2]] = _border(b)
        tb = tpr.find(_w("tblBorders")) if tpr is not None else None
        for b in (tb if tb is not None else []):
            borders[b.tag.rpartition("}")[2]] = _border(b)
        rows, starts = [], {}
        for ri, tr in enumerate(tbl.findall(_w("tr"))):
            col, cells = 0, []
            for tc in tr.findall(_w("tc")):
                pr = tc.find(_w("tcPr"))
                span = _num(pr.find(_w("gridSpan")).get(_w("val")), 1) if pr is not None and pr.find(_w("gridSpan")) is not None else 1
                vm = pr.find(_w("vMerge")) if pr is not None else None
                if vm is not None and vm.get(_w("val")) in (None, "continue") and col in starts:
                    starts[col]["rowspan"] += 1
                else:
                    cell = {"tc": tc, "pr": pr, "span": span, "rowspan": 1}
                    cells.append(cell)
                    if vm is not None:
                        starts[col] = cell
                col += span
            h = tr.find("%s/%s" % (_w("trPr"), _w("trHeight")))
            rows.append((cells, _num(h.get(_w("val"))) / 15 if h is not None else 0, ri))
        width = sum(grid)
        out.append('<table style="table-layout:fixed;border-collapse:collapse;width:%gpx;max-width:100%%">' % (width / 15 if width else 600))
        if grid:
            out.append("<colgroup>%s</colgroup>" % "".join('<col style="width:%gpx">' % (g / 15) for g in grid))
        for cells, h, _ri in rows:
            out.append("<tr%s>" % (' style="height:%gpx"' % h if h else ""))
            for c in cells:
                pr, css = c["pr"], ["padding:1px 7px", "vertical-align:top", "overflow-wrap:anywhere"]
                va = pr.find(_w("vAlign")) if pr is not None else None
                if va is not None:
                    css[1] = "vertical-align:" + {"center": "middle", "bottom": "bottom"}.get(va.get(_w("val")), "top")
                shd = pr.find(_w("shd")) if pr is not None else None
                if shd is not None and _color(shd.get(_w("fill"))):
                    css.append("background:" + _color(shd.get(_w("fill"))))
                tcb = pr.find(_w("tcBorders")) if pr is not None else None
                mine = {b.tag.rpartition("}")[2]: _border(b) for b in (tcb if tcb is not None else [])}
                for side, alt in (("top", "top"), ("bottom", "bottom"), ("left", "left"), ("right", "right")):
                    b = mine.get(side, mine.get({"left": "start", "right": "end"}.get(side, ""), borders.get(side) or borders.get("inside" + ("H" if side in ("top", "bottom") else "V"), "")))
                    if b:
                        css.append("border-%s:%s" % (alt, b))
                inner = []
                self.blocks(c["tc"], inner, part)
                out.append('<td colspan="%d" rowspan="%d" style="%s">%s</td>' % (c["span"], c["rowspan"], ";".join(css), "".join(inner) or "<p><br></p>"))
            out.append("</tr>")
        out.append("</table>")

    def blocks(self, container, out, part):
        for c in container:
            t = c.tag.rpartition("}")[2]
            if t == "p":
                self._para(c, out, part)
            elif t == "tbl":
                self._table(c, out, part)
            elif t == "sdt":
                content = c.find(_w("sdtContent"))
                if content is not None:
                    self.blocks(content, out, part)

    # ---- Seite
    def render(self):
        body = self.d.element.body
        sect = body.find(_w("sectPr"))
        pg = sect.find(_w("pgSz")) if sect is not None else None
        mar = sect.find(_w("pgMar")) if sect is not None else None
        w = _num(pg.get(_w("w")), 11906) / 15 if pg is not None else 794
        top, right, bottom, left = [(_num(mar.get(_w(k)), 1134) / 15 if mar is not None else 76) for k in ("top", "right", "bottom", "left")]
        cols = sect.find(_w("cols")) if sect is not None else None
        ncols = _num(cols.get(_w("num")), 1) if cols is not None else 1
        gap = _num(cols.get(_w("space")), 708) / 15 if cols is not None else 0
        fam = self._family(self.default_r.get("font", "Calibri")) + ",Carlito,Arial"
        head, foot = [], []
        try:
            s0 = self.d.sections[0]
            for hf, dst in ((s0.header, head), (s0.footer, foot)):
                if not hf.is_linked_to_previous:
                    self.blocks(hf._element, dst, hf.part)
        except Exception:
            pass
        main = []
        self.blocks(body, main, self.part)
        colcss = ";column-count:%d;column-gap:%gpx" % (ncols, gap) if ncols > 1 else ""
        return ('<div class="wpage" data-w="%d" style="width:%gpx;padding:%gpx %gpx %gpx %gpx;font-family:%s;font-size:%gpt">%s%s%s</div>' %
                (w, w, top, right, bottom, left, fam, self.default_r.get("sz", 11),
                 '<div class="whead">%s</div>' % "".join(head) if "".join(head).strip() else "",
                 '<div class="wbody" style="%s">%s</div>' % (colcss.lstrip(";"), "".join(main)),
                 '<div class="wfoot">%s</div>' % "".join(foot) if "".join(foot).strip() else ""))


def render(docx_doc):
    return Renderer(docx_doc).render()


def thumbnail_png(docx_doc, scale=0.5):
    """Erste Seite der Seitenansicht als kleines PNG (für Vorschaubilder); wirft bei Problemen eine Ausnahme."""
    import os
    import tempfile

    import fitz

    story = fitz.Story(html="<html><body>%s</body></html>" % render(docx_doc), user_css="p{margin:0}")
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        out = fitz.DocumentWriter(path)
        page = fitz.paper_rect("a4")
        dev = out.begin_page(page)
        story.place(page + (8, 8, -8, -8))
        story.draw(dev)
        out.end_page()
        out.close()
        pdf = fitz.open(path)
        try:
            return pdf[0].get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
        finally:
            pdf.close()
    finally:
        os.unlink(path)
