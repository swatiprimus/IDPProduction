# Cache Performance Fix - Instant Page Loading

## Problem
When clicking on a page that was already extracted by LLM and cached in S3, it was still taking 1-3 seconds to load because:

1. **S3 Network Latency**: Every page click made an S3 API call (~100-300ms)
2. **Backend Processing**: Even cached data went through flattening operations
3. **No Browser Cache**: Frontend always called the backend API, even for pages already viewed

## Solution
Added **browser-side caching** so pages load instantly after first view.

## Files Modified
1. **templates/account_based_viewer.html** - Account-based document viewer
2. **templates/unified_page_viewer.html** - Unified page viewer (for non-account documents)

### Changes Made

#### 1. Browser Cache Storage (`templates/account_based_viewer.html`)
```javascript
let pageDataCache = {}; // Browser-side cache: {accountIndex_pageIndex: result}
```

#### 2. Cache Check Before API Call
```javascript
async function renderPageData() {
    // Check browser cache first
    const cacheKey = `${currentAccountIndex}_${currentPageIndex}`;
    if (pageDataCache[cacheKey]) {
        console.log(`[CACHE HIT] Loading page instantly from browser cache`);
        displayPageData(pageDataCache[cacheKey], account, true);
        return; // INSTANT - No API call!
    }
    
    // Cache miss - fetch from server
    const response = await fetch(...);
    const result = await response.json();
    
    // Store in browser cache for next time
    pageDataCache[cacheKey] = result;
}
```

#### 3. Cache Indicators
- **⚡ Instant (Browser Cache)**: Page loaded from browser memory (0ms)
- **💾 Cached (S3)**: Page loaded from S3 cache (~100-300ms)
- **No badge**: Fresh extraction from LLM (~2-5 seconds)

#### 4. Cache Invalidation
Browser cache is cleared when:
- User clicks "🔄 Refresh" button (clears all pages for current account)
- User saves edits to a page (clears only that page)
- User switches accounts (cache persists for other accounts)

## Performance Impact

### Before Fix
- **First click**: 2-5 seconds (LLM extraction)
- **Second click**: 1-3 seconds (S3 cache + network)
- **Third click**: 1-3 seconds (S3 cache + network)

### After Fix
- **First click**: 2-5 seconds (LLM extraction)
- **Second click**: **INSTANT** (~0ms, browser cache)
- **Third click**: **INSTANT** (~0ms, browser cache)

## Benefits
1. **Instant Navigation**: Pages load instantly after first view
2. **Reduced S3 Costs**: Fewer S3 API calls
3. **Better UX**: No waiting when reviewing pages
4. **Preserved Accuracy**: Cache is invalidated on edits

## Testing

### For Account-Based Documents (Loan Documents)
1. Upload a document with multiple accounts
2. Click through pages in an account
3. First click: Shows loading spinner (2-5 sec)
4. Click same page again: **Instant load** with "⚡ Instant (Browser Cache)" badge
5. Click "🔄 Refresh": Clears cache, next click fetches fresh data
6. Edit a field and save: That page's cache is cleared

### For Regular Documents (Certificates, IDs, etc.)
1. Upload a non-account document (death certificate, driver's license, etc.)
2. Click through pages
3. First click: Shows loading spinner (2-5 sec)
4. Click same page again: **Instant load** with "⚡ Instant (Browser Cache)" badge
5. Click "🔄 Refresh": Clears all page cache
6. Edit a field and save: That page's cache is cleared

## Technical Details
- Cache is stored in browser memory (not localStorage)
- Cache is cleared on page refresh
- Each account's pages are cached independently
- Cache key format: `{accountIndex}_{pageIndex}`
