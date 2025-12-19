# Quick Reference Guide - Per-Field Confidence & Page Independence

## Overview

This document provides a quick reference for understanding how the system handles per-field confidence updates and page independence.

---

## Key Concepts

### 1. Per-Field Confidence Updates
When a user edits, adds, or deletes a field:
- **Only that field's confidence is updated**
- **Other fields' confidence remains unchanged**
- **Overall confidence is preserved (not recalculated)**

### 2. Page Independence
Each page maintains completely independent data:
- **Page 1 data ≠ Page 2 data**
- **Same field can exist on different pages with different values**
- **Duplicate detection is per-page only**

---

## Data Flow

### Adding a Field

```
User clicks "Add" button
    ↓
User enters field name and value
    ↓
Frontend checks if field exists on THIS PAGE ONLY
    ↓
Frontend sends ONLY the new field to backend:
{
    "page_data": {
        "new_field": "value"
    },
    "action_type": "add"
}
    ↓
Backend receives request
    ↓
Backend loads existing fields from S3 cache
    ↓
Backend adds new field with confidence = 100
    ↓
Backend preserves all other fields' confidence
    ↓
Backend saves to S3 cache
    ↓
Backend returns updated data
    ↓
Frontend displays new field with confidence badge
```

### Editing a Field

```
User clicks "Edit" button
    ↓
User modifies field value
    ↓
Frontend sends ONLY the edited field to backend:
{
    "page_data": {
        "field_name": "new_value"
    },
    "action_type": "edit"
}
    ↓
Backend receives request
    ↓
Backend loads existing fields from S3 cache
    ↓
Backend updates field with confidence = 100
    ↓
Backend preserves all other fields' confidence
    ↓
Backend saves to S3 cache
    ↓
Backend returns updated data
    ↓
Frontend displays updated field with confidence = 100
```

### Deleting a Field

```
User clicks "Delete" button
    ↓
User selects fields to delete
    ↓
Frontend sends ONLY deleted field names to backend:
{
    "page_data": {
        "field_to_delete": null
    },
    "deleted_fields": ["field_to_delete"],
    "action_type": "delete"
}
    ↓
Backend receives request
    ↓
Backend loads existing fields from S3 cache
    ↓
Backend removes deleted field
    ↓
Backend preserves all other fields' confidence
    ↓
Backend saves to S3 cache
    ↓
Backend returns updated data
    ↓
Frontend displays remaining fields unchanged
```

---

## Code Locations

### Frontend (templates/account_based_viewer.html)

| Function | Line | Purpose |
|----------|------|---------|
| `savePage()` | 2148 | Sends edited fields to backend |
| `addNewField()` | 2269 | Sends new field to backend |
| `confirmDeleteFields()` | 2640 | Sends deleted fields to backend |
| `exitEditMode()` | 2080 | Resets edit state and variables |
| `renamedFields` initialization | 988 | Initializes field rename tracking |

### Backend (app_modular.py)

| Function | Line | Purpose |
|----------|------|---------|
| `update_page_data()` | 6234 | Processes field updates |
| `get_account_page_data()` | 4552 | Retrieves page data from cache |

---

## Important Variables

### Frontend

```javascript
// Tracks edited fields (only changed fields)
let editedFields = {};

// Tracks renamed fields
let renamedFields = {};

// Stores current page's data
let currentPageData = null;

// Tracks fields selected for deletion
let selectedFieldsForDelete = new Set();
```

### Backend

```python
# Existing fields from S3 cache
existing_fields = existing_cache.get("data", {})

# Fields to process (only from request)
page_data = data.get("page_data")

# Fields marked for deletion
deleted_fields = data.get("deleted_fields", [])

# Action type (edit, add, delete)
action_type = data.get("action_type", "edit")
```

---

## S3 Cache Structure

### Cache Key Format
```
page_data/{doc_id}/account_{account_index}/page_{page_num}.json
```

### Cache Data Format
```json
{
  "data": {
    "field_name": {
      "value": "field_value",
      "confidence": 100,
      "source": "human_corrected",
      "edited_at": "2025-12-18T12:34:56.789123"
    }
  },
  "overall_confidence": 92.5,
  "account_number": "ACC123",
  "edited": true,
  "edited_at": "2025-12-18T12:34:56.789123",
  "action_type": "edit"
}
```

---

## Confidence Score Rules

### New Field (Add)
```
confidence = 100
source = "human_added"
```

### Edited Field (Edit)
```
confidence = 100
source = "human_corrected"
```

### Unchanged Field (Preserved)
```
confidence = (original value)
source = (original source)
```

### Deleted Field
```
(removed from data)
```

### Overall Confidence
```
(preserved from cache, not recalculated)
```

---

## Common Scenarios

### Scenario 1: Add Field on Page 1, Then Page 2

```
Page 1: Add "phone" = "555-1234"
  → S3: page_data/doc123/account_0/page_1.json
  → Contains: phone (confidence: 100)

Page 2: Add "phone" = "555-5678"
  → S3: page_data/doc123/account_0/page_2.json
  → Contains: phone (confidence: 100)

Result: Both pages have "phone" with different values ✅
```

### Scenario 2: Edit Field, Refresh Page

```
Page 1: Edit "name" to "Jane"
  → S3: page_data/doc123/account_0/page_1.json
  → name: confidence = 100

Refresh page
  → Frontend loads from S3 cache
  → name: confidence = 100 (persisted)

Result: Edit persists after refresh ✅
```

### Scenario 3: Edit Multiple Fields

```
Before: name (95%), email (90%), phone (85%)

Edit name to "Jane"
  → Frontend sends: { "name": "Jane" }
  → Backend updates: name (confidence: 100)
  → Backend preserves: email (90%), phone (85%)

After: name (100%), email (90%), phone (85%)

Result: Only edited field's confidence changed ✅
```

---

## Debugging Tips

### Check Frontend Data Sending
```javascript
// In browser console, check what's being sent:
console.log('Sending to backend:', dataToSave);
```

### Check Backend Processing
```python
# In app_modular.py, check logs:
print(f"[INFO] Processing fields: {list(page_data.keys())}")
print(f"[INFO] Preserving fields: {list(existing_fields.keys())}")
```

### Check S3 Cache
```python
# Read cache from S3:
cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
cache_data = json.loads(cache_response['Body'].read())
print(json.dumps(cache_data, indent=2))
```

### Check Page Independence
```javascript
// Verify each page has separate data:
console.log('Page 1 data:', currentPageData);
// Navigate to Page 2
console.log('Page 2 data:', currentPageData);
// Should be different objects
```

---

## Common Issues & Solutions

### Issue: All fields' confidence updated
**Solution:** Check that frontend sends only edited fields, not all fields

### Issue: Overall confidence recalculated
**Solution:** Check that backend preserves existing overall_confidence from cache

### Issue: Field appears on multiple pages
**Solution:** Check that each page has separate S3 cache key

### Issue: Changes don't persist after refresh
**Solution:** Check that S3 cache is being saved correctly

### Issue: renamedFields is not defined
**Solution:** Ensure renamedFields is initialized at line 988 and reset in exitEditMode()

---

## Testing Checklist

- [ ] Add field on Page 1
- [ ] Verify field doesn't appear on Page 2
- [ ] Add same field on Page 2 with different value
- [ ] Verify both pages have independent values
- [ ] Edit field on Page 1
- [ ] Verify only that field's confidence = 100
- [ ] Verify other fields' confidence unchanged
- [ ] Refresh page
- [ ] Verify edit persists
- [ ] Navigate to Page 2
- [ ] Verify Page 2 unaffected
- [ ] Delete field on Page 1
- [ ] Verify field removed
- [ ] Verify other fields unchanged
- [ ] Refresh page
- [ ] Verify deletion persists

---

## API Reference

### GET /api/document/{id}/account/{idx}/page/{num}/data
Returns page-specific data from S3 cache

**Response:**
```json
{
  "success": true,
  "data": {
    "field_name": {
      "value": "...",
      "confidence": 100,
      "source": "human_corrected"
    }
  },
  "overall_confidence": 92.5,
  "cached": true,
  "cache_source": "s3_user_edits"
}
```

### POST /api/document/{id}/account/{idx}/page/{num}/update
Updates page data and saves to S3 cache

**Request:**
```json
{
  "page_data": {
    "field_name": "new_value"
  },
  "action_type": "edit",
  "deleted_fields": []
}
```

**Response:**
```json
{
  "success": true,
  "message": "Page data updated successfully",
  "data": {
    "field_name": {
      "value": "new_value",
      "confidence": 100,
      "source": "human_corrected"
    }
  }
}
```

---

## Key Takeaways

1. **Frontend sends only changed fields** - Not all fields
2. **Backend processes only received fields** - Preserves others
3. **Each page has independent data** - No cross-page sharing
4. **Confidence is per-field** - Only edited field's confidence updated
5. **Overall confidence is preserved** - Not recalculated
6. **Data persists in S3 cache** - Survives page refresh

---

**Last Updated:** December 18, 2025  
**Version:** 1.0 - Final
