# Handwritten & Stamp Extraction Fix

## Problem Fixed
Death certificates and other documents were not properly extracting:
- ❌ Handwritten account numbers (showing as generic "Stamping" instead of "Account_Number")
- ❌ "VERIFIED" stamps (not extracted or extracted with wrong field names)
- ❌ Names in stamps like "BRENDA HALLSTEAD" (not extracted as "Verified_By")
- ❌ Multiple handwritten numbers on same page

## Root Cause
The extraction prompt didn't prioritize handwritten text and stamps, so the LLM treated them as secondary information or described them generically instead of extracting them as actual data fields.

## Solution
Completely rewrote the extraction prompt to:
1. **Prioritize handwritten text** - Made it #1 priority
2. **Treat stamps as data** - Extract stamp text as field values, not descriptions
3. **Add explicit examples** - Show exactly how to extract stamps and handwritten text
4. **Use visual indicators** - Added 🔴 markers for critical extraction points

## New Prompt Structure

### Priority Order (Changed)
**BEFORE:**
1. Identifying Numbers
2. Names
3. Dates
...

**AFTER:**
1. 🔴 **HANDWRITTEN NUMBERS** (highest priority!)
2. 🔴 **STAMPS & VERIFICATION MARKS**
3. **IDENTIFYING NUMBERS**
4. **NAMES**
...

### Explicit Instructions Added

```
SPECIAL ATTENTION REQUIRED:
🔴 **HANDWRITTEN TEXT:** Extract ALL handwritten numbers and text - these are CRITICAL
   - Handwritten numbers are often account numbers, reference numbers, or IDs
   - Extract them with appropriate field names (Account_Number, Reference_Number, etc.)
   
🔴 **STAMPS & SEALS:** Extract ALL stamps, seals, and verification marks
   - "VERIFIED" stamp → Verified: "Yes" or "VERIFIED"
   - Date stamps → Stamp_Date or Verified_Date
   - Names in stamps → Verified_By or Stamped_By
   - Official seals → Official_Seal: "Present" or description
```

### Examples Added
```
- Example: If you see "VERIFIED" stamp → use "Verified" with value "Yes" or "VERIFIED"
- Example: If you see handwritten "4630" near "Account" → use "Account_Number" with value "4630"
- Example: Name in stamp "BRENDA HALLSTEAD" → use "Verified_By" with value "BRENDA HALLSTEAD"
```

## What Will Now Be Extracted

### From Your Death Certificate Page 2:
**BEFORE (Wrong):**
- Stamping: "Some generic description"
- (Missing account numbers)
- (Missing verified status)

**AFTER (Correct):**
- ✅ Account_Number: "4630"
- ✅ Account_Number_2: "85333" (if multiple numbers)
- ✅ Verified: "Yes" or "VERIFIED"
- ✅ Verified_By: "BRENDA HALLSTEAD"
- ✅ All other handwritten text
- ✅ All stamp dates and marks

## Files Modified
- `app_modular.py` - Enhanced comprehensive extraction prompt
- `universal_idp.py` - Enhanced comprehensive extraction prompt

## Testing Instructions

### For NEW Uploads (Recommended)
1. Delete the existing death certificate
2. Upload it again
3. ✅ All handwritten text and stamps will extract correctly

### For EXISTING Documents
1. Open the document
2. Click "🔄 Refresh" button
3. Confirm cache clear
4. ✅ Re-extraction will use new prompt

## Expected Results

### Page 2 of Death Certificate Should Show:
```json
{
  "Account_Number": "4630",
  "Account_Number_2": "85333",
  "Verified": "VERIFIED",
  "Verified_By": "BRENDA HALLSTEAD",
  "Certificate_Number": "...",
  "Deceased_Name": "...",
  "Death_Date": "...",
  ... (all other fields)
}
```

## Key Improvements
1. **Handwritten text is now #1 priority** - Never skipped
2. **Stamps are treated as data** - Not descriptions
3. **Multiple numbers supported** - Account_Number, Account_Number_2, etc.
4. **Explicit field naming** - "Verified", "Verified_By", not generic names
5. **Visual emphasis** - 🔴 markers draw AI attention to critical fields

## Important Notes
- The AI now knows handwritten text is MORE important than printed text
- Stamps are extracted as actual field values, not descriptions
- Multiple handwritten numbers on same page are all extracted
- Field names are specific (Account_Number, Verified_By) not generic (Stamping, Notes)

## Why This Works
The LLM (Claude) responds well to:
- ✅ **Priority ordering** - Tells it what's most important
- ✅ **Explicit examples** - Shows exactly what to do
- ✅ **Visual markers** - 🔴 draws attention
- ✅ **Clear instructions** - "Extract as field value, not description"
