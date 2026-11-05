import asyncio
import json
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def scrape_caribbean_events():
    print("🚀 Initializing live web browser pipeline...")
    target_url = "https://islandetickets.com" 

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"📡 Navigating tracking matrix onto: {target_url}")
        await page.goto(target_url, timeout=60000, wait_until="networkidle")
        html_content = await page.content()
        await browser.close()
        
    print("🧹 Download complete. Processing page flow sequentially...")
    soup = BeautifulSoup(html_content, "html.parser")
    staged_events = []
    
    # Locate all event title nodes across the layout stream
    event_titles = soup.find_all("h5")
    
    months_map = {
        "JAN": "01", "JANUARY": "01",
        "FEB": "02", "FEBRUARY": "02",
        "NOV": "11", "NOVEMBER": "11",
        "DEC": "12", "DECEMBER": "12"
    }

    for index, title_node in enumerate(event_titles):
        try:
            name = title_node.get_text(strip=True)
            # Skip promotional banners or section titles
            if not name or "THESE EVENTS" in name.upper() or name.upper() in months_map.keys():
                continue
                
            parent_card = title_node.find_parent("div")
            if not parent_card:
                continue
                
            card_text = parent_card.get_text("\n", strip=True)
            lines = [line.strip() for line in card_text.split("\n") if line.strip()]
            
            location = "Trinidad Venue TBA"
            start_time = "22:00"
            for line in lines:
                if line.startswith("@"):
                    location = line.replace("@", "").strip()
                elif any(x in line.lower() for x in ["am", "pm"]):
                    start_time = line.strip()

            # --- ROBUST UPWARD MONTH-TRACKING SCANNER ---
            # Search parent elements to isolate sticky header markers
            current_year = "2026"
            current_month_num = "11"
            
            # Look at immediate container ancestors first
            ancestor = title_node.find_parent(class_=re.compile(r'(card|holder|event|item|col)', re.I)) or parent_card
            context_text = ancestor.get_text(" ", strip=True).upper() if ancestor else ""
            
            # Backup text search through previous siblings to find floating section tags
            prev_sib = parent_card.find_previous()
            sibling_text = prev_sib.get_text(" ", strip=True).upper() if prev_sib else ""
            
            full_search_text = context_text + " " + sibling_text
            
            # Update date tracker context matching
            if "JAN" in full_search_text or "JANUARY" in full_search_text:
                current_month_num = "01"
                current_year = "2027"
            elif "FEB" in full_search_text or "FEBRUARY" in full_search_text:
                current_month_num = "02"
                current_year = "2027"
            elif "DEC" in full_search_text or "DECEMBER" in full_search_text:
                current_month_num = "12"
                current_year = "2026"
            else:
                current_month_num = "11"
                current_year = "2026"

            # Parse numeric day digit tokens sitting adjacent to card elements
            day_num = "01"
            prev_elements = parent_card.find_previous_siblings()
            for elem in prev_elements:
                elem_text = elem.get_text(strip=True)
                # Strip out trailing th, nd, st tags from strings (e.g. '5th' -> '5')
                clean_digits = re.sub(r'\D', '', elem_text)
                if clean_digits and 1 <= int(clean_digits) <= 31:
                    day_num = clean_digits.zfill(2)
                    break

            date_iso = f"{current_year}-{current_month_num}-{day_num}"

            # --- CRITICAL STRICT CARNIVAL WINDOW FILTER ---
            # Drop any event that does not fall into January 2027 or February 2027
            if not (date_iso.startswith("2027-01") or date_iso.startswith("2027-02")):
                continue

            link_node = parent_card.find_parent("a") or parent_card.find("a")
            ticket_url = link_node['href'] if link_node and link_node.has_attr('href') else target_url
            if ticket_url.startswith("/"):
                ticket_url = f"https://islandetickets.com{ticket_url}"

            event_type = "Fete"
            if "CRUISE" in name.upper() or "BOAT" in name.upper():
                event_type = "Boat Cruise"
            elif "COOLER" in name.upper():
                event_type = "Cooler Fete"
            elif "BREAKFAST" in name.upper():
                event_type = "Breakfast Fete"
            elif "INCLUSIVE" in name.upper():
                event_type = "All-Inclusive"

            region = "North"
            if "SOUTH" in card_text.upper() or "FERNANDO" in card_text.upper():
                region = "South"
            elif any(e in card_text.upper() for e in ["VALSAYN", "ARIMA", "MACOYA"]):
                region = "East"

            staged_events.append({
                "id": f"island-{len(staged_events)}",
                "name": name,
                "type": event_type,
                "date": date_iso,
                "startTime": start_time,
                "location": location,
                "region": region,
                "ticketUrl": ticket_url,
                "tags": ["islandetickets"]
            })
        except Exception as e:
            continue

    # Deduplicate entries by name cleanly
    unique_events = {e["name"]: e for e in staged_events}.values()

    # Sync directly with production database file path targets
    output_filename = "src/data/events.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(list(unique_events), f, indent=2, ensure_ascii=False)
        
    print(f"✅ Success! Isolated [{len(unique_events)}] pristine Carnival 2027 elements.")
    print(f"📂 Synced clean data layout file: {output_filename}")

if __name__ == "__main__":
    asyncio.run(scrape_caribbean_events())
