# Confidence Score Tracking - Testing Guide

## Quick Test Scenarios

### Scenario 1: Add New Field
1. Open a document and select an account/page
2. Click "➕ Add" button
3. Enter field name: "Test Field"
4. Enter field value: "Test Value"
5. Click "Add Field"

**Expected Result:**
- Field appears in the grid
- Confidence badge shows: **100%** (Green)
- Source: "human_added"
- Overall confidence increases

### Scenario 2: Edit Existing Field
1. Open a document and select an account/page
2. Click "📝 Edit" button
3. Click on any field value to edit
4. Change the value
5. Click "✓ Save"

**Expected Result:**
- Field value updates
- Confidence badge shows: **100%** (Green)
- Source: "human_corrected"
- Overall confidence updates

### Scenario 3: Delete Field
1. Open a document and select an account/page
2. Click "🗑️ Delete" button
3. Check the checkbox next to a field
4. Click "✓ Confirm"

**Expected Result:**
- Field is removed from grid
- Overall confidence recalculates
- Remaining fields' confidence preserved

### Scenario 4: Confidence Color Coding
After performing actions, verify confidence badges display correct colors:

| Confidence | Color | Meaning |
|-----------|-------|---------|
| ≥90% | 🟢 Green | High confidence |
| 70-89% | 🟠 Orange | Medium confidence |
| <70% | 🔴 Red | Low confidence |
| 100% (Human) | 🟢 Green + Badge | Human verified |

## Verification Checklist

### Backend (S3 Cache)
- [ ] Cache file exists at: `page_data/{doc_id}/account_{account_index}/page_{page_num}.json`
- [ ] Cache contains `overall_confidence` field
- [ ] Each field has structure: `{ "value": "...", "confidence": 0-100, "source": "..." }`
- [ ] Deleted fields are NOT in cache
- [ ] `edited_at` timestamp is present
- [ ] `action_type` is recorded ("edit", "add", or "delete")

### Frontend (UI)
- [ ] Confidence badges display next to field values
- [ ] Colors match confidence levels
- [ ] Human-verified fields show special badge
- [ ] Overall confidence updates after each action
- [ ] Fields refresh without page reload

### Data Persistence
- [ ] Refresh page → confidence scores persist
- [ ] Close and reopen document → confidence scores preserved
- [ ] Multiple edits on same field → confidence stays 100%

## API Response Examples

### Add Field Response
```json
{
  "success": true,
  "message": "Page data updated successfully",
  "data": {
    "Test Field": {
      "value": "Test Value",
      "confidence": 100,
      "source": "human_added",
      "edited_at": "2025-12-18T12:34:56.789123"
    }
  },
  "overall_confidence": 85.5
}
```

### Edit Field Response
```json
{
  "success": true,
  "message": "Page data updated successfully",
  "data": {
    "Account Number": {
      "value": "123456789",
      "confidence": 100,
      "source": "human_corrected",
      "edited_at": "2025-12-18T12:34:56.789123"
    }
  },
  "overall_confidence": 92.3
}
```

### Delete Field Response
```json
{
  "success": true,
  "message": "Page data updated successfully",
  "data": {
    "Account Number": {
      "value": "123456789",
      "confidence": 95,
      "source": "ai_extracted"
    }
  },
  "overall_confidence": 95.0
}
```

## Debugging Tips

### Check S3 Cache
```bash
# View cache file content
aws s3 cp s3://bucket/page_data/{doc_id}/account_{account_index}/page_{page_num}.json -
```

### Browser Console
```javascript
// Check currentPageData structure
console.log(currentPageData);

// Check fieldConfidence mapping
console.log(fieldConfidence);

// Check overall confidence
console.log('Overall confidence:', result.overall_confidence);
```

### Backend Logs
Look for these log messages:
- `[INFO] Added new field: {field_name} (confidence: 100, source: human_added)`
- `[INFO] Edited field: {field_name} (confidence: 100, source: human_corrected)`
- `[INFO] Deleting field: {field_name}`
- `[INFO] Updated cache: {cache_key} (overall_confidence: {score})`

## Common Issues & Solutions

### Issue: Confidence shows 0% after edit
**Solution:** Check that the backend is receiving the action_type parameter. Verify frontend is sending:
```javascript
body: JSON.stringify({
  page_data: dataToSave,
  action_type: 'edit'  // Must be included
})
```

### Issue: Confidence badge not displaying
**Solution:** Verify renderPageData() is extracting confidence from field objects:
```javascript
if (fieldValue && typeof fieldValue === 'object' && 'confidence' in fieldValue) {
  confidence = fieldValue.confidence;
}
```

### Issue: Overall confidence not updating
**Solution:** Ensure backend is calculating overall_confidence:
```python
overall_confidence = _calculate_overall_confidence(processed_data)
```

### Issue: Deleted fields still appear after refresh
**Solution:** Verify deleted fields are NOT included in processed_data before saving to S3:
```python
if field_name in deleted_fields:
    continue  # Skip this field
```

## Performance Notes

- Confidence calculation: O(n) where n = number of fields
- S3 cache update: ~100-500ms depending on network
- UI refresh: ~300ms (setTimeout in confirmDeleteFields)
- Overall impact: Minimal, no noticeable slowdown

## Future Enhancements

- [ ] Batch confidence updates for multiple fields
- [ ] Confidence history tracking (audit trail)
- [ ] Confidence trends over time
- [ ] Machine learning to improve AI confidence scores
- [ ] Confidence-based field validation rules
