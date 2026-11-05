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
    
    # Target the primary container where all calendar data streams sequentially
    main_container = soup.select_one(".container, body")
    if not main_container:
        print("❌ Could not locate main body wrapper.")
        return

    # Months converter map
    months_map = {"JAN": "01", "JANUARY": "01", "FEB": "02", "FEBRUARY": "02"}
    
    # State tracking variables
    current_year = "2026"
    current_month_num = "11"
    
    # Loop over elements to maintain top-to-bottom reading context
    for element in main_container.find_all(recursive=True):
        # 1. Catch sticky header updates (e.g., "Nov 2026" or "Jan 2027")
        if element.name in ['h5', 'h4', 'h3', 'div'] and any(m in element.get_text().upper() for m in months_map.keys()):
            header_text = element.get_text(" ", strip=True).upper()
            match = re.search(r'\b(JAN|JANUARY|FEB|FEBRUARY)\b\s*(\d{4})?', header_text)
            if match:
                month_name = match.group(1)
                current_month_num = months_map[month_name]
                if match.group(2):
                    current_year = match.group(2)
                else:
                    current_year = "2027"
                continue

        # 2. Process Event Card Blocks
        if element.name == "h5" and element.find_parent("div"):
            parent_card = element.find_parent("div")
            name = element.get_text(strip=True)
            
            # Skip noise nodes or structural header banners
            if not name or "THESE EVENTS" in name.upper() or name.upper() in months_map.keys():
                continue

            # CRITICAL ENFORCEMENT FILTER: Skip anything that belongs to 2026
            if current_year == "2026":
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

            # Isolate the Day Number token sitting next to card elements
            day_num = "01"
            prev_siblings = parent_card.find_previous_siblings()
            for sib in prev_siblings:
                sib_text = sib.get_text(strip=True)
                if sib_text.isdigit() and 1 <= int(sib_text) <= 31:
                    day_num = sib_text.zfill(2)
                    break

            date_iso = f"{current_year}-{current_month_num}-{day_num}"

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

    # Deduplicate entries cleanly
    unique_events = {e["name"]: e for e in staged_events}.values()

    output_filename = "src/data/events.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(list(unique_events), f, indent=2, ensure_ascii=False)
        
    print(f"✅ Success! Isolated [{len(unique_events)}] real Carnival 2027 elements.")
    print(f"📂 Synced database configuration file: {output_filename}")

if __name__ == "__main__":
    asyncio.run(scrape_caribbean_events())
