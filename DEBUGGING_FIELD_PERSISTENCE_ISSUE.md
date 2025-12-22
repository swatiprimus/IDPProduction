# Debugging Field Persistence Issue - Complete Guide

## Issue
User added field "1234" on Page 2 of a newly uploaded document, but after refresh the field is not showing.

## Solution Implemented
Added comprehensive logging to both frontend and backend to help diagnose where the issue is occurring.

## Frontend Logging Added

### In `addNewField()` function (templates/unified_page_viewer.html)
```javascript
console.log('=== ADD NEW FIELD DEBUG ===');
console.log('fieldName:', fieldName);
console.log('fieldValue:', fieldValue);
console.log('currentPageIndex:', currentPageIndex);
console.log('documentId:', documentId);
console.log('dataToSave keys:', Object.keys(dataToSave));
console.log('New field in dataToSave?', fieldName in dataToSave);
console.log('API URL:', `/api/document/${documentId}/page/${currentPageIndex + 1}/update`);
console.log('Save response status:', response.status);
console.log('Save response:', result);
console.log('New field in response?', fieldName in (result.data || {}));
```

### In `renderPageData()` function (templates/unified_page_viewer.html)
```javascript
console.log('=== RENDER PAGE DATA DEBUG ===');
console.log('currentPageIndex:', currentPageIndex);
console.log('API URL:', apiUrl);
console.log('Fetch response status:', response.status);
console.log('Fetch response:', result);
console.log('Cache source:', result.cache_source || result.source || 'unknown');
console.log('Data keys:', Object.keys(result.extracted_fields || result.data || {}));
console.log('Fields received:', fields);
```

## How to Use the Logging

### Step 1: Reproduce the Issue
1. Open the application
2. Upload a new document
3. Go to Page 2
4. Click "Add Field"
5. Enter: Name = "1234", Value = "test"
6. Click "Add"

### Step 2: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for logs starting with `=== ADD NEW FIELD DEBUG ===`
4. Check if field is in `dataToSave`
5. Check if field is in response

### Step 3: Check Server Logs
1. Look for logs like:
   ```
   [INFO] Updating regular cache: page_data/{doc_id}/page_1.json
   [INFO] VERIFIED: Cache contains X fields
   ```
2. Check if field "1234" is in the list of fields

### Step 4: Refresh and Check Again
1. Refresh the page
2. Look for logs starting with `=== RENDER PAGE DATA DEBUG ===`
3. Check if cache is being retrieved
4. Check if field "1234" is in the retrieved data

## Expected Logs

### Successful Add (Browser Console)
```
=== ADD NEW FIELD DEBUG ===
fieldName: 1234
fieldValue: test
currentPageIndex: 1
documentId: 3271403d63af
dataToSave keys: (30) ['Bank_Name', 'Form_Name', 'Customer_Name', ..., '1234']
New field in dataToSave? true
API URL: /api/document/3271403d63af/page/2/update
Save response status: 200
Save response: {success: true, data: {...}, verified: true, cache_key: 'page_data/3271403d63af/page_1.json'}
New field in response? true
Calling renderPageData()...
```

### Successful Retrieval (Browser Console)
```
=== RENDER PAGE DATA DEBUG ===
currentPageIndex: 1
API URL: /api/document/3271403d63af/page/2/extract
Fetch response status: 200
Fetch response: {success: true, data: {...}, cached: true, cache_source: 's3_user_edits'}
Cache source: s3_user_edits
Data keys: (30) ['Bank_Name', 'Form_Name', 'Customer_Name', ..., '1234']
Fields received: {Bank_Name: {...}, Form_Name: {...}, ..., 1234: {...}}
```

### Successful Save (Server Logs)
```
[INFO] Updating regular cache: page_data/3271403d63af/page_1.json (page_num: 2 → 0-based: 1)
[INFO] Saved to S3: page_data/3271403d63af/page_1.json
[INFO] VERIFIED: Cache contains 30 fields
[INFO] Total fields in response: 30
[INFO] All fields: ['Bank_Name', 'Form_Name', 'Customer_Name', ..., '1234']
```

### Successful Retrieval (Server Logs)
```
[DEBUG] Checking S3 cache: page_data/3271403d63af/page_1.json
[DEBUG] Found cached data in S3
[DEBUG] Applied flattening to cached data
```

## Troubleshooting Based on Logs

### If field NOT in dataToSave
**Problem**: Field not being added to the save request
**Check**: Is `currentPageData` being updated?
**Solution**: Verify that `currentPageData[fieldName] = {...}` is being executed

### If field NOT in response
**Problem**: Backend not including field in response
**Check**: Are there backend errors?
**Solution**: Check server logs for `[ERROR]` messages

### If cache NOT being checked
**Problem**: Retrieval not checking S3 cache
**Check**: Do you see `[DEBUG] Checking S3 cache:` in server logs?
**Solution**: Verify that `/extract` endpoint is checking cache

### If cache key MISMATCH
**Problem**: Save and retrieval using different cache keys
**Check**: Compare cache keys in logs
**Solution**: Ensure both use `page_data/{doc_id}/page_{page_num-1}.json`

### If field NOT persisting after refresh
**Problem**: Field saved but not retrieved
**Check**: Is cache being retrieved?
**Solution**: Check if field is in retrieved data

## Document Information

- **Document ID**: 3271403d63af
- **Document Type**: Regular (non-account-based)
- **Page Number**: 2 (1-based from UI)
- **Page Index**: 1 (0-based internally)
- **Cache Key**: `page_data/3271403d63af/page_1.json`
- **Field Added**: "1234"

## Next Steps

1. **Reproduce the issue** with the logging in place
2. **Collect the logs** from browser console and server
3. **Analyze the logs** to identify where the issue is
4. **Report the findings** with the logs
5. **Implement the fix** based on the findings

## Files Modified

- `templates/unified_page_viewer.html`:
  - Added logging to `addNewField()` function
  - Added logging to `renderPageData()` function

## How to Disable Logging

Once the issue is fixed, you can remove the logging by:
1. Removing all `console.log()` statements
2. Or wrapping them in a debug flag:
   ```javascript
   const DEBUG = false;
   if (DEBUG) console.log(...);
   ```

## Summary

The logging has been added to help diagnose where the field persistence issue is occurring. By following the steps above and checking the logs, you should be able to identify whether the problem is:
1. In the frontend (field not being sent)
2. In the backend save (field not being saved to cache)
3. In the backend retrieval (field not being retrieved from cache)
4. In the cache itself (field not being stored in S3)

Once you identify where the issue is, the fix can be targeted accordingly.
