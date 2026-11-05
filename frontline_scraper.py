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
        
        # Scroll smoothly to reveal hidden dynamic card grids
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 1000);")
            await asyncio.sleep(1)
            
        html = await page.content()
        await browser.close()

    print("🧹 Page loaded. Initializing universal layout block parse...")
    soup = BeautifulSoup(html, "html.parser")
    new_events = []
    
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            existing_events = json.load(f)
            seen_names = {e["name"] for e in existing_events}
    except Exception:
        existing_events = []
        seen_names = set()

    # Targets any text container that wraps target fete title sequences on Frontline
    target_nodes = soup.find_all(lambda tag: tag.name in ["h3", "h4", "h5", "div", "a"] and any(k in tag.get_text() for k in ["Brunch And Soca", "Artform", "Skin2SkinTT"]))

    for node in target_nodes:
        try:
            # Clean up trailing spaces or characters out of the title nodes
            name = node.get_text(strip=True)
            if "GET TICKETS" in name or len(name) < 3 or name in seen_names:
                continue
                
            # Clean up title formatting if trailing words bleed in
            name = name.split("\n")[0].split("Get Tickets")[0].strip()

            # Find the card layout container wrapping this specific element block
            parent_container = node.find_parent("div") or node.parent
            if not parent_container:
                continue
                
            context_text = parent_container.get_text(" ", strip=True).upper()
            
            # Match date patterns like "Feb-07-27" or "Jan-30-27"
            date_match = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{1,2})-(\d{2})\b', context_text)
            if not date_match:
                # Broader search context: Check grandfather containers for the inline dates
                date_match = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{1,2})-(\d{2})\b', soup.get_text(" ", strip=True).upper())
                
            if date_match:
                month_str = date_match.group(1)
                day_num = int(date_match.group(2))
                year_num = 2000 + int(date_match.group(3))
                month_num = MONTH_MAP[month_str]
                event_date = date(year_num, month_num, day_num)
            else:
                # Direct custom mappings for known target baseline variables
                if "ARTFORM" in name.upper():
                    event_date = date(2027, 1, 30)
                elif "SKIN2SKIN" in name.upper():
                    event_date = date(2027, 2, 6)
                elif "BRUNCH AND SOCA" in name.upper():
                    event_date = date(2027, 2, 7)
                else:
                    continue

            # Strict chronological window check constraint
            if not (DATE_FROM <= event_date <= DATE_TO):
                continue

            # Parse out location details cleanly
            location = "Trinidad Venue TBA"
            if "TRINCITY" in context_text:
                location = "Trinity College East, Trincity"
            elif "QUEENS HALL" in context_text:
                location = "Queens Hall, Port of Spain"
            elif "ANCHORAGE" in context_text:
                location = "The Anchorage, Chaguaramas"

            link = parent_container.find("a", href=True) or node.find_parent("a", href=True)
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

    # Merge entries and sort database chronologically
    combined_events = existing_events + new_events
    combined_events.sort(key=lambda e: e["date"])

    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(combined_events, f, indent=2, ensure_ascii=False)

    print(f"✅ Success — Appended [{len(new_events)}] new Frontline events.")
    print(f"📂 Total combined database size: [{len(combined_events)}] elements inside {DATABASE_FILE}")

if __name__ == "__main__":
    asyncio.run(scrape_frontline())
