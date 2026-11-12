import asyncio
import json
import re
from datetime import date
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

DATE_FROM = date(2027, 1, 1)
DATE_TO   = date(2027, 2, 28)

SCAN_URLS = [
    "https://islandetickets.com",
    "https://islandetickets.com",
]

WATCHLIST_URLS = [
    "https://islandetickets.com",
    "https://islandetickets.com",
    "https://islandetickets.com",
]

OUTPUT_FILE = "src/data/events.json"

EVENT_TYPE_KEYWORDS = {
    "Boat Cruise":     ["CRUISE", "BOAT", "SAIL"],
    "Cooler Fete":     ["COOLER", "STINK"],
    "Breakfast Fete":  ["BREAKFAST", "SUNRISE"],
    "All-Inclusive":   ["INCLUSIVE", "ALL INCLUSIVE", "PRESTIGE"],
}

REGION_KEYWORDS = {
    "South": ["SOUTH", "FERNANDO", "SIPARIA", "DEBE", "POINT FORTIN"],
    "East":  ["VALSAYN", "ARIMA", "MACOYA", "TUNAPUNA", "CHAGUANAS", "TRINCITY"],
    "West":  ["WEST", "DIEGO MARTIN", "CARENAGE", "CHAGUARAMAS", "WESTMOORINGS"],
    "North": ["NORTH", "PORT OF SPAIN", "POS", "SAN JUAN", "ST. CLAIR", "WOODBROOK", "MARAVAL", "ST. ANNS"]
}

MONTH_HEADERS = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEP": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}

def classify_event_type(name: str) -> str:
    upper = name.upper()
    for label, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(k in upper for k in keywords):
            return label
    return "Fete"

def classify_region(text: str) -> str:
    upper = text.upper()
    for region, keywords in REGION_KEYWORDS.items():
        if any(k in upper for k in keywords):
            return region
    return "North"

async def auto_scroll(page):
    for _ in range(8):
        await page.evaluate("window.scrollBy(0, 1200);")
        await asyncio.sleep(0.8)

def parse_detail_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    title_node = soup.find(["h1", "h2", "h3", "h4"])
    name = title_node.get_text(strip=True) if title_node else ""
    if not name or len(name) < 3:
        return None

    date_match = re.search(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|Jan|Feb)\s*,?\s*(2027)\b',
        text,
        re.I
    )
    if not date_match:
        return None

    day = int(date_match.group(1))
    month_str = date_match.group(2)[:3].upper()
    month = 1 if month_str == "JAN" else 2

    try:
        event_date = date(2027, month, day)
    except ValueError:
        return None

    if not (DATE_FROM <= event_date <= DATE_TO):
        return None

    time_match = re.search(
        r'\d{1,2}:\d{2}\s*(?:AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM)',
        text,
        re.I
    )
    start_time = time_match.group(0) if time_match else "22:00"

    location = "Trinidad"
    for i, line in enumerate(lines):
        if time_match and time_match.group(0) in line and i + 1 < len(lines):
            candidate = lines[i + 1]
            if candidate.upper() not in ["SHARE", "HOME", "CALENDAR"]:
                location = candidate
            break

    return {
        "name": name,
        "type": classify_event_type(name),
        "date": event_date.isoformat(),
        "startTime": start_time,
        "location": location,
        "region": classify_region(f"{name} {location}"),
        "ticketUrl": url,
        "tags": ["islandetickets", "watchlist"],
    }

async def scrape():
    # Preserve manual entries and Frontline additions while clearing bad scraped dates
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_events = json.load(f)
    except Exception:
        existing_events = []

    preserved_events = [
        e for e in existing_events
        if "islandetickets" not in e.get("tags", [])
    ]

    seen = {e["name"].strip().upper() for e in preserved_events}
    fresh_events = []

    print(f"Preserved {len(preserved_events)} manual/external event(s).")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for target in SCAN_URLS:
            print(f"Scanning catalog → {target}")
            try:
                await page.goto(target, timeout=60000, wait_until="domcontentloaded")
                await auto_scroll(page)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Track active month/year sequentially from top to bottom
                active_year = None
                active_month = None

                for tag in soup.find_all(["h3", "h4", "h5"]):
                    text = tag.get_text(" ", strip=True)
                    upper = text.upper()

                    # Check if this tag is a sticky month header like "Nov2026" or "Jan 2027"
                    header_match = re.fullmatch(
                        r'(JAN|JANUARY|FEB|FEBRUARY|MAR|MARCH|APR|APRIL|MAY|JUN|JUNE|JUL|JULY|AUG|AUGUST|SEP|SEPTEMBER|OCT|OCTOBER|NOV|NOVEMBER|DEC|DECEMBER)\s*(202\d)',
                        upper
                    )
                    if header_match:
                        active_month = MONTH_HEADERS[header_match.group(1)]
                        active_year = int(header_match.group(2))
                        continue

                    if tag.name != "h5":
                        continue

                    if not text or len(text) < 3 or "THESE EVENTS" in upper or upper in seen:
                        continue

                    # Require a confirmed 2027 Jan/Feb header before accepting cards
                    if active_year != 2027 or active_month not in (1, 2):
                        continue

                    parent_card = tag.find_parent("div")
                    if not parent_card:
                        continue

                    card_text = parent_card.get_text(" ", strip=True)
                    raw_lines = parent_card.get_text("\n", strip=True).split("\n")

                    day = 1
                    prev_sib = parent_card.find_previous()
                    if prev_sib:
                        sib_text = re.sub(r'\D', '', prev_sib.get_text(strip=True))
                        if sib_text and sib_text.isdigit() and 1 <= int(sib_text) <= 31:
                            day = int(sib_text)

                    try:
                        event_date = date(active_year, active_month, day)
                    except ValueError:
                        continue

                    if not (DATE_FROM <= event_date <= DATE_TO):
                        continue

                    location = "Trinidad Venue TBA"
                    start_time = "22:00"
                    for line in [l.strip() for l in raw_lines if l.strip()]:
                        if line.startswith("@"):
                            location = line.lstrip("@").strip()
                        elif re.search(r'\d{1,2}:\d{2}\s*(am|pm)', line, re.I):
                            start_time = line.strip()
                        elif re.search(r'\d{1,2}\s*(am|pm)', line, re.I):
                            start_time = line.strip()

                    link = parent_card.find_parent("a") or parent_card.find("a")
                    ticket_url = link["href"] if link and link.has_attr("href") else target
                    if ticket_url.startswith("/"):
                        ticket_url = f"https://islandetickets.com{ticket_url}"

                    seen.add(upper)
                    fresh_events.append({
                        "id": f"island-{len(preserved_events) + len(fresh_events)}",
                        "name": text,
                        "type": classify_event_type(text),
                        "date": event_date.isoformat(),
                        "startTime": start_time,
                        "location": location,
                        "region": classify_region(card_text),
                        "ticketUrl": ticket_url,
                        "tags": ["islandetickets"],
                    })
            except Exception as e:
                print(f"Skipped {target}: {e}")

        for url in WATCHLIST_URLS:
            print(f"Checking watchlist → {url}")
            try:
                await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
                html = await page.content()
                parsed = parse_detail_page(html, url)
                if parsed and parsed["name"].upper() not in seen:
                    seen.add(parsed["name"].upper())
                    parsed["id"] = f"island-{len(preserved_events) + len(fresh_events)}"
                    fresh_events.append(parsed)
            except Exception as e:
                print(f"Watchlist error on {url}: {e}")

        await browser.close()

    combined = preserved_events + fresh_events
    combined.sort(key=lambda e: e["date"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"Done — Rebuilt with {len(fresh_events)} verified 2027 Island eTickets event(s).")
    print(f"Total clean events in {OUTPUT_FILE}: {len(combined)}")

if __name__ == "__main__":
    asyncio.run(scrape())
