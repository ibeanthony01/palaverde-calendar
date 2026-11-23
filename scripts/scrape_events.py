#!/usr/bin/env python3
"""Collect upcoming events from configured public schedule pages and write JSON + ICS."""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
import unicodedata
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "scripts/sources.json").read_text(encoding="utf-8"))
VENUE = json.loads((ROOT / "venue.json").read_text(encoding="utf-8"))["venue"]
ROME = ZoneInfo("Europe/Rome")


def flatten(value):
    if isinstance(value, list):
        for item in value:
            yield from flatten(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if graph is not None:
            yield from flatten(graph)
        else:
            yield value


def is_event(obj):
    kind = obj.get("@type", [])
    if isinstance(kind, str):
        kind = [kind]
    return any(str(x).split("/")[-1].lower() == "event" for x in kind)


def normalized(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


def cell_text(cell):
    """Read visible table text, falling back to image alt labels for team logos."""
    text = cell.get_text(" ", strip=True)
    if not text:
        text = " ".join(img.get("alt", "") for img in cell.select("img") if img.get("alt"))
    return re.sub(r"\s+", " ", text).strip()


def table_rows(soup, required_headers):
    """Yield (normalized header-to-index map, cell texts) for schedule table rows."""
    required = {normalized(header) for header in required_headers}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_index = None
        headers = None
        for index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            names = [normalized(cell_text(cell)) for cell in cells]
            if cells and (required.issubset(set(names)) or (row.find("th") and required.intersection(names))):
                header_index = index
                headers = names
                break
        if header_index is None:
            continue
        header_map = {name: index for index, name in enumerate(headers) if name}
        for row in rows[header_index + 1:]:
            cells = row.find_all(["th", "td"], recursive=False)
            texts = [cell_text(cell) for cell in cells]
            if texts:
                yield header_map, texts


def column(row, headers, name, fallback=None):
    """Get a table cell by a flexible, accent-insensitive header name."""
    index = next((i for header, i in headers.items() if name in header), fallback)
    return row[index] if index is not None and index < len(row) else ""


def event_date(text):
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def kickoff_time(text, default="18:00"):
    match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text)
    if not match:
        return default
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def local_start(day, hour_minute):
    hour, minute = map(int, hour_minute.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=ROME).isoformat()


def upcoming(day, today):
    return day is not None and day >= today


def extract_trevisobasket(page, source):
    """Read home match cards from Treviso Basket's static 2026/27 schedule."""
    soup = BeautifulSoup(page, "html.parser")
    today = datetime.now(ROME).date()
    records = []
    home_prefix = "Nutribullet Treviso Basket vs "

    # Matchups are rendered as headings, with date/round and time in their nearby
    # match card. Use the smallest ancestor containing both the matchup and date.
    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        matchup = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
        if not matchup.startswith(home_prefix):
            continue

        context = heading
        context_text = matchup
        for parent in heading.parents:
            if parent.name in {"body", "html"}:
                break
            candidate = parent.get_text(" ", strip=True)
            if len(candidate) > 1200:
                break
            if event_date(candidate):
                context, context_text = parent, candidate
                break

        day = event_date(context_text)
        if not upcoming(day, today):
            continue
        round_match = re.search(r"\(\s*(\d{1,2}\s*°\s*Giornata)\s*\)", context_text, flags=re.IGNORECASE)
        round_label = round_match.group(1).strip() if round_match else ""
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", context_text)
        if time_match:
            kickoff = kickoff_time(time_match.group(0), "18:00")
        else:
            kickoff = "20:00" if day.weekday() == 0 else "18:00"

        away_team = matchup[len(home_prefix):].strip()
        if not away_team:
            continue
        records.append({
            "title": f"Nutribullet Treviso Basket vs {away_team}",
            "startDate": local_start(day, kickoff),
            "description": round_label,
            "category": "basket",
            "venue": VENUE["name"],
            "location": f"{VENUE['city']}, {VENUE['province']}",
            "ticketUrl": "https://www.vivaticket.com/it/search?q=Treviso%20Basket",
            "sourceUrl": source["url"],
        })
    return records


def extract_imoco(page, source):
    soup = BeautifulSoup(page, "html.parser")
    today = datetime.now(ROME).date()
    records = []
    home_prefix = "prosecco doc a.carraro imoco volley vs"
    for headers, row in table_rows(soup, ["data", "partita", "risultati", "competizione"]):
        date_text = column(row, headers, "data", fallback=0)
        match = column(row, headers, "partita", fallback=1)
        result = column(row, headers, "risultati", fallback=2)
        competition = column(row, headers, "competizione", fallback=3)
        day = event_date(date_text + " " + " ".join(row))
        match_normalized = normalized(match)
        if not match_normalized.startswith(home_prefix) or not upcoming(day, today):
            continue
        # The club's neutral-site notation appears after the opponent (for example, "(Bari, ore 18.00)").
        if re.search(r"\(\s*(?!ore\b)[^)]*[A-Za-zÀ-ÿ]", match, flags=re.IGNORECASE):
            continue
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", result)
        if time_match:
            kickoff = kickoff_time(time_match.group(0))
        else:
            ore_match = re.search(r"\(\s*ore\s*(\d{1,2})[.:](\d{2})\s*\)", match, flags=re.IGNORECASE)
            kickoff = f"{int(ore_match.group(1)):02d}:{ore_match.group(2)}" if ore_match else kickoff_time(match)
        away = re.sub(r"^.*?\bvs\b", "", match, count=1, flags=re.IGNORECASE)
        away = re.sub(r"\(\s*ore\s*\d{1,2}[.:]\d{2}\s*\)", "", away, flags=re.IGNORECASE).strip(" -–|·")
        if not away:
            continue
        records.append({
            "title": f"Prosecco DOC A.Carraro Imoco Volley vs {away}",
            "startDate": local_start(day, kickoff),
            "description": competition,
            "category": "volley",
            "venue": VENUE["name"],
            "location": f"{VENUE['city']}, {VENUE['province']}",
            "ticketUrl": "https://www.vivaticket.com/it/search?q=Imoco%20Volley",
            "sourceUrl": source["url"],
        })
    return records


def extract_jsonld(page, source):
    soup = BeautifulSoup(page, "html.parser")
    records = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (ValueError, TypeError):
            continue
        for obj in flatten(data):
            if not is_event(obj):
                continue
            loc = obj.get("location") or {}
            loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
            address = loc.get("address", {}) if isinstance(loc, dict) else {}
            addr_text = " ".join(str(address.get(k, "")) for k in ("streetAddress", "addressLocality")) if isinstance(address, dict) else str(address)
            text = f"{loc_name} {addr_text} {obj.get('name', '')}".lower()
            terms = CONFIG.get("venue_match_terms", [])
            if terms and not any(term.lower() in text for term in terms):
                continue
            start = obj.get("startDate")
            if not obj.get("name") or not start:
                continue
            offers = obj.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            records.append({
                "title": obj["name"], "startDate": start,
                "endDate": obj.get("endDate"),
                "description": obj.get("description", ""),
                "category": source.get("category", "concert"),
                "venue": loc_name or VENUE["name"],
                "location": addr_text,
                "ticketUrl": offers.get("url") or obj.get("url") or source["url"],
                "sourceUrl": obj.get("url") or source["url"],
            })
    return records


def extract(page, source):
    parser = source.get("parser", "jsonld")
    parsers = {
        "trevisobasket": extract_trevisobasket,
        "imoco": extract_imoco,
        "jsonld": extract_jsonld,
    }
    if parser not in parsers:
        raise ValueError(f"Unsupported parser '{parser}' for {source.get('name', source['url'])}")
    return parsers[parser](page, source)


def fetch_source(source):
    url = source["url"]
    if not urlparse(url).scheme.startswith("http"):
        raise ValueError(f"Not an HTTP(S) URL: {url}")
    req = Request(url, headers={"User-Agent": "PalaverdeEventCalendar/1.0 (public event calendar; contact site owner)"})
    with urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def ics_escape(value):
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_date(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_ics(events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Palaverde Eventi//IT", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for event in events:
        uid = re.sub(r"[^a-zA-Z0-9]+", "-", event["title"]).strip("-").lower() + "-" + event["startDate"][:10] + "@palaverde-calendar"
        lines += ["BEGIN:VEVENT", f"UID:{ics_escape(uid)}", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}", f"DTSTART:{ics_date(event['startDate'])}"]
        if event.get("endDate"):
            lines.append(f"DTEND:{ics_date(event['endDate'])}")
        lines += [f"SUMMARY:{ics_escape(event['title'])}", f"LOCATION:{ics_escape(VENUE['name'] + ', ' + VENUE['address'] + ', ' + VENUE['city'])}", f"DESCRIPTION:{ics_escape(event.get('description', ''))}", f"URL:{ics_escape(event.get('ticketUrl', ''))}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    results, failures = [], []
    for source in CONFIG["sources"]:
        try:
            found = extract(fetch_source(source), source)
            print(f"{source['name']}: {len(found)} event(s)")
            results.extend(found)
        except Exception as exc:
            failures.append(f"{source['name']}: {exc}")
            print(f"Warning: {failures[-1]}", file=sys.stderr)
    unique = {}
    for event in results:
        key = (event["title"].strip().lower(), event["startDate"])
        unique[key] = event
    events = sorted(unique.values(), key=lambda x: x["startDate"])
    payload = {"updatedAt": datetime.now(timezone.utc).isoformat(), "events": events, "sourceFailures": failures}
    (ROOT / "events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "events.ics").write_text(write_ics(events), encoding="utf-8", newline="")
    print(f"Wrote {len(events)} unique events to events.json and events.ics")
    if failures and not events:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
