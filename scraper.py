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

REGION_KEYWORDS = {
    "South": ["SOUTH", "FERNANDO", "SAN JUAN", "SIPARIA"],
    "East":  ["VALSAYN", "ARIMA", "MACOYA", "TUNAPUNA"],
    "West":  ["WEST", "DIEGO MARTIN", "CARENAGE"],
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

    print("🧹 Page loaded. Processing page elements sequentially...")
    soup   = BeautifulSoup(html, "html.parser")
    events = []
    seen   = set()

    # Track active date state context down the page flow timeline
    current_year = 2026
    current_month = 11

    # Locate the container where the text groups live
    container = soup.select_one("body")
    if not container:
        return

    # Loop directly over child elements to catch sticky group headings
    for node in container.find_all(recursive=True):
        # 1. Update calendar state when crossing month boundary headers (e.g. "##### Jan 2027")
        if node.name in ["h5", "h4", "h3"] and not node.find_parent("div", class_="col-md-4"):
            text = node.get_text(" ", strip=True).upper()
            if "JAN" in text:
                current_month = 1
                current_year = 2027
            elif "FEB" in text:
                current_month = 2
                current_year = 2027
            elif "NOV" in text:
                current_month = 11
                current_year = 2026
            elif "DEC" in text:
                current_month = 12
                current_year = 2026
            continue

        # 2. Extract Event data card nodes
        if node.name == "h5" and node.find_parent("div"):
            name = node.get_text(strip=True)
            if not name or len(name) < 3 or name in seen or "THESE EVENTS" in name.upper():
                continue

            parent_card = node.find_parent("div")
            card_text = parent_card.get_text(" ", strip=True)
            raw_lines = parent_card.get_text("\n", strip=True).split("\n")

            # Isolate numerical day digit indicators sitting near card nodes
            day = 1
            prev_sib = parent_card.find_previous()
            if prev_sib:
                sib_text = re.sub(r'\D', '', prev_sib.get_text(strip=True))
                if sib_text and 1 <= int(sib_text) <= 31:
                    day = int(sib_text)

            try:
                event_date = date(current_year, current_month, day)
            except ValueError:
                continue

            # Strict bounds evaluation check
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

    # Sort data entries chronologically
    events.sort(key=lambda e: e["date"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    print(f"✅ Success — {len(events)} real 2027 Carnival event(s) written to {OUTPUT_FILE}")
    if events:
        print(f"  Date scope tracking span: {events[0]['date']} → {events[-1]['date']}")


if __name__ == "__main__":
    asyncio.run(scrape())
