# Family Document Matching

## Overview

The document analyzer now automatically links family documents (death certificates, marriage certificates, birth certificates) to accounts when they mention family members of account holders.

## Supported Document Types

### 1. Death Certificates
- Extracts: Deceased name, surviving spouse, informant, address, date of death
- Links to accounts where: Surviving spouse or informant matches an account holder

### 2. Marriage Certificates
- Extracts: Bride/groom names, witness names, address, date of marriage
- Links to accounts where: Either spouse matches an account holder

### 3. Birth Certificates
- Extracts: Child name, parent names, address, date of birth
- Links to accounts where: Either parent matches an account holder

## Matching Logic

### Step 1: Document Detection
The system identifies family documents by looking for keywords:
- Death Certificate: "DEATH" + "CERTIFICATE"
- Marriage Certificate: "MARRIAGE" + "CERTIFICATE"
- Birth Certificate: "BIRTH" + "CERTIFICATE"

### Step 2: Information Extraction
For each document type, the system extracts:

**Death Certificate:**
- Deceased person's name
- Surviving spouse name
- Informant name (person reporting death)
- Address on certificate
- Date of death

**Marriage Certificate:**
- Bride name
- Groom name
- Witness names
- Address
- Date of marriage

**Birth Certificate:**
- Child name
- Father name
- Mother name
- Address
- Date of birth

### Step 3: Family Member Matching (Multi-Strategy)

The system uses three matching strategies in order of priority:

#### Strategy 1: Full Name Matching (Highest Confidence)
- Uses flexible name matching on complete names
- Handles abbreviations, reversals, spelling variations
- Confidence: 85-100%
- Example: "Rahmah A Gooba" matches "RAHMAH ABDULLA GOOBA"

#### Strategy 2: Last Name Only Matching (Indirect)
- Matches only the last name component
- Useful when first/middle names differ
- Confidence: 85-90%
- Example: "Jane Smith" matches "Jane Jones" (both have "Smith" as last name)

#### Strategy 3: First Name Only Matching (Indirect)
- Matches only the first name component
- Useful for partial name information
- Confidence: 85%
- Example: "John Smith" matches "John Jones" (both have "John" as first name)

### Step 4: Confidence Scoring
Uses flexible name matching confidence scores:
- 100%: Exact match (full name)
- 95%: Initial expansion (full name)
- 90%: Last name match (indirect)
- 90%: Abbreviation or reversed order (full name)
- 85%: First name match (indirect)
- 85%: Spelling variation (full name)

**Minimum threshold**: 85% confidence required for linking

## Examples

### Example 1: Death Certificate - Surviving Spouse
```
Account Holder: "Rahmah A Gooba"
Death Certificate Contains: "Surviving Spouse: RAHMAH ABDULLA GOOBA"
Result: ✓ LINKED (95% confidence)
Reason: Surviving spouse name matches account holder
```

### Example 2: Death Certificate - Informant
```
Account Holder: "John Smith"
Death Certificate Contains: "Informant: JOHN SMITH"
Result: ✓ LINKED (100% confidence)
Reason: Informant name matches account holder
```

### Example 3: Marriage Certificate - Bride
```
Account Holder: "Jennifer Frederick"
Marriage Certificate Contains: "Bride: JENNIFER FREDERICK"
Result: ✓ LINKED (100% confidence)
Reason: Bride name matches account holder
```

### Example 4: Birth Certificate - Mother
```
Account Holder: "Mary Johnson"
Birth Certificate Contains: "Mother: MARY JOHNSON"
Result: ✓ LINKED (100% confidence)
Reason: Mother name matches account holder
```

### Example 5: Indirect Matching - Last Name Only
```
Account Holder: "Jane Smith"
Death Certificate Contains: "Surviving Spouse: Jane Johnson"
Result: ✓ LINKED (90% confidence)
Reason: Last name "Smith" matches (indirect matching)
```

### Example 6: Indirect Matching - First Name Only
```
Account Holder: "John Smith"
Death Certificate Contains: "Informant: John Johnson"
Result: ✓ LINKED (85% confidence)
Reason: First name "John" matches (indirect matching)
```

### Example 7: No Match
```
Account Holder: "Rahmah Gooba"
Death Certificate Contains: "Deceased: John Smith"
                           "Surviving Spouse: Jane Smith"
Result: ✗ NOT LINKED (0% confidence)
Reason: No family members match any account holders
```

## Implementation Details

### Functions Added

#### `extract_family_document_info(page_text)`
Extracts information from family documents.

**Returns:**
```python
{
    "document_type": "death_certificate|marriage_certificate|birth_certificate",
    "deceased_name": "...",
    "surviving_spouse": "...",
    "informant_name": "...",
    "address": "...",
    "date": "..."
}
```

#### `match_family_member_to_accounts(family_info, all_account_holders)`
Matches extracted family members to account holders.

**Parameters:**
- `family_info`: Dict with extracted family document information
- `all_account_holders`: List of all account holders with their info

**Returns:**
- List of matching account numbers

### Integration with Analyze Function

The family document matching is integrated into the document analysis workflow:

1. **Direct Pages**: Account number found → Link directly
2. **Holder Pages**: Account holder name/SSN found → Link to all their accounts
3. **Family Pages**: Family member found → Link to accounts where that person is a holder
4. **Unassociated Pages**: No matches found → Flag for manual review

## Matching Rules

### Rule 1: Surviving Spouse
If a death certificate mentions a surviving spouse, and that spouse's name matches an account holder, the document is linked to that account.

**Example:**
- Account: "Rahmah A Gooba"
- Death Certificate: "Surviving Spouse: RAHMAH ABDULLA GOOBA"
- Result: ✓ LINKED

### Rule 2: Informant
If a death certificate mentions an informant (person reporting the death), and that person's name matches an account holder, the document is linked to that account.

**Example:**
- Account: "John Smith"
- Death Certificate: "Informant: JOHN SMITH"
- Result: ✓ LINKED

### Rule 3: Spouse in Marriage Certificate
If a marriage certificate mentions a spouse, and that spouse's name matches an account holder, the document is linked to that account.

**Example:**
- Account: "Jennifer Frederick"
- Marriage Certificate: "Bride: JENNIFER FREDERICK"
- Result: ✓ LINKED

### Rule 4: Parent in Birth Certificate
If a birth certificate mentions a parent, and that parent's name matches an account holder, the document is linked to that account.

**Example:**
- Account: "Mary Johnson"
- Birth Certificate: "Mother: MARY JOHNSON"
- Result: ✓ LINKED

## Flexible Name Matching

Family document matching uses the same flexible name matching algorithm as holder matching:

✓ **Matches:**
- "Rahmah A Gooba" = "RAHMAH ABDULLA GOOBA" (initial expansion)
- "John Smith" = "JOHN SMITH" (case variation)
- "Jennifer Frederick" = "J Frederick" (abbreviation)
- "Mary Johnson" = "JOHNSON MARY" (reversed order)

✗ **No Match:**
- "Rahmah Gooba" ≠ "Ronald Honore" (different first name)
- "John Smith" ≠ "John Jones" (different last name)

## Confidence Scoring

| Match Type | Confidence | Example |
|-----------|-----------|---------|
| Exact match | 100% | "John Smith" = "John Smith" |
| Initial expansion | 95% | "A" = "Abdulla" |
| Abbreviation | 90% | "J Smith" = "John Smith" |
| Reversed order | 90% | "Smith John" = "John Smith" |
| Spelling variation | 85% | "Rahmha" = "Rahmah" |

**Minimum threshold**: 85% confidence required

## Document Classification

Family documents are classified as:
- **Death Certificate**: "DEATH" + "CERTIFICATE"
- **Marriage Certificate**: "MARRIAGE" + "CERTIFICATE"
- **Birth Certificate**: "BIRTH" + "CERTIFICATE"

## Logging

The system logs all family document matching activities:

```
[DOCUMENT_ANALYSIS] Category: FAMILY DOCUMENT (death_certificate)
[DOCUMENT_ANALYSIS] Extracted info: {'document_type': 'death_certificate', 'deceased_name': 'JOHN SMITH', 'surviving_spouse': 'JANE SMITH', ...}
[DOCUMENT_ANALYSIS] Found family member matches: ['0210630620']
[DOCUMENT_ANALYSIS] Associated page 5 with account 0210630620 (family member match)
```

## Use Cases

### Use Case 1: Estate Settlement
When an account holder passes away, their death certificate is automatically linked to their account, helping with estate settlement and account closure procedures.

### Use Case 2: Name Change After Marriage
When an account holder gets married, their marriage certificate is automatically linked to their account, documenting the name change.

### Use Case 3: Account Holder Verification
When opening a new account, birth certificates of family members can be automatically linked to verify family relationships.

### Use Case 4: Account Consolidation
When consolidating accounts for a family, family documents help identify related accounts and family members.

## Benefits

✓ **Automatic Linking**: Family documents automatically linked without manual intervention
✓ **Relationship Tracking**: Maintains clear record of family relationships
✓ **Flexible Matching**: Handles name variations and formatting differences
✓ **Comprehensive**: Supports death, marriage, and birth certificates
✓ **Accurate**: Uses flexible name matching with confidence scoring
✓ **Auditable**: Logs all matching decisions for compliance

## Limitations

- Requires clear extraction of family member names from documents
- Relies on flexible name matching (85%+ confidence threshold)
- May not match if names are significantly different or misspelled
- Requires OCR for scanned documents

## Future Enhancements

- Support for divorce decrees
- Support for adoption certificates
- Support for guardianship documents
- Address matching for additional verification
- Date correlation with account opening/changes
- Machine learning for confidence scoring

## Testing

To test family document matching:

1. Upload a document containing a death certificate
2. Ensure the death certificate mentions a surviving spouse or informant
3. Verify that the spouse/informant name matches an account holder
4. Click "Analyze"
5. Check that the death certificate page is linked to the correct account

## Configuration

Family document matching is enabled by default. No configuration required.

## Troubleshooting

### Family Document Not Linked
- Check that family member name matches account holder name (85%+ confidence)
- Verify document contains clear family member information
- Check logs for extraction and matching details

### Incorrect Linking
- Review confidence scores in logs
- Verify family member names are correctly extracted
- Check for name variations or spelling differences

---

**Implementation Date**: December 16, 2025
**Status**: ✅ Complete and Ready for Testing
