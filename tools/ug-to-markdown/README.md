# ug2md – Ultimate Guitar Favoriten als Markdown sichern

Lädt Chords- und Tab-Seiten von Ultimate Guitar und speichert jeden Song als
eigene Markdown-Datei. Dazu entsteht ein `index.md`, sortiert nach Artist.
Es wird nur die Python-Standardbibliothek gebraucht (Python ≥ 3.9).

> ⚠️ Nur für ein privates Backup. Die Tabs sind urheberrechtlich geschützt,
> also **nicht** in dieses öffentliche Repo committen. `ug-backup/` und
> `links.txt` stehen deshalb in `.gitignore`.

## Nutzung

1. Die Links in `links.txt` eintragen, einen pro Zeile. Leere Zeilen und
   Zeilen, die mit `#` beginnen, werden ignoriert.
   ```
   https://tabs.ultimate-guitar.com/tab/oasis/wonderwall-chords-27596
   https://tabs.ultimate-guitar.com/tab/metallica/nothing-else-matters-tabs-8519
   ```
2. Das Script starten:
   ```bash
   python3 ug2md.py links.txt -o ~/Music/ug-backup
   ```

| Option      | Default     | Bedeutung                                         |
|-------------|-------------|---------------------------------------------------|
| `-o/--out`  | `ug-backup` | Zielordner                                        |
| `--delay`   | `1.5`       | Pause zwischen den Requests in Sekunden           |
| `--force`   | aus         | Auch bereits gesicherte Tabs neu herunterladen    |

## Verhalten

- **Fortsetzbar:** Bereits gesicherte URLs werden in `.done.json` gemerkt und
  beim nächsten Lauf übersprungen. Ein Abbruch mit Ctrl+C schadet also nicht.
- **Fehler:** Fehlgeschlagene URLs landen in `failed.txt`. Diese Datei kann
  man direkt wieder als Eingabe verwenden.
- **Nicht unterstützt:** Guitar-Pro-, Official- und Pro-Tabs, weil sie keinen
  Textinhalt haben.
- **Ausgabeformat:** YAML-Front-Matter mit Artist, Key, Capo, Tuning, Rating
  und Quelle, danach der Tab als `text`-Codeblock. So bleiben die Akkorde
  über dem Text ausgerichtet.
