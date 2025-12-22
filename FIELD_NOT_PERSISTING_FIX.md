# Field Not Persisting After Save - Root Cause and Fix

## Issue
User adds a new field on Page 2, clicks Save, but after refresh the field is gone.

## Root Cause Analysis

### Potential Cause 1: Frontend Not Sending Correct Data
**Issue**: The frontend might not be including the new field in the `page_data` sent to backend

**Check**:
```javascript
// In savePage() function
const dataToSave = {};

// Copy all existing fields
for (const [key, value] of Object.entries(currentPageData)) {
    dataToSave[key] = value;
}

// Update edited fields
for (const [fieldName, fieldValue] of Object.entries(editedFields)) {
    dataToSave[fieldName] = {
        value: fieldValue,
        confidence: 100,
        source: 'human'
    };
}

// Send to backend
fetch(`/api/document/${documentId}/page/${currentPageIndex + 1}/update`, {
    body: JSON.stringify({ page_data: dataToSave })
})
```

**Problem**: If `editedFields` is not being populated correctly, the new field won't be sent

**Solution**: Add logging to verify `editedFields` contains the new field

### Potential Cause 2: Backend Not Saving to Correct Cache Key
**Issue**: Backend might be saving to wrong cache key

**Check**:
- Frontend sends: `page_num = currentPageIndex + 1` (1-based)
- Backend receives: `page_num = 2` (for Page 2)
- Backend converts: `page_num_0based = page_num - 1 = 1`
- Backend saves to: `page_data/{doc_id}/page_1.json`

**Problem**: If conversion is wrong, cache is saved to wrong location

**Solution**: Verify cache key in server logs

### Potential Cause 3: Retrieval Not Checking Cache
**Issue**: After refresh, retrieval endpoint might not be checking cache

**Check**:
- Frontend calls: `/api/document/{doc_id}/page/{currentPageIndex + 1}/extract`
- Backend receives: `page_num = 2` (for Page 2)
- Backend converts: `page_num - 1 = 1`
- Backend checks: `page_data/{doc_id}/page_1.json`

**Problem**: If retrieval doesn't check cache, it will extract fresh data without the new field

**Solution**: Verify retrieval is checking cache in server logs

### Potential Cause 4: Cache Not Being Verified
**Issue**: Backend might not be verifying cache save was successful

**Check**:
- Backend saves to S3
- Backend tries to read back to verify
- If read fails, save might have failed silently

**Problem**: If verification fails, response might show "success": true but data wasn't actually saved

**Solution**: Check for verification errors in server logs

## Verification Steps

### Step 1: Check Frontend Logs
Add console logging to savePage():

```javascript
async function savePage() {
    console.log('=== SAVE PAGE DEBUG ===');
    console.log('currentPageIndex:', currentPageIndex);
    console.log('currentPageData:', currentPageData);
    console.log('editedFields:', editedFields);
    
    const dataToSave = {};
    for (const [key, value] of Object.entries(currentPageData)) {
        dataToSave[key] = value;
    }
    for (const [fieldName, fieldValue] of Object.entries(editedFields)) {
        dataToSave[fieldName] = {
            value: fieldValue,
            confidence: 100,
            source: 'human'
        };
    }
    
    console.log('dataToSave:', dataToSave);
    console.log('dataToSave keys:', Object.keys(dataToSave));
    console.log('New field in dataToSave?', '1234' in dataToSave);
    
    const response = await fetch(`/api/document/${documentId}/page/${currentPageIndex + 1}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_data: dataToSave })
    });
    
    const result = await response.json();
    console.log('Save response:', result);
    console.log('Response data keys:', Object.keys(result.data || {}));
    console.log('New field in response?', '1234' in (result.data || {}));
}
```

### Step 2: Check Backend Logs
Look for messages like:
```
[INFO] Updating regular cache: page_data/3271403d63af/page_1.json
[INFO] Saved to S3: page_data/3271403d63af/page_1.json
[INFO] VERIFIED: Cache contains 30 fields
[INFO] All fields: ['Bank_Name', 'Form_Name', ..., '1234']
```

### Step 3: Check Retrieval Logs
After refresh, look for:
```
[DEBUG] Checking S3 cache: page_data/3271403d63af/page_1.json
[DEBUG] Found cached data in S3
```

### Step 4: Verify Cache in S3
Check if cache file exists in S3:
- Bucket: (your S3 bucket)
- Key: `page_data/3271403d63af/page_1.json`
- Content should include the new field "1234"

## Likely Fix

The issue is probably that the frontend is not properly tracking the new field in `editedFields`. When you add a new field, it should be added to `editedFields` so that `savePage()` includes it in the save.

### Check the "Add Field" Function

Look for the function that adds a new field (probably `addNewField()` or similar):

```javascript
function addNewField() {
    const fieldName = document.getElementById('newFieldName').value;
    const fieldValue = document.getElementById('newFieldValue').value;
    
    if (!fieldName || !fieldValue) {
        showNotification('Please enter field name and value', 'error');
        return;
    }
    
    // CRITICAL: Add to editedFields so savePage() includes it
    editedFields[fieldName] = fieldValue;
    
    // Also add to currentPageData for display
    currentPageData[fieldName] = {
        value: fieldValue,
        confidence: 100,
        source: 'human'
    };
    
    // Re-render to show the new field
    renderPageData();
    
    // Close modal
    document.getElementById('addFieldModal').style.display = 'none';
}
```

**Problem**: If `editedFields[fieldName] = fieldValue` is not being called, the new field won't be saved

**Solution**: Ensure new fields are added to `editedFields`

## Implementation

### Fix 1: Ensure New Fields Are Added to editedFields
In the "Add Field" function, make sure to add the field to `editedFields`:

```javascript
editedFields[fieldName] = fieldValue;
```

### Fix 2: Add Logging to Verify
Add console logging to verify the field is being tracked:

```javascript
console.log('Added field to editedFields:', fieldName);
console.log('editedFields now contains:', Object.keys(editedFields));
```

### Fix 3: Verify Save Includes New Field
In `savePage()`, verify the new field is in `dataToSave`:

```javascript
console.log('New field in dataToSave?', fieldName in dataToSave);
```

## Testing

### Test 1: Add Field and Verify It's Tracked
1. Open document
2. Go to Page 2
3. Click "Add Field"
4. Enter: Name = "1234", Value = "test"
5. Click "Add"
6. Open browser console
7. Check if field appears in `currentPageData`
8. Check if field appears in `editedFields`

### Test 2: Save and Verify It's Sent
1. Click "Save"
2. Open browser console
3. Check if field appears in `dataToSave`
4. Check if field appears in response

### Test 3: Refresh and Verify It Persists
1. Refresh page
2. Check if field still appears
3. Check server logs for cache retrieval

## Expected Behavior After Fix

1. User adds field "1234" on Page 2
2. Field appears in `editedFields`
3. User clicks Save
4. Field is included in `dataToSave`
5. Backend saves to `page_data/3271403d63af/page_1.json`
6. Backend verifies save was successful
7. Backend returns response with field "1234"
8. Frontend shows success notification
9. User refreshes page
10. Backend retrieves from cache
11. Field "1234" appears on Page 2

## Summary

The issue is likely that new fields are not being properly added to `editedFields`, so they're not being sent to the backend for saving. The fix is to ensure that when a new field is added, it's added to `editedFields` so that `savePage()` includes it in the save request.
