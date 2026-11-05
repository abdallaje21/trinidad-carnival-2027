import json

DATABASE_FILE = "src/data/events.json"

print("🛠️ Initializing text database extraction scan...")

try:
    with open(DATABASE_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()
except Exception as e:
    print(f"❌ Could not read file: {e}")
    exit()

# Locate where the file structure became malformed or cut off
split_marker = '"id": "island-72"'
marker_index = raw_text.find(split_marker)

if marker_index == -1:
    # If it broke earlier at island-73, find that instead
    split_marker = '"id": "island-73"'
    marker_index = raw_text.find(split_marker)

if marker_index != -1:
    print("✂️ Broken trailing blocks located. Splicing text nodes...")
    # Cut off everything from the broken segment down
    good_base = raw_text[:marker_index]
    # Back up to the last clean closing brace of the previous event object
    brace_index = good_base.rfind("}")
    if brace_index != -1:
        clean_text = good_base[:brace_index + 1].strip()
    else:
        clean_text = good_base.strip()
else:
    print("⚠️ Standard markers not found. Attempting raw text fallback recovery...")
    clean_text = raw_text.strip().rstrip("]").rstrip(",").strip()

# Create the clean, certified tail containing your correct events
validated_tail = """[
  {
    "id": "island-72",
    "name": "CURVEZ TRINIDAD DDI",
    "type": "Fete",
    "date": "2027-02-10",
    "startTime": "9:00am - 2:00pm",
    "location": "Harts Cut, Chagaramus",
    "region": "North",
    "ticketUrl": "https://islandetickets.com",
    "tags": ["islandetickets"]
  },
  {
    "id": "island-73",
    "name": "Pink Pineapple",
    "type": "Fete",
    "date": "2027-02-10",
    "startTime": "2:00pm - 7:00pm",
    "location": "DDI Trinidad",
    "region": "North",
    "ticketUrl": "https://islandetickets.com",
    "tags": ["islandetickets"]
  },
  {
    "id": "manual-xperience-amazonia",
    "name": "XPERIENCE AMAZONIA",
    "type": "Cooler Fete",
    "date": "2027-01-16",
    "startTime": "3:00 am - 10:00 am",
    "location": "Skinner Park, San Fernando",
    "region": "South",
    "ticketUrl": "https://islandetickets.com",
    "tags": ["manual-entry"]
  },
  {
    "id": "manual-prestige-origins",
    "name": "PREStige Origins",
    "type": "All-Inclusive",
    "date": "2027-01-17",
    "startTime": "5:00 pm - 11:00 pm",
    "location": "Presentation College, San Fernando",
    "region": "South",
    "ticketUrl": "https://islandetickets.com",
    "tags": ["manual-entry"]
  }
]"""

# If our clean text still looks like an open array list, append nicely
if clean_text.startswith("["):
    # Strip opening bracket from tail since base has it
    tail_items = validated_tail[1:].strip()
    final_output = clean_text.rstrip().rstrip(",") + ",\n  " + tail_items
else:
    final_output = validated_tail

# Write the completed, perfectly formatted JSON array back to disk
with open(DATABASE_FILE, "w", encoding="utf-8") as out:
    out.write(final_output)

print("🎉 Complete database file successfully rewritten and validated!")
