import asyncio
import json
import re
from datetime import date
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ─── Strict date window ──────────────────────────────────────
DATE_FROM = date(2027, 1, 1)
DATE_TO   = date(2027, 2, 28)

TARGET_URL   = "https://islandetickets.com"
OUTPUT_FILE  = "src/data/events.json"

EVENT_TYPE_KEYWORDS = {
    "Boat Cruise":     ["CRUISE", "BOAT"],
    "Cooler Fete":     ["COOLER"],
    "Breakfast Fete":  ["BREAKFAST", "SUNRISE"],
    "All-Inclusive":   ["INCLUSIVE", "ALL INCLUSIVE"],
}

# Fixed: Moved SAN JUAN from South to North category mapping arrays
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


async def scrape():
    print(f"🚀 Launching browser → {TARGET_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(TARGET_URL, timeout=60000, wait_until="networkidle")
        html = await page.content()
        await browser.close()

    print("🧹 Page loaded. Parsing document structures...")
    soup   = BeautifulSoup(html, "html.parser")
    events = []
    seen   = set()

    event_titles = soup.find_all("h5")

    for title_node in event_titles:
        try:
            name = title_node.get_text(strip=True)
            if not name or len(name) < 3 or "THESE EVENTS" in name.upper():
                continue
            if name in seen:
                continue

            parent_card = title_node.find_parent("div")
            if not parent_card:
                continue

            card_text = parent_card.get_text(" ", strip=True)
            raw_lines = parent_card.get_text("\n", strip=True).split("\n")

            # ─── ROBUST UPWARD MONTH & YEAR TRACKER ───
            current_year = 2026
            current_month = 11
            
            search_pointer = parent_card
            found_date_context = False
            
            while search_pointer and not found_date_context:
                search_pointer = search_pointer.find_previous()
                if not search_pointer:
                    break
                
                text_content = search_pointer.get_text(" ", strip=True).upper()
                if "JAN" in text_content and ("2027" in text_content or search_pointer.name in ["h5", "h4", "h3"]):
                    current_month = 1
                    current_year = 2027
                    found_date_context = True
                elif "FEB" in text_content and ("2027" in text_content or search_pointer.name in ["h5", "h4", "h3"]):
                    current_month = 2
                    current_year = 2027
                    found_date_context = True
                elif "NOV" in text_content:
                    current_month = 11
                    current_year = 2026
                    found_date_context = True
                elif "DEC" in text_content:
                    current_month = 12
                    current_year = 2026
                    found_date_context = True

            # Isolate numerical day digit indicators sitting near card nodes
            day = 1
            prev_sib = parent_card.find_previous()
            if prev_sib:
                sib_text = re.sub(r'\D', '', prev_sib.get_text(strip=True))
                if sib_text and sib_text.isdigit() and 1 <= int(sib_text) <= 31:
                    day = int(sib_text)

            # Precision Override: Hard-align New Year's Day Marquee entries to Jan 1st
            if any(k in name.upper() for k in ["DAY ONE", "1ST JAM", "TAILOR MADE", "SOCA1ST"]):
                current_month = 1
                current_year = 2027
                day = 1

            try:
                event_date = date(current_year, current_month, day)
            except ValueError:
                continue

            # Strict date boundary window enforcement check
            if not (DATE_FROM <= event_date <= DATE_TO):
                continue

            # ── Location & Time Processing ────────────────────
            location = "Trinidad Venue TBA"
            start_time = "22:00"
            for line in [l.strip() for l in raw_lines if l.strip()]:
                if line.startswith("@"):
                    location = line.lstrip("@").strip()
                elif re.search(r'\d{1,2}:\d{2}\s*(am|pm)', line, re.I):
                    start_time = line.strip()
                elif re.search(r'\d{1,2}\s*(am|pm)', line, re.I):
                    start_time = line.strip()

            # ── Ticket URL ────────────────────────────────────
            link = parent_card.find_parent("a") or parent_card.find("a")
            if link and link.has_attr("href"):
                ticket_url = link["href"]
                if ticket_url.startswith("/"):
                    ticket_url = f"https://islandetickets.com{ticket_url}"
            else:
                ticket_url = TARGET_URL

            seen.add(name)
            events.append({
                "id":        f"island-{len(events)}",
                "name":      name,
                "type":      classify_event_type(name),
                "date":      event_date.isoformat(),
                "startTime": start_time,
                "location":  location,
                "region":    classify_region(card_text),
                "ticketUrl": ticket_url,
                "tags":      ["islandetickets"],
            })

        except Exception:
            continue

    # Sort data entries chronologically
    events.sort(key=lambda e: e["date"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    print(f"✅ Success — {len(events)} real 2027 Carnival event(s) written to {OUTPUT_FILE}")
    if events:
        print(f"  Date scope tracking span: {events[0]['date']} → {events[-1]['date']}")


if __name__ == "__main__":
    asyncio.run(scrape())
