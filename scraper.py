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

# Fixed: Only scan for the months that actually matter for your window
CARNIVAL_MONTHS = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
}

EVENT_TYPE_KEYWORDS = {
    "Boat Cruise":     ["CRUISE", "BOAT"],
    "Cooler Fete":     ["COOLER"],
    "Breakfast Fete":  ["BREAKFAST"],
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


def parse_date_from_context(search_text: str) -> date | None:
    upper = search_text.upper()

    for month_str, month_num in CARNIVAL_MONTHS.items():
        pattern = rf'\b{month_str}\w*\s+(\d{{1,2}})\b|\b(\d{{1,2}})\w*\s+{month_str}\w*\b'
        match = re.search(pattern, upper)
        if not match:
            continue

        day_str = match.group(1) or match.group(2)
        if not day_str:
            continue

        day = int(day_str)
        if not (1 <= day <= 31):
            continue

        # Target year is strictly 2027 for this window
        year = 2027

        try:
            candidate = date(year, month_num, day)
        except ValueError:
            continue

        if DATE_FROM <= candidate <= DATE_TO:
            return candidate

    return None


async def scrape():
    print(f"Launching browser → {TARGET_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(TARGET_URL, timeout=60000, wait_until="networkidle")
        html = await page.content()
        await browser.close()

    print("Page loaded. Parsing...")
    soup   = BeautifulSoup(html, "html.parser")
    events = []
    seen   = set()

    for title_node in soup.find_all("h5"):
        try:
            name = title_node.get_text(strip=True)
            if not name or len(name) < 3:
                continue
            if name in seen:
                continue

            parent_card = title_node.find_parent("div")
            if not parent_card:
                continue

            # Target lines to look for explicit location labels or details
            card_text = parent_card.get_text(" ", strip=True)
            raw_lines = parent_card.get_text("\n", strip=True).split("\n")

            prev_sib      = parent_card.find_previous()
            sibling_text  = prev_sib.get_text(" ", strip=True) if prev_sib else ""
            full_context  = f"{sibling_text} {card_text}"

            # ── Date detection (strict) ───────────────────────
            event_date = parse_date_from_context(full_context)
            if event_date is None:
                ancestor = (
                    title_node.find_parent(class_=re.compile(r'card|holder|event|item|col', re.I))
                    or parent_card
                )
                ancestor_text = ancestor.get_text(" ", strip=True) if ancestor else ""
                event_date = parse_date_from_context(ancestor_text)

            if event_date is None:
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

    # Sort chronologically
    events.sort(key=lambda e: e["date"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    print(f"✅ Done — {len(events)} event(s) written to {OUTPUT_FILE}")
    if events:
        print(f"  Date range: {events[0]['date']} → {events[-1]['date']}")


if __name__ == "__main__":
    asyncio.run(scrape())
