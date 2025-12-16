# Universal Page Linking Rules

## Overview

These are the comprehensive rules for linking pages to accounts. Apply these rules to EVERY page to find ALL matching accounts.

## Rule 1: Exact Account Number

**Condition**: Page contains the exact account number

**Example:**
```
Account: 0210630620
Page Content: "Account Number: 0210630620"
Result: ✓ LINK to account 0210630620
Confidence: 100%
```

**Matching Strategies:**
- Direct match: "0210630620" = "0210630620"
- With formatting: "0210630620" = "0210-630620" = "0210 630620"
- With leading zeros: "0210630620" = "210630620"
- With O/0 substitution: "0210630620" = "O21O63O62O"

**Confidence**: 100%

---

## Rule 2: Exact SSN Match

**Condition**: Page contains SSN that matches account holder's SSN

**Example:**
```
Account Holder: "John Smith" (SSN: 123-45-6789)
Page Content: "SSN: 123456789"
Result: ✓ LINK to account
Confidence: 100%
```

**Matching Strategies:**
- Format 1: "123456789" (no separators)
- Format 2: "123-45-6789" (with dashes)
- Format 3: "123 45 6789" (with spaces)
- Format 4: "123.45.6789" (with dots)

**All formats are equivalent:**
```
123456789 = 123-45-6789 = 123 45 6789 = 123.45.6789
```

**Confidence**: 100%

---

## Rule 3: Name Match

**Condition**: Page contains a name that matches an account holder's name

### 3.1 Case Insensitivity
Case doesn't matter - all case variations match:

```
Account: "John Smith"
Page: "JOHN SMITH" ✓
Page: "john smith" ✓
Page: "John Smith" ✓
Page: "JoHn SmItH" ✓
Result: ✓ LINK
Confidence: 100%
```

### 3.2 Middle Name/Initial Optional
Middle names and initials are optional:

```
Account: "John Smith"
Page: "John A Smith" ✓
Page: "John Albert Smith" ✓
Page: "John Smith" ✓
Result: ✓ LINK
Confidence: 95% (if middle differs)
```

**Examples:**
- "John Smith" = "John A Smith" (95%)
- "John A Smith" = "John Albert Smith" (95%)
- "John Smith" = "John Smith" (100%)
- "John A Smith" = "John B Smith" (85%)

### 3.3 Reversed Order OK
Names can appear in reversed order (Last-First):

```
Account: "John Smith"
Page: "Smith John" ✓
Page: "SMITH JOHN" ✓
Page: "smith john" ✓
Result: ✓ LINK
Confidence: 90%
```

**Examples:**
- "John Smith" = "Smith John" (90%)
- "John A Smith" = "Smith John A" (90%)
- "John A Smith" = "Smith A John" (90%)

### 3.4 Minor Spelling Variations OK
Allow 1-2 letter spelling differences (85%+ similarity):

```
Account: "Rahmah Gooba"
Page: "RAHMAHA GOOBA" ✓ (1 letter different)
Page: "Rahmah Goba" ✓ (1 letter different)
Page: "Rahmha Gooba" ✓ (1 letter different)
Result: ✓ LINK
Confidence: 85%
```

**Examples:**
- "Rahmah" = "RAHMAHA" (85%)
- "Gooba" = "Goba" (85%)
- "Mohammed" = "Muhammad" (85%)
- "Catherine" = "Katherine" (85%)

### 3.5 First + Last Name Must Match
First and last names MUST match (middle can differ):

```
Account: "John Smith"
Page: "John Jones" ✗ (different last name)
Page: "James Smith" ✗ (different first name)
Page: "John A Smith" ✓ (middle differs, OK)
Result: ✓ LINK only if first AND last match
Confidence: Varies based on middle name
```

**Critical Rule**: First name AND last name must match for any link to occur.

### 3.6 Abbreviations and Initials
Abbreviations and initials are supported:

```
Account: "John Smith"
Page: "J Smith" ✓ (first name abbreviated)
Page: "John S" ✓ (last name abbreviated)
Page: "J S" ✓ (both abbreviated)
Result: ✓ LINK
Confidence: 90%
```

**Examples:**
- "John Smith" = "J Smith" (90%)
- "John Smith" = "John S" (90%)
- "John Smith" = "J S" (90%)
- "John Albert Smith" = "J A Smith" (90%)

### 3.7 Punctuation Ignored
Punctuation is ignored:

```
Account: "John Smith"
Page: "John-Smith" ✓
Page: "John.Smith" ✓
Page: "John, Smith" ✓
Page: "O'Brien" = "OBrien" ✓
Result: ✓ LINK
Confidence: 100%
```

### 3.8 Whitespace Normalized
Extra whitespace is normalized:

```
Account: "John Smith"
Page: "John  Smith" ✓ (double space)
Page: "  John Smith  " ✓ (leading/trailing)
Page: "John\tSmith" ✓ (tab)
Result: ✓ LINK
Confidence: 100%
```

### Name Matching Confidence Scale

| Scenario | Confidence |
|----------|-----------|
| Exact match | 100% |
| Case variation | 100% |
| Punctuation variation | 100% |
| Whitespace variation | 100% |
| Initial expansion | 95% |
| Abbreviation | 90% |
| Reversed order | 90% |
| Missing middle name | 95% |
| Spelling variation | 85% |
| Different middle name | 85% |

**Minimum threshold**: 85% confidence required for linking

---

## Rule 4: Family Relationship

**Condition**: Page mentions a family member of an account holder

### 4.1 Death Certificate - Surviving Spouse
If death certificate mentions surviving spouse, and spouse name matches account holder:

```
Account Holder: "William S Campbell"
Death Certificate: "Surviving Spouse: William Campbell"
Result: ✓ LINK
Confidence: 95%
Reason: Surviving spouse matches account holder
```

### 4.2 Death Certificate - Informant
If death certificate mentions informant, and informant name matches account holder:

```
Account Holder: "John Smith"
Death Certificate: "Informant: John Smith"
Result: ✓ LINK
Confidence: 100%
Reason: Informant matches account holder
```

### 4.3 Marriage Certificate - Spouse
If marriage certificate mentions spouse, and spouse name matches account holder:

```
Account Holder: "Jennifer Frederick"
Marriage Certificate: "Bride: Jennifer Frederick"
Result: ✓ LINK
Confidence: 100%
Reason: Bride matches account holder
```

### 4.4 Birth Certificate - Parent
If birth certificate mentions parent, and parent name matches account holder:

```
Account Holder: "Mary Johnson"
Birth Certificate: "Mother: Mary Johnson"
Result: ✓ LINK
Confidence: 100%
Reason: Mother matches account holder
```

### 4.5 Indirect Matching - Last Name Only
If only last name matches (first name differs):

```
Account Holder: "Jane Smith"
Death Certificate: "Surviving Spouse: Jane Johnson"
Result: ✓ LINK
Confidence: 90%
Reason: Last name "Smith" matches (indirect)
```

### 4.6 Indirect Matching - First Name Only
If only first name matches (last name differs):

```
Account Holder: "John Smith"
Death Certificate: "Informant: John Johnson"
Result: ✓ LINK
Confidence: 85%
Reason: First name "John" matches (indirect)
```

### Family Relationship Confidence Scale

| Match Type | Confidence |
|-----------|-----------|
| Full name match | 100% |
| Initial expansion | 95% |
| Abbreviation | 90% |
| Reversed order | 90% |
| Last name only | 90% |
| First name only | 85% |
| Spelling variation | 85% |

**Minimum threshold**: 85% confidence required for linking

---

## Rule 5: Address Match

**Condition**: Page contains address that matches account holder's address

**Example:**
```
Account Holder: "John Smith" (Address: 123 Main St, Anytown, PA 12345)
Page Content: "Address: 123 Main St, Anytown, PA 12345"
Result: ✓ LINK (supporting evidence)
Confidence: 90%
```

**Matching Strategies:**
- Full address match
- Partial address match (street address)
- City/State match
- ZIP code match

**Note**: Address matching is typically used as supporting evidence, not primary linking criterion.

---

## Comprehensive Matching Examples

### Example 1: Direct Account Number
```
Account: 0210630620
Page: "Account Number: 0210630620"
Result: ✓ LINK (100%)
Rule: Rule 1 (Exact Account Number)
```

### Example 2: SSN Match
```
Account Holder: "John Smith" (SSN: 123-45-6789)
Page: "SSN: 123456789"
Result: ✓ LINK (100%)
Rule: Rule 2 (Exact SSN Match)
```

### Example 3: Exact Name Match
```
Account Holder: "John Smith"
Page: "John Smith"
Result: ✓ LINK (100%)
Rule: Rule 3 (Name Match - Exact)
```

### Example 4: Case Variation
```
Account Holder: "John Smith"
Page: "JOHN SMITH"
Result: ✓ LINK (100%)
Rule: Rule 3 (Name Match - Case Insensitive)
```

### Example 5: Middle Initial Missing
```
Account Holder: "William S Campbell"
Page: "William Campbell"
Result: ✓ LINK (95%)
Rule: Rule 3 (Name Match - Middle Optional)
```

### Example 6: Reversed Order
```
Account Holder: "John Smith"
Page: "Smith John"
Result: ✓ LINK (90%)
Rule: Rule 3 (Name Match - Reversed Order)
```

### Example 7: Spelling Variation
```
Account Holder: "Rahmah Gooba"
Page: "RAHMAHA GOOBA"
Result: ✓ LINK (85%)
Rule: Rule 3 (Name Match - Spelling Variation)
```

### Example 8: Abbreviation
```
Account Holder: "John Smith"
Page: "J Smith"
Result: ✓ LINK (90%)
Rule: Rule 3 (Name Match - Abbreviation)
```

### Example 9: Death Certificate - Surviving Spouse
```
Account Holder: "William S Campbell"
Death Certificate: "Surviving Spouse: William Campbell"
Result: ✓ LINK (95%)
Rule: Rule 4 (Family Relationship)
```

### Example 10: No Match - Different Last Name
```
Account Holder: "John Smith"
Page: "John Jones"
Result: ✗ NO LINK (0%)
Reason: Last names don't match
```

---

## Implementation Strategy

### Step 1: Extract Information from Page
- Account numbers
- SSNs
- Names
- Family relationships
- Addresses

### Step 2: Check Each Rule in Order
1. Check for exact account number
2. Check for exact SSN match
3. Check for name match (all variations)
4. Check for family relationships
5. Check for address match

### Step 3: Link to All Matching Accounts
- If any rule matches with 85%+ confidence → LINK
- Link to ALL accounts that match
- Record confidence score and matching rule

### Step 4: Log Results
- Log all matches with confidence scores
- Log matching rule used
- Log any unmatched pages

---

## Matching Priority

When multiple rules could apply, use this priority:

1. **Exact Account Number** (100%) - Highest priority
2. **Exact SSN Match** (100%)
3. **Exact Name Match** (100%)
4. **Name Match with Variations** (85-95%)
5. **Family Relationship** (85-100%)
6. **Address Match** (90%) - Supporting evidence

---

## Confidence Thresholds

| Threshold | Action |
|-----------|--------|
| 100% | Definite match - LINK |
| 95% | Very likely match - LINK |
| 90% | Likely match - LINK |
| 85% | Possible match - LINK |
| <85% | Unlikely match - DO NOT LINK |

**Minimum threshold**: 85% confidence required for any link

---

## Special Cases

### Case 1: Multiple Accounts Match
If a page matches multiple accounts:
- Link to ALL matching accounts
- Record confidence for each match
- Flag for manual review if confidence varies significantly

### Case 2: Partial Information
If page has only partial information:
- Use available information to match
- Apply appropriate confidence score
- Example: Only first name available → 85% confidence

### Case 3: Ambiguous Names
If name is very common (e.g., "John Smith"):
- Require additional matching criteria
- Use address or SSN as supporting evidence
- Flag for manual review

### Case 4: Name Changes
If account holder changed name (marriage, divorce):
- Match both old and new names
- Link to same account
- Document the name change

---

## Logging Requirements

For each page, log:
1. Page number
2. Information extracted (account #, SSN, names, etc.)
3. Matching rule(s) applied
4. Accounts matched
5. Confidence score(s)
6. Match reason

**Example Log:**
```
[PAGE_LINKING] Page 5:
  Extracted: Name="William Campbell", SSN=None, Account#=None
  Rule Applied: Rule 3 (Name Match)
  Accounts Matched: [0210630620]
  Confidence: 95%
  Reason: Name match with middle initial missing
```

---

## Testing Checklist

- ✓ Exact account number matching
- ✓ SSN matching (all formats)
- ✓ Case insensitive name matching
- ✓ Middle name/initial optional
- ✓ Reversed name order
- ✓ Spelling variations
- ✓ Abbreviations and initials
- ✓ Punctuation handling
- ✓ Whitespace normalization
- ✓ Family relationship matching
- ✓ Address matching
- ✓ Multiple account matching
- ✓ Confidence scoring
- ✓ Logging

---

## Summary

These universal page linking rules provide comprehensive guidance for linking pages to accounts. Apply all rules to every page to find ALL matching accounts. Use confidence scoring to prioritize matches and flag ambiguous cases for manual review.

**Key Principles:**
1. First and last names MUST match
2. Middle names are optional
3. Case, punctuation, and whitespace don't matter
4. Spelling variations allowed (85%+ similarity)
5. Reversed order is acceptable
6. Family relationships count
7. Minimum 85% confidence required

---

**Implementation Date**: December 16, 2025
**Status**: ✅ Complete and Ready for Implementation
