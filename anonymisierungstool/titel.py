"""Titel der Anonymisierung: ein Ordner pro Titel mit den anonymisierten Dokumenten und der gemeinsamen Schlüsseldatei."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import store
from .keyfile import KEY_NAME, dump_key, load_key

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


class InvalidTitle(Exception):
    pass


def default_dir():
    return Path.home() / "Documents" / "Anonymisierungen"


def env_locked():
    """Ist der Ablageort per Umgebungsvariable festgelegt (dann nicht änderbar)?"""
    return bool(os.environ.get("ANONYMISIERUNGSTOOL_AUSGABE"))


def base_dir():
    env = os.environ.get("ANONYMISIERUNGSTOOL_AUSGABE")
    if env:
        return Path(env)
    custom = store.load_settings().get("ablage")
    return Path(custom).expanduser() if custom else default_dir()


def set_base_dir(path_str):
    """Ablageort ändern (leer = Standard). Der Ordner wird angelegt und auf Schreibbarkeit geprüft."""
    if env_locked():
        raise InvalidTitle("Der Ablageort ist durch eine Umgebungsvariable festgelegt und kann hier nicht geändert werden.")
    settings = store.load_settings()
    path_str = (path_str or "").strip()
    if not path_str:
        settings.pop("ablage", None)
    else:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            raise InvalidTitle("Bitte einen vollständigen Pfad angeben (z. B. /Users/name/Dokumente/Anonymisierungen).")
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".schreibtest"
            probe.write_text("x")
            probe.unlink()
        except OSError as exc:
            raise InvalidTitle("In diesem Ordner kann nicht gespeichert werden (%s)." % (exc.strerror or exc))
        settings["ablage"] = str(p)
    store.save_settings(settings)
    return base_dir()


ORIGINALS = "Originale"       # die hochgeladenen Originale (enthalten die echten Angaben)
STATE_DIR = ".Arbeitsstand"   # Bearbeitungsstand je Original (versteckt), damit man später weitermachen kann


def _safe_filename(name):
    name = _BAD.sub("-", Path(name or "").name).strip(" .-")[:120]
    return name or "Dokument"


def save_original(title, filename, data):
    """Legt das hochgeladene Original im Ordner des Titels ab (Unterordner Originale). Gleicher Inhalt: gleiche Datei, anderer
    Inhalt unter gleichem Namen: Nummer anhängen. Gibt den Dateinamen zurück."""
    d = folder(title, True) / ORIGINALS
    d.mkdir(exist_ok=True)
    base = _safe_filename(filename)
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    n = 1
    while True:
        name = base if n == 1 else "%s_%d%s" % (stem, n, "." + ext if ext else "")
        p = d / name
        if not p.exists():
            p.write_bytes(data)
            return name
        if p.read_bytes() == data:
            return name
        n += 1


def read_original(title, name):
    p = folder(title) / ORIGINALS / name
    if Path(name).name != name or not p.is_file():
        raise InvalidTitle("Das Original wurde nicht gefunden.")
    return p.read_bytes()


def read_result(title, name):
    """Datei aus dem Titel-Ordner (anonymisierte oder wiederhergestellte Fassung), z. B. für das Vorschaubild."""
    p = folder(title) / name
    if Path(name).name != name or name.startswith(".") or not p.is_file():
        raise InvalidTitle("Die Datei wurde nicht gefunden.")
    return p.read_bytes()


def _delete_file(path):
    if path.is_file() and not path.is_symlink():
        path.unlink()
        return True
    return False


def delete_original(title, name):
    """Original samt Bearbeitungsstand löschen. Schon erstellte anonymisierte Dateien und der Schlüssel bleiben."""
    if Path(name).name != name or name.startswith("."):
        raise InvalidTitle("Ungültiger Dateiname.")
    ok = _delete_file(folder(title) / ORIGINALS / name)
    _delete_file(_state_file(title, name))
    if not ok:
        raise InvalidTitle("Das Original wurde nicht gefunden.")


def delete_result(title, name):
    """Anonymisierte oder wiederhergestellte Datei löschen (nicht die Schlüsseldatei)."""
    if Path(name).name != name or name.startswith(".") or name == KEY_NAME or file_kind(name) == "andere":
        raise InvalidTitle("Diese Datei kann hier nicht gelöscht werden.")
    if not _delete_file(folder(title) / name):
        raise InvalidTitle("Die Datei wurde nicht gefunden.")


def delete_title(title):
    """Ganzen Titel mit allen Dokumenten, Originalen, Bearbeitungsständen und der Schlüsseldatei löschen."""
    import shutil

    p = folder(title)
    base = base_dir().resolve()
    if not p.is_dir() or p.is_symlink() or p.resolve().parent != base:
        raise InvalidTitle("Der Titel wurde nicht gefunden.")
    shutil.rmtree(p)


def _state_file(title, name):
    return folder(title) / STATE_DIR / (Path(name).name + ".json")


def save_state(title, name, state):
    keep = {k: state[k] for k in ("findings", "blackouts", "rm", "done") if k in state}
    f = _state_file(title, name)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")


def load_state(title, name):
    try:
        return json.loads(_state_file(title, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_originals(title):
    d = folder(title) / ORIGINALS
    out = []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                st = load_state(title, f.name)
                out.append({"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime,
                            "has_state": st is not None, "done": bool(st and st.get("done"))})
    return out


def library():
    """Alle Titel im Ablageort: Name, Zahl der Dokumente, Schlüssel vorhanden, letzte Änderung."""
    base = base_dir()
    out = []
    if base.is_dir():
        for p in base.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            files = [f for f in p.iterdir() if f.is_file() and not f.name.startswith(".")]
            origs = list_originals(p.name)
            all_times = [f.stat().st_mtime for f in files] + [o["modified"] for o in origs]
            out.append({"name": p.name,
                        "docs": sum(file_kind(f.name) == "anonymisiert" for f in files),
                        "restored": sum(file_kind(f.name) == "wiederhergestellt" for f in files),
                        "originals": len(origs), "open": sum(not o["done"] for o in origs),
                        "has_key": (p / KEY_NAME).is_file(),
                        "modified": max(all_times or [p.stat().st_mtime])})
    out.sort(key=lambda t: -t["modified"])
    return out


def title_files(title):
    d = folder(title)
    out = []
    if d.is_dir():
        for f in d.iterdir():
            if not f.is_file() or f.name.startswith("."):
                continue
            kind = "schluessel" if f.name == KEY_NAME else file_kind(f.name)
            st = f.stat()
            out.append({"name": f.name, "kind": kind, "size": st.st_size, "modified": st.st_mtime})
    order = {"anonymisiert": 0, "wiederhergestellt": 1, "andere": 2, "schluessel": 3}
    out.sort(key=lambda f: (order[f["kind"]], f["name"]))
    return out


def folder_name(title):
    """Macht aus dem Titel einen sicheren Ordnernamen (keine Pfadzeichen, kein Verlassen des Ausgabeordners)."""
    name = re.sub(r"\s+", " ", _BAD.sub("-", (title or "").strip())).strip(" .-")[:80].strip(" .-")
    if not name:
        raise InvalidTitle("Bitte einen Titel für die Anonymisierung eingeben.")
    if name.upper() in _RESERVED:
        name += "_"
    return name


def folder(title, create=False):
    path = base_dir() / folder_name(title)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def list_titles(with_key=False):
    base = base_dir()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (not with_key or (p / KEY_NAME).is_file()))


def load_key_for(title):
    """Gibt die Schlüsseldaten des Titels zurück oder None, wenn es noch keine gibt."""
    f = folder(title) / KEY_NAME
    return load_key(f.read_bytes()) if f.is_file() else None


def save_key(title, payload):
    path = folder(title, True) / KEY_NAME
    path.write_bytes(dump_key(payload))
    return path


def save_file(title, stem, ext, data):
    """Speichert nummeriert (stem_01.ext, stem_02.ext, ...) und überschreibt nie etwas. Alte Namensform; neu siehe save_named."""
    d = folder(title, True)
    n = 1
    while True:
        p = d / ("%s_%02d.%s" % (stem, n, ext))
        try:
            with open(p, "xb") as fh:
                fh.write(data)
            return p
        except FileExistsError:
            n += 1


def save_named(title, name, ext, data):
    """Speichert als name.ext, bei Kollision name_2.ext; überschreibt nie etwas."""
    d = folder(title, True)
    n = 1
    while True:
        p = d / ("%s.%s" % (name if n == 1 else "%s_%d" % (name, n), ext))
        try:
            with open(p, "xb") as fh:
                fh.write(data)
            return p
        except FileExistsError:
            n += 1


def file_kind(name):
    """Art einer Datei im Titel-Ordner: alte Namen (Dokument_anonymisiert_01) und neue (<Original>_anonymisiert)."""
    stem = name.rpartition(".")[0] or name
    if re.search(r"(^Dokument_anonymisiert_\d+$)|(_anonymisiert(_\d+)?$)", stem):
        return "anonymisiert"
    if re.search(r"(^Dokument_wiederhergestellt_)|(_wiederhergestellt(_\d+)?$)", stem):
        return "wiederhergestellt"
    return "andere"


def _open(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_folder(title=None):
    path = folder(title) if title else base_dir()
    if not path.is_dir():
        if title:
            raise InvalidTitle("Der Ordner existiert noch nicht.")
        path.mkdir(parents=True, exist_ok=True)
    _open(path)


def open_file(title, filename, sub=None):
    """Eine Datei aus dem Ordner des Titels (oder dessen Unterordner Originale) mit dem Standardprogramm öffnen."""
    path = folder(title) / (ORIGINALS if sub == ORIGINALS else "") / filename
    if Path(filename).name != filename or not path.is_file():
        raise InvalidTitle("Die Datei wurde nicht gefunden.")
    _open(path)


def choose_folder():
    """Systemdialog zur Ordnerauswahl; gibt den Pfad zurück oder '' bei Abbruch."""
    prompt = "Ablageort für PP-Inkognito wählen"
    if sys.platform == "darwin":
        cmd = ["osascript", "-e", 'POSIX path of (choose folder with prompt "%s")' % prompt]
    elif os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; "
               "$f.Description = '%s'; if ($f.ShowDialog() -eq 'OK') { $f.SelectedPath }" % prompt]
    else:
        cmd = ["zenity", "--file-selection", "--directory", "--title=" + prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        raise InvalidTitle("Der Auswahldialog ist auf diesem System nicht verfügbar. Bitte den Pfad eintippen.")
    return r.stdout.strip() if r.returncode == 0 else ""
