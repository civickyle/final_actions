#!/usr/bin/env python3
"""
Add isCharterAmendment flag to all legislation items in meeting JSON files.
"""

import json
from pathlib import Path

def is_charter_amendment(description):
    """Check if description indicates a charter amendment."""
    if not description:
        return False
    return "TO AMEND THE CHARTER OF THE CITY OF ATLANTA" in description.upper()

def process_files():
    """Process all meeting JSON files and add charter amendment flags."""
    meeting_dates_dir = Path("meeting_dates")

    total_files = 0
    total_items = 0
    charter_amendments = 0

    # Iterate through all JSON files
    for json_file in sorted(meeting_dates_dir.rglob("*.json")):
        if json_file.suffix != '.json' or '.bak' in json_file.name:
            continue

        try:
            # Read the file
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Track if we made any changes
            modified = False

            # Process each item in the meeting
            for item in data.get('data', []):
                total_items += 1

                # Check if this is a charter amendment
                description = item.get('description', '')
                is_charter = is_charter_amendment(description)

                # Add the flag if it's a charter amendment
                if is_charter:
                    item['isCharterAmendment'] = True
                    charter_amendments += 1
                    modified = True
                # Optionally add false flag for non-charter amendments
                # elif 'isCharterAmendment' not in item:
                #     item['isCharterAmendment'] = False
                #     modified = True

            # Write back if modified
            if modified:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                total_files += 1

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    print(f"\nProcessing complete!")
    print(f"Files processed: {total_files}")
    print(f"Total items checked: {total_items:,}")
    print(f"Charter amendments found: {charter_amendments}")

if __name__ == '__main__':
    print("Adding charter amendment flags to legislation items...")
    process_files()
