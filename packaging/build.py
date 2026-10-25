"""Baut PP-Inkognito als Installer: Mac-Abbild (.dmg mit PP-Inkognito.app) bzw. Windows-Setup (.exe).

Aufruf: python packaging/build.py <plattform>   z. B. macos-arm64 oder windows
Ergebnis: dist-zip/PP-Inkognito-<version>-<plattform>.dmg bzw. -Setup.exe
Die Programme sind nicht signiert (siehe README).
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anonymisierungstool import __version__  # noqa: E402

PLATFORM = sys.argv[1] if len(sys.argv) > 1 else sys.platform
IS_WIN = PLATFORM.startswith("windows")
NAME = "PP-Inkognito"
SEP = os.pathsep  # PyInstaller trennt Quelle und Ziel bei --add-data mit ":" (Mac/Linux) bzw. ";" (Windows)
OUT = ROOT / "dist-zip"


def render_icon_png(size, path):
    """Zeichen aus favicon.svg als PNG."""
    import fitz

    doc = fitz.open(str(ROOT / "anonymisierungstool" / "static" / "favicon.svg"))
    page = doc[0]
    zoom = size / page.rect.width
    page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True).save(str(path))


def make_icon(tmp):
    if IS_WIN:
        from PIL import Image

        big = tmp / "icon.png"
        render_icon_png(256, big)
        ico = tmp / "icon.ico"
        Image.open(big).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return ico
    iconset = tmp / "icon.iconset"
    iconset.mkdir()
    for base in (16, 32, 128, 256, 512):
        render_icon_png(base, iconset / ("icon_%dx%d.png" % (base, base)))
        render_icon_png(base * 2, iconset / ("icon_%dx%d@2x.png" % (base, base)))
    icns = tmp / "icon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
    return icns


def run_pyinstaller(icon):
    import PyInstaller.__main__ as pyi

    args = ["--noconfirm", "--clean", "--name", NAME, "--specpath", str(ROOT / "build"), "--windowed", "--icon", str(icon),
            "--add-data", "%s%sanonymisierungstool/templates" % (ROOT / "anonymisierungstool" / "templates", SEP),
            "--add-data", "%s%sanonymisierungstool/static" % (ROOT / "anonymisierungstool" / "static", SEP),
            "--hidden-import", "anonymisierungstool.server"]
    if not IS_WIN:
        args += ["--osx-bundle-identifier", "de.performplus.ppinkognito"]
    priv = ROOT / "anonymisierungstool" / "kontakt_privat.json"   # nur im Installer, entsteht aus einem GitHub-Geheimnis
    if priv.is_file():
        args += ["--add-data", "%s%sanonymisierungstool" % (priv, SEP)]
    for pkg in ("spacy", "de_core_news_md", "thinc", "srsly", "cymem", "preshed", "blis", "murmurhash", "spacy_legacy", "spacy_loggers",
                "pymupdf", "fitz", "docx"):
        args += ["--collect-all", pkg]
    args.append(str(ROOT / "app.py"))
    pyi.run(args)


def build_mac():
    stage = Path(tempfile.mkdtemp()) / NAME
    stage.mkdir()
    subprocess.run(["ditto", str(ROOT / "dist" / (NAME + ".app")), str(stage / (NAME + ".app"))], check=True)
    os.symlink("/Applications", stage / "Programme")
    shutil.copy(ROOT / "packaging" / "LIES-MICH-Mac.txt", stage / "LIES-MICH.txt")
    shutil.copy(ROOT / "LICENSE", stage / "LICENSE.txt")
    dmg = OUT / ("%s-%s-Mac.dmg" % (NAME, __version__))
    subprocess.run(["hdiutil", "create", "-volname", NAME, "-srcfolder", str(stage), "-ov", "-format", "UDZO", str(dmg)], check=True)
    return dmg


def build_windows():
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    shutil.copy(ROOT / "LICENSE", ROOT / "dist" / NAME / "LICENSE.txt")
    shutil.copy(ROOT / "packaging" / "LIES-MICH-Windows.txt", ROOT / "dist" / NAME / "LIES-MICH.txt")
    subprocess.run([iscc, "/Qp", "/DAppVersion=%s" % __version__, "/DSourceDir=%s" % (ROOT / "dist" / NAME), "/DOutDir=%s" % OUT,
                    "/DIconFile=%s" % (ROOT / "build" / "icon.ico"), str(ROOT / "packaging" / "installer.iss")], check=True)
    return OUT / ("%s-%s-Windows-Setup.exe" % (NAME, __version__))


def main():
    for d in ("build", "dist", "dist-zip"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    OUT.mkdir()
    (ROOT / "build").mkdir()
    icon = make_icon(ROOT / "build")
    run_pyinstaller(icon)
    result = build_windows() if IS_WIN else build_mac()
    print("Fertig:", result, "%.0f MB" % (result.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
