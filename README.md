# PP-Inkognito

> Entwurf. Firmendaten stammen aus dem öffentlichen Impressum von performplus.de; vor der Veröffentlichung bestätigen.

**PP-Inkognito** ist ein kostenloses, lokales Werkzeug der **PerformPlus GmbH** (PP = PerformPlus, *we empower people.*) für Beratende und Teilnehmende. Es anonymisiert oder pseudonymisiert
personenbezogene Angaben in **Bewerbungsunterlagen** (Word, PDF, Text), damit sie mit einer KI bearbeitet werden können, und setzt
die echten Angaben danach wieder ein.

**Alles läuft nur auf Ihrem Rechner.** Es gibt keine Cloud-KI und keine Internetverbindung während der Arbeit. Ihre Dateien
verlassen den Rechner nicht.

## Warum ist das Programm so groß?

In PP-Inkognito steckt eine kleine **lokale KI** (ein Sprachmodell) zur Texterkennung. Sie erkennt Namen, Orte und Firmen in Ihren
Unterlagen und läuft ausschließlich auf Ihrem Rechner. Sie macht das Programm groß (der Download ist rund 110 MB groß), ist aber
der Grund, warum Ihre Unterlagen den Rechner nicht verlassen müssen.

## Wichtig vorab

- Die Erkennung ist **nicht zu 100 % zuverlässig**. Prüfen Sie jedes Ergebnis vollständig, bevor Sie es weitergeben.
- Bilder, Dateinamen und Metadaten können Hinweise auf Personen enthalten. Das Tool entfernt Metadaten und auf Wunsch Bilder.
- Die **Schlüsseldatei** enthält die echten Angaben im Klartext. Laden Sie sie **nie** in eine KI hoch, sondern nur die
  anonymisierten Dokumente. Pseudonymisierte Daten bleiben personenbezogen, solange die Schlüsseldatei existiert.
- Für die Einhaltung des Datenschutzes sind Sie selbst verantwortlich.

## Installation und erster Start (bitte zuerst lesen)

Laden Sie unter [Releases](../../releases/latest) die Datei für Ihr System herunter (direkte Links, immer die neueste Version: [Mac](../../releases/latest/download/PP-Inkognito-Mac.dmg), [Windows](../../releases/latest/download/PP-Inkognito-Windows-Setup.exe)). Das Programm ist kostenlos und **nicht signiert**
(Apple und Microsoft verlangen dafür ein kostenpflichtiges Entwicklerkonto). Deshalb warnen **Mac und Windows beim ersten Start**.
Das Programm ist nicht beschädigt. So geben Sie es einmalig frei:

### Mac: `PP-Inkognito-Mac.dmg`

1. Die `.dmg`-Datei öffnen und das Symbol **PP-Inkognito** auf den Ordner **Programme** ziehen. Danach das Fenster auswerfen.
2. In **Programme** auf **PP-Inkognito** doppelklicken. Es erscheint die Meldung *„PP-Inkognito nicht geöffnet – Apple konnte nicht überprüfen, ob PP-Inkognito frei von Schadsoftware ist“*. Klicken Sie auf **Fertig** (nicht auf „In den Papierkorb legen“).
3. Öffnen Sie die **Systemeinstellungen** (Apfel-Symbol oben links > Systemeinstellungen) und wählen Sie links **Datenschutz & Sicherheit**.
4. **Scrollen Sie ganz nach unten** zum Abschnitt **Sicherheit**. Dort steht: *„PP-Inkognito“ wurde blockiert, um deinen Mac zu schützen.* Klicken Sie auf **Dennoch öffnen**.
5. Bestätigen Sie mit Ihrem Passwort oder Touch ID und klicken Sie im nächsten Fenster auf **Öffnen**.

Das geht nur einmal. Der Hinweis in den Systemeinstellungen erscheint erst nach einem Öffnen-Versuch (Schritt 2) und bleibt etwa eine Stunde.
Ab dem zweiten Start öffnet sich das Programm wie jedes andere. Beim allerersten Start dauert es etwas länger, dann öffnet sich Ihr Browser.

### Windows: `PP-Inkognito-Windows-Setup.exe`

1. Die Setup-Datei doppelklicken. Erscheint *„Der Computer wurde durch Windows geschützt“*, klicken Sie auf **Weitere Informationen** und dann auf **Trotzdem ausführen**.
2. Dem Installationsassistenten folgen. PP-Inkognito finden Sie danach im Startmenü.

Der Quelltext ist öffentlich, und die Installer werden automatisch daraus gebaut.

**Für Entwickelnde:** Voraussetzung: Python 3.9 oder neuer.

```bash
cd Anonymisierungstool
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m spacy download de_core_news_md
```

Die Installer baut GitHub Actions (`.github/workflows/installer.yml`, Skript `packaging/build.py`) bei jedem Versions-Tag `v*`.

## Starten

```bash
.venv/bin/python app.py
```

oder per Doppelklick auf `Tool starten.command` (Mac) bzw. `Tool starten.bat` (Windows). Das Tool öffnet sich im Browser unter einer
**festen Adresse** (`http://127.0.0.1:8765/?t=…`). Speichern Sie sie als Lesezeichen. Das Zugriffstoken liegt in
`~/.anonymisierungstool/zugang.txt`.

## So arbeiten Sie damit

1. **Titel der Anonymisierung** eingeben (z. B. „Bewerbung Mustermann“). Alle Dokumente mit demselben Titel teilen sich eine
   Schlüsseldatei und bekommen dieselben Pseudonyme. Der Titel ist der Ordnername unter `Dokumente/Anonymisierungen/`.
2. **Dateien** ablegen (mehrere möglich). PDFs (mit lesbarem Text) lassen sich derzeit am einfachsten bearbeiten; Word-Dateien funktionieren genauso gut, die Formatierung ändert sich dabei aber leicht. Scan-Seiten erkennt das Tool nicht (sie lassen sich von Hand schwärzen).
3. **Prüfen:** Gefundene Angaben stehen farbig markiert im Dokument und rechts in der Liste, jeweils mit dem Pseudonym, das sich
   überschreiben lässt. Bei PDFs sehen Sie links die Originalseiten. Eine Markierung anklicken ändert sie, ein Wort anklicken oder
   über Wörter ziehen markiert Neues. Gescannte Stellen schwärzen Sie von Hand (Rechteck, Kreis, Stift); sie werden fest ins Bild
   eingebrannt.
4. **Anonymisierte Fassung erstellen.** Ergebnis und Schlüsseldatei liegen im Ordner des Titels. Schon beim Laden wird das Original im Unterordner `Originale` abgelegt und Ihr Bearbeitungsstand automatisch gesichert; über die Ablage können Sie jederzeit weiterarbeiten. Die Originale enthalten die echten Angaben und gehören nie in eine KI.
5. **Persönliche Daten wieder einsetzen:** Das von der KI überarbeitete Dokument im zweiten Reiter („2 · Persönliche Daten wieder einsetzen“) mit dem Titel wieder einlesen. Danach stehen im Dokument wieder die echten Namen und Angaben.

## Grenzen

- Namen werden über Muster, E-Mail-Adresse, Namenszeile und ein Sprachmodell erkannt; ausländische Namen sind schwächer.
- PDF: Die Schrift an ersetzten Stellen kann leicht vom Original abweichen. Begriffe, die über einen Zeilenumbruch laufen, werden
  nicht gefunden.
- Gescannte Dokumente werden nicht per Texterkennung gelesen; dafür gibt es das Schwärzwerkzeug.

## Lizenz

GNU Affero General Public License v3.0 (AGPL-3.0). PP-Inkognito nutzt PyMuPDF (AGPL), deshalb steht auch dieses Programm unter der AGPL.
Der Quelltext ist öffentlich. © 2026 PerformPlus GmbH.

## Kontakt

PerformPlus GmbH · Im Birket 6 · 82166 Gräfelfing/München ·
https://performplus.de · [Kontaktseite](https://performplus.de/kontakt/) · [Impressum](https://performplus.de/impressum/) · [Datenschutz](https://performplus.de/datenschutz-2/)
