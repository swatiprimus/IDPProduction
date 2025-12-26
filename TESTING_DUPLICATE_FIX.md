# Testing the Duplicate Processing Fix

## Quick Test Steps

### Setup

```bash
# Terminal 1: Start app_modular.py (main app)
python app_modular.py

# Terminal 2: Start simple_upload_app.py (upload app)
python simple_upload_app.py
```

### Test 1: Upload from simple_upload_app.py

**Steps:**
1. Open browser: `http://localhost:5001`
2. Upload a PDF file
3. Check the response - should say "Uploaded to S3 - will be processed by S3 fetcher"
4. Wait 30 seconds for S3 fetcher to detect it
5. Open `http://localhost:5015` (main app dashboard)
6. Check if document appears

**Expected Results:**
- ✅ Document appears on dashboard
- ✅ Only ONE entry in `processed_documents.json`
- ✅ Document is fully processed
- ✅ No duplicate entries

**Check processed_documents.json:**
```bash
cat processed_documents.json | grep -A 5 "filename"
```

Should show ONE entry per file, not two.

### Test 2: Check Logs for Duplicate Processing

**Steps:**
1. Upload file from simple_upload_app.py
2. Watch the logs in both terminals
3. Look for these patterns:

**Expected Log Sequence:**

Terminal 1 (app_modular.py):
```
[S3_FETCHER] 🔄 Processing: document.pdf
[S3_FETCHER]    ✅ Marked as processing in local map
[S3_FETCHER]    📤 Calling /process endpoint...
[S3_FETCHER]    ✅ Job submitted: abc123
[QUEUE] ➕ Added to queue: abc123 (document.pdf) from s3_fetcher
[QUEUE] 🔄 Marked as processing: abc123
[BG_PROCESSOR] 🚀 Starting background processing for document abc123
[BG_PROCESSOR] 🎉 PIPELINE COMPLETED for abc123
[QUEUE] ✅ Marked as completed: abc123
```

**Should NOT see:**
- ❌ Multiple "[S3_FETCHER] 🔄 Processing" messages for same file
- ❌ Multiple "[QUEUE] ➕ Added to queue" messages for same file
- ❌ Multiple "[BG_PROCESSOR] 🚀 Starting background processing" messages for same file

### Test 3: Verify No Duplicate Document Records

**Steps:**
1. Upload file from simple_upload_app.py
2. Wait for processing to complete
3. Check `processed_documents.json`

**Expected:**
```json
[
  {
    "id": "abc123",
    "filename": "document.pdf",
    "status": "completed",
    "documents": [
      {
        "accounts": [...],
        "background_processed": true
      }
    ]
  }
]
```

**Should NOT have:**
```json
[
  {
    "id": "abc123",
    "filename": "document.pdf",
    "status": "pending"
  },
  {
    "id": "def456",
    "filename": "document.pdf",
    "status": "completed"
  }
]
```

### Test 4: Verify S3 Fetcher Doesn't Call /process Twice

**Steps:**
1. Upload file from simple_upload_app.py
2. Check logs for "/process" calls
3. Should see exactly ONE call

**Expected:**
```
[S3_FETCHER]    📤 Calling /process endpoint...
[S3_FETCHER]    ✅ Job submitted: abc123
```

**Should NOT see:**
```
[S3_FETCHER]    📤 Calling /process endpoint...
[S3_FETCHER]    ✅ Job submitted: abc123
[S3_FETCHER]    📤 Calling /process endpoint...
[S3_FETCHER]    ✅ Job submitted: def456
```

### Test 5: Verify Skill Catalog Still Works

**Steps:**
1. Open `http://localhost:5015`
2. Upload file from skill catalog
3. Verify it processes normally

**Expected:**
- ✅ Document appears on dashboard
- ✅ Processing completes
- ✅ No duplicate entries

## Troubleshooting

### Issue: Document appears twice

**Cause:** Old `processed_documents.json` file still has duplicates

**Fix:**
```bash
# Backup old file
cp processed_documents.json processed_documents.json.backup

# Delete old file
rm processed_documents.json

# Restart app_modular.py
python app_modular.py
```

### Issue: S3 fetcher not detecting file

**Cause:** S3 bucket not configured or file not uploaded

**Fix:**
1. Check S3 bucket name in code (should be "aws-idp-uploads")
2. Check AWS credentials are configured
3. Check file was actually uploaded to S3

### Issue: Document not processing

**Cause:** Background processor not running or document not queued

**Fix:**
1. Check app_modular.py logs for "[BG_PROCESSOR]" messages
2. Check if document is in global queue: `cat .document_processing_queue.json`
3. Restart app_modular.py

## Success Criteria

✅ All tests pass if:
1. Only ONE document entry per upload
2. No duplicate processing logs
3. Document fully processes
4. No errors in logs
5. Skill catalog uploads still work

## Performance Expectations

- Upload to S3: < 1 second
- S3 fetcher detection: ~30 seconds
- Document processing: 1-5 minutes (depending on document size)
- Total time from upload to completion: ~2-6 minutes

## Next Steps

If all tests pass:
1. ✅ Duplicate processing is fixed
2. ✅ Ready for production
3. ✅ Monitor logs for any issues
4. ✅ Clean up old test files

If tests fail:
1. Check logs for errors
2. Review the fix documentation
3. Verify all files were updated correctly
4. Restart all services
