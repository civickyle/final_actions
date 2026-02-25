#!/usr/bin/env python3
"""
Analyze legislation descriptions to identify final action patterns.
"""

import json
import re
from pathlib import Path
from collections import Counter, defaultdict

def analyze_final_actions():
    """Analyze all legislation to identify final action patterns."""

    meeting_dates_dir = Path("meeting_dates")

    # Patterns to track
    all_endings = []  # Last part of each description
    potential_actions = Counter()  # Potential final action keywords
    items_with_vote_info = 0
    items_without_vote_info = 0

    # Common final action keywords to look for
    action_keywords = [
        'ADOPTED', 'FILED', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'TABLED',
        'DEFERRED', 'REFERRED', 'PASSED', 'FAILED', 'VETOED', 'CARRIED',
        'DEFEATED', 'POSTPONED', 'HELD', 'CONTINUED'
    ]

    # Track different patterns
    patterns = defaultdict(list)

    # Sample items for each pattern
    samples = defaultdict(list)
    max_samples = 5

    total_items = 0

    print("Analyzing legislation descriptions...")

    for json_file in meeting_dates_dir.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    total_items += 1
                    description = item.get('description', '')

                    if not description:
                        continue

                    # Get the last sentence or segment
                    # Many descriptions end with action and voting info
                    last_segment = description.strip()

                    # Check for voting information
                    if 'ROLL CALL VOTE' in last_segment.upper():
                        items_with_vote_info += 1
                    else:
                        items_without_vote_info += 1

                    # Look for action keywords at the end
                    found_action = None
                    for keyword in action_keywords:
                        # Check if keyword appears near the end
                        if keyword in last_segment.upper():
                            # Try to extract the context around it
                            pattern = rf'([A-Z\s,;]*{keyword}[^.]*)'
                            matches = re.findall(pattern, last_segment.upper())
                            if matches:
                                found_action = matches[-1].strip()  # Get last occurrence
                                potential_actions[keyword] += 1

                                # Categorize the pattern
                                if 'ROLL CALL VOTE' in found_action:
                                    pattern_type = 'ACTION_WITH_VOTE'
                                elif 'CONSENT' in found_action:
                                    pattern_type = 'ACTION_ON_CONSENT'
                                else:
                                    pattern_type = 'ACTION_SIMPLE'

                                patterns[pattern_type].append(item['number'])

                                # Store sample
                                if len(samples[pattern_type]) < max_samples:
                                    samples[pattern_type].append({
                                        'number': item['number'],
                                        'action': found_action,
                                        'full_desc': description[:200] + '...' if len(description) > 200 else description
                                    })
                                break

                    # Track last 100 characters for pattern analysis
                    ending = last_segment[-100:] if len(last_segment) > 100 else last_segment
                    all_endings.append(ending)

                    if not found_action:
                        # Track items without clear action
                        patterns['NO_CLEAR_ACTION'].append(item['number'])
                        if len(samples['NO_CLEAR_ACTION']) < max_samples:
                            samples['NO_CLEAR_ACTION'].append({
                                'number': item['number'],
                                'ending': ending,
                                'full_desc': description[:200] + '...' if len(description) > 200 else description
                            })

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Generate report
    print("\n" + "="*80)
    print("FINAL ACTION ANALYSIS REPORT")
    print("="*80)

    print(f"\nTotal legislation items analyzed: {total_items:,}")
    print(f"Items with voting information: {items_with_vote_info:,} ({items_with_vote_info/total_items*100:.1f}%)")
    print(f"Items without voting information: {items_without_vote_info:,} ({items_without_vote_info/total_items*100:.1f}%)")

    print("\n" + "-"*80)
    print("ACTION KEYWORD FREQUENCY")
    print("-"*80)
    for keyword, count in potential_actions.most_common():
        print(f"{keyword:20s}: {count:6,} ({count/total_items*100:.1f}%)")

    print("\n" + "-"*80)
    print("PATTERN DISTRIBUTION")
    print("-"*80)
    for pattern_type, items in sorted(patterns.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(items)
        print(f"{pattern_type:25s}: {count:6,} ({count/total_items*100:.1f}%)")

    print("\n" + "="*80)
    print("SAMPLE EXTRACTIONS BY PATTERN")
    print("="*80)

    for pattern_type in ['ACTION_WITH_VOTE', 'ACTION_ON_CONSENT', 'ACTION_SIMPLE', 'NO_CLEAR_ACTION']:
        if pattern_type in samples and samples[pattern_type]:
            print(f"\n{pattern_type}")
            print("-"*80)
            for i, sample in enumerate(samples[pattern_type], 1):
                print(f"\n{i}. Legislation: {sample['number']}")
                if 'action' in sample:
                    print(f"   Extracted Action: {sample['action']}")
                elif 'ending' in sample:
                    print(f"   Description Ending: ...{sample['ending']}")
                print(f"   Full Description: {sample['full_desc']}")

    # Identify common patterns in endings
    print("\n" + "="*80)
    print("COMMON ENDING PATTERNS (sample of 20)")
    print("="*80)

    # Sample some random endings
    import random
    for ending in random.sample(all_endings, min(20, len(all_endings))):
        print(f"...{ending}")

    # Calculate confidence levels
    print("\n" + "="*80)
    print("CONFIDENCE ASSESSMENT")
    print("="*80)

    high_confidence = patterns.get('ACTION_WITH_VOTE', []) + patterns.get('ACTION_ON_CONSENT', [])
    medium_confidence = patterns.get('ACTION_SIMPLE', [])
    low_confidence = patterns.get('NO_CLEAR_ACTION', [])

    print(f"\nHigh Confidence (clear action with voting details):")
    print(f"  Count: {len(high_confidence):,} ({len(high_confidence)/total_items*100:.1f}%)")
    print(f"  Can extract: Final action + voting results")

    print(f"\nMedium Confidence (clear action, no voting details):")
    print(f"  Count: {len(medium_confidence):,} ({len(medium_confidence)/total_items*100:.1f}%)")
    print(f"  Can extract: Final action only")

    print(f"\nLow Confidence (no clear action keyword):")
    print(f"  Count: {len(low_confidence):,} ({len(low_confidence)/total_items*100:.1f}%)")
    print(f"  May need: Manual review or additional pattern analysis")

    print("\n" + "="*80)
    print("RECOMMENDATIONS & QUESTIONS")
    print("="*80)

    print("\n1. EXTRACTION STRATEGY:")
    print("   - Use regex to extract final action from end of description")
    print("   - Extract voting information when present (ROLL CALL VOTE)")
    print("   - Create separate fields: 'finalAction' and 'votingResults'")

    print("\n2. CHALLENGES IDENTIFIED:")
    print("   - Inconsistent formatting of voting results")
    print("   - Some items have no clear final action")
    print("   - Multiple action keywords may appear in same description")

    print("\n3. QUESTIONS FOR CLARIFICATION:")
    print("   - Should we extract just the action word (e.g., 'ADOPTED')")
    print("     or the full phrase (e.g., 'ADOPTED ON CONSENT BY A ROLL CALL VOTE')?")
    print("   - Should voting results be in a separate field?")
    print("   - How should we handle items with no clear final action?")
    print("   - Should we preserve original description or remove extracted action?")

if __name__ == "__main__":
    analyze_final_actions()
