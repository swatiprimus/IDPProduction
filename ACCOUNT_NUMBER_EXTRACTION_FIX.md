# Account Number Extraction Fix

## Problem
When viewing a single page from a loan document, the system was extracting ALL account numbers visible on the page, including:
- The primary account number from the main form (correct)
- Account numbers from summary lists in sidebars (incorrect)
- Account numbers from reference sections (incorrect)

### Example Issue:
On a page with:
- **Primary Account**: 0210091691 (in the main form header)
- **Summary List**: "Account Numbers: 0210091691, 0469168561, 0210715637, 0211029293..." (in sidebar)

The AI was extracting ALL numbers from the summary list instead of just the primary account number.

## Root Cause
The AI prompts (`get_loan_document_prompt()` and `get_comprehensive_extraction_prompt()`) were instructed to extract "ALL" account numbers without distinguishing between:
1. The PRIMARY account number (the one the page is about)
2. Reference lists of other account numbers

## Solution
Updated both prompts to include explicit instructions:

### Added to Prompts:
```
**CRITICAL FOR ACCOUNT NUMBER**: 
  * Extract ONLY the PRIMARY account number from the main form/header (usually labeled "ACCOUNT NUMBER:" at the top)
  * DO NOT extract account numbers from summary lists, sidebars, or reference sections
  * If you see a list of multiple account numbers (like "Account Numbers: 123, 456, 789"), IGNORE IT
  * Only extract the single account number that this specific page is about
  * The primary account number is typically at the top of the form in a field labeled "ACCOUNT NUMBER"
```

## Files Modified
- `universal_idp.py`:
  - Updated `get_loan_document_prompt()` (line ~500)
  - Updated `get_comprehensive_extraction_prompt()` (line ~290)

## Testing
1. Open a document with multiple pages
2. Navigate to a page that has:
   - A primary account number in the form header
   - A list of account numbers in a sidebar/summary section
3. The extracted data should now show ONLY the primary account number
4. The summary list should be ignored

## Expected Behavior
✅ Extract: Primary account number from "ACCOUNT NUMBER: 0210091691" field
❌ Ignore: Account numbers from "Account Numbers: 0210091691, 0469168561, 0210715637..." list

## Benefits
- More accurate data extraction
- Cleaner output with only relevant account information
- Prevents confusion from seeing multiple unrelated account numbers
- Better alignment with user expectations (one page = one account)
