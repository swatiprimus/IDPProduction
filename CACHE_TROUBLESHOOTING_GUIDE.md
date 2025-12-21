# Page-Level Cache Troubleshooting Guide

## Quick Diagnosis

### Symptom: Changes not persisting after Save
**Check these in order:**

1. **Verify S3 Response**
   - Look for `"verified": True` in the API response
   - If missing or `False`, the cache save failed

2. **Check Console Logs**
   - Look for: `[INFO] ✅ VERIFIED: Cache contains X fields`
   - If you see `[ERROR] ⚠️ Verification failed`, S3 save is failing

3. **Verify Cache Key Format**
   - Should be: `page_data/{doc_id}/account_{account_index}/page_{page_num_0based}.json`
   - Example: `page_data/doc123/account_0/page_0.json` (NOT page_1)

### Symptom: "Cache save verification failed" error
**This means:**
- The data was written to S3
- But reading it back failed
- Possible causes:
  - S3 permissions issue
  - S3 bucket not accessible
  - Network timeout

**Solution:**
1. Check S3 bucket permissions
2. Verify AWS credentials are valid
3. Check network connectivity to S3

### Symptom: Fields disappear after page refresh
**This means:**
- Cache save succeeded (you saw `verified: True`)
- But retrieval is failing
- Possible causes:
  - Cache key mismatch (old vs new format)
  - Retrieval function not checking correct cache key
  - S3 object was deleted

**Solution:**
1. Check the cache key in logs during save
2. Check the cache key in logs during retrieval
3. They should match exactly
4. If they don't, there's a page number conversion issue

## Debug Checklist

### Before Reporting an Issue

- [ ] Check browser console for errors
- [ ] Check server logs for `[ERROR]` messages
- [ ] Verify the API response includes `"verified": True`
- [ ] Check that cache key format is correct (0-based page numbers)
- [ ] Try the operation on a different page
- [ ] Try the operation on a different document
- [ ] Clear browser cache and try again
- [ ] Check S3 bucket directly for the cache file

### Information to Collect

When reporting a cache issue, provide:

1. **Document ID**: `doc_id` from the URL
2. **Account Index**: Which account (0, 1, 2, etc.)
3. **Page Number**: Which page (1-based as shown in UI)
4. **Operation**: Add, Edit, or Delete
5. **Field Name**: Which field was modified
6. **API Response**: Full JSON response from the save operation
7. **Console Logs**: Relevant log lines with timestamps
8. **Expected vs Actual**: What should happen vs what actually happened

## Common Issues and Solutions

### Issue 1: Page Number Off-by-One
**Symptom**: Data saves but appears on wrong page after refresh

**Cause**: Page number conversion error (1-based vs 0-based)

**Solution**:
- Check logs for: `page_num: X → 0-based: Y`
- Verify Y = X - 1
- If not, there's a conversion bug

### Issue 2: Cache Key Mismatch
**Symptom**: Save succeeds but retrieval fails

**Cause**: Save and retrieval using different cache keys

**Solution**:
1. Note the cache key from save logs
2. Note the cache key from retrieval logs
3. They must be identical
4. If different, check page number format

### Issue 3: S3 Permission Denied
**Symptom**: `[ERROR] Failed to update cache: Access Denied`

**Cause**: AWS credentials don't have S3 write permission

**Solution**:
1. Check AWS IAM policy for S3 access
2. Verify bucket name is correct
3. Verify credentials are valid
4. Check S3 bucket policy

### Issue 4: Intermittent Failures
**Symptom**: Sometimes works, sometimes doesn't

**Cause**: Network timeout or S3 throttling

**Solution**:
1. Check network connectivity
2. Check S3 request rate (may be throttled)
3. Add retry logic with exponential backoff
4. Check CloudWatch logs for S3 errors

## Performance Optimization

### If Cache Operations Are Slow

1. **Check S3 Region**
   - Ensure S3 bucket is in same region as app
   - Cross-region access is slower

2. **Check Network**
   - Verify low latency to S3
   - Check for network congestion

3. **Check S3 Performance**
   - Look for S3 throttling errors
   - Consider S3 Transfer Acceleration
   - Check for hot partitions

### If Verification Takes Too Long

1. **Reduce Verification Scope**
   - Only verify field count, not all fields
   - Skip verification for small updates

2. **Make Verification Async**
   - Return success immediately
   - Verify in background
   - Log verification results

## Monitoring

### Key Metrics to Track

1. **Cache Hit Rate**
   - Count successful retrievals from cache
   - Count cache misses
   - Target: >90% hit rate

2. **Save Success Rate**
   - Count successful saves
   - Count failed saves
   - Target: 100% success rate

3. **Verification Success Rate**
   - Count successful verifications
   - Count failed verifications
   - Target: 100% success rate

4. **Operation Latency**
   - Time to save
   - Time to verify
   - Time to retrieve
   - Target: <500ms total

### Log Patterns to Monitor

```
# Good pattern (successful operation)
[INFO] 💾 Updating account-based cache: page_data/doc123/account_0/page_0.json
[INFO] ✅ Saved to S3: page_data/doc123/account_0/page_0.json
[INFO] ✅ VERIFIED: Cache contains 15 fields
[INFO] ✅ VERIFIED: Cache key is correct: page_data/doc123/account_0/page_0.json

# Bad pattern (failed operation)
[INFO] 💾 Updating account-based cache: page_data/doc123/account_0/page_0.json
[ERROR] ⚠️ Verification failed - cache may not have been saved: NoSuchKey
[ERROR] ❌ Failed to update cache: NoSuchKey
```

## Recovery Procedures

### If Cache Gets Corrupted

1. **Clear All Cache for Document**
   ```
   DELETE all objects with prefix: page_data/{doc_id}/
   ```

2. **Trigger Re-extraction**
   - Re-upload the document
   - Let background processor re-extract all pages
   - Cache will be rebuilt

3. **Verify Recovery**
   - Check that new cache files are created
   - Verify data is correct
   - Test Add/Edit/Delete operations

### If Cache Gets Out of Sync

1. **Identify Affected Pages**
   - Check which pages have stale data
   - Note the last modification time

2. **Clear Affected Pages**
   ```
   DELETE objects: page_data/{doc_id}/account_{idx}/page_{num}.json
   ```

3. **Re-extract Affected Pages**
   - Trigger extraction for those pages
   - Verify new cache is created
   - Test operations

## Support Resources

- **AWS S3 Documentation**: https://docs.aws.amazon.com/s3/
- **Flask Documentation**: https://flask.palletsprojects.com/
- **Python JSON**: https://docs.python.org/3/library/json.html

## Contact Support

When contacting support about cache issues, include:
1. This troubleshooting checklist (completed)
2. Relevant log excerpts
3. API response JSON
4. Steps to reproduce
5. Expected vs actual behavior
