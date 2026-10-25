"""Lokaler Webserver. Hört nur auf 127.0.0.1; Dateien liegen ausschließlich im Arbeitsspeicher."""
import copy
import os
import re
import random
import secrets
import socket
import threading
import webbrowser
from datetime import datetime

from pathlib import Path

from flask import Flask, Response, abort, jsonify, make_response, redirect, request

from . import __version__, store, titel
from . import config as _cfg
from .config import APP_NAME, DEFAULT_PORT, MAX_UPLOAD_MB, ORG_CONTACT, ORG_NAME
from .detect import CATEGORIES, DROPDOWN_ORDER, analyze_all, name_variants
from .documents import UnsupportedFile, open_document
from .keyfile import load_key
from .restore import build_reverse, plan, regex_for
from .pseudonymize import DATE_MODES, Item, anonymize_filename, build_mapping
from .textutil import term_regex

INDEX_HTML = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")
app = Flask(__name__)
app.json.sort_keys = False
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

def _load_token():
    """Das Zugriffstoken bleibt zwischen den Starts gleich, damit ein Lesezeichen weiter funktioniert. Es liegt nur im eigenen Benutzerordner."""
    f = store.data_dir() / "zugang.txt"
    try:
        token = f.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if len(token) < 20:
        token = secrets.token_urlsafe(24)
        try:
            f.write_text(token, encoding="utf-8")
            os.chmod(f, 0o600)
        except OSError:
            pass
    return token


TOKEN = _load_token()
SHIFTS = {}  # je Titel eine feste Jahresverschiebung, damit Vorschau und Export dasselbe Datum ergeben
DOCS, RESULTS, DOCMETA = {}, {}, {}   # DOCMETA: doc_id -> {title, original} für das automatische Speichern
PORT = {"value": 0}


@app.before_request
def _guard():
    if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
        abort(403)
    # Schutz vor Anfragen anderer Webseiten (auch anderer lokaler Ports): Absender muss dieselbe Adresse sein
    origin = request.headers.get("Origin")
    if request.method not in ("GET", "HEAD") and origin and origin != "http://" + request.host:
        abort(403)
    if request.path == "/" and request.args.get("t") == TOKEN:
        return None
    if request.cookies.get("tok") != TOKEN:
        abort(403)


@app.after_request
def _headers(resp):
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    return resp


@app.get("/")
def index():
    if request.args.get("t") == TOKEN:
        resp = make_response(redirect("/"))
        resp.set_cookie("tok", TOKEN, httponly=True, samesite="Strict")
        return resp
    return Response(INDEX_HTML, mimetype="text/html")


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    resp = app.send_static_file("favicon.svg")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@app.get("/api/config")
def api_config():
    org_info = {"name": ORG_NAME, "slogan": _cfg.ORG_SLOGAN, "address": _cfg.ORG_ADDRESS, "links": _cfg.ORG_LINKS, "license": _cfg.LICENSE_NAME, "year": _cfg.COPYRIGHT_YEAR}
    return jsonify(app=APP_NAME, version=__version__, org=ORG_NAME, contact=ORG_CONTACT, org_info=org_info,
                   categories=CATEGORIES, drop_order=DROPDOWN_ORDER, date_modes=DATE_MODES, max_mb=MAX_UPLOAD_MB,
                   out_dir=str(titel.base_dir()))


@app.get("/api/titles")
def api_titles():
    return jsonify(titles=titel.list_titles(), with_key=titel.list_titles(with_key=True))


@app.post("/api/open-folder")
def api_open_folder():
    try:
        titel.open_folder((request.get_json(force=True) or {}).get("title"))
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True)


_THUMB_LOCK = threading.Lock()  # PyMuPDF ist nicht für gleichzeitige Aufrufe gedacht; die Liste lädt mehrere Bilder parallel


def _thumb_png(name, data):
    with _THUMB_LOCK:
        return _thumb_png_unlocked(name, data)


def _thumb_png_unlocked(name, data):
    """Kleines Vorschaubild der ersten Seite; Word und Text haben keine Seitenansicht, dort steht der Anfang des Textes auf einer Miniseite."""
    import fitz

    if name.lower().endswith(".pdf"):
        src = fitz.open(stream=data, filetype="pdf")
        pix = src[0].get_pixmap(matrix=fitz.Matrix(0.35, 0.35))
        return pix.tobytes("png")
    doc = open_document(name, data)
    if doc.kind == "docx":
        try:
            from .docx_html import thumbnail_png

            return thumbnail_png(doc)
        except Exception:
            pass  # sonst Textanfang
    text = " ".join(doc.text().split())[:900]
    page = fitz.open().new_page()
    page.insert_textbox(fitz.Rect(36, 36, 559, 806), text, fontname="helv", fontsize=11)
    return page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35)).tobytes("png")


@app.get("/api/original-thumb")
def api_original_thumb():
    try:
        name = request.args.get("file", "")
        read = titel.read_result if request.args.get("sub") == "ergebnis" else titel.read_original
        return _png(_thumb_png(name, read(request.args.get("title"), name)))
    except Exception:
        abort(404)


@app.post("/api/delete")
def api_delete():
    """Löscht endgültig: einen ganzen Titel, ein Original (mit Bearbeitungsstand) oder eine erstellte Datei. Die Rückfrage stellt die Oberfläche."""
    b = request.get_json(force=True) or {}
    title, kind, name = b.get("title"), b.get("kind"), b.get("file") or ""
    try:
        if kind == "title":
            titel.delete_title(title)
        elif kind == "original":
            titel.delete_original(title, name)
        elif kind == "result":
            titel.delete_result(title, name)
        else:
            return jsonify(error="Unbekannte Anfrage."), 400
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400
    except OSError as exc:
        return jsonify(error="Das Löschen ist fehlgeschlagen (%s)." % (exc.strerror or exc)), 500
    for k, m in list(DOCMETA.items()):   # geladene Dokumente dieses Titels/Originals nicht mehr automatisch speichern (sonst entstünde der Ordner neu)
        if titel.folder_name(m["title"]) == titel.folder_name(title) and (kind == "title" or (kind == "original" and m["original"] == name)):
            DOCMETA.pop(k, None)
    return jsonify(ok=True)


@app.post("/api/open-file")
def api_open_file():
    b = request.get_json(force=True) or {}
    try:
        titel.open_file(b.get("title"), b.get("file") or "", b.get("sub"))
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True)


def _library_json():
    return jsonify(out_dir=str(titel.base_dir()), default_dir=str(titel.default_dir()), locked=titel.env_locked(), titles=titel.library())


@app.get("/api/library")
def api_library():
    return _library_json()


@app.get("/api/title-files")
def api_title_files():
    try:
        return jsonify(folder=str(titel.folder(request.args.get("title"))), files=titel.title_files(request.args.get("title")),
                       originals=titel.list_originals(request.args.get("title")))
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/library/location")
def api_library_location():
    try:
        titel.set_base_dir((request.get_json(force=True) or {}).get("path"))
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400
    return _library_json()


@app.post("/api/library/choose")
def api_library_choose():
    try:
        return jsonify(path=titel.choose_folder())
    except titel.InvalidTitle as exc:
        return jsonify(error=str(exc)), 400


def _register(filename, data, title=None):
    """Dokument einlesen und analysieren. Mit title wird das Original sofort im Ordner des Titels abgelegt."""
    doc = open_document(filename, data)
    doc.filename = filename
    text = doc.text()
    findings, warn = analyze_all(text, doc.alt_texts())
    warnings = list(doc.warnings) + ([warn] if warn else [])
    if text.strip() and not any(f["category"] == "name" for f in findings):
        warnings.append("Es wurde kein Name gefunden. Ist das Dokument vielleicht schon anonymisiert, oder wurde ein Name "
                        "übersehen? Bitte den Text prüfen und fehlende Namen markieren oder unter „Eigene Begriffe“ ergänzen.")
    if not text.strip() and doc.kind != "pdf":
        warnings.append("Es wurde kein Text gefunden.")
    stored = titel.save_original(title, filename, data) if title else None
    doc_id = secrets.token_hex(8)
    DOCS[doc_id] = doc
    if stored:
        DOCMETA[doc_id] = {"title": title, "original": stored}
    pages = [{"w": w, "h": h} for w, h in getattr(doc, "page_sizes", [])]
    return dict(doc_id=doc_id, kind=doc.kind, text=text, findings=findings, warnings=warnings, images=doc.image_count, pages=pages, original=stored)


@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Keine Datei erhalten."), 400
    try:
        return jsonify(_register(f.filename, f.read(), (request.form.get("title") or "").strip() or None))
    except (UnsupportedFile, titel.InvalidTitle) as exc:
        return jsonify(error=str(exc)), 400
    except OSError as exc:
        return jsonify(error="Das Original konnte nicht gespeichert werden (%s)." % (exc.strerror or exc)), 500


@app.post("/api/resume")
def api_resume():
    """Ein im Titel-Ordner abgelegtes Original samt Bearbeitungsstand wieder laden."""
    b = request.get_json(force=True) or {}
    title, name = b.get("title"), b.get("original") or ""
    try:
        payload = _register(name, titel.read_original(title, name), None)
        DOCMETA[payload["doc_id"]] = {"title": title, "original": name}
        payload.update(original=name, state=titel.load_state(title, name))
        return jsonify(payload)
    except (UnsupportedFile, titel.InvalidTitle) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/doc/<doc_id>/state")
def api_state(doc_id):
    """Bearbeitungsstand (Auswahl, Pseudonym-Änderungen, Schwärzungen) automatisch speichern."""
    meta = DOCMETA.get(doc_id)
    if not meta:
        return jsonify(saved=False)
    try:
        titel.save_state(meta["title"], meta["original"], request.get_json(force=True) or {})
    except (titel.InvalidTitle, OSError) as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(saved=True)


def _pdf(doc_id):
    doc = DOCS.get(doc_id)
    if doc is None or doc.kind != "pdf":
        abort(404)
    return doc


def _png(data):
    return Response(data, mimetype="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/doc/<doc_id>/page/<int:n>.png")
def api_page(doc_id, n):
    doc = _pdf(doc_id)
    if not 0 <= n < len(doc.page_sizes):
        abort(404)
    return _png(doc.render_page(n))


@app.post("/api/doc/<doc_id>/marks")
def api_marks(doc_id):
    doc = _pdf(doc_id)
    terms = [t for t in (request.get_json(force=True) or {}).get("terms", []) if isinstance(t, str)]
    return jsonify(marks=doc.marks(terms))


@app.post("/api/doc/<doc_id>/rect")
def api_rect(doc_id):
    doc = _pdf(doc_id)
    b = request.get_json(force=True) or {}
    try:
        n = int(b["page"])
        text = doc.text_in_rect(n, float(b["x0"]), float(b["y0"]), float(b["x1"]), float(b["y1"]), bool(b.get("touch"))) if 0 <= n < len(doc.page_sizes) else ""
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Ungültiger Rahmen."), 400
    return jsonify(text=text)


def _word_html(doc):
    from .docx_html import render

    try:
        return jsonify(html=render(doc))
    except Exception:
        return jsonify(error="Die Word-Ansicht konnte nicht erstellt werden. Bitte die Textansicht benutzen."), 500


@app.get("/api/doc/<doc_id>/html")
def api_doc_html(doc_id):
    doc = DOCS.get(doc_id)
    if doc is None or doc.kind != "docx":
        abort(404)
    return _word_html(doc)


@app.get("/api/result/<rid>/html")
def api_result_html(rid):
    res = RESULTS.get(rid, {}).get("doc")
    if not res or not res[1].lower().endswith(".docx"):
        abort(404)
    return _word_html(open_document(res[1], res[0]))


@app.get("/api/result/<rid>/page/<int:n>.png")
def api_result_page(rid, n):
    res = RESULTS.get(rid, {}).get("doc")
    if not res or not res[1].lower().endswith(".pdf"):
        abort(404)
    import fitz

    pdf = fitz.open(stream=res[0], filetype="pdf")
    try:
        if not 0 <= n < len(pdf):
            abort(404)
        return _png(pdf[n].get_pixmap(dpi=110, alpha=False).tobytes("png"))
    finally:
        pdf.close()


@app.route("/api/dictionary", methods=["GET", "POST", "DELETE"])
def api_dictionary():
    if request.method == "GET":
        return jsonify(entries=store.load_dictionary())
    body = request.get_json(force=True)
    text, cat = (body.get("text") or "").strip(), body.get("category")
    if cat not in CATEGORIES or not text:
        return jsonify(error="Ungültige Angabe."), 400
    if request.method == "POST":
        return jsonify(entries=store.add_entry(text, cat))
    return jsonify(entries=store.remove_entry(text, cat))


def _items(raw):
    return [Item(i["text"], i["category"], "schwaerzen" if i.get("action") == "schwaerzen" else "pseudonym", i.get("date_mode") or "",
                 bool(i.get("main")), i.get("gender") or "", (i.get("override") or "").strip())
            for i in raw if i.get("text") and i.get("category") in CATEGORIES]


def _plan(body):
    """Gemeinsame Vorbereitung für Vorschau und Export: Schlüssel des Titels laden und die Zuordnung berechnen."""
    title = body.get("title")
    key = titel.load_key_for(title) or {"version": 2, "entries": []}
    key.setdefault("date_shift", SHIFTS.setdefault(titel.folder_name(title), random.choice([-2, -1, 1, 2])))
    items = _items(body.get("items", []))
    doc0 = DOCS.get(body.get("doc_id"))
    if doc0 is not None:   # Sicherheitsnetz: jede Schreibweise eines gewählten Namens wird mitersetzt, auch wenn die Erkennung sie anders einordnete
        have = {i.text for i in items}
        hay = [doc0.text()] + [a for a in doc0.alt_texts() if a]
        for it in [i for i in items if i.category == "name"]:
            for v, _n in name_variants(it.text, hay):
                if v not in have:
                    have.add(v)
                    items.append(Item(v, "name", action=it.action, gender=it.gender))
    date_mode = body.get("date_mode") if body.get("date_mode") in DATE_MODES else "jahr"
    doc = DOCS.get(body.get("doc_id"))
    words = set(re.findall(r"[\wÄÖÜäöüß-]+", doc.text().lower())) if doc else set()
    mapping, entries = build_mapping(items, date_mode, key=key, avoid=words)
    return title, key, items, mapping, entries, words


@app.post("/api/preview")
def api_preview():
    body = request.get_json(force=True)
    try:
        _t, key, _i, mapping, _e, words = _plan(body)
    except (titel.InvalidTitle, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    # Vorschläge für noch nicht angehakte Funde: so würden sie heißen, wenn man sie zusätzlich ersetzt
    extra = [i for i in _items(body.get("extra", [])) if i.text not in mapping]
    suggestions = build_mapping(extra, "jahr", key=copy.deepcopy(key), avoid=words)[0] if extra else {}
    return jsonify(previews=mapping, suggestions=suggestions)


@app.post("/api/doc/<doc_id>/preview-render")
def api_preview_render(doc_id):
    """Vorschau der fertigen Datei mit dem aktuellen Stand (nichts wird gespeichert)."""
    body = request.get_json(force=True) or {}
    doc = DOCS.get(doc_id)
    if doc is None:
        return jsonify(error="Das Dokument ist nicht mehr geladen."), 404
    body["doc_id"] = doc_id
    try:
        _t, _key, items, mapping, _e, _w = _plan(body)
    except (titel.InvalidTitle, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    blackouts = [b for b in (body.get("blackouts") or [])[:2000] if isinstance(b, dict)] if doc.kind == "pdf" else []
    data, ext, mime = doc.export(term_regex(mapping.keys()), mapping, bool(body.get("remove_images", True)), blackouts=blackouts)
    RESULTS.pop(body.get("prev_rid") or "", None)
    rid = secrets.token_hex(8)
    RESULTS[rid] = {"doc": (data, "Vorschau." + ext, mime)}
    out = dict(rid=rid, kind=doc.kind, previews=mapping)
    if ext == "pdf":
        out["pages"] = len(getattr(doc, "page_sizes", []))
    elif ext == "docx":
        from .docx_html import render

        try:
            out["html"] = render(open_document("v.docx", data))
        except Exception:
            out["html"] = ""
    return jsonify(out)


@app.post("/api/result/<rid>/rect")
def api_result_rect(rid):
    """Text im Rahmen auf der Ergebnis-Vorschau (zum Markieren auch im Ergebnis)."""
    res = RESULTS.get(rid, {}).get("doc")
    if not res or not res[1].lower().endswith(".pdf"):
        abort(404)
    from .documents import PdfDoc

    doc = PdfDoc(res[0])
    b = request.get_json(force=True) or {}
    try:
        n = int(b["page"])
        text = doc.text_in_rect(n, float(b["x0"]), float(b["y0"]), float(b["x1"]), float(b["y1"]), bool(b.get("touch"))) if 0 <= n < len(doc.page_sizes) else ""
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Ungültiger Rahmen."), 400
    return jsonify(text=text)


@app.post("/api/result/<rid>/marks")
def api_result_marks(rid):
    res = RESULTS.get(rid, {}).get("doc")
    if not res or not res[1].lower().endswith(".pdf"):
        abort(404)
    from .documents import PdfDoc

    terms = [t for t in (request.get_json(force=True) or {}).get("terms", []) if isinstance(t, str)]
    return jsonify(marks=PdfDoc(res[0]).marks(terms))


@app.post("/api/export")
def api_export():
    body = request.get_json(force=True)
    doc = DOCS.get(body.get("doc_id"))
    if doc is None:
        return jsonify(error="Das Dokument ist nicht mehr geladen. Bitte erneut hochladen."), 404
    try:
        title, key, items, mapping, entries, _w = _plan(body)
    except (titel.InvalidTitle, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    blackouts = [b for b in (body.get("blackouts") or [])[:2000] if isinstance(b, dict)] if doc.kind == "pdf" else []
    if not items and not blackouts:
        return jsonify(error="Es ist nichts zum Anonymisieren ausgewählt."), 400
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    key.setdefault("created", stamp)
    key["updated"] = stamp
    regex = term_regex(mapping.keys())
    data, ext, mime = doc.export(regex, mapping, bool(body.get("remove_images", True)), blackouts=blackouts)
    leftover = doc.leftover_check(data, ext, list(mapping.keys()))
    has_key = any(e["reversible"] for e in key["entries"])
    try:
        stem = Path(getattr(doc, "filename", "") or "Dokument").stem
        path = titel.save_named(title, anonymize_filename(stem, mapping, key.get("name_parts")) + "_anonymisiert", ext, data)
        if has_key:
            titel.save_key(title, key)
    except OSError as exc:
        return jsonify(error="Die Dateien konnten nicht gespeichert werden (%s)." % (exc.strerror or exc)), 500
    rid = secrets.token_hex(8)
    RESULTS[rid] = {"doc": (data, path.name, mime)}
    n_pages = len(getattr(doc, "page_sizes", [])) if ext == "pdf" else 0
    return jsonify(result_id=rid, has_key=has_key, leftover=leftover, folder=str(path.parent), file=path.name, result_pages=n_pages,
                   mapping=[{"original": e["original"], "replacement": e["replacement"]} for e in entries])


@app.post("/api/restore")
def api_restore():
    f, keyfile = request.files.get("file"), request.files.get("key")
    title = (request.form.get("title") or "").strip()
    if not f or not (keyfile or title):
        return jsonify(error="Bitte das überarbeitete Dokument und einen Titel (oder eine Schlüsseldatei) auswählen."), 400
    try:
        payload = load_key(keyfile.read()) if keyfile else titel.load_key_for(title)
    except (titel.InvalidTitle, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    if payload is None:
        return jsonify(error="Zu diesem Titel gibt es keine Schlüsseldatei."), 400
    try:
        doc = open_document(f.filename, f.read())
    except UnsupportedFile as exc:
        return jsonify(error=str(exc)), 400
    mapping, lost = build_reverse(payload)
    report = plan(doc.text(), mapping)
    data, ext, mime = doc.export(regex_for(mapping), mapping, remove_images=False, scrub=False)
    stem = re.sub(r"_anonymisiert(_\d+)?$", "", Path(f.filename or "Dokument").stem)
    base = anonymize_filename(stem, mapping) + "_wiederhergestellt"
    name, folder = "%s.%s" % (base, ext), None
    if not keyfile:
        try:
            path = titel.save_named(title, base, ext, data)
            name, folder = path.name, str(path.parent)
        except OSError:
            pass  # Download bleibt möglich
    rid = secrets.token_hex(8)
    RESULTS[rid] = {"doc": (data, name, mime)}
    report.update(result_id=rid, not_restorable=lost, folder=folder, file=name, kind=doc.kind, result_pages=len(getattr(doc, "page_sizes", [])) if doc.kind == "pdf" else 0,
                  warnings=doc.warnings if doc.kind != "pdf" else [])
    return jsonify(report)


@app.get("/download/<rid>/<which>")
def download(rid, which):
    res = RESULTS.get(rid, {}).get(which)
    if not res:
        abort(404)
    data, name, mime = res
    return Response(data, mimetype=mime, headers={"Content-Disposition": 'attachment; filename="%s"' % name})


@app.post("/api/quit")
def api_quit():
    DOCS.clear()
    RESULTS.clear()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify(ok=True)


def _free_port(preferred=0):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", preferred))
        except OSError:
            s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(open_browser=True):
    wanted = int(os.environ.get("ANONYMISIERUNGSTOOL_PORT") or DEFAULT_PORT)
    port = _free_port(wanted)
    PORT["value"] = port
    url = "http://127.0.0.1:%d/?t=%s" % (port, TOKEN)
    if port != wanted:
        print("Hinweis: Port %d ist belegt (läuft das Tool vielleicht schon?). Diesmal wird eine andere Adresse verwendet." % wanted)
    print("%s läuft lokal. Diese Adresse im Browser als Lesezeichen speichern (sie bleibt immer gleich):\n%s" % (APP_NAME, url))
    if open_browser and not os.environ.get("ANONYMISIERUNGSTOOL_NOBROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)
