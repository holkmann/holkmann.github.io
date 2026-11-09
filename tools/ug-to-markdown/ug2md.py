#!/usr/bin/env python3
"""Ultimate Guitar tabs -> Markdown backup.

Reads a text file with one Ultimate Guitar tab URL per line and writes one
Markdown file per tab plus an index.md. Uses only the Python standard library.

Usage:
    python3 ug2md.py links.txt -o backup/
    python3 ug2md.py links.txt -o backup/ --delay 2 --force

Lines that are empty or start with '#' are ignored.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
STORE_RE = re.compile(r'class="js-store"\s+data-content="([^"]*)"')
URL_RE = re.compile(r"https?://(?:tabs\.|www\.)?ultimate-guitar\.com/\S+", re.I)


@dataclass
class Tab:
    url: str
    artist: str
    song: str
    type_name: str
    version: int
    tab_id: int
    rating: float | None
    votes: int | None
    difficulty: str
    key: str
    capo: int | None
    tuning: str
    content: str


# --------------------------------------------------------------------------- #
# Fetching / parsing
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 3, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (404, 410):
                break  # no point retrying
            wait = 2 ** attempt * (5 if e.code == 429 else 1)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            wait = 2 ** attempt
        if attempt < retries:
            time.sleep(wait)
    raise RuntimeError(f"Download fehlgeschlagen: {last_err}")


def parse(url: str, page: str) -> Tab:
    m = STORE_RE.search(page)
    if not m:
        raise ValueError("Kein js-store gefunden (Layout geändert oder Bot-Sperre?)")
    data = json.loads(html.unescape(m.group(1)))["store"]["page"]["data"]

    tab = data.get("tab") or {}
    view = data.get("tab_view") or {}
    meta = view.get("meta") or {}
    content = (view.get("wiki_tab") or {}).get("content")
    if not content:
        kind = tab.get("type_name") or tab.get("type") or "?"
        raise ValueError(f"Kein Textinhalt (Typ '{kind}' – Pro/Official-Tabs gehen nicht)")

    tuning = meta.get("tuning") or {}
    tuning_str = " / ".join(x for x in (tuning.get("name"), tuning.get("value")) if x)

    return Tab(
        url=tab.get("tab_url") or url,
        artist=tab.get("artist_name") or "Unknown Artist",
        song=tab.get("song_name") or "Unknown Song",
        type_name=tab.get("type_name") or tab.get("type") or "",
        version=int(tab.get("version") or 1),
        tab_id=int(tab.get("id") or 0),
        rating=round(float(tab["rating"]), 2) if tab.get("rating") else None,
        votes=tab.get("votes"),
        difficulty=meta.get("difficulty") or tab.get("difficulty") or "",
        key=meta.get("tonality") or tab.get("tonality_name") or "",
        capo=meta.get("capo") or None,
        tuning=tuning_str,
        content=content,
    )


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def clean_content(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\[/?ch\]", "", text)
    text = re.sub(r"\[/?tab\]", "", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return text.replace("```", "'''")  # don't break the code fence


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[\s_-]+", "-", value) or "untitled"


def filename_for(tab: Tab) -> str:
    parts = [tab.artist, tab.song, tab.type_name, f"v{tab.version}"]
    return slugify(" ".join(p for p in parts if p)) + ".md"


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # JSON strings are valid YAML


def to_markdown(tab: Tab) -> str:
    front = {
        "title": tab.song,
        "artist": tab.artist,
        "type": tab.type_name,
        "version": tab.version,
        "key": tab.key,
        "capo": tab.capo,
        "tuning": tab.tuning,
        "difficulty": tab.difficulty,
        "rating": tab.rating,
        "votes": tab.votes,
        "source": tab.url,
        "ug_id": tab.tab_id,
    }
    lines = ["---"]
    for k, v in front.items():
        if v in (None, ""):
            continue
        lines.append(f"{k}: {yaml_str(v) if isinstance(v, str) else v}")
    lines.append("---")

    info = [f"**{label}:** {val}" for label, val in (
        ("Key", tab.key),
        ("Capo", tab.capo),
        ("Tuning", tab.tuning),
        ("Typ", f"{tab.type_name} (v{tab.version})"),
    ) if val]

    body = [
        "",
        f"# {tab.artist} – {tab.song}",
        "",
        "  \n".join(info),
        "",
        f"Quelle: <{tab.url}>",
        "",
        "```text",
        clean_content(tab.content),
        "```",
        "",
    ]
    return "\n".join(lines + body)


def read_front_matter(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return meta
    for line in text[4:].split("\n"):
        if line == "---":
            break
        k, _, v = line.partition(": ")
        try:
            meta[k] = json.loads(v)
        except json.JSONDecodeError:
            meta[k] = v
    return meta


def write_index(out_dir: Path) -> int:
    entries = []
    for p in sorted(out_dir.glob("*.md")):
        if p.name == "index.md":
            continue
        m = read_front_matter(p)
        entries.append((str(m.get("artist", "?")), str(m.get("title", p.stem)),
                        str(m.get("type", "")), p.name))
    entries.sort(key=lambda e: (e[0].casefold(), e[1].casefold()))

    lines = ["# Ultimate Guitar Backup", "", f"{len(entries)} Tabs", ""]
    current = None
    for artist, title, kind, fname in entries:
        if artist != current:
            lines += ["", f"## {artist}", ""]
            current = artist
        suffix = f" ({kind})" if kind else ""
        lines.append(f"- [{title}]({fname}){suffix}")
    (out_dir / "index.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return len(entries)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def read_links(path: Path) -> list[str]:
    links, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = URL_RE.search(line)
        if not m:
            print(f"  ! Übersprungen (keine UG-URL): {line}", file=sys.stderr)
            continue
        url = m.group(0).split("?")[0].split("#")[0]
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def main() -> int:
    ap = argparse.ArgumentParser(description="Ultimate Guitar Tabs als Markdown sichern.")
    ap.add_argument("links", type=Path, help="Textdatei, eine URL pro Zeile")
    ap.add_argument("-o", "--out", type=Path, default=Path("ug-backup"), help="Zielordner")
    ap.add_argument("--delay", type=float, default=1.5, help="Pause zwischen Requests (s)")
    ap.add_argument("--force", action="store_true", help="Vorhandene Dateien neu laden")
    args = ap.parse_args()

    links = read_links(args.links)
    args.out.mkdir(parents=True, exist_ok=True)
    done_file = args.out / ".done.json"
    done: dict[str, str] = {}
    if done_file.exists() and not args.force:
        done = json.loads(done_file.read_text(encoding="utf-8"))

    ok = skipped = 0
    failed: list[tuple[str, str]] = []
    print(f"{len(links)} Links → {args.out}/")

    for i, url in enumerate(links, 1):
        prefix = f"[{i}/{len(links)}]"
        if url in done and (args.out / done[url]).exists():
            skipped += 1
            print(f"{prefix} = {done[url]} (schon vorhanden)")
            continue
        try:
            tab = parse(url, fetch(url))
            fname = filename_for(tab)
            (args.out / fname).write_text(to_markdown(tab), encoding="utf-8")
            done[url] = fname
            done_file.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
            ok += 1
            print(f"{prefix} ✓ {fname}")
        except Exception as e:  # noqa: BLE001 – keep going, report at the end
            failed.append((url, str(e)))
            print(f"{prefix} ✗ {url}: {e}", file=sys.stderr)
        if i < len(links):
            time.sleep(args.delay)

    count = write_index(args.out)
    if failed:
        (args.out / "failed.txt").write_text(
            "\n".join(f"{u}\t# {err}" for u, err in failed) + "\n", encoding="utf-8")
    else:
        (args.out / "failed.txt").unlink(missing_ok=True)

    print(f"\nFertig: {ok} neu, {skipped} übersprungen, {len(failed)} Fehler. "
          f"index.md enthält {count} Tabs.")
    if failed:
        print(f"Fehlgeschlagene URLs: {args.out / 'failed.txt'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
