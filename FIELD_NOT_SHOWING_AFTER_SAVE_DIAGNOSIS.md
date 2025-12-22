# Field Not Showing After Save - Diagnosis Guide

## Issue Description
User added a new field "1234" on Page 2 of a newly uploaded document, but after refresh, the field is not showing on Page 2.

## Possible Causes

### 1. Save Request Not Being Sent
**Symptoms**:
- No `/update` endpoint call in server logs
- Field appears to save (success notification shown)
- But field doesn't persist after refresh

**Diagnosis**:
- Check browser console for errors
- Check if savePage() function is being called
- Check if the fetch request is being sent

**Solution**:
- Open browser DevTools (F12)
- Go to Network tab
- Add the field and click Save
- Look for POST request to `/api/document/.../page/.../update`
- If not present, there's a frontend issue

### 2. Save Request Sent But Cache Not Updated
**Symptoms**:
- `/update` endpoint called in server logs
- Response shows "success": true
- But field doesn't show after refresh

**Diagnosis**:
- Check server logs for cache save errors
- Check S3 permissions
- Check cache key format

**Solution**:
- Look for log messages like:
  - `[INFO] Updating regular cache: page_data/{doc_id}/page_1.json`
  - `[INFO] VERIFIED: Cache contains X fields`
- If verification fails, S3 save failed

### 3. Retrieval Not Checking Cache
**Symptoms**:
- Save works (verified in logs)
- But refresh doesn't show the field
- Cache exists in S3

**Diagnosis**:
- Check if `/extract` endpoint is checking cache
- Check if cache key format matches between save and retrieval

**Solution**:
- Look for log messages like:
  - `[DEBUG] Checking S3 cache: page_data/{doc_id}/page_1.json`
  - `[DEBUG] Found cached data in S3`
- If not present, retrieval is not checking cache

### 4. Page Number Mismatch
**Symptoms**:
- Save and retrieval using different page numbers
- Field saved to page_1.json but retrieved from page_2.json

**Diagnosis**:
- Check cache key in save logs
- Check cache key in retrieval logs
- Compare page numbers

**Solution**:
- Save should use: `page_data/{doc_id}/page_{page_num-1}.json`
- Retrieval should use: `page_data/{doc_id}/page_{page_num-1}.json`
- Both should convert 1-based to 0-based

## Step-by-Step Debugging

### Step 1: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Add a field and click Save
4. Look for any error messages
5. Check if savePage() is being called

### Step 2: Check Network Requests
1. Open browser DevTools (F12)
2. Go to Network tab
3. Add a field and click Save
4. Look for POST request to `/api/document/.../page/.../update`
5. Click on the request and check:
   - Request URL
   - Request body (should contain page_data)
   - Response status (should be 200)
   - Response body (should contain "success": true)

### Step 3: Check Server Logs
1. Look for log messages when you click Save
2. Should see messages like:
   ```
   [INFO] Updating regular cache: page_data/{doc_id}/page_1.json
   [INFO] Saved to S3: page_data/{doc_id}/page_1.json
   [INFO] VERIFIED: Cache contains X fields
   ```
3. If not present, save request didn't reach backend

### Step 4: Check Retrieval
1. After save, refresh the page
2. Look for GET request to `/api/document/.../page/.../extract`
3. Check server logs for:
   ```
   [DEBUG] Checking S3 cache: page_data/{doc_id}/page_1.json
   [DEBUG] Found cached data in S3
   ```
4. If not present, retrieval is not checking cache

## Common Issues and Fixes

### Issue: Page Number Off-by-One
**Problem**: User is on Page 2 (1-based), but cache is saved to page_1.json (0-based)

**Check**:
- Frontend sends: `currentPageIndex + 1` (should be 2 for Page 2)
- Backend converts: `page_num - 1` (should be 1 for page_1.json)
- Retrieval uses: `page_num - 1` (should be 1 for page_1.json)

**Fix**: Ensure all three use the same conversion

### Issue: Cache Key Mismatch
**Problem**: Save uses `page_data/{doc_id}/page_1.json` but retrieval looks for `page_data/{doc_id}/page_2.json`

**Check**:
- Save logs show: `page_data/{doc_id}/page_1.json`
- Retrieval logs show: `page_data/{doc_id}/page_1.json`
- They should match exactly

**Fix**: Ensure cache key format is consistent

### Issue: S3 Permission Denied
**Problem**: Save fails with "Access Denied" error

**Check**:
- Server logs show: `[ERROR] Failed to update cache: Access Denied`
- Response shows: `"verified": false`

**Fix**: Check AWS IAM permissions for S3 bucket

### Issue: Retrieval Not Checking Cache
**Problem**: Cache exists but retrieval doesn't check it

**Check**:
- Server logs don't show: `[DEBUG] Checking S3 cache:`
- Retrieval logs show: `[DEBUG] No cache found, will extract data`

**Fix**: Ensure retrieval function checks cache before extracting

## Testing the Fix

### Test 1: Add Field and Verify Save
1. Open a document
2. Go to Page 2
3. Click "Edit Page"
4. Add a new field: `test_field = "test_value"`
5. Click "Save"
6. Check browser console for errors
7. Check server logs for save confirmation
8. Verify response shows "success": true

### Test 2: Verify Cache Save
1. Check server logs for:
   ```
   [INFO] Updating regular cache: page_data/{doc_id}/page_1.json
   [INFO] VERIFIED: Cache contains X fields
   ```
2. If not present, save failed

### Test 3: Verify Retrieval
1. Refresh the page
2. Check server logs for:
   ```
   [DEBUG] Checking S3 cache: page_data/{doc_id}/page_1.json
   [DEBUG] Found cached data in S3
   ```
3. If not present, retrieval is not checking cache

### Test 4: Verify Field Persists
1. After refresh, check if field is still there
2. If yes, everything is working
3. If no, check logs to see where it failed

## Logs to Look For

### Successful Save
```
[INFO] Updating regular cache: page_data/3271403d63af/page_1.json (page_num: 2 → 0-based: 1)
[INFO] Saved to S3: page_data/3271403d63af/page_1.json
[INFO] VERIFIED: Cache contains 30 fields
[INFO] Total fields in response: 30
[INFO] All fields: ['Bank_Name', 'Form_Name', 'Customer_Name', ..., 'test_field']
```

### Successful Retrieval
```
[DEBUG] Checking S3 cache: page_data/3271403d63af/page_1.json
[DEBUG] Found cached data in S3
[DEBUG] Applied flattening to cached data
```

### Failed Save
```
[ERROR] Failed to update cache: Access Denied
[ERROR] Verification failed - cache may not have been saved
```

### Failed Retrieval
```
[DEBUG] No cache found, will extract data
[DEBUG] Cache check failed: NoSuchKey, will extract data
```

## Next Steps

1. **Reproduce the issue** with a fresh document
2. **Check browser console** for errors
3. **Check network requests** to see if save is being sent
4. **Check server logs** to see if save is being received
5. **Check S3 cache** to see if data is being saved
6. **Check retrieval logs** to see if cache is being checked

## Document Information

- **Document ID**: 3271403d63af
- **Document Type**: Regular (non-account-based)
- **Page Number**: 2 (1-based from UI)
- **Page Index**: 1 (0-based internally)
- **Cache Key**: `page_data/3271403d63af/page_1.json`
- **Field Added**: "1234"

## Expected Behavior

1. User adds field "1234" on Page 2
2. User clicks Save
3. Frontend sends POST to `/api/document/3271403d63af/page/2/update`
4. Backend saves to `page_data/3271403d63af/page_1.json`
5. Backend verifies save was successful
6. Backend returns response with all fields including "1234"
7. Frontend shows success notification
8. User refreshes page
9. Frontend sends GET to `/api/document/3271403d63af/page/2/extract`
10. Backend checks cache `page_data/3271403d63af/page_1.json`
11. Backend finds cached data with "1234"
12. Backend returns cached data
13. Frontend displays page with "1234" field

## Actual Behavior

- Field appears to save (success notification shown)
- But field doesn't show after refresh
- Suggests cache is not being checked or saved correctly
