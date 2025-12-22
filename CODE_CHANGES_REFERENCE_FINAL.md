# Code Changes Reference - Final Implementation

## Overview

This document provides exact code references for all changes made to implement per-field confidence updates and page independence.

---

## Frontend Changes (templates/account_based_viewer.html)

### 1. Variable Initialization (Line 988)

**Location:** Global scope, after page load

```javascript
let originalData = {};
let editedFields = {};
let renamedFields = {};  // ✅ ADDED: Initialize renamedFields
let sidebarCollapsed = false;
```

**Purpose:** Initialize renamedFields to prevent "undefined" errors

---

### 2. savePage() Function (Line 2148)

**Location:** Data saving function

```javascript
async function savePage() {
    if (Object.keys(editedFields).length === 0 && Object.keys(renamedFields).length === 0) {
        showNotification('No changes to save', 'error');
        return;
    }
    
    try {
        // Handle field renames first
        for (const [oldName, newName] of Object.entries(renamedFields)) {
            if (currentPageData[oldName] !== undefined) {
                currentPageData[newName] = currentPageData[oldName];
                delete currentPageData[oldName];
                console.log(`Renamed field: ${oldName} → ${newName}`);
            }
        }
        
        // ✅ CHANGED: Prepare the data to save - ONLY send edited fields to backend
        const dataToSave = {};
        
        // ✅ CHANGED: Only include edited fields (not all fields)
        for (const [fieldName, fieldValue] of Object.entries(editedFields)) {
            const actualFieldName = renamedFields[fieldName] || fieldName;
            dataToSave[actualFieldName] = fieldValue;
            console.log(`Sending edited field: ${actualFieldName} = ${fieldValue}`);
        }
        
        // Update currentPageData locally
        for (const [fieldName, fieldValue] of Object.entries(editedFields)) {
            const actualFieldName = renamedFields[fieldName] || fieldName;
            if (typeof currentPageData[actualFieldName] === 'object' && currentPageData[actualFieldName].value !== undefined) {
                currentPageData[actualFieldName].value = fieldValue;
            } else {
                currentPageData[actualFieldName] = fieldValue;
            }
        }
        
        const actualPageNum = accountPageNumbers[currentPageIndex] || currentPageIndex;
        
        // ✅ CHANGED: Send ONLY edited fields to backend
        const response = await fetch(`/api/document/${documentId}/account/${currentAccountIndex}/page/${actualPageNum}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_data: dataToSave,  // ✅ ONLY edited fields
                action_type: 'edit'
            })
        });
        
        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message);
        }
        
        if (result.data) {
            currentPageData = result.data;
        }
        
        showNotification('✅ Saved successfully! Changes will persist after refresh.', 'success');
        exitEditMode();
        renderPageData();
    } catch (error) {
        showNotification('❌ Failed to save: ' + error.message, 'error');
    }
}
```

**Key Changes:**
- Only sends edited fields in `dataToSave` (not all fields)
- Preserves other fields' confidence on backend
- Logs which fields are being sent

---

### 3. addNewField() Function (Line 2269)

**Location:** Add field dialog handler

```javascript
async function addNewField() {
    const fieldName = document.getElementById('newFieldName').value.trim();
    const fieldValue = document.getElementById('newFieldValue').value.trim();
    
    if (!fieldName) {
        showNotification('Please enter a field name', 'error');
        return;
    }
    
    if (!fieldValue) {
        showNotification('Please enter a field value', 'error');
        return;
    }
    
    // ✅ CHANGED: Check if field already exists on THIS PAGE ONLY
    if (currentPageData && currentPageData[fieldName]) {
        if (!confirm(`Field "${fieldName}" already exists. Do you want to overwrite it?`)) {
            return;
        }
    }
    
    try {
        if (!currentPageData) {
            currentPageData = {};
        }
        
        // ✅ CHANGED: Prepare the data to save - ONLY send the new field to backend
        const dataToSave = {};
        
        // ✅ CHANGED: Add ONLY the new field (not all fields)
        dataToSave[fieldName] = fieldValue;
        console.log(`Sending new field: ${fieldName} = ${fieldValue}`);
        
        currentPageData[fieldName] = fieldValue;
        
        const account = accounts[currentAccountIndex];
        const actualPageNum = accountPageNumbers[currentPageIndex] || currentPageIndex;
        
        // ✅ CHANGED: Send ONLY the new field to backend
        const response = await fetch(`/api/document/${documentId}/account/${currentAccountIndex}/page/${actualPageNum}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_data: dataToSave,  // ✅ ONLY new field
                action_type: 'add'
            })
        });
        
        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message);
        }
        
        if (result.data) {
            currentPageData = result.data;
        }
        
        console.log('Field added successfully, cache updated:', result);
        showNotification(`Field "${fieldName}" added successfully!`, 'success');
        closeAddFieldDialog();
        
        setTimeout(() => {
            showPage(currentPageIndex);
        }, 300);
    } catch (error) {
        console.error('Add field error:', error);
        showNotification('Failed to add field: ' + error.message, 'error');
    }
}
```

**Key Changes:**
- Only sends new field in `dataToSave` (not all fields)
- Duplicate detection is per-page only
- Preserves other fields' confidence on backend

---

### 4. confirmDeleteFields() Function (Line 2640)

**Location:** Delete field confirmation handler

```javascript
async function confirmDeleteFields() {
    if (selectedFieldsForDelete.size === 0) {
        showNotification('No fields selected', 'error');
        return;
    }
    
    const count = selectedFieldsForDelete.size;
    if (!confirm(`Delete ${count} selected field${count > 1 ? 's' : ''}?`)) {
        return;
    }
    
    try {
        // ✅ CHANGED: Send ONLY the deleted fields to backend
        const dataToSave = {};
        for (const fieldName of selectedFieldsForDelete) {
            dataToSave[fieldName] = null;  // Mark for deletion
        }
        
        // Update currentPageData locally (remove deleted fields)
        for (const fieldName of selectedFieldsForDelete) {
            delete currentPageData[fieldName];
        }
        
        const actualPageNum = accountPageNumbers[currentPageIndex] || currentPageIndex;
        
        // ✅ CHANGED: Send ONLY deleted fields to backend
        const response = await fetch(`/api/document/${documentId}/account/${currentAccountIndex}/page/${actualPageNum}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                page_data: dataToSave,  // ✅ ONLY deleted fields
                deleted_fields: Array.from(selectedFieldsForDelete),
                action_type: 'delete'
            })
        });
        
        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message);
        }
        
        if (result.data) {
            currentPageData = result.data;
        }
        
        showNotification(`${count} field${count > 1 ? 's' : ''} deleted successfully!`, 'success');
        cancelDeleteMode();
        
        setTimeout(() => {
            showPage(currentPageIndex);
        }, 300);
        
    } catch (error) {
        showNotification('Failed to delete fields: ' + error.message, 'error');
    }
}
```

**Key Changes:**
- Only sends deleted fields in `dataToSave` (not all fields)
- Preserves other fields' confidence on backend
- Includes `deleted_fields` list for backend processing

---

### 5. exitEditMode() Function (Line 2080)

**Location:** Edit mode exit handler

```javascript
function exitEditMode() {
    editMode = false;
    const editBtn = document.getElementById('editBtn');
    const saveBtn = document.getElementById('saveBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    
    editBtn.classList.remove('active');
    editBtn.textContent = '📝 Edit Page';
    saveBtn.style.display = 'none';
    cancelBtn.style.display = 'none';
    
    document.querySelectorAll('.field-value').forEach(field => {
        field.classList.remove('editable');
        field.onclick = null;
    });
    
    editedFields = {};
    renamedFields = {};  // ✅ ADDED: Reset renamedFields
    originalData = {};
}
```

**Key Changes:**
- Added `renamedFields = {}` reset to prevent undefined errors

---

## Backend Changes (app_modular.py)

### 1. update_page_data() Endpoint (Line 6234)

**Location:** POST endpoint for updating page data

```python
@app.route("/api/document/<doc_id>/page/<int:page_num>/update", methods=["POST"])
@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>/update", methods=["POST"])
def update_page_data(doc_id, page_num, account_index=None):
    """Update page data and save to S3 cache with confidence tracking"""
    import json
    
    try:
        data = request.get_json()
        page_data = data.get("page_data")
        action_type = data.get("action_type", "edit")  # 'edit', 'add', 'delete'
        deleted_fields = data.get("deleted_fields", [])  # List of field names to delete
        
        if account_index is None:
            account_index = data.get("account_index")
        
        if not page_data:
            return jsonify({"success": False, "message": "No page data provided"}), 400
        
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Determine cache key based on whether this is an account-based document
        if account_index is not None:
            cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
            print(f"[INFO] Updating account-based cache: {cache_key}")
        else:
            cache_key = f"page_data/{doc_id}/page_{page_num - 1}.json"
            print(f"[INFO] Updating regular cache: {cache_key}")
        
        # ✅ CHANGED: Get existing cache to preserve metadata and original field structure
        existing_fields = {}
        existing_cache = {}
        account_number = None
        try:
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            existing_cache = json.loads(cache_response['Body'].read().decode('utf-8'))
            existing_fields = existing_cache.get("data", {})
            account_number = existing_cache.get("account_number")
        except:
            pass  # Cache miss or error, start fresh
        
        # ✅ CHANGED: Start with existing fields (preserve all fields)
        processed_data = {}
        for field_name, field_value in existing_fields.items():
            processed_data[field_name] = field_value
        
        # ✅ CHANGED: Process ONLY the updated fields from page_data
        for field_name, field_value in page_data.items():
            # Skip deleted fields
            if field_name in deleted_fields:
                print(f"[INFO] Deleting field: {field_name}")
                if field_name in processed_data:
                    del processed_data[field_name]
                continue
            
            # Determine if this field was edited/added by human
            existing_field = existing_fields.get(field_name)
            is_new_field = field_name not in existing_fields
            
            # Extract the actual value (handle both string and object formats)
            if isinstance(field_value, dict):
                actual_value = field_value.get("value", field_value)
            else:
                actual_value = field_value
            
            # Check if value changed from original
            existing_value = None
            if existing_field:
                if isinstance(existing_field, dict):
                    existing_value = existing_field.get("value", existing_field)
                else:
                    existing_value = existing_field
            
            value_changed = existing_value != actual_value
            
            # ✅ CHANGED: Build field object with confidence
            if is_new_field:
                # NEW FIELD: Set confidence to 100 and mark as human_added
                processed_data[field_name] = {
                    "value": actual_value,
                    "confidence": 100,
                    "source": "human_added",
                    "edited_at": datetime.now().isoformat()
                }
                print(f"[INFO] Added new field: {field_name} (confidence: 100, source: human_added)")
            
            elif value_changed:
                # EDITED FIELD: Set confidence to 100 and mark as human_corrected
                processed_data[field_name] = {
                    "value": actual_value,
                    "confidence": 100,
                    "source": "human_corrected",
                    "edited_at": datetime.now().isoformat()
                }
                print(f"[INFO] Edited field: {field_name} (confidence: 100, source: human_corrected)")
            
            else:
                # UNCHANGED FIELD: Preserve original confidence and source
                if isinstance(existing_field, dict):
                    processed_data[field_name] = existing_field
                else:
                    # Old format without confidence, assume AI-extracted
                    processed_data[field_name] = {
                        "value": actual_value,
                        "confidence": 0,
                        "source": "ai_extracted"
                    }
                print(f"[INFO] Preserved field: {field_name}")
        
        # ✅ CHANGED: Build cache data (do NOT recalculate overall confidence)
        cache_data = {
            "data": processed_data,
            "extracted_at": datetime.now().isoformat(),
            "edited": True,
            "edited_at": datetime.now().isoformat(),
            "action_type": action_type
        }
        
        # ✅ CHANGED: Preserve existing overall_confidence if it exists
        if existing_cache and "overall_confidence" in existing_cache:
            cache_data["overall_confidence"] = existing_cache["overall_confidence"]
        
        if account_number:
            cache_data["account_number"] = account_number
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            print(f"[INFO] Updated cache: {cache_key}")
            print(f"[INFO] Updated fields: {list(processed_data.keys())}")
            
            return jsonify({
                "success": True,
                "message": "Page data updated successfully",
                "data": processed_data
            })
        except Exception as s3_error:
            print(f"[ERROR] Failed to update cache: {str(s3_error)}")
            return jsonify({"success": False, "message": f"Failed to update cache: {str(s3_error)}"}), 500
    
    except Exception as e:
        print(f"[ERROR] update_page_data failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
```

**Key Changes:**
- Loads existing fields from cache first
- Processes ONLY the fields in the request
- Preserves all other fields' confidence
- Sets new/edited field confidence to 100
- Preserves existing overall_confidence (doesn't recalculate)
- Logs all operations for debugging

---

### 2. get_account_page_data() Endpoint (Line 4552)

**Location:** GET endpoint for retrieving page data

```python
@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>/data")
def get_account_page_data(doc_id, account_index, page_num):
    """Extract data for a specific page of an account - with S3 caching"""
    import fitz
    import json
    
    # CRITICAL FIX: page_num from URL is 1-based (from frontend), convert to 0-based for PDF operations
    page_num_0based = page_num - 1
    
    print(f"[API] 📄 Page data request: doc_id={doc_id}, account={account_index}, page={page_num} (0-based: {page_num_0based})")
    
    # ✅ PRIORITY 0: Check S3 cache FIRST for user edits (this is where savePage stores data)
    cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
    try:
        print(f"[DEBUG] Checking S3 cache for user edits: {cache_key}")
        cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
        cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
        
        cached_fields = cached_data.get("data", {})
        print(f"[CACHE] ✅ Serving page {page_num} from S3 user edits cache (account {account_index})")
        print(f"[CACHE] 📊 Cache contains {len(cached_fields)} fields with confidence scores")
        
        response = jsonify({
            "success": True,
            "page_number": page_num + 1,
            "account_number": cached_data.get("account_number"),
            "data": cached_fields,
            "overall_confidence": cached_data.get("overall_confidence"),
            "cached": True,
            "cache_source": "s3_user_edits"
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except s3_client.exceptions.NoSuchKey:
        print(f"[DEBUG] No S3 user edits cache found, checking other sources")
    except Exception as s3_error:
        print(f"[DEBUG] S3 cache check failed: {str(s3_error)}, checking other sources")
    
    # ✅ PRIORITY 1: Check account's page_data (from background processing)
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if account_index < len(accounts):
            account = accounts[account_index]
            page_data = account.get("page_data", {})
            
            # Check if this page has data in the account's page_data (1-based keys)
            page_key = str(page_num)
            if page_key in page_data:
                print(f"[CACHE] ✅ Serving page {page_num} from account page_data (account {account_index})")
                print(f"[CACHE] 📊 Page data contains {len(page_data[page_key])} fields")
                response = jsonify({
                    "success": True,
                    "data": page_data[page_key],
                    "account_number": account.get("accountNumber", "Unknown"),
                    "cache_source": "account_page_data",
                    "cached": True
                })
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                return response
            else:
                print(f"[DEBUG] Page {page_num} not found in account page_data. Available pages: {list(page_data.keys())}")
```

**Key Changes:**
- Checks S3 user edits cache FIRST (Priority 0)
- Returns raw cached data with confidence scores intact
- Includes overall_confidence in response
- Proper cache priority order

---

## Summary of Changes

### Frontend (templates/account_based_viewer.html)

| Change | Line | Purpose |
|--------|------|---------|
| Initialize renamedFields | 988 | Prevent undefined errors |
| savePage() - send only edited fields | 2148 | Only changed fields sent to backend |
| addNewField() - send only new field | 2269 | Only new field sent to backend |
| confirmDeleteFields() - send only deleted fields | 2640 | Only deleted fields sent to backend |
| exitEditMode() - reset renamedFields | 2080 | Properly reset state |

### Backend (app_modular.py)

| Change | Line | Purpose |
|--------|------|---------|
| Load existing fields first | 6234 | Preserve other fields |
| Process only received fields | 6234 | Don't update all fields |
| Set new field confidence to 100 | 6234 | Mark as human_added |
| Set edited field confidence to 100 | 6234 | Mark as human_corrected |
| Preserve other fields' confidence | 6234 | Don't change unchanged fields |
| Preserve overall_confidence | 6234 | Don't recalculate |
| Check S3 cache first | 4552 | Get user edits first |

---

## Testing the Changes

### Test 1: Add Field
```javascript
// Frontend sends:
{
  "page_data": {
    "phone": "555-1234"
  },
  "action_type": "add"
}

// Backend returns:
{
  "success": true,
  "data": {
    "phone": {
      "value": "555-1234",
      "confidence": 100,
      "source": "human_added"
    }
  }
}
```

### Test 2: Edit Field
```javascript
// Frontend sends:
{
  "page_data": {
    "name": "Jane"
  },
  "action_type": "edit"
}

// Backend returns:
{
  "success": true,
  "data": {
    "name": {
      "value": "Jane",
      "confidence": 100,
      "source": "human_corrected"
    },
    "email": {
      "value": "jane@example.com",
      "confidence": 90,
      "source": "ai_extracted"
    }
  }
}
```

### Test 3: Delete Field
```javascript
// Frontend sends:
{
  "page_data": {
    "phone": null
  },
  "deleted_fields": ["phone"],
  "action_type": "delete"
}

// Backend returns:
{
  "success": true,
  "data": {
    "name": {
      "value": "Jane",
      "confidence": 100,
      "source": "human_corrected"
    },
    "email": {
      "value": "jane@example.com",
      "confidence": 90,
      "source": "ai_extracted"
    }
  }
}
```

---

**Last Updated:** December 18, 2025  
**Version:** 1.0 - Final
