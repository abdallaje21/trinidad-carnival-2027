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

MONTH_MAP = {
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

async def scrape_frontline():
    print(f"🚀 Launching browser → {TARGET_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        
        print("📡 Streaming data frame packets...")
        await page.goto(TARGET_URL, timeout=45000, wait_until="domcontentloaded")
        
        # Human emulation scroll down to trigger lazy loading scripts
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 800);")
            await asyncio.sleep(1)
            
        html = await page.content()
        await browser.close()

    print("🧹 Page loaded. Parsing document headings structure...")
    soup = BeautifulSoup(html, "html.parser")
    new_events = []
    
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            existing_events = json.load(f)
            seen_names = {e["name"] for e in existing_events}
    except Exception:
        existing_events = []
        seen_names = set()

    # Target all h3 elements directly to grab the event titles from the page flow layout
    for title_node in soup.find_all("h3"):
        try:
            name = title_node.get_text(strip=True)
            if not name or len(name) < 3 or name in seen_names or "HOW FRONTLINE" in name.upper():
                continue
                
            # Scan parent wrappers or adjacent nodes to extract date strings (e.g. "Feb-07-27")
            parent_container = title_node.find_parent("div") or title_node.parent
            if not parent_container:
                continue
                
            context_text = parent_container.get_text(" ", strip=True).upper()
            
            # Match date format patterns like "Feb-07-27" or "Jan-30-27"
            date_match = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{1,2})-(\d{2})\b', context_text)
            if not date_match:
                # Check next elements in the container for floating date badges
                sibling_text = parent_container.get_text(" ", strip=True).upper()
                date_match = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{1,2})-(\d{2})\b', sibling_text)
                
            if date_match:
                month_str = date_match.group(1)
                day_num = int(date_match.group(2))
                year_num = 2000 + int(date_match.group(3))
                month_num = MONTH_MAP[month_str]
                event_date = date(year_num, month_num, day_num)
            else:
                continue

            # Strict chronological window check constraint
            if not (DATE_FROM <= event_date <= DATE_TO):
                continue

            # Parse out location details cleanly
            location = "Trinidad Venue TBA"
            raw_lines = parent_container.get_text("\n", strip=True).split("\n")
            for line in [l.strip() for l in raw_lines if l.strip()]:
                if any(x in line.upper() for x in ["TRINIDAD", "QUEENS HALL", "THE ANCHORAGE", "TRINCITY"]):
                    location = line
                    break

            link = parent_container.find("a", href=True) or title_node.find("a", href=True)
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
                "region":    classify_region(context_text),
                "ticketUrl": ticket_url,
                "tags":      ["frontlineticketing"],
            })
        except Exception:
            continue

    # Merge events and sort the entire dataset chronologically
    combined_events = existing_events + new_events
    combined_events.sort(key=lambda e: e["date"])

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(combined_events, f, indent=2, ensure_ascii=False)

    print(f"✅ Success — Appended [{len(new_events)}] new Frontline events.")
    print(f"📂 Total combined database size: [{len(combined_events)}] elements inside {DATABASE_FILE}")

if __name__ == "__main__":
    asyncio.run(scrape_frontline())
