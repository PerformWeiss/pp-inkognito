"""Baut PP-Inkognito als eigenständiges Programm (PyInstaller) und packt es als ZIP.

Aufruf: python packaging/build.py <plattform-name>   z. B. macos-arm64 oder windows
Ergebnis: dist-zip/PP-Inkognito-<version>-<plattform>.zip
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anonymisierungstool import __version__  # noqa: E402

PLATFORM = sys.argv[1] if len(sys.argv) > 1 else sys.platform
NAME = "PP-Inkognito"
SEP = os.pathsep  # PyInstaller trennt Quelle und Ziel bei --add-data mit ":" (Mac/Linux) bzw. ";" (Windows)


def main():
    import PyInstaller.__main__ as pyi

    for d in ("build", "dist", "dist-zip"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    args = ["--noconfirm", "--clean", "--name", NAME, "--specpath", str(ROOT / "build"),
            "--add-data", "%s%sanonymisierungstool/templates" % (ROOT / "anonymisierungstool" / "templates", SEP),
            "--add-data", "%s%sanonymisierungstool/static" % (ROOT / "anonymisierungstool" / "static", SEP),
            "--hidden-import", "anonymisierungstool.server"]
    priv = ROOT / "anonymisierungstool" / "kontakt_privat.json"   # nur im Installer, entsteht aus einem GitHub-Geheimnis
    if priv.is_file():
        args += ["--add-data", "%s%sanonymisierungstool" % (priv, SEP)]
    for pkg in ("spacy", "de_core_news_md", "thinc", "srsly", "cymem", "preshed", "blis", "murmurhash", "spacy_legacy", "spacy_loggers",
                "pymupdf", "fitz", "docx"):
        args += ["--collect-all", pkg]
    args.append(str(ROOT / "app.py"))
    pyi.run(args)

    folder = ROOT / "dist" / NAME
    shutil.copy(ROOT / "packaging" / ("LIES-MICH-%s.txt" % ("Windows" if PLATFORM.startswith("windows") else "Mac")), folder / "LIES-MICH.txt")
    shutil.copy(ROOT / "LICENSE", folder / "LICENSE.txt")
    out = ROOT / "dist-zip"
    out.mkdir()
    zip_path = out / ("%s-%s-%s.zip" % (NAME, __version__, PLATFORM))
    if sys.platform == "darwin":  # ditto erhält Ausführungsrechte und Mac-Besonderheiten
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(folder), str(zip_path)], check=True)
    else:
        shutil.make_archive(str(zip_path.with_suffix("")), "zip", folder.parent, NAME)
    print("Fertig:", zip_path, "%.0f MB" % (zip_path.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
