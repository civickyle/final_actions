#!/usr/bin/env python3
"""Generate PDF URLs from deduplicated numbers."""

import json
from pathlib import Path

def number_to_url(number: str) -> str:
    """Convert a number to a PDF URL.

    Example: "84-R-15428" -> "https://aimewebapp.blob.core.windows.net/finalactions/84r15428.pdf"
    """
    # Remove hyphens and convert to lowercase
    cleaned_number = number.replace('-', '').lower()
    # Create URL
    url = f"https://aimewebapp.blob.core.windows.net/finalactions/{cleaned_number}.pdf"
    return url

def main():
    # Read the deduplicated numbers
    input_file = Path(__file__).parent / 'deduplicated_numbers.json'
    with open(input_file, 'r', encoding='utf-8') as f:
        numbers = json.load(f)

    print(f"Processing {len(numbers)} numbers...")

    # Generate URLs
    urls = [number_to_url(number) for number in numbers]

    # Save URLs as text file (one per line)
    output_txt = Path(__file__).parent / 'pdf_urls.txt'
    with open(output_txt, 'w', encoding='utf-8') as f:
        for url in urls:
            f.write(f"{url}\n")

    print(f"\nURLs saved to: {output_txt}")

    # Save as JSON array
    output_json = Path(__file__).parent / 'pdf_urls.json'
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(urls, f, indent=2)

    print(f"JSON URLs saved to: {output_json}")

    # Print first 10 as sample
    print("\nFirst 10 URLs (sample):")
    for url in urls[:10]:
        print(f"  {url}")

    print(f"\nTotal URLs generated: {len(urls)}")

if __name__ == '__main__':
    main()
