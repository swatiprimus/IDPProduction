# Certificate Extraction Fix - All Fields on All Pages

## Problem Fixed
Death certificates and other certificates were not extracting all fields on all pages:
- Page 1: Missing some fields (e.g., "verified" status)
- Page 2: Missing account numbers
- Inconsistent field extraction across pages

## Root Cause
When we added the fast upload optimization, certificates were incorrectly treated as "loan documents" and went through the loan document processing path instead of the normal certificate extraction path.

### The Bug
```python
# OLD CODE (BUGGY)
if has_loan_indicators or is_certificate or is_drivers_license:
    is_loan_document = True  # ❌ WRONG! Certificates are NOT loan documents
    
# Later in code...
if doc_type_preview == "loan_document":
    result = process_loan_document(text, ...)  # ❌ Wrong path for certificates!
else:
    result = detect_and_extract_documents(text)  # ✅ Correct path for certificates
```

**Result:** Certificates went through `process_loan_document()` which:
- Looks for account numbers and splits by accounts
- Doesn't extract all certificate fields properly
- Causes missing fields on pages

## Solution Implemented
Separated the "skip upfront OCR" optimization from the document type detection.

### The Fix
```python
# NEW CODE (FIXED)
skip_upfront_ocr = False  # Flag for optimization only
actual_doc_type = None    # Track actual document type

if has_loan_indicators:
    skip_upfront_ocr = True
    actual_doc_type = "loan_document"  # ✅ Correctly identified
elif is_certificate:
    skip_upfront_ocr = True
    actual_doc_type = "certificate"    # ✅ Correctly identified
elif is_drivers_license:
    skip_upfront_ocr = True
    actual_doc_type = "drivers_license"  # ✅ Correctly identified

# Later in code...
if actual_doc_type == "loan_document":
    doc_type_preview = "loan_document"
else:
    doc_type_preview = detect_document_type(text)  # ✅ Proper detection

if doc_type_preview == "loan_document":
    result = process_loan_document(text, ...)  # Only for actual loan docs
else:
    result = detect_and_extract_documents(text)  # ✅ Certificates go here now!
```

## What Changed

### Before Fix
1. Certificate uploaded → Detected as certificate
2. Set `is_loan_document = True` (for optimization)
3. Skipped upfront OCR ✅ (good)
4. Processed as loan document ❌ (bad)
5. Missing fields on pages ❌

### After Fix
1. Certificate uploaded → Detected as certificate
2. Set `skip_upfront_ocr = True` (for optimization)
3. Set `actual_doc_type = "certificate"` (for routing)
4. Skipped upfront OCR ✅ (good)
5. Processed as certificate ✅ (good)
6. All fields extracted properly ✅

## Benefits
✅ **All fields extracted** - Every page gets full field extraction
✅ **Fast uploads maintained** - Still skip expensive upfront OCR
✅ **Correct processing path** - Certificates use certificate extraction logic
✅ **Consistent results** - Same fields on every page view

## Files Modified
- `app_modular.py` - Fixed document type routing
- `universal_idp.py` - Fixed document type routing

## Testing
Upload a death certificate and verify:
1. ✅ Upload is fast (2-5 seconds)
2. ✅ Page 1 shows all fields including verification status
3. ✅ Page 2 shows account number if present
4. ✅ All pages extract complete field sets
5. ✅ No missing fields across pages

## Technical Details

### Variables Introduced
- `skip_upfront_ocr` - Boolean flag for optimization (skip Textract during upload)
- `actual_doc_type` - String tracking actual document type ("loan_document", "certificate", "drivers_license")

### Processing Paths
- **Loan Documents** → `process_loan_document()` - Splits by accounts, extracts per account
- **Certificates** → `detect_and_extract_documents()` - Extracts all fields from full document
- **Driver's Licenses** → `detect_and_extract_documents()` - Extracts all fields from full document

### Optimization Maintained
All document types still benefit from:
- Fast PyMuPDF text extraction during upload
- Deferred OCR to page-level viewing
- Reduced AWS Textract costs
- 2-5 second upload times
