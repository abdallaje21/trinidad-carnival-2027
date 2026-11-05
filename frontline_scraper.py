import asyncio
import json
import re
from datetime import date
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ─── Strict date window ──────────────────────────────────────
DATE_FROM = date(2027, 1, 1)
DATE_TO   = date(2027, 2, 28)

TARGET_URL   = "https://www.frontlineticketing.com"
DATABASE_FILE = "src/data/events.json"

EVENT_TYPE_KEYWORDS = {
    "Boat Cruise":     ["CRUISE", "BOAT", "SAIL"],
    "Cooler Fete":     ["COOLER"],
    "Breakfast Fete":  ["BREAKFAST", "SUNRISE"],
    "All-Inclusive":   ["INCLUSIVE", "ALL INCLUSIVE", "PREMIUM"],
}

REGION_KEYWORDS = {
    "South": ["SOUTH", "FERNANDO", "SIPARIA", "DEBE", "POINT FORTIN"],
    "East":  ["VALSAYN", "ARIMA", "MACOYA", "TUNAPUNA", "CHAGUANAS", "TRINCITY", "MAUSICA"],
    "West":  ["WEST", "DIEGO MARTIN", "CARENAGE", "CHAGUARAMAS", "WESTMOORINGS"],
    "North": ["NORTH", "PORT OF SPAIN", "POS", "SAN JUAN", "ST. CLAIR", "WOODBROOK", "MARAVAL", "ST. ANNS", "MOKA"]
}

MONTH_CONVERTER = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
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
    """Scroll down the page sequentially to trigger lazy-loading image/data grids."""
    print("📜 Simulating human viewport scrolling to trigger lazy loaders...")
    for _ in range(5):
        await page.evaluate("window.scrollBy(0, 800);")
        await asyncio.sleep(1)


async def scrape_frontline():
    print(f"🚀 Launching browser → {TARGET_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        
        print("📡 Streaming data frame packets...")
        await page.goto(TARGET_URL, timeout=45000, wait_until="domcontentloaded")
        
        # Force lazy load content triggers via automated viewport updates
        await auto_scroll(page)
        
        html = await page.content()
        await browser.close()

    print("🧹 Page loaded. Parsing Frontline document elements...")
    soup = BeautifulSoup(html, "html.parser")
    new_events = []
    
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            existing_events = json.load(f)
            seen_names = {e["name"] for e in existing_events}
    except Exception:
        existing_events = []
        seen_names = set()

    # Broadened structural scanner loop to target Frontline's actual container text trees
    cards = soup.find_all(lambda tag: tag.name in ["div", "section"] and tag.find("a", href=True) and any(m in tag.get_text() for m in ["-27", "2027"]))
    
    for card in cards:
        try:
            # Locate title elements inside nested grids
            title_node = card.find(["h3", "h4", "h5"])
            if not title_node:
                continue
            name = title_node.get_text(strip=True)
            
            if not name or len(name) < 3 or name in seen_names or any(x in name.upper() for x in ["STICKER", "USD", "CAMPAIGN"]):
                continue

            card_text = card.get_text(" ", strip=True)
            text_upper = card_text.upper()
            
            # --- DATE EXTRACTION HANDLING ---
            # Parses dates directly from explicit structure signatures (e.g., "Jan-30-27" or "Feb-07-27")
            date_match = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{1,2})-(\d{2})\b', text_upper)
            
            if date_match:
                month_str = date_match.group(1)
                day_num = int(date_match.group(2))
                year_num = 2000 + int(date_match.group(3))
                month_num = MONTH_CONVERTER[month_str]
                event_date = date(year_num, month_num, day_num)
            else:
                continue

            # Strict date boundary window gatekeeper
            if not (DATE_FROM <= event_date <= DATE_TO):
                continue

            # ── Location Processing ──────────────────────────
            location = "Trinidad Venue TBA"
            lines = [l.strip() for l in card.get_text("\n", strip=True).split("\n") if l.strip()]
            for line in lines:
                if any(x in line.upper() for x in ["TRINIDAD", "QUEENS HALL", "THE ANCHORAGE", "MOKA", "TRINCITY"]):
                    location = line
                    break

            link = card.find("a", href=True)
            ticket_url = link["href"] if link else TARGET_URL
            if ticket_url.startswith("/"):
                ticket_url = f"https://www.frontlineticketing.com{ticket_url}"

            seen_names.add(name)
            new_events.append({
                "id":        f"frontline-{len(existing_events) + len(new_events)}",
                "name":      name,
                "type":      classify_event_type(name),
                "date":      event_date.isoformat(),
                "startTime": "22:00",
                "location":  location,
                "region":    classify_region(card_text),
                "ticketUrl": ticket_url,
                "tags":      ["frontlineticketing"],
            })
        except Exception:
            continue

    # Combine datasets and enforce chronological sorting
    combined_events = existing_events + new_events
    combined_events.sort(key=lambda e: e["date"])

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(combined_events, f, indent=2, ensure_ascii=False)

    print(f"✅ Success — Appended [{len(new_events)}] new Frontline events.")
    print(f"📂 Total combined database size: [{len(combined_events)}] elements inside {DATABASE_FILE}")

if __name__ == "__main__":
    asyncio.run(scrape_frontline())
