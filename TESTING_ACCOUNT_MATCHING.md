# Testing Account Matching Feature

## Quick Test Guide

### Test 1: Upload Initial Document
1. Start the application: `python app_modular.py`
2. Open browser to `http://localhost:5015`
3. Upload a document with an account number (e.g., loan document)
4. Wait for processing to complete
5. Verify document appears in dashboard with "Ready" status

### Test 2: Upload Duplicate with Changes
1. Modify the same document (change a name, add a field, etc.)
2. Upload the modified document
3. **Expected Result:**
   - Processing completes
   - Status message shows: "Document merged with existing account [number] - X changes detected"
   - Dashboard shows the document with:
     - Yellow/amber background
     - "Needs Review (X changes)" badge
     - Left border highlight

### Test 3: Review Changes
1. Click on the updated document in the dashboard
2. **Expected Result:**
   - Document viewer opens
   - Yellow notification banner at top shows:
     - "This document has been updated and needs review"
     - Number of fields changed
     - Source filename
     - "Mark as Reviewed" button

### Test 4: Mark as Reviewed
1. In the document viewer, click "Mark as Reviewed"
2. **Expected Result:**
   - Success notification appears
   - Page reloads
   - Yellow banner disappears
   - Document returns to normal "Ready" status in dashboard

### Test 5: Multiple Accounts
1. Upload a loan document with multiple accounts (e.g., accounts 123, 456, 789)
2. Upload another document with one of those accounts (e.g., 456) but with updated info
3. **Expected Result:**
   - Only the matching account (456) is merged
   - Other accounts (123, 789) remain unchanged
   - Changes tracked specifically for account 456

## Test Data Examples

### Example 1: Simple Account Update
**First Upload - account_001.pdf:**
```
Account Number: 0210630620
Account Holder: John Doe
SSN: 123-45-6789
```

**Second Upload - account_001_updated.pdf:**
```
Account Number: 0210630620
Account Holder: John A. Doe
SSN: 123-45-6789
Phone: (555) 123-4567
```

**Expected Changes:**
- `account_holder_name`: "John Doe" → "John A. Doe" (updated)
- `phone`: "(555) 123-4567" (added)

### Example 2: Business Card Update
**First Upload:**
```
Account Number: 0208856641
Business Name: ABC Construction
Contact: Jane Smith
```

**Second Upload:**
```
Account Number: 0208856641
Business Name: ABC Construction Inc.
Contact: Jane Smith
Email: jane@abc.com
```

**Expected Changes:**
- `business_name`: "ABC Construction" → "ABC Construction Inc." (updated)
- `email`: "jane@abc.com" (added)

## Verification Checklist

- [ ] Account number is correctly detected in new uploads
- [ ] Existing documents are found by account number
- [ ] Only changed fields are updated
- [ ] New fields are added without removing existing data
- [ ] Changes are tracked with old/new values
- [ ] Dashboard shows "Needs Review" badge
- [ ] Document row is highlighted in yellow
- [ ] Notification banner appears in viewer
- [ ] "Mark as Reviewed" button works
- [ ] After review, document returns to normal status
- [ ] Changes are moved to history after review

## Troubleshooting

### Issue: Document not merging
**Check:**
- Account number format matches (system normalizes spaces/dashes)
- Account number is being extracted correctly
- Look in browser console for merge_info in status response

### Issue: Changes not showing
**Check:**
- `needs_review` flag is set to `true` in processed_documents.json
- `changes` array contains the expected changes
- Browser cache (try hard refresh: Ctrl+F5)

### Issue: Review button not working
**Check:**
- Browser console for JavaScript errors
- Network tab for API call to `/api/document/<id>/mark-reviewed`
- Server logs for any errors

## Manual Database Inspection

To manually check the database:
```bash
# View processed_documents.json
cat processed_documents.json | python -m json.tool

# Search for a specific account
cat processed_documents.json | grep -A 20 "0210630620"

# Check for needs_review flags
cat processed_documents.json | grep "needs_review"
```

## Expected Log Messages

When merging occurs, you should see:
```
[INFO] Account 0210630620 already exists in document abc123 - merging changes
[INFO] ✅ Merged 2 changes into existing document
```

When processing completes:
```
[INFO] ✅ Document processing completed - data will be extracted on-demand when pages are viewed
```
