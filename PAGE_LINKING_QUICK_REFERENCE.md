# Page Linking Quick Reference Card

## 5 Universal Rules for Linking Pages to Accounts

### Rule 1: Exact Account Number ✓
```
Page has: "Account Number: 0210630620"
Account: 0210630620
Result: ✓ LINK (100%)
```

### Rule 2: Exact SSN Match ✓
```
Page has: "SSN: 123-45-6789"
Account Holder SSN: 123456789
Result: ✓ LINK (100%)
Note: Format doesn't matter (123-45-6789 = 123456789)
```

### Rule 3: Name Match ✓
```
Account: "John Smith"
Page has: "JOHN SMITH" or "John A Smith" or "Smith John"
Result: ✓ LINK (85-100%)
```

**Name Matching Allowances:**
- ✓ Case: "JOHN" = "John" = "john"
- ✓ Middle: "John Smith" = "John A Smith"
- ✓ Reversed: "Smith John" = "John Smith"
- ✓ Spelling: "Rahmah" = "RAHMAHA" (1-2 letters)
- ✓ Abbreviation: "John Smith" = "J Smith"
- ✗ First/Last: "John Smith" ≠ "John Jones"

### Rule 4: Family Relationship ✓
```
Death Certificate: "Surviving Spouse: William Campbell"
Account: "William S Campbell"
Result: ✓ LINK (95%)
```

**Family Relationships:**
- Surviving spouse (death certificate)
- Informant (death certificate)
- Bride/Groom (marriage certificate)
- Parent (birth certificate)

### Rule 5: Address Match ✓
```
Page: "123 Main St, Anytown, PA 12345"
Account: "123 Main St, Anytown, PA 12345"
Result: ✓ LINK (90%)
```

---

## Confidence Levels

| Confidence | Meaning | Action |
|-----------|---------|--------|
| 100% | Definite match | LINK |
| 95% | Very likely | LINK |
| 90% | Likely | LINK |
| 85% | Possible | LINK |
| <85% | Unlikely | DO NOT LINK |

**Minimum**: 85% confidence required

---

## Name Matching Examples

| Stored | Page | Match? | Confidence |
|--------|------|--------|-----------|
| John Smith | JOHN SMITH | ✓ | 100% |
| John Smith | John A Smith | ✓ | 95% |
| John Smith | Smith John | ✓ | 90% |
| John Smith | J Smith | ✓ | 90% |
| John Smith | Jon Smith | ✓ | 85% |
| John Smith | John Jones | ✗ | 0% |
| John Smith | James Smith | ✗ | 0% |

---

## Quick Decision Tree

```
Does page have exact account number?
  YES → LINK (Rule 1, 100%)
  NO ↓

Does page have exact SSN match?
  YES → LINK (Rule 2, 100%)
  NO ↓

Does page have matching name?
  YES → LINK (Rule 3, 85-100%)
  NO ↓

Does page mention family member?
  YES → LINK (Rule 4, 85-100%)
  NO ↓

Does page have matching address?
  YES → LINK (Rule 5, 90%)
  NO ↓

NO MATCH → Flag for manual review
```

---

## Common Scenarios

### Scenario 1: Bank Statement
```
Page: "Account Holder: John Smith"
Account: "John Smith"
Result: ✓ LINK (100%)
Rule: Rule 3 (Name Match)
```

### Scenario 2: Death Certificate
```
Page: "Surviving Spouse: William Campbell"
Account: "William S Campbell"
Result: ✓ LINK (95%)
Rule: Rule 4 (Family Relationship)
```

### Scenario 3: Supporting Document
```
Page: "William Campbell"
Account: "William S Campbell"
Result: ✓ LINK (95%)
Rule: Rule 3 (Name Match - Middle Optional)
```

### Scenario 4: Abbreviated Name
```
Page: "J Smith"
Account: "John Smith"
Result: ✓ LINK (90%)
Rule: Rule 3 (Name Match - Abbreviation)
```

### Scenario 5: Reversed Name
```
Page: "Smith John"
Account: "John Smith"
Result: ✓ LINK (90%)
Rule: Rule 3 (Name Match - Reversed Order)
```

---

## What MUST Match

✓ **First Name** - MUST match (case-insensitive)
✓ **Last Name** - MUST match (case-insensitive)
✓ **Account Number** - MUST match exactly
✓ **SSN** - MUST match (format doesn't matter)

---

## What's OPTIONAL

✓ Middle name - Can be present or missing
✓ Middle initial - Can be initial or full name
✓ Case - Can be any case
✓ Punctuation - Can be present or missing
✓ Whitespace - Can be any amount
✓ Order - Can be normal or reversed

---

## What DOESN'T Match

✗ Different first names: "John" ≠ "James"
✗ Different last names: "Smith" ≠ "Jones"
✗ Too many spelling errors: "Jhn" ≠ "John"
✗ Completely different names: "John Smith" ≠ "Mary Johnson"

---

## Logging Template

```
[PAGE_LINKING] Page X:
  Extracted: [account#, SSN, names, etc.]
  Rule Applied: Rule Y (description)
  Accounts Matched: [list]
  Confidence: Z%
  Reason: [explanation]
```

---

## Key Reminders

1. **Apply ALL rules** to every page
2. **Link to ALL matching accounts** (not just first match)
3. **Record confidence scores** for each match
4. **Use 85% minimum** threshold
5. **Log everything** for audit trail
6. **Flag ambiguous cases** for manual review

---

**Quick Reference Version**: December 16, 2025
**Status**: ✅ Ready for Use
