# Fix: Field Not Persisting After Save

## Root Cause Found

The `addNewField()` function in `unified_page_viewer.html` is correctly:
1. Preparing data with all fields + new field
2. Sending POST to `/api/document/{doc_id}/page/{currentPageIndex + 1}/update`
3. Calling `renderPageData()` to refresh

However, there might be an issue with:
1. **Cache key mismatch** between save and retrieval
2. **Page number conversion** (1-based vs 0-based)
3. **Response data structure** not matching what frontend expects

## Solution: Add Comprehensive Logging

### Step 1: Add Logging to Frontend (addNewField)

Add this logging to `addNewField()` function in `templates/unified_page_viewer.html`:

```javascript
async function addNewField() {
    const fieldName = document.getElementById('newFieldName').value.trim();
    const fieldValue = document.getElementById('newFieldValue').value.trim();
    
    console.log('=== ADD NEW FIELD DEBUG ===');
    console.log('fieldName:', fieldName);
    console.log('fieldValue:', fieldValue);
    console.log('currentPageIndex:', currentPageIndex);
    console.log('documentId:', documentId);
    
    if (!fieldName) {
        showNotification('Please enter a field name', 'error');
        return;
    }
    
    if (!fieldValue) {
        showNotification('Please enter a field value', 'error');
        return;
    }
    
    if (currentPageData && currentPageData[fieldName]) {
        if (!confirm(`Field "${fieldName}" already exists. Do you want to overwrite it?`)) {
            return;
        }
    }
    
    try {
        if (!currentPageData) {
            currentPageData = {};
        }
        
        const dataToSave = {};
        for (const [key, value] of Object.entries(currentPageData)) {
            dataToSave[key] = value;
        }
        
        dataToSave[fieldName] = {
            value: fieldValue,
            confidence: 100,
            source: 'human'
        };
        
        currentPageData = dataToSave;
        
        console.log('dataToSave keys:', Object.keys(dataToSave));
        console.log('New field in dataToSave?', fieldName in dataToSave);
        console.log('API URL:', `/api/document/${documentId}/page/${currentPageIndex + 1}/update`);
        
        const response = await fetch(`/api/document/${documentId}/page/${currentPageIndex + 1}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_data: dataToSave
            })
        });
        
        const result = await response.json();
        console.log('Save response status:', response.status);
        console.log('Save response:', result);
        console.log('New field in response?', fieldName in (result.data || {}));
        
        if (!result.success) {
            throw new Error(result.message);
        }
        
        showNotification(`Field "${fieldName}" added successfully!`, 'success');
        closeAddFieldDialog();
        
        console.log('Calling renderPageData()...');
        renderPageData();
    } catch (error) {
        console.error('Error in addNewField:', error);
        showNotification('Failed to add field: ' + error.message, 'error');
    }
}
```

### Step 2: Add Logging to Frontend (renderPageData)

Add this logging to `renderPageData()` function:

```javascript
async function renderPageData() {
    const container = document.getElementById('dataContent');
    
    const metaText = hasAccounts && currentAccountIndex >= 0 
        ? `Account ${accounts[currentAccountIndex].accountNumber} - Page ${currentPageIndex + 1} - Loading...`
        : `Page ${currentPageIndex + 1} - Loading...`;
    document.getElementById('dataMeta').textContent = metaText;
    container.innerHTML = '<div class="loading"><div class="spinner"></div><div>Extracting data from page...</div></div>';
    
    try {
        let response, result;
        if (hasAccounts && currentAccountIndex >= 0) {
            response = await fetch(`/api/document/${documentId}/account/${currentAccountIndex}/page/${currentPageIndex}/data`);
        } else {
            const apiUrl = `/api/document/${documentId}/page/${currentPageIndex + 1}/extract`;
            console.log('=== RENDER PAGE DATA DEBUG ===');
            console.log('currentPageIndex:', currentPageIndex);
            console.log('API URL:', apiUrl);
            
            response = await fetch(apiUrl);
        }
        
        result = await response.json();
        console.log('Fetch response status:', response.status);
        console.log('Fetch response:', result);
        console.log('Cache source:', result.cache_source || result.source || 'unknown');
        console.log('Data keys:', Object.keys(result.extracted_fields || result.data || {}));
        
        if (result.success) {
            let fields = result.extracted_fields || result.data || {};
            console.log('Fields received:', fields);
            
            // ... rest of renderPageData function
        }
    } catch (error) {
        console.error('Error in renderPageData:', error);
        showNotification('Failed to load page data: ' + error.message, 'error');
    }
}
```

### Step 3: Check Backend Logs

When you add a field and save, look for these log messages:

**Save logs**:
```
[INFO] Updating regular cache: page_data/{doc_id}/page_{page_num-1}.json
[INFO] Saved to S3: page_data/{doc_id}/page_{page_num-1}.json
[INFO] VERIFIED: Cache contains X fields
[INFO] All fields: [...]
```

**Retrieval logs**:
```
[DEBUG] Checking S3 cache: page_data/{doc_id}/page_{page_num-1}.json
[DEBUG] Found cached data in S3
```

## Debugging Checklist

- [ ] Add logging to `addNewField()` function
- [ ] Add logging to `renderPageData()` function
- [ ] Add a new field and click "Add"
- [ ] Check browser console for logs
- [ ] Verify field is in `dataToSave`
- [ ] Verify field is in response
- [ ] Check server logs for save confirmation
- [ ] Refresh page
- [ ] Check browser console for retrieval logs
- [ ] Check server logs for cache retrieval
- [ ] Verify field appears after refresh

## Expected Logs

### Frontend Console (After Adding Field)
```
=== ADD NEW FIELD DEBUG ===
fieldName: 1234
fieldValue: test
currentPageIndex: 1
documentId: 3271403d63af
dataToSave keys: ['Bank_Name', 'Form_Name', ..., '1234']
New field in dataToSave? true
API URL: /api/document/3271403d63af/page/2/update
Save response status: 200
Save response: {success: true, data: {...}, verified: true}
New field in response? true
Calling renderPageData()...

=== RENDER PAGE DATA DEBUG ===
currentPageIndex: 1
API URL: /api/document/3271403d63af/page/2/extract
Fetch response status: 200
Fetch response: {success: true, data: {...}, cached: true}
Cache source: s3_user_edits
Data keys: ['Bank_Name', 'Form_Name', ..., '1234']
```

### Server Logs (After Adding Field)
```
[INFO] Updating regular cache: page_data/3271403d63af/page_1.json (page_num: 2 → 0-based: 1)
[INFO] Saved to S3: page_data/3271403d63af/page_1.json
[INFO] VERIFIED: Cache contains 30 fields
[INFO] All fields: ['Bank_Name', 'Form_Name', ..., '1234']
```

### Server Logs (After Refresh)
```
[DEBUG] Checking S3 cache: page_data/3271403d63af/page_1.json
[DEBUG] Found cached data in S3
[DEBUG] Applied flattening to cached data
```

## If Logs Show Problem

### If field not in dataToSave
- Problem: Field not being added to dataToSave
- Solution: Check if `currentPageData` is being updated correctly

### If field not in response
- Problem: Backend not including field in response
- Solution: Check backend logs for save errors

### If cache not being checked
- Problem: Retrieval not checking cache
- Solution: Verify cache key format matches between save and retrieval

### If cache key mismatch
- Problem: Save uses different key than retrieval
- Solution: Ensure both use `page_data/{doc_id}/page_{page_num-1}.json`

## Implementation

Replace the `addNewField()` function in `templates/unified_page_viewer.html` with the version that includes logging above.

Replace the `renderPageData()` function in `templates/unified_page_viewer.html` with the version that includes logging above.

## Testing

1. Open a document
2. Go to Page 2
3. Click "Add Field"
4. Enter: Name = "1234", Value = "test"
5. Click "Add"
6. Open browser console (F12)
7. Check logs
8. Refresh page
9. Check if field persists
10. Check logs again

## Expected Result

After implementing logging and testing:
- Field should appear in `dataToSave`
- Field should appear in response
- Field should appear in cache
- Field should persist after refresh

If field doesn't persist, logs will show where the problem is.
