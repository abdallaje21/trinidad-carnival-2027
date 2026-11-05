def parse_date_from_context(search_text: str) -> date | None:
    upper = search_text.upper()

    for month_str, month_num in CARNIVAL_MONTHS.items():
        # Updated regex to gracefully handle numbers followed by ST, ND, RD, or TH (e.g. 16th)
        pattern = rf'\b{month_str}\w*\s+(\d{{1,2}})(?:ST|ND|RD|TH)?\b|\b(\d{{1,2}})(?:ST|ND|RD|TH)?\s+{month_str}\w*\b'
        match = re.search(pattern, upper)
        if not match:
            continue

        day_str = match.group(1) or match.group(2)
        if not day_str:
            continue

        day = int(day_str)
        if not (1 <= day <= 31):
            continue

        year = 2027

        try:
            candidate = date(year, month_num, day)
        except ValueError:
            continue

        if DATE_FROM <= candidate <= DATE_TO:
            return candidate

    return None
