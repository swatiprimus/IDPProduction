# Family Document Matching - Quick Reference

## What It Does

Automatically links family documents (death certificates, marriage certificates, birth certificates) to accounts when they mention family members of account holders.

## Supported Documents

| Document Type | Key Information | Links To |
|--------------|-----------------|----------|
| Death Certificate | Surviving spouse, Informant | Account holder who is spouse/informant |
| Marriage Certificate | Bride, Groom, Witnesses | Account holder who is bride/groom/witness |
| Birth Certificate | Mother, Father | Account holder who is parent |

## How It Works

### Step 1: Detect Document Type
```
Document contains "DEATH" + "CERTIFICATE"?
→ Death Certificate
```

### Step 2: Extract Family Members
```
Death Certificate:
- Deceased: John Smith
- Surviving Spouse: Jane Smith
- Informant: Jane Smith
```

### Step 3: Match to Account Holders
```
Account Holders:
- Jane Smith (Account: 0210630620)

Match: Jane Smith (Surviving Spouse) = Jane Smith (Account Holder)
→ LINK to Account 0210630620
```

## Examples

### Example 1: Death Certificate - Surviving Spouse
```
Account: "Jane Smith"
Death Certificate: "Surviving Spouse: JANE SMITH"
Result: ✓ LINKED (100% confidence)
```

### Example 2: Death Certificate - Informant
```
Account: "John Smith"
Death Certificate: "Informant: JOHN SMITH"
Result: ✓ LINKED (100% confidence)
```

### Example 3: Marriage Certificate
```
Account: "Jennifer Frederick"
Marriage Certificate: "Bride: JENNIFER FREDERICK"
Result: ✓ LINKED (100% confidence)
```

### Example 4: Birth Certificate
```
Account: "Mary Johnson"
Birth Certificate: "Mother: MARY JOHNSON"
Result: ✓ LINKED (100% confidence)
```

### Example 5: No Match
```
Account: "Rahmah Gooba"
Death Certificate: "Deceased: John Smith"
                   "Surviving Spouse: Jane Smith"
Result: ✗ NOT LINKED (no matches)
```

## Matching Rules

### Strategy 1: Full Name Matching
- Exact name match: "Jane Smith" = "Jane Smith"
- Case variation: "JANE SMITH" = "Jane Smith"
- Initial expansion: "J Smith" = "Jane Smith"
- Reversed order: "Smith Jane" = "Jane Smith"
- Spelling variation: "Jayne Smith" ≈ "Jane Smith" (1-2 letters)

### Strategy 2: Last Name Only (Indirect)
- Last name match: "Jane Smith" matches "Jane Johnson" (both "Smith")
- Last name with spelling: "Jane Smith" matches "Jane Smyth" (similar last names)

### Strategy 3: First Name Only (Indirect)
- First name match: "John Smith" matches "John Johnson" (both "John")
- First name initial: "J Smith" matches "John Johnson" (J = John)

### ✗ WILL NOT MATCH
- No common names: "Jane Smith" ≠ "Robert Jones"
- Too many spelling errors: "Jne Smith" ≠ "Jane Smith"

## Confidence Levels

| Match Type | Confidence | Strategy |
|-----------|-----------|----------|
| Exact match | 100% | Full name |
| Initial expansion | 95% | Full name |
| Abbreviation | 90% | Full name |
| Reversed order | 90% | Full name |
| Last name match | 90% | Indirect |
| First name match | 85% | Indirect |
| Spelling variation | 85% | Full name |

**Minimum**: 85% confidence required for linking

## Document Detection

### Death Certificate
```
Keywords: "DEATH" + "CERTIFICATE"
Extracts: Deceased, Surviving Spouse, Informant, Address, Date
```

### Marriage Certificate
```
Keywords: "MARRIAGE" + "CERTIFICATE"
Extracts: Bride, Groom, Witnesses, Address, Date
```

### Birth Certificate
```
Keywords: "BIRTH" + "CERTIFICATE"
Extracts: Child, Mother, Father, Address, Date
```

## Linking Logic

### Death Certificate
1. Extract surviving spouse name
2. Check if spouse matches any account holder
3. If match found → Link to that account
4. Extract informant name
5. Check if informant matches any account holder
6. If match found → Link to that account

### Marriage Certificate
1. Extract bride name
2. Check if bride matches any account holder
3. If match found → Link to that account
4. Extract groom name
5. Check if groom matches any account holder
6. If match found → Link to that account

### Birth Certificate
1. Extract mother name
2. Check if mother matches any account holder
3. If match found → Link to that account
4. Extract father name
5. Check if father matches any account holder
6. If match found → Link to that account

## Use Cases

### Estate Settlement
Death certificate automatically linked to deceased's account for estate settlement.

### Name Change Documentation
Marriage certificate automatically linked to account for name change documentation.

### Family Relationship Verification
Birth certificate automatically linked to parent's account for relationship verification.

### Account Consolidation
Family documents help identify related accounts for consolidation.

## Logging

The system logs all family document matching:

```
[DOCUMENT_ANALYSIS] Category: FAMILY DOCUMENT (death_certificate)
[DOCUMENT_ANALYSIS] Extracted info: {...}
[DOCUMENT_ANALYSIS] Found family member matches: ['0210630620']
[DOCUMENT_ANALYSIS] Associated page 5 with account 0210630620 (family member match)
```

## Troubleshooting

### Family Document Not Linked
- Verify family member name matches account holder (85%+ confidence)
- Check document contains clear family member information
- Review logs for extraction details

### Incorrect Linking
- Check confidence scores in logs
- Verify family member names are correctly extracted
- Look for name variations or spelling differences

## Benefits

✓ Automatic linking without manual intervention
✓ Maintains family relationship records
✓ Handles name variations and formatting
✓ Supports multiple document types
✓ Accurate with confidence scoring
✓ Fully auditable

## Status

✅ **Enabled by default**
✅ **No configuration required**
✅ **Ready for production**

---

**Last Updated**: December 16, 2025
