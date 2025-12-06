# Signer Display Fix - Complete Guide

## What Was Fixed

The system was returning signers as nested objects instead of flat fields:

**Before (Wrong):**
```json
{
  "Signer1": {
    "Name": "John Doe",
    "SSN": "123-45-6789"
  }
}
```

**After (Correct):**
```json
{
  "Signer1_Name": "John Doe",
  "Signer1_SSN": "123-45-6789"
}
```

## How to See the Fix

### Option 1: Migrate Existing Cache (Recommended)
This updates your existing cached data without re-running OCR/LLM:

**In Browser Console (F12):**
```javascript
fetch('/api/document/YOUR_DOC_ID/migrate-cache', {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    console.log(d);
    location.reload(); // Refresh page
  });
```

Replace `YOUR_DOC_ID` with your actual document ID.

### Option 2: Clear Cache and Re-extract
This forces complete re-extraction with new prompts:

**In Browser Console:**
```javascript
fetch('/api/document/YOUR_DOC_ID/clear-cache', {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    console.log(d);
    location.reload(); // Refresh page
  });
```

### Option 3: Upload New Document
Just upload a new document - it will use the new code automatically.

## What Changed in the Code

### 1. Enhanced LLM Prompt
- Added explicit "WRONG FORMAT" vs "CORRECT FORMAT" examples
- Emphasized flat field naming: `Signer1_Name`, `Signer1_SSN`
- Added warning: "CRITICAL FOR SIGNERS - DO NOT USE NESTED OBJECTS"

### 2. Automatic Flattening Function
```python
def flatten_nested_objects(data):
    # Converts Signer1: {Name: "John"} -> Signer1_Name: "John"
```

Applied in 3 places:
- When extracting new data from LLM
- When loading cached data from S3
- When pre-caching pages

### 3. Cache Migration Endpoint
New endpoint: `/api/document/<doc_id>/migrate-cache`
- Reads existing cache
- Applies flattening
- Saves back to S3
- No re-extraction needed!

## Verification

### Check Console Logs
Look for these messages:
```
[DEBUG] Flattening signer object: Signer1 with 6 fields
[DEBUG] Created flat field: Signer1_Name = John Doe
[DEBUG] Created flat field: Signer1_SSN = 123-45-6789
[DEBUG] Applied flattening to cached data
```

### Check Browser Console
Look for:
```
Signer fields found: ["Signer1_Name", "Signer1_SSN", "Signer1_DateOfBirth", ...]
Displaying 2 signer groups
```

### Visual Check
You should now see:
```
┌─────────────────────────────────────┐
│ Signer 1 (6 fields)            ▼   │
├─────────────────────────────────────┤
│ Name: John Doe                      │
│ SSN: 123-45-6789                    │
│ Date Of Birth: 01/15/1980           │
│ Address: 123 Main St                │
│ Phone: (555) 123-4567               │
│ Drivers License: DL123456           │
└─────────────────────────────────────┘
```

## Troubleshooting

### Signers Still Not Showing?

1. **Check if data exists:**
   - Open browser console (F12)
   - Look for "Signer fields found: []"
   - If empty, the document may not have signer data

2. **Check field names:**
   - Look for "All field keys:" in console
   - Verify fields start with "Signer"

3. **Try migration:**
   ```javascript
   fetch('/api/document/YOUR_DOC_ID/migrate-cache', {method: 'POST'})
     .then(r => r.json())
     .then(d => console.log(d));
   ```

4. **Hard refresh:**
   - Press `Ctrl + Shift + R` (Windows)
   - Or `Cmd + Shift + R` (Mac)

5. **Clear browser cache:**
   - F12 → Network tab → Check "Disable cache"
   - Refresh page

### Still Having Issues?

Check the server logs for:
```
[DEBUG] Flattening signer object: Signer1 with X fields
```

If you don't see this, the LLM might not be returning signer data at all.

## API Endpoints

### Migrate Cache
```bash
POST /api/document/<doc_id>/migrate-cache
```
Updates existing cache with flattened data.

### Clear Cache
```bash
POST /api/document/<doc_id>/clear-cache
```
Deletes cache, forces re-extraction.

### Get Page Data
```bash
GET /api/document/<doc_id>/account/<account_index>/page/<page_num>/data
```
Returns page data (now automatically flattened).

## Benefits

1. **No Re-extraction Needed**: Migration updates cache in-place
2. **Automatic**: New extractions use correct format automatically
3. **Backward Compatible**: Old cache is automatically flattened when loaded
4. **Cost Effective**: No additional OCR/LLM calls needed

## Summary

- ✅ LLM prompt updated with clear examples
- ✅ Automatic flattening function added
- ✅ Applied to all data loading points
- ✅ Cache migration endpoint created
- ✅ Backward compatible with old cache

Your signers should now display correctly!
