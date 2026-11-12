import asyncio
import json
import re
from datetime import date, datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

DATE_FROM = date(2027, 1, 1)
DATE_TO   = date(2027, 2, 28)

SCAN_URLS = [
    "https://islandetickets.com",
    "https://islandetickets.com",
]

# Add direct URLs for premier events that might not be on the main feed yet
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

    # Title is usually the first major heading on individual event pages
    title_node = soup.find(["h1", "h2", "h3", "h4"])
    name = title_node.get_text(strip=True) if title_node else ""
    if not name or len(name) < 3:
        return None

    # Match full detail page dates like "Sat 30th January , 2027"
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

    # Extract time range like "3:00 AM - 10:00 AM"
    time_match = re.search(
        r'\d{1,2}:\d{2}\s*(?:AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM)',
        text,
        re.I
    )
    start_time = time_match.group(0) if time_match else "22:00"

    # Find location line right after time or date
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
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_events = json.load(f)
    except Exception:
        existing_events = []

    seen = {e["name"].strip().upper() for e in existing_events}
    new_events = []

    print(f"Loaded {len(existing_events)} existing event(s).")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Crawl main catalog pages with auto-scroll
        for target in SCAN_URLS:
            print(f"Scanning catalog → {target}")
            try:
                await page.goto(target, timeout=60000, wait_until="domcontentloaded")
                await auto_scroll(page)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                for title_node in soup.find_all("h5"):
                    name = title_node.get_text(strip=True)
                    if not name or len(name) < 3 or "THESE EVENTS" in name.upper() or name.upper() in seen:
                        continue

                    parent_card = title_node.find_parent("div")
                    if not parent_card:
                        continue

                    card_text = parent_card.get_text(" ", strip=True)
                    raw_lines = parent_card.get_text("\n", strip=True).split("\n")

                    current_year, current_month = 2026, 11
                    search_pointer = parent_card
                    found_date_context = False

                    while search_pointer and not found_date_context:
                        search_pointer = search_pointer.find_previous()
                        if not search_pointer:
                            break
                        text_content = search_pointer.get_text(" ", strip=True).upper()
                        if "JAN" in text_content and ("2027" in text_content or search_pointer.name in ["h5", "h4", "h3"]):
                            current_month, current_year, found_date_context = 1, 2027, True
                        elif "FEB" in text_content and ("2027" in text_content or search_pointer.name in ["h5", "h4", "h3"]):
                            current_month, current_year, found_date_context = 2, 2027, True

                    day = 1
                    prev_sib = parent_card.find_previous()
                    if prev_sib:
                        sib_text = re.sub(r'\D', '', prev_sib.get_text(strip=True))
                        if sib_text and sib_text.isdigit() and 1 <= int(sib_text) <= 31:
                            day = int(sib_text)

                    if any(k in name.upper() for k in ["DAY ONE", "1ST JAM", "TAILOR MADE", "SOCA1ST"]):
                        current_month, current_year, day = 1, 2027, 1

                    try:
                        event_date = date(current_year, current_month, day)
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

                    seen.add(name.upper())
                    new_events.append({
                        "id": f"island-{len(existing_events) + len(new_events)}",
                        "name": name,
                        "type": classify_event_type(name),
                        "date": event_date.isoformat(),
                        "startTime": start_time,
                        "location": location,
                        "region": classify_region(card_text),
                        "ticketUrl": ticket_url,
                        "tags": ["islandetickets"],
                    })
            except Exception as e:
                print(f"Skipped {target}: {e}")

        # 2. Check premier event watchlist URLs directly
        for url in WATCHLIST_URLS:
            print(f"Checking watchlist → {url}")
            try:
                await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
                html = await page.content()
                parsed = parse_detail_page(html, url)
                if parsed and parsed["name"].upper() not in seen:
                    seen.add(parsed["name"].upper())
                    parsed["id"] = f"island-{len(existing_events) + len(new_events)}"
                    new_events.append(parsed)
            except Exception as e:
                print(f"Watchlist error on {url}: {e}")

        await browser.close()

    combined = existing_events + new_events
    combined.sort(key=lambda e: e["date"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"Done — Added {len(new_events)} new event(s). Total database size: {len(combined)}")
    for e in new_events:
        print(f"  + {e['date']} | {e['name']} ({e['location']})")

if __name__ == "__main__":
    asyncio.run(scrape())
