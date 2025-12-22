# Confidence Score Tracking Implementation

## Overview
Implemented comprehensive confidence score tracking for edit, add, and delete operations on document fields. The system now properly handles human actions and recalculates overall document confidence.

## Rules Implemented

### 1. Initial Extraction
- Auto-extracted fields return model-generated confidence score (0–100)
- Confidence represents model certainty only
- Stored in format: `{ "value": "...", "confidence": 0-100, "source": "ai_extracted" }`

### 2. Human Actions Handling

#### A. Add Field (Manual)
- When a new field is added manually by a human:
  - ✅ Confidence = 100
  - ✅ Source = "human_added"
  - ✅ Marked as edited_at timestamp

#### B. Edit Field (Manual)
- When an existing field value is edited by a human:
  - ✅ Confidence = 100
  - ✅ Source = "human_corrected"
  - ✅ Marked as edited_at timestamp

#### C. Delete Field
- When a field is deleted by a human:
  - ✅ Field removed completely
  - ✅ NOT returned in response
  - ✅ Overall confidence recalculated

### 3. Confidence Refresh Logic
- ✅ Recalculates overall document confidence after every action
- ✅ Overall confidence = weighted average of all remaining fields
- ✅ Fields with confidence = 100 strongly influence overall score
- ✅ Formula: `sum(all_field_confidences) / field_count`

### 4. Cache & State Rules
- ✅ Always returns updated field list exactly as it should appear in UI
- ✅ Response is cache-ready (stored in S3)
- ✅ Confidence NEVER reset to 0 under any condition
- ✅ If no extraction exists but human adds fields, confidence = 100

### 5. Output Consistency
- ✅ Field confidence NEVER null or zero unless explicitly extracted with zero certainty
- ✅ Human-modified fields always win over AI-extracted values
- ✅ Confidence badges display in UI with color coding:
  - Green (≥90%): High confidence
  - Orange (70-89%): Medium confidence
  - Red (<70%): Low confidence

### 6. Page & Account Scope
- ✅ Page-level actions update only page JSON
- ✅ Account-level actions update account JSON
- ✅ Confidence recalculated correctly for both scopes
- ✅ Cache key format: `page_data/{doc_id}/account_{account_index}/page_{page_num}.json`

### 7. UI Sync
- ✅ Returned data reflects:
  - Updated grid with new/edited/deleted fields
  - Updated confidence badge with color coding
  - Updated cached state in S3
  - Overall confidence score

## Backend Implementation

### New Helper Function
```python
def _calculate_overall_confidence(fields_data: Dict) -> float:
    """Calculate weighted average confidence across all fields"""
    - Iterates through all fields
    - Extracts confidence from each field
    - Returns weighted average (0-100)
```

### Updated Endpoint: `/api/document/<doc_id>/page/<int:page_num>/update`
Also supports: `/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>/update`

**Request Body:**
```json
{
  "page_data": { /* field data */ },
  "action_type": "edit|add|delete",
  "deleted_fields": ["field1", "field2"]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Page data updated successfully",
  "data": { /* processed fields with confidence */ },
  "overall_confidence": 85.5
}
```

**Processing Logic:**
1. Retrieves existing cache to preserve original field structure
2. For each field in page_data:
   - If field is new: confidence = 100, source = "human_added"
   - If field value changed: confidence = 100, source = "human_corrected"
   - If field unchanged: preserves original confidence and source
3. Removes deleted fields completely
4. Calculates overall_confidence as weighted average
5. Stores in S3 with metadata (edited_at, action_type, etc.)

## Frontend Implementation

### Updated Functions

#### 1. savePage()
- Sends `action_type: 'edit'` to backend
- Updates currentPageData with response data (includes confidence)
- Calls renderPageData() to refresh UI with confidence badges

#### 2. addNewField()
- Sends `action_type: 'add'` to backend
- Updates currentPageData with response data
- Displays success notification with field name

#### 3. confirmDeleteFields()
- Sends `action_type: 'delete'` with deleted_fields array
- Updates currentPageData with response data
- Recalculates confidence after deletion
- Refreshes UI to show updated confidence

### Confidence Badge Display
In renderPageData():
- Extracts confidence from field objects
- Displays color-coded badge:
  - Green: ≥90% (High confidence)
  - Orange: 70-89% (Medium confidence)
  - Red: <70% (Low confidence)
- Shows source indicator for human-verified fields

## Data Flow

```
User Action (Edit/Add/Delete)
    ↓
Frontend collects field data
    ↓
Sends to backend with action_type
    ↓
Backend processes:
  - Identifies new/changed/unchanged fields
  - Sets confidence based on action
  - Calculates overall_confidence
  - Stores in S3 cache
    ↓
Returns processed data with confidence scores
    ↓
Frontend updates UI:
  - Displays fields with confidence badges
  - Shows overall confidence
  - Refreshes grid
```

## Testing Checklist

- [ ] Add new field → confidence = 100, source = "human_added"
- [ ] Edit existing field → confidence = 100, source = "human_corrected"
- [ ] Delete field → field removed, overall confidence recalculated
- [ ] Confidence badges display with correct colors
- [ ] Overall confidence updates after each action
- [ ] S3 cache stores confidence data correctly
- [ ] Page refresh preserves confidence scores
- [ ] Multiple edits on same field preserve confidence = 100
- [ ] Confidence never becomes null or 0 for human actions

## Files Modified

1. **app_modular.py**
   - Added `_calculate_overall_confidence()` function
   - Updated `update_page_data()` endpoint with confidence tracking
   - Added support for account index in URL path

2. **templates/account_based_viewer.html**
   - Updated `savePage()` to send action_type and handle response
   - Updated `addNewField()` to send action_type and handle response
   - Updated `confirmDeleteFields()` to send action_type and deleted_fields
   - Confidence badge rendering already in place in renderPageData()

## Notes

- Confidence scores are preserved across page refreshes (stored in S3)
- Human actions always override AI confidence
- Overall confidence is recalculated after every action
- Deleted fields are completely removed (not stored with confidence = 0)
- Source field tracks whether value is "ai_extracted", "human_added", or "human_corrected"
