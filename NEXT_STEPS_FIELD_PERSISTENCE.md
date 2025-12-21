# Next Steps: Field Persistence Issue Diagnosis

## Current Status
- Server is running with enhanced debugging
- Logging has been added to track the field save and retrieval process
- Frontend logging is in place to track field addition

## What to Do Now

### Step 1: Add a Field on Page 2
1. Open the application
2. Upload a new document (or use existing one)
3. Go to Page 2
4. Click "Add Field"
5. Enter:
   - Name: `test_field_1234`
   - Value: `test_value`
6. Click "Add"

### Step 2: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for logs starting with `=== ADD NEW FIELD DEBUG ===`
4. Check:
   - Is `test_field_1234` in `dataToSave`?
   - Is `test_field_1234` in the response?
   - What is the response status?

### Step 3: Check Server Logs
1. Look for logs like:
   ```
   [DEBUG] update_page_data called: doc_id=3271403d63af, page_num=2, account_index=None
   [DEBUG] Request data: page_data keys=[...], action_type=add
   [INFO] Updating regular cache: page_data/3271403d63af/page_1.json
   [INFO] Saved to S3: page_data/3271403d63af/page_1.json
   [INFO] VERIFIED: Cache contains X fields
   ```

2. If you DON'T see these logs, the update endpoint is not being called

### Step 4: Refresh Page and Check Again
1. Refresh the page (F5)
2. Check browser console for logs starting with `=== RENDER PAGE DATA DEBUG ===`
3. Check:
   - What is the API URL?
   - What is the cache source?
   - Is `test_field_1234` in the retrieved data?

### Step 5: Check Server Logs for Retrieval
1. Look for logs like:
   ```
   [DEBUG] Checking S3 cache: page_data/3271403d63af/page_1.json
   [DEBUG] Found cached data in S3
   ```

2. If you see `[DEBUG] No cache found, will extract data`, the cache is not being saved

## Possible Outcomes

### Outcome 1: Field Shows After Refresh ✅
- **Meaning**: Everything is working correctly
- **Action**: Issue is resolved

### Outcome 2: Field NOT in dataToSave
- **Meaning**: Frontend is not collecting the field properly
- **Action**: Check `addNewField()` function in frontend
- **Check**: Is `editedFields` being populated?

### Outcome 3: Field NOT in response
- **Meaning**: Backend is not including field in response
- **Action**: Check server logs for errors
- **Check**: Look for `[ERROR]` messages

### Outcome 4: update_page_data NOT called
- **Meaning**: Frontend is not sending the request
- **Action**: Check browser Network tab
- **Check**: Is POST request being sent to `/api/document/.../page/.../update`?

### Outcome 5: Cache NOT being saved
- **Meaning**: S3 save is failing
- **Action**: Check S3 permissions
- **Check**: Look for `[ERROR]` messages in server logs

### Outcome 6: Cache NOT being retrieved
- **Meaning**: Retrieval is not checking cache
- **Action**: Check if `/extract` endpoint is checking cache
- **Check**: Look for `[DEBUG] Checking S3 cache:` in server logs

## Debugging Commands

### To see all logs:
```
Get-Content -Path "server_logs.txt" -Tail 100
```

### To filter for update logs:
```
Get-Content -Path "server_logs.txt" | Select-String "update_page_data|Updating.*cache|VERIFIED"
```

### To filter for errors:
```
Get-Content -Path "server_logs.txt" | Select-String "ERROR|Failed"
```

## Expected Behavior

1. **Add field**: Field appears in UI immediately
2. **Click Save**: 
   - Browser console shows field in `dataToSave`
   - Server logs show cache being saved
   - Response shows field in response data
3. **Refresh page**:
   - Browser console shows cache being retrieved
   - Server logs show cache being checked
   - Field appears on page

## If Field Still Not Showing

1. **Collect all logs** from browser console and server
2. **Note the exact steps** you took
3. **Check the cache key** - is it correct?
4. **Check the page number** - is it 1-based or 0-based?
5. **Check S3 directly** - does the cache file exist?

## Key Information

- **Document ID**: 3271403d63af
- **Page Number**: 2 (1-based from UI)
- **Page Index**: 1 (0-based internally)
- **Cache Key**: `page_data/3271403d63af/page_1.json`
- **Update Endpoint**: `/api/document/3271403d63af/page/2/update`
- **Retrieve Endpoint**: `/api/document/3271403d63af/page/2/extract`

## Summary

The enhanced logging should help identify exactly where the issue is occurring. Once you follow these steps and collect the logs, we can pinpoint the exact problem and implement a targeted fix.
