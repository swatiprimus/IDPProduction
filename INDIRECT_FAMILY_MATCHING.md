# Indirect Family Document Matching

## Overview

The family document matching system now supports **indirect matching** - linking documents based on partial name matches (last name only or first name only) when full name matching is not possible.

## What is Indirect Matching?

Indirect matching links a family document to an account when:
- The document mentions a family member with a partial name match
- Only the last name or first name matches an account holder
- The full name doesn't match, but a component does

## Why Indirect Matching?

Real-world scenarios where indirect matching is useful:

1. **Name Changes After Marriage**
   - Account: "Jane Smith" (married name)
   - Death Certificate: "Surviving Spouse: Jane Johnson" (maiden name)
   - Match: Last name "Smith" matches → LINK

2. **Incomplete Information**
   - Account: "John Michael Smith"
   - Death Certificate: "Informant: John Smith"
   - Match: Full name matches → LINK (but if it didn't, first name would)

3. **Common Names**
   - Account: "John Smith"
   - Death Certificate: "Informant: John Johnson"
   - Match: First name "John" matches → LINK (indirect)

4. **Name Variations**
   - Account: "Jane Smith"
   - Death Certificate: "Surviving Spouse: Jane Smyth"
   - Match: Last name similar → LINK

## Matching Strategies

### Strategy 1: Full Name Matching (Highest Priority)
Matches complete names using flexible name matching.

**Confidence**: 85-100%

**Examples:**
- "Jane Smith" = "JANE SMITH" (100%)
- "Jane Smith" = "J Smith" (90%)
- "Jane Smith" = "Smith Jane" (90%)
- "Jane Smith" = "Jayne Smith" (85%)

**When it works:**
- Both names are complete
- Names are similar enough for flexible matching

### Strategy 2: Last Name Only Matching (Medium Priority)
Matches only the last name component when full name doesn't match.

**Confidence**: 85-90%

**Examples:**
- "Jane Smith" matches "Jane Johnson" (both have "Smith" as last name) → 90%
- "Jane Smith" matches "Jane Smyth" (similar last names) → 85%

**When it works:**
- Full names don't match
- Last names are identical or similar
- Useful for married name changes

**When it doesn't work:**
- Last names are completely different
- Last name is too common (e.g., "Smith")

### Strategy 3: First Name Only Matching (Lowest Priority)
Matches only the first name component when full name and last name don't match.

**Confidence**: 85%

**Examples:**
- "John Smith" matches "John Johnson" (both have "John" as first name) → 85%
- "J Smith" matches "John Johnson" (J = John initial) → 85%

**When it works:**
- Full names don't match
- Last names don't match
- First names are identical or initial matches
- Useful for common first names

**When it doesn't work:**
- First names are completely different
- First name is too common (e.g., "John")

## Matching Priority

The system tries matching strategies in this order:

1. **Full Name Matching** (highest confidence)
   - If match found with 85%+ confidence → LINK
   - If no match → Continue to Strategy 2

2. **Last Name Only Matching** (medium confidence)
   - If match found with 85%+ confidence → LINK
   - If no match → Continue to Strategy 3

3. **First Name Only Matching** (lowest confidence)
   - If match found with 85%+ confidence → LINK
   - If no match → No link

## Real-World Examples

### Example 1: Married Name Change
```
Account Holder: "Jane Smith" (married name)
Death Certificate: "Surviving Spouse: Jane Johnson" (maiden name)

Step 1: Try full name matching
  "Jane Smith" vs "Jane Johnson"
  Result: No match (different last names)

Step 2: Try last name only matching
  Last name: "Smith" vs "Johnson"
  Result: No match (different last names)

Step 3: Try first name only matching
  First name: "Jane" vs "Jane"
  Result: MATCH (85% confidence)

Final Result: ✓ LINKED (85% confidence)
Reason: First name "Jane" matches
```

### Example 2: Surviving Spouse with Same Last Name
```
Account Holder: "Jane Smith"
Death Certificate: "Surviving Spouse: Jane Smith"

Step 1: Try full name matching
  "Jane Smith" vs "Jane Smith"
  Result: MATCH (100% confidence)

Final Result: ✓ LINKED (100% confidence)
Reason: Exact name match
```

### Example 3: Informant with Different First Name
```
Account Holder: "John Smith"
Death Certificate: "Informant: Robert Smith"

Step 1: Try full name matching
  "John Smith" vs "Robert Smith"
  Result: No match (different first names)

Step 2: Try last name only matching
  Last name: "Smith" vs "Smith"
  Result: MATCH (90% confidence)

Final Result: ✓ LINKED (90% confidence)
Reason: Last name "Smith" matches
```

### Example 4: Abbreviated Name
```
Account Holder: "John Michael Smith"
Death Certificate: "Informant: J M Smith"

Step 1: Try full name matching
  "John Michael Smith" vs "J M Smith"
  Result: MATCH (90% confidence - abbreviation)

Final Result: ✓ LINKED (90% confidence)
Reason: Abbreviation match
```

### Example 5: No Match
```
Account Holder: "Jane Smith"
Death Certificate: "Surviving Spouse: Robert Johnson"

Step 1: Try full name matching
  "Jane Smith" vs "Robert Johnson"
  Result: No match (completely different)

Step 2: Try last name only matching
  Last name: "Smith" vs "Johnson"
  Result: No match (different last names)

Step 3: Try first name only matching
  First name: "Jane" vs "Robert"
  Result: No match (different first names)

Final Result: ✗ NOT LINKED (0% confidence)
Reason: No matching names
```

## Confidence Scoring

### Full Name Matching
- 100%: Exact match
- 95%: Initial expansion
- 90%: Abbreviation or reversed order
- 85%: Spelling variation

### Last Name Only Matching
- 90%: Exact last name match
- 85%: Last name with spelling variation

### First Name Only Matching
- 85%: Exact first name match or initial match

## Implementation Details

### Functions Added

#### `match_last_name_only(family_name, holder_name)`
Matches names using last name only.

**Returns**: (is_match, confidence, reason)

**Example:**
```python
match_last_name_only("Jane Johnson", "Jane Smith")
# Returns: (False, 0, "No last name match")

match_last_name_only("Jane Smith", "Jane Smith")
# Returns: (True, 90, "Last name match (indirect)")
```

#### `match_first_name_only(family_name, holder_name)`
Matches names using first name only.

**Returns**: (is_match, confidence, reason)

**Example:**
```python
match_first_name_only("John Johnson", "John Smith")
# Returns: (True, 85, "First name match (indirect)")

match_first_name_only("Robert Smith", "John Smith")
# Returns: (False, 0, "No first name match")
```

### Enhanced Function

#### `match_family_member_to_accounts(family_info, all_account_holders)`
Now uses three-strategy matching:
1. Full name matching
2. Last name only matching
3. First name only matching

**Returns**: List of matching account numbers

## Use Cases

### Use Case 1: Estate Settlement
```
Scenario: Account holder passes away
Document: Death certificate with surviving spouse
Matching: Surviving spouse name matches account holder
Result: Document linked to account for estate settlement
```

### Use Case 2: Name Change After Marriage
```
Scenario: Account holder gets married
Document: Marriage certificate
Matching: Bride name matches account holder (maiden name)
Result: Document linked to account for name change documentation
```

### Use Case 3: Family Relationship Verification
```
Scenario: Opening new account for family member
Document: Birth certificate
Matching: Parent name matches account holder
Result: Document linked to account for relationship verification
```

### Use Case 4: Account Consolidation
```
Scenario: Consolidating family accounts
Document: Death certificate
Matching: Surviving spouse name matches account holder
Result: Document linked to account for consolidation
```

## Benefits

✓ **More Flexible**: Links documents even with partial name matches
✓ **Real-World Applicable**: Handles common scenarios like name changes
✓ **Comprehensive**: Three-strategy approach catches most matches
✓ **Accurate**: Confidence scoring prevents false positives
✓ **Auditable**: Logs all matching decisions

## Limitations

- May create false positives with very common names (e.g., "John Smith")
- Requires at least one name component to match
- Does not use address or date matching for additional verification
- May not work for significantly different names

## Future Enhancements

- Address matching for additional verification
- Date correlation with account opening/changes
- Machine learning for confidence scoring
- Manual override capability
- Soundex/Metaphone for phonetic matching

## Testing

### Test Scenario 1: Full Name Match
```
Account: "Jane Smith"
Document: "Surviving Spouse: JANE SMITH"
Expected: ✓ LINKED (100%)
```

### Test Scenario 2: Last Name Match
```
Account: "Jane Smith"
Document: "Surviving Spouse: Jane Johnson"
Expected: ✓ LINKED (85%)
```

### Test Scenario 3: First Name Match
```
Account: "John Smith"
Document: "Informant: John Johnson"
Expected: ✓ LINKED (85%)
```

### Test Scenario 4: No Match
```
Account: "Jane Smith"
Document: "Surviving Spouse: Robert Johnson"
Expected: ✗ NOT LINKED (0%)
```

## Configuration

Indirect matching is enabled by default. No configuration required.

## Troubleshooting

### Document Not Linked
- Check that at least one name component matches (first or last name)
- Verify confidence score is 85% or higher
- Review logs for matching details

### Incorrect Linking
- Check confidence scores in logs
- Verify name components are correctly extracted
- Look for false positives with common names

---

**Implementation Date**: December 16, 2025
**Status**: ✅ Complete and Ready for Testing
