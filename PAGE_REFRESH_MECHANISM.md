# Page Refresh After Save - How It Works

## Overview
When you click "Save" on a page, the page automatically refreshes to show the updated data. This happens through a coordinated process between the frontend and backend.

## Step-by-Step Flow

### Step 1: User Clicks Save
```
Frontend: User clicks "Save" button
  ↓
Frontend: savePage() function is called
```

### Step 2: Frontend Prepares Data
```javascript
async function savePage() {
    // Collect all edited fields
    const dataToSave = {
        "Account_Number": "999999999",
        "test_field": "New Value"
    };
    
    // Get the actual page number
    const actualPageNum = accountPageNumbers[currentPageIndex] || (currentPageIndex + 1);
    
    // Send to backend
    const response = await fetch(
        `/api/document/${documentId}/account/${currentAccountIndex}/page/${actualPageNum}/update`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_data: dataToSave,
                action_type: 'edit'
            })
        }
    );
```

### Step 3: Backend Processes Save
```python
def update_page_data(doc_id, page_num, account_index=None):
    # 1. Load existing fields from S3 cache
    existing_fields = load_from_s3_cache(doc_id, account_index, page_num)
    
    # 2. Merge with new/edited fields
    processed_data = merge_fields(existing_fields, page_data)
    
    # 3. Update confidence scores
    for field_name, field_value in page_data.items():
        if field_name not in existing_fields:
            # New field
            processed_data[field_name] = {
                "value": field_value,
                "confidence": 100,
                "source": "human_added"
            }
        else:
            # Edited field
            processed_data[field_name] = {
                "value": field_value,
                "confidence": 100,
                "source": "human_corrected"
            }
    
    # 4. Save to S3 cache
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=f"page_data/{doc_id}/account_{account_index}/page_{page_num-1}.json",
        Body=json.dumps({"data": processed_data, ...})
    )
    
    # 5. Verify save was successful
    verify_response = s3_client.get_object(...)
    
    # 6. Return response with updated fields
    return jsonify({
        "success": True,
        "data": processed_data,  # Flat structure with all fields
        "verified": True
    })
```

### Step 4: Frontend Receives Response
```javascript
const result = await response.json();

// Response structure:
{
    "success": true,
    "data": {
        "Account_Number": {
            "value": "999999999",
            "confidence": 100,
            "source": "human_corrected"
        },
        "test_field": {
            "value": "New Value",
            "confidence": 100,
            "source": "human_added"
        },
        // ... other fields
    },
    "verified": true
}
```

### Step 5: Frontend Updates In-Memory Data
```javascript
// Update the in-memory cache
if (result.data) {
    currentPageData = result.data;
    console.log('Updated currentPageData from response:', currentPageData);
}
```

### Step 6: Frontend Refreshes Display
```javascript
// Call renderPageDataDirect to re-render the page
if (!currentPageData || typeof currentPageData !== 'object' || Object.keys(currentPageData).length === 0) {
    console.warn('currentPageData is empty, falling back to renderPageData');
    renderPageData();  // Fetch from backend
} else {
    try {
        renderPageDataDirect(currentPageData);  // Use in-memory data
        console.log('renderPageDataDirect completed successfully');
    } catch (renderError) {
        console.error('Error in renderPageDataDirect:', renderError);
        renderPageData();  // Fallback to fetch from backend
    }
}
```

### Step 7: renderPageDataDirect Processes Data
```javascript
function renderPageDataDirect(fields) {
    // Process each field
    const processedData = {};
    const fieldConfidence = {};
    
    for (const [key, value] of Object.entries(fields)) {
        // Extract value and confidence from confidence object
        if (value && typeof value === 'object' && 'value' in value && 'confidence' in value) {
            displayValue = value.value;
            confidence = value.confidence;
        } else {
            displayValue = value;
            confidence = 0;
        }
        
        processedData[key] = displayValue;
        fieldConfidence[key] = confidence;
    }
    
    // Build HTML with confidence badges
    let html = '';
    for (const [key, displayValue] of Object.entries(processedData)) {
        const confidence = fieldConfidence[key] || 0;
        const confidenceColor = confidence >= 90 ? '#10b981' : confidence >= 70 ? '#f59e0b' : '#ef4444';
        
        html += `
            <div class="field-item">
                <div class="field-label">${key}</div>
                <div class="field-value">
                    ${displayValue}
                    <span style="color: ${confidenceColor}; font-weight: 600;">
                        ${confidence}%
                    </span>
                </div>
            </div>
        `;
    }
    
    // Update the DOM
    container.innerHTML = html;
}
```

### Step 8: Page Displays Updated Data
```
Frontend: Page refreshes with new data
  ↓
User sees: Updated fields with confidence scores
  ↓
User sees: Success notification "Saved successfully!"
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                          │
│                                                                 │
│  [Edit Page] → [Save] → Success Notification                   │
│                  ↓                                              │
│            Page Refreshes                                       │
│            Shows Updated Data                                  │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (JavaScript)                        │
│                                                                 │
│  1. savePage() collects edited fields                          │
│  2. Sends POST to /api/document/.../update                     │
│  3. Receives response with updated fields                      │
│  4. Updates currentPageData in memory                          │
│  5. Calls renderPageDataDirect(currentPageData)                │
│  6. Renders HTML with confidence badges                        │
│  7. Updates DOM with new HTML                                  │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (Python/Flask)                       │
│                                                                 │
│  1. Receives POST with edited fields                           │
│  2. Loads existing fields from S3 cache                        │
│  3. Merges with new/edited fields                              │
│  4. Updates confidence scores (100% for edits)                 │
│  5. Saves to S3 cache                                          │
│  6. Verifies save was successful                               │
│  7. Returns response with all fields                           │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                      S3 CACHE (AWS)                             │
│                                                                 │
│  Cache Key: page_data/{doc_id}/account_{idx}/page_{num}.json   │
│                                                                 │
│  Stores:                                                        │
│  {                                                              │
│    "data": {                                                    │
│      "Account_Number": {                                        │
│        "value": "999999999",                                    │
│        "confidence": 100,                                       │
│        "source": "human_corrected"                              │
│      },                                                         │
│      ...                                                        │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Key Points

### 1. Immediate Refresh
- Page refreshes immediately after save
- Uses in-memory data (currentPageData) for instant display
- No need to wait for another API call

### 2. Confidence Scores
- New fields: 100% confidence, source="human_added"
- Edited fields: 100% confidence, source="human_corrected"
- Unchanged fields: Original confidence preserved
- Displayed as colored badges (green=high, yellow=medium, red=low)

### 3. Persistence
- Data saved to S3 cache immediately
- Survives browser refresh
- Survives navigation away and back
- Survives server restart (data in S3)

### 4. Verification
- Backend verifies save was successful
- Returns "verified": true in response
- If verification fails, returns error
- Frontend shows error notification

### 5. Fallback Logic
- If renderPageDataDirect fails, falls back to renderPageData
- renderPageData fetches fresh data from backend
- Ensures page always displays correctly

## Response Data Structure

### Before Save
```json
{
    "Account_Number": {
        "value": "468869904",
        "confidence": 95,
        "source": "ai_extracted"
    },
    "Account_Holders": {
        "value": "DANETTE EBERLY",
        "confidence": 90,
        "source": "ai_extracted"
    }
}
```

### After Edit
```json
{
    "Account_Number": {
        "value": "999999999",
        "confidence": 100,
        "source": "human_corrected"  // Changed!
    },
    "Account_Holders": {
        "value": "DANETTE EBERLY",
        "confidence": 90,
        "source": "ai_extracted"  // Unchanged
    },
    "test_field": {
        "value": "New Value",
        "confidence": 100,
        "source": "human_added"  // New!
    }
}
```

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Save to S3 | ~300ms | Network latency to AWS |
| Verify save | ~100ms | Read back from S3 |
| Frontend render | ~50ms | DOM update |
| **Total** | **~450ms** | User sees refresh in <1 second |

## Troubleshooting

### Page doesn't refresh after save
1. Check browser console for errors
2. Check that renderPageDataDirect is being called
3. Check that currentPageData is being updated
4. Check server logs for any errors

### Fields show wrong values
1. Check response data structure
2. Verify confidence objects are being extracted
3. Check that field names match between backend and frontend
4. Check S3 cache for correct data

### Confidence scores not showing
1. Check that response includes confidence objects
2. Verify renderPageDataDirect is processing confidence
3. Check CSS for confidence badge styling

### Changes don't persist after refresh
1. Check S3 cache for saved data
2. Verify cache key format is correct
3. Check S3 permissions
4. Check server logs for save errors

## Summary

The page refresh mechanism works by:
1. **Saving** edited data to S3 cache
2. **Returning** updated data in response
3. **Updating** in-memory currentPageData
4. **Rendering** page with renderPageDataDirect
5. **Displaying** updated fields with confidence scores

This provides instant visual feedback to the user while ensuring data persistence.
