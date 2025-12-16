# Supported Name Formats

## Overview
The flexible name matching algorithm supports a wide variety of name formats and variations. This document lists all supported formats with examples.

## Base Name: "Rahmah A Gooba"

### 1. Case Variations
All case variations are supported:
- ✓ "Rahmah A Gooba" (title case)
- ✓ "RAHMAH A GOOBA" (uppercase)
- ✓ "rahmah a gooba" (lowercase)
- ✓ "RaHmAh A GoObA" (mixed case)

**Confidence**: 100%

### 2. Middle Name Variations

#### Initial Form
- ✓ "Rahmah A Gooba" (single letter initial)
- ✓ "Rahmah A. Gooba" (initial with period)
- ✓ "Rahmah A . Gooba" (initial with spaces)

**Confidence**: 100%

#### Full Middle Name
- ✓ "Rahmah Abdulla Gooba" (full middle name)
- ✓ "Rahmah Abdul Gooba" (different middle name)
- ✓ "Rahmah Mohammed Gooba" (alternative middle name)

**Confidence**: 95% (initial expansion)

#### Missing Middle Name
- ✓ "Rahmah Gooba" (no middle name)

**Confidence**: 90%

### 3. Abbreviated Forms

#### Single Letter Abbreviations
- ✓ "R A Gooba" (first and middle as initials)
- ✓ "R Gooba" (first as initial, no middle)
- ✓ "Rahmah A" (first and middle, no last - unusual but supported)

**Confidence**: 90%

#### Multiple Letter Abbreviations
- ✓ "Ra A Gooba" (first name abbreviated)
- ✓ "Rah A Gooba" (first name abbreviated)

**Confidence**: 90%

### 4. Punctuation Variations

#### Periods
- ✓ "Rahmah A. Gooba" (period after initial)
- ✓ "R. A. Gooba" (periods after all initials)
- ✓ "Rahmah. A. Gooba" (periods everywhere)

**Confidence**: 100%

#### Hyphens
- ✓ "Rahmah-A-Gooba" (hyphens instead of spaces)
- ✓ "Rahmah-A Gooba" (mixed separators)

**Confidence**: 100%

#### Apostrophes
- ✓ "Rahmah A O'Gooba" (apostrophe in last name)
- ✓ "O'Rahmah A Gooba" (apostrophe in first name)

**Confidence**: 100%

### 5. Whitespace Variations

#### Extra Spaces
- ✓ "Rahmah  A  Gooba" (double spaces)
- ✓ "  Rahmah A Gooba  " (leading/trailing spaces)
- ✓ "Rahmah   A   Gooba" (multiple spaces)

**Confidence**: 100%

#### Tabs and Mixed Whitespace
- ✓ "Rahmah\tA\tGooba" (tabs)
- ✓ "Rahmah \t A \t Gooba" (mixed spaces and tabs)

**Confidence**: 100%

### 6. Reversed Order

#### Simple Reversal
- ✓ "Gooba Rahmah" (Last-First)
- ✓ "GOOBA RAHMAH" (uppercase reversed)

**Confidence**: 90%

#### Reversed with Middle Name
- ✓ "Gooba Rahmah A" (Last-First-Middle)
- ✓ "Gooba A Rahmah" (Last-Middle-First)

**Confidence**: 90%

#### Reversed with Spelling Variation
- ✓ "GOOBA RAHMAHA" (reversed + 1-letter variation)
- ✓ "Gooba Rahmah" (reversed, missing middle)

**Confidence**: 85%

### 7. Spelling Variations

#### 1-Letter Differences
- ✓ "Rahmah A Gooba" = "Rahmha A Gooba" (missing 'm')
- ✓ "Rahmah A Gooba" = "Rahmah A Gooba" (exact)
- ✓ "Rahmah A Gooba" = "Rahmah A Goba" (missing 'o')

**Confidence**: 85%

#### 2-Letter Differences
- ✓ "Rahmah A Gooba" = "Rahmha A Goba" (2 letters different)

**Confidence**: 85%

#### Common Spelling Variants
- ✓ "Mohammed" = "Muhammad" = "Mohamed"
- ✓ "Catherine" = "Katherine" = "Kathryn"
- ✓ "Rahmah" = "Ramah" (common variant)

**Confidence**: 85%

### 8. Combined Variations

#### Abbreviation + Case
- ✓ "r a gooba" (abbreviated + lowercase)
- ✓ "R A GOOBA" (abbreviated + uppercase)

**Confidence**: 90%

#### Abbreviation + Punctuation
- ✓ "R. A. Gooba" (abbreviated with periods)
- ✓ "R-A-Gooba" (abbreviated with hyphens)

**Confidence**: 90%

#### Reversed + Abbreviation
- ✓ "G R A" (reversed abbreviated)
- ✓ "Gooba R A" (reversed with abbreviated first/middle)

**Confidence**: 85%

#### Reversed + Spelling + Abbreviation
- ✓ "GOOBA RAHMAHA" (reversed + spelling variation)
- ✓ "G R Gooba" (reversed abbreviated + spelling)

**Confidence**: 85%

## Real-World Examples

### Example 1: Bank Document
```
Stored in Account: "Rahmah A Gooba"
Found on Page: "RAHMAH ABDULLA GOOBA"
Match: ✓ YES (95% confidence)
Reason: Initial expansion (A = Abdulla)
```

### Example 2: Signature Card
```
Stored in Account: "Rahmah A Gooba"
Found on Page: "GOOBA RAHMAH"
Match: ✓ YES (90% confidence)
Reason: Reversed order (Last-First)
```

### Example 3: Supporting Document
```
Stored in Account: "Rahmah A Gooba"
Found on Page: "R A GOOBA"
Match: ✓ YES (90% confidence)
Reason: Abbreviated form
```

### Example 4: International Document
```
Stored in Account: "Rahmah A Gooba"
Found on Page: "GOOBA RAHMAHA"
Match: ✓ YES (85% confidence)
Reason: Reversed order + spelling variation
```

### Example 5: Formal Document
```
Stored in Account: "Rahmah A Gooba"
Found on Page: "Rahmah A. Gooba"
Match: ✓ YES (100% confidence)
Reason: Exact match (punctuation normalized)
```

## Matching Algorithm Summary

### Step 1: Normalize
- Convert to uppercase
- Remove punctuation (periods, hyphens, apostrophes)
- Trim whitespace
- Separate into components

### Step 2: Try Direct Match
- Compare [First, Middle, Last] components
- Allow initial expansion (A = Abdulla)
- Allow 1-2 letter spelling variations

### Step 3: Try Abbreviation Match
- Check if one name is abbreviated form of other
- Example: "R A Gooba" is abbreviation of "Rahmah Abdul Gooba"

### Step 4: Try Reversed Match
- Try Last-First-Middle order
- Allow spelling variations in reversed order

### Step 5: Calculate Confidence
- 100%: Exact match or SSN match
- 95%: Initial expansion
- 90%: Abbreviation or reversed order
- 85%: Spelling variation or reversed + spelling

## Confidence Thresholds

- **Accept Match**: 85% or higher
- **Reject Match**: Below 85%
- **Minimum Requirement**: First and last name must match (after normalization)

## Special Cases

### Hispanic Names (Two Last Names)
- ✓ "Hector Hernandez Hernandez" = "Hector Hernandez"
- ✓ "Raymunda Ramirez Martin" = "Raymunda Ramirez"

### Compound First Names
- ✓ "Jean-Paul Dupont" = "Jean Paul Dupont"
- ✓ "Mary-Kate Smith" = "Mary Kate Smith"

### Patronymic Names (Middle East)
- ✓ "Mohammed Ali Ahmed" = "Mohammed Ahmed" (father's name as middle)

### Nicknames (Limited Support)
- ✓ "Robert" = "Bob" (common nicknames)
- ✓ "William" = "Bill"

## What Won't Match

### Different First Names
- ✗ "Rahmah Gooba" ≠ "Ronald Honore"
- ✗ "John Smith" ≠ "James Smith"

### Different Last Names
- ✗ "Rahmah Gooba" ≠ "Rahmah Honore"
- ✗ "John Smith" ≠ "John Jones"

### Too Many Spelling Errors
- ✗ "Rahmah" ≠ "Ramah" (if >2 letters different)
- ✗ "Gooba" ≠ "Goba" (if >2 letters different)

### Completely Different Names
- ✗ "Jennifer Frederick" ≠ "Frederick Gregory Hill"
- ✗ "Michael Davis" ≠ "David Michael"

## Implementation

The matching is implemented in `app_modular.py` with these functions:

1. **`normalize_name_component(component)`** - Normalizes individual name parts
2. **`parse_name_into_components(full_name)`** - Splits names into [First, Middle, Last]
3. **`is_initial_of(initial, full_name)`** - Checks if initial matches first letter
4. **`calculate_string_similarity(str1, str2)`** - Calculates similarity percentage
5. **`is_name_abbreviation(short_name, long_name)`** - Checks if one is abbreviation of other
6. **`match_name_components(...)`** - Matches individual components
7. **`try_reversed_name_match(...)`** - Tries reversed order matching
8. **`flexible_name_match(stored_name, page_name)`** - Main matching function

## Testing

See `test_flexible_name_matching.html` for interactive test cases covering all these formats.

---

**Last Updated**: December 16, 2025
**Status**: ✅ Complete
