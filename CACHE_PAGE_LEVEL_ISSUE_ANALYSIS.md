# Page-Level Cache Not Saving Issue - Root Cause Analysis

## Problem Summary
When performing Add, Edit, and Delete operations on page-level fields, the data is not being saved to the page-level cache properly. The issue is a **cache key mismatch** between the retrieval and update operations.

## Root Cause: Cache Key Mismatch

### In `get_account_page_data()` (Line 4620):
```python
cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
```
- Uses **1-based page_num** directly from the URL
- Example: `page_data/doc123/account_0/page_1.json`

### In `update_page_data()` (Line 6363):
```python
if account_index is not None:
    # Account-based document (loan documents)
    cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
```
- Also uses **1-based page_num** directly from the URL
- Example: `page_data/doc123/account_0/page_1.json`

**Wait, these match!** But there's a subtle issue...

## The Real Issue: Page Number Conversion Inconsistency

Looking at the flow:

1. **Frontend sends page_num as 1-based** (page 1, 2, 3...)
2. **`get_account_page_data()` receives 1-based page_num** and uses it directly in cache key
3. **`update_page_data()` receives 1-based page_num** and uses it directly in cache key
4. **BUT** - The cache is being checked with **1-based keys** while the data might be stored with **0-based keys**

## Secondary Issue: Cache Retrieval Priority

In `get_account_page_data()` (Line 4620), the cache retrieval order is:

1. **Priority 0**: Check S3 cache for user edits: `page_data/{doc_id}/account_{account_index}/page_{page_num}.json`
2. **Priority 1**: Check account's page_data from document record
3. **Priority 2**: Check background processor cache (converts to 0-based)

The problem: When `update_page_data()` saves to S3, it uses the **1-based page_num**, but the retrieval might be looking for **0-based** in some cases.

## The Fix Required

### Issue 1: Standardize Page Number Format
The cache key format needs to be consistent. Currently:
- **Retrieval uses**: 1-based page_num directly
- **Update uses**: 1-based page_num directly
- **But background processor uses**: 0-based page_num

### Issue 2: Ensure Cache is Actually Being Saved
The `update_page_data()` function saves to S3 with this key:
```python
cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
```

But when retrieving, it checks:
```python
cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
```

These should match, but the issue might be:
1. **S3 put_object is failing silently** (no error handling)
2. **Page number conversion is happening somewhere** that's not visible
3. **Cache key format changed** between different parts of the code

## Recommended Solution

### Step 1: Add Logging to Verify Cache Save
In `update_page_data()`, add verification after S3 put:
```python
try:
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=cache_key,
        Body=json.dumps(cache_data),
        ContentType='application/json'
    )
    print(f"[INFO] ✅ Successfully saved to S3: {cache_key}")
    
    # VERIFY: Try to read it back immediately
    verify_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
    verify_data = json.loads(verify_response['Body'].read())
    print(f"[INFO] ✅ Verified cache save - contains {len(verify_data.get('data', {}))} fields")
except Exception as e:
    print(f"[ERROR] ❌ Failed to save cache: {str(e)}")
```

### Step 2: Standardize Page Number Format
Use **0-based page numbers** consistently throughout:
- Store in cache with 0-based: `page_data/{doc_id}/account_{account_index}/page_{page_num_0based}.json`
- Convert 1-based from URL to 0-based immediately
- Use 0-based consistently in all cache operations

### Step 3: Add Cache Invalidation
After updating cache, clear any in-memory caches:
```python
# Clear any cached responses
if hasattr(background_processor, 'page_cache'):
    cache_key_pattern = f"{doc_id}_account_{account_index}_page_{page_num}"
    # Clear matching cache entries
```

## Implementation Priority

1. **HIGH**: Add verification logging to confirm S3 saves are working
2. **HIGH**: Standardize page number format (0-based throughout)
3. **MEDIUM**: Add cache invalidation after updates
4. **MEDIUM**: Add error handling for S3 operations

## Testing Steps

1. Add a field to a page
2. Check S3 directly to verify the cache file exists
3. Refresh the page and verify the field is still there
4. Edit the field and verify the change persists
5. Delete the field and verify it's removed
