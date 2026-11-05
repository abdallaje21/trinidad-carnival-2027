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
        
    print("🧹 Download complete. Extracting true dataset elements...")
    soup = BeautifulSoup(html_content, "html.parser")
    staged_events = []
    
    # Locate all event cards / titles on the page
    event_titles = soup.find_all("h5")
    
    months_map = {
        "JAN": "01", "JANUARY": "01",
        "FEB": "02", "FEBRUARY": "02"
    }

    for index, title_node in enumerate(event_titles):
        try:
            name = title_node.get_text(strip=True)
            if "THESE EVENTS" in name.upper() or not name:
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

            # --- DYNAMIC DATE EXTRACTION ---
            date_str = None
            
            # Find the date badge or header associated with this card block
            # Islandetickets typically uses a date container nearby
            card_container = title_node.find_parent(class_=re.compile(r'(card|holder|event|item)', re.I)) or parent_card
            container_text = card_container.get_text(" ", strip=True).upper() if card_container else ""
            
            # Look upwards or in text content for explicit Jan/Feb 2027 markers
            month_match = re.search(r'\b(JAN|JANUARY|FEB|FEBRUARY)\b\s*(2027)?', container_text)
            
            if month_match:
                month_name = month_match.group(1)
                month_num = months_map[month_name]
                
                # Dig out the nearest numeric day digit
                day_digits = re.findall(r'\b\d{1,2}\b', container_text)
                day_num = "01"
                for d in day_digits:
                    if 1 <= int(d) <= 31:
                        day_num = d.zfill(2)
                        break
                date_str = f"2027-{month_num}-{day_num}"
            else:
                # Secondary fallback scanner: Check nearby parent nodes for structural date logs
                sibling_text = ""
                prev_sib = parent_card.find_previous()
                if prev_sib:
                    sibling_text = prev_sib.get_text(" ", strip=True).upper()
                
                if "JAN" in sibling_text or "JANUARY" in sibling_text:
                    date_str = "2027-01-03"  # Standard early Jan fete bucket
                elif "FEB" in sibling_text or "FEBRUARY" in sibling_text:
                    date_str = "2027-02-03"  # Peak Carnival window bucket

            # ENFORCE STRICT DATE WINDOW SCOPE (January 1 - February 28, 2027)
            if not date_str:
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
            joined_context = " ".join(lines).upper() + " " + name.upper()
            if any(x in j...

