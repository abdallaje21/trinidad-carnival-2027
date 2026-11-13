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
]

OUTPUT_FILE = "src/data/events.json"

EVENT_TYPE_KEYWORDS = {
    "Boat Cruise":     ["CRUISE", "BOAT", "SAIL", "YACHT", "RAFT UP", "RAFTUP"],
    "Cooler Fete":     ["COOLER", "STINK"],
    "Breakfast Fete":  ["BREAKFAST", "SUNRISE", "BRUNCH"],
    "All-Inclusive":   ["INCLUSIVE", "ALL INCLUSIVE", "PRESTIGE"],
    "J'ouvert":        ["JOUVERT", "J'OUVERT", "JOUVERTT"],
}

REGION_KEYWORDS = {
    "South":   ["SOUTH", "FERNANDO", "SIPARIA", "DEBE", "POINT FORTIN", "CLIFTON HILL", "MAYARO", "PENAL"],
    "Central": ["COUVA", "CHAGUANAS", "POINTE A PIERRE", "CARONI"],
    "East":    ["VALSAYN", "ARIMA", "MACOYA", "TUNAPUNA", "TRINCITY", "ST. AUGUSTINE", "SAINT AUGUSTINE", "ST. JOSEPH", "ARANGUEZ", "EL DORADO", "TACARIGUA", "AROUCA"],
    "West":    ["WEST", "DIEGO MARTIN", "CARENAGE", "CHAGUARAMAS", "CHAGARAMAS", "CHAGURAMAS", "WESTMOORINGS", "COCORITE", "DDI"],
    "North":   ["NORTH", "PORT OF SPAIN", "PORT-OF-SPAIN", "POS", "SAN JUAN", "ST. CLAIR", "WOODBROOK", "MARAVAL", "ST. ANNS", "SANTA CRUZ", "PARAMIN", "ST. JAMES"]
}

TRINIDAD_SAFE_KEYWORDS = [
    "trinidad", "tobago", "port of spain", "port-of-spain", "chaguaramas",
    "chagaramas", "chaguramas", "queens hall", "queen's hall", "napa",
    "san fernando", "couva", "arima", "maraval", "st. clair", "woodbrook",
    "santa cruz", "mayaro", "harbour master", "habour master", "ocean pelican",
    "sound forge", "soundforge", "o2 park", "02 park", "diego martin",
    "westmoorings", "st. augustine", "valsayn", "trincity", "macoya"
]

NON_TRINIDAD_KEYWORDS = [
    "new orleans", "creole queen", "miami", "new york", "brooklyn",
    "toronto", "london", "atlanta", "lux cafe", "orlando", "barbara lee",
    "houston", "barbados", "grenada", "st. lucia", "gros islet", "jamaica",
    "guyana", "panama", "dubai", "cincinnati", "louisville", "pittsburgh",
    "chicago", "minneapolis", "usa", "canada", "uk"
]

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

def is_trinidad_event(event_title: str, event_location: str, raw_card_text: str = "") -> bool:
    combined = f"{event_title} {event_location} {raw_card_text}".lower()

    if any(safe in combined for safe in TRINIDAD_SAFE_KEYWORDS):
        return True

    for word in NON_TRINIDAD_KEYWORDS:
        if re.search(rf"\b{re.escape(word)}\b", combined):
            return False

    return True

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
    for _ in range(12):
        await page.evaluate("window.scrollBy(0, 1200);")
        await asyncio.sleep(0.8)

async def scrape():
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
    skipped_foreign = 0

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

                active_year = None
                active_month = None

                for tag in soup.find_all(["h3", "h4", "h5"]):
                    text = tag.get_text(" ", strip=True)
                    upper = text.upper()

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

                    if not is_trinidad_event(text, location, card_text):
                        skipped_foreign += 1
                        print(f"  [Skipped non-Trinidad] {text} (@ {location})")
                        continue

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
                        "region": classify_region(f"{text} {location}"),
                        "ticketUrl": ticket_url,
                        "tags": ["islandetickets"],
                    })
            except Exception as err:
                print(f"Error scanning {target}: {err}")

        await browser.close()

    all_events = preserved_events + fresh_events
    all_events.sort(key=lambda x: (x.get("date", "9999-12-31"), x.get("name", "")))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Saved {len(fresh_events)} Trinidad event(s) from Island eTickets (skipped {skipped_foreign} non-Trinidad).")
    print(f"Total events in {OUTPUT_FILE}: {len(all_events)}")

if __name__ == "__main__":
    asyncio.run(scrape())
