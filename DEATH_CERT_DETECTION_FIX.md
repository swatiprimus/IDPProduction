# Death Certificate Detection & Field Naming Fix

## Problems Fixed

### Problem 1: Death Certificate Misidentified
Death certificates were being misidentified as "invoice" or "withdrawal form" instead of "death_certificate".

### Problem 2: Wrong Field Names
Handwritten account numbers were being extracted as "Reference_Number" instead of "Account_Number".

## Root Causes

### Issue 1: Weak Detection Logic
The quick scan only looked for exact matches like:
- "CERTIFICATE" AND "DEATH" on first page
- But many death certificates don't have both words clearly visible on page 1

### Issue 2: Ambiguous Prompt
The extraction prompt wasn't explicit enough about field naming for handwritten numbers on certificates.

## Solutions Implemented

### Fix 1: Aggressive Certificate Detection
Added multiple detection patterns to catch death certificates:

**BEFORE (Weak):**
```python
is_certificate = (
    ("CERTIFICATE" in text or "CERTIFICATION" in text) and
    ("DEATH" in text or "BIRTH" in text)
)
```

**AFTER (Strong):**
```python
is_certificate = (
    # Standard indicators
    (("CERTIFICATE" or "CERTIFICATION") and ("DEATH" or "BIRTH" or "MARRIAGE")) or
    # Death-specific indicators
    ("DECEASED" in text) or
    ("DECEDENT" in text) or
    ("CAUSE OF DEATH" in text) or
    ("DATE OF DEATH" in text) or
    ("PLACE OF DEATH" in text) or
    ("REGISTRAR" and "DEATH" in text) or
    # Birth-specific
    ("DATE OF BIRTH" and "PLACE OF BIRTH" in text) or
    # Marriage-specific
    ("BRIDE" and "GROOM" in text) or
    # Generic vital records
    ("VITAL STATISTICS" in text) or
    ("STATE FILE NUMBER" and ("DELAWARE" or "PENNSYLVANIA") in text)
)
```

### Fix 2: Explicit Field Naming Rules
Updated the extraction prompt with crystal-clear instructions:

**BEFORE (Ambiguous):**
```
- The main certificate number MUST be extracted as "account_number"
- DO NOT use "certificate_number"
```

**AFTER (Explicit):**
```
CRITICAL NAMING FOR DEATH CERTIFICATES AND VITAL RECORDS:
- ANY handwritten number on the certificate MUST be extracted as "Account_Number"
- DO NOT use "Reference_Number", "Certificate_Number", or any other name
- ALWAYS use "Account_Number" for handwritten numbers
- Examples:
  * Handwritten "468431466" → Account_Number: "468431466"
  * Handwritten "4630" → Account_Number: "4630"
  * Handwritten "85333" → Account_Number: "85333"
- If MULTIPLE handwritten numbers, use Account_Number, Account_Number_2, Account_Number_3
- NEVER use "Reference_Number" for handwritten numbers on certificates
```

## Detection Patterns Added

### Death Certificates Now Detected By:
- ✅ "DECEASED" or "DECEDENT" (person status)
- ✅ "CAUSE OF DEATH" (field label)
- ✅ "DATE OF DEATH" (field label)
- ✅ "PLACE OF DEATH" (field label)
- ✅ "REGISTRAR" + "DEATH" (official + type)
- ✅ "VITAL STATISTICS" (department)
- ✅ "STATE FILE NUMBER" + state name (vital records)
- ✅ Standard "CERTIFICATE" + "DEATH" (original pattern)

### Birth Certificates Now Detected By:
- ✅ "DATE OF BIRTH" + "PLACE OF BIRTH" (both fields)
- ✅ "CERTIFICATE" + "BIRTH"

### Marriage Certificates Now Detected By:
- ✅ "BRIDE" + "GROOM" (both parties)
- ✅ "CERTIFICATE" + "MARRIAGE"

## Files Modified
- `app_modular.py` - Enhanced detection + explicit field naming
- `universal_idp.py` - Enhanced detection + explicit field naming

## Expected Results

### Document Type Detection
**BEFORE:**
- Upload death certificate → Detected as "invoice" or "withdrawal_form" ❌

**AFTER:**
- Upload death certificate → Detected as "certificate" ✅
- Shows "OPTIMIZATION: Detected certificate - will skip full OCR"

### Field Extraction
**BEFORE:**
- Handwritten "4630" → Reference_Number: "4630" ❌
- Handwritten "85333" → Reference_Number: "85333" ❌

**AFTER:**
- Handwritten "4630" → Account_Number: "4630" ✅
- Handwritten "85333" → Account_Number_2: "85333" ✅

## Testing Instructions

### Test 1: Document Type Detection
1. Upload a death certificate
2. Check console logs for: "[INFO] OPTIMIZATION: Detected certificate"
3. ✅ Should NOT say "invoice" or "withdrawal_form"

### Test 2: Field Naming
1. Upload death certificate with handwritten numbers
2. Click on page with handwritten numbers
3. Check extracted fields
4. ✅ Should show "Account_Number" not "Reference_Number"

### Test 3: Multiple Handwritten Numbers
1. Upload death certificate with multiple handwritten numbers
2. Check extracted fields
3. ✅ Should show "Account_Number", "Account_Number_2", etc.

## Important Notes
- Detection happens during upload (quick scan of first page)
- Field extraction happens when viewing pages
- Multiple handwritten numbers are numbered sequentially
- The word "Reference" should NEVER appear for certificate numbers
