# Analysis of Remaining Duplicates

After initial deduplication (removing exact duplicates), there are still **9,786 legislation numbers** that appear multiple times with different field values.

## Summary Statistics

- **Total legislation items**: 107,272
- **Unique legislation numbers**: 97,486
- **Legislation numbers with duplicates**: 9,786 (10.0%)
- **Total duplicate pairs analyzed**: 10,757

## Types of Differences Found

### 1. Description Field Differences (10,746 total)

#### a) Quote/Apostrophe Differences (2,316 cases) ✅ **EASILY FIXABLE**
- **Issue**: Smart quotes (Unicode characters) vs regular ASCII quotes
- **Example**: `OWNER'S` (U+2019) vs `OWNER'S` (U+0027)
- **Same IDs**: 36645 vs 117732 for legislation 13-R-3322
- **Resolution**: Normalize all Unicode quotes to ASCII equivalents
  - `'` (U+2018) → `'` (U+0027)
  - `'` (U+2019) → `'` (U+0027)
  - `"` (U+201C) → `"` (U+0022)
  - `"` (U+201D) → `"` (U+0022)
  - `–` (U+2013) → `-` (U+002D)
  - `—` (U+2014) → `-` (U+002D)

#### b) Whitespace Differences (114 cases) ✅ **EASILY FIXABLE**
- **Issue**: Extra spaces, tabs, or line breaks
- **Example**: Multiple spaces vs single space between words
- **Resolution**: Normalize all whitespace to single spaces

#### c) Substring Differences (3,123 cases) ⚠️ **PARTIALLY FIXABLE**
- **Issue**: One description is a complete substring of another
- **Example**:
  - Shorter (ID 185145): "...NORTH AVENUE, "
  - Longer (ID 218161): "...NORTH AVENUE, ADOPTED BY A ROLL CALL VOTE OF 14 YEAS; 0 NAYS"
- **Pattern**: Often the longer version includes voting results appended
- **Resolution Options**:
  1. Keep the longer version (more complete information)
  2. Truncate both to shortest common version
  3. Flag for manual review

#### d) General Text Differences (5,193 cases) ❌ **NOT EASILY FIXABLE**
- **Issue**: Substantive text differences in descriptions
- **These may represent**:
  - Different versions of the same legislation (amended vs original)
  - Corrected typos
  - Updated language
  - Actually different legislation with same number (data quality issue)
- **Resolution**: Requires case-by-case review

### 2. Legislation Date Differences (500 cases) ❌ **NOT EASILY FIXABLE**

- **Issue**: Same legislation number but different dates
- **Example**: Legislation 23-R-3533
  - ID 281190: 2024-06-03
  - ID 281085: 2024-05-20
- **Possible reasons**:
  - Legislation introduced on one date, passed on another
  - Amended and re-voted
  - Data entry errors
- **Resolution**: Keep both records as they may represent different actions

### 3. Multiple Field Differences (489 cases) ❌ **COMPLEX**

- **Issue**: Differences in both description AND date
- **Resolution**: Requires individual analysis

## Recommendations for Normalization

### Phase 1: Safe Normalizations ✅
These changes can be applied safely without losing information:

1. **Quote Normalization** (2,316 field differences)
   - Convert all Unicode quote characters to ASCII equivalents
   - Apply before comparing for duplicates

2. **Whitespace Normalization** (114 field differences)
   - Trim leading/trailing whitespace
   - Collapse multiple spaces to single space
   - Apply before comparing for duplicates

**Expected result**: ~2,430 additional duplicates could be identified and removed

### Phase 2: Substring Resolution ⚠️
Requires policy decision:

3. **Substring Handling** (3,123 cases)
   - **Option A**: Keep longer version (recommended)
     - Assumes longer = more complete
     - Preserves voting results and other appended info
   - **Option B**: Keep shorter version
     - Assumes shorter = original
   - **Option C**: Flag for manual review

### Phase 3: Manual Review ❌
Cannot be automated safely:

4. **Text Differences** (5,193 cases)
   - Review samples to identify patterns
   - May represent legitimate different versions

5. **Date Differences** (500 cases)
   - Likely represent different legislative actions
   - Should probably keep both records

## Implementation Priority

### High Priority (Safe & High Impact)
1. ✅ Implement quote normalization
2. ✅ Implement whitespace normalization
3. ✅ Re-run deduplication

**Impact**: Could eliminate ~2,430 duplicates (22.6% of remaining)

### Medium Priority (Requires Decision)
4. ⚠️ Decide policy for substring differences
5. ⚠️ Implement substring resolution

**Impact**: Could eliminate up to ~3,123 duplicates (29.0% of remaining)

### Low Priority (Manual)
6. ❌ Sample review of text differences
7. ❌ Review date differences
8. ❌ Flag truly problematic cases

## Files Most Affected

The duplicates are spread across 1,093 files, with the highest concentrations in:
- 2013 files (many quote character issues)
- 2023-2024 files (substring/voting result additions)
- 1987-1991 files (some date discrepancies)
