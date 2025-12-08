# Performance Optimization & Fixes

## Issues Fixed

### 1. Document Name Changing ✅ FIXED
**Problem**: Document names were being auto-generated, overwriting the user's chosen filename.

**Root Cause**: Line 1585 in `app_modular.py` was auto-generating names like "Loan/Account Document - 2025-12-06" even when user provided a filename.

**Solution**: Now uses the filename (without extension) as the document name.
```python
# Before:
document_name = f"{doc_type_name} - {date_str}"  # Auto-generated

# After:
document_name = filename.rsplit('.', 1)[0]  # Use filename without extension
```

---

### 2. Account Splitting Timing ✅ OPTIMIZED
**Question**: When does account splitting happen?

**Answer**: Account splitting happens **during Textract processing** (early in the pipeline):

```
Upload → Textract OCR → Split Accounts → Detect Type → Save to DB → Complete
         (1-2 min)      (instant)        (instant)     (instant)
```

**Flow**:
1. **Line 1526**: Quick account count check using `split_accounts_strict(text)`
2. **Loan Processor**: Splits full document text into account chunks
3. **No LLM calls during upload** - just identifies account numbers
4. **Data extraction happens on-demand** when user views a page

**Performance**: Splitting is FAST (regex-based, no AI), happens once during upload.

---

### 3. Processing Speed ✅ OPTIMIZED

#### Problem: Why was it slow?
The pre-caching process was doing expensive operations for EVERY page:

**For a 27-page document:**
- 27 × Textract OCR calls (~$0.0015 each = $0.04)
- 27 × Bedrock AI extractions (~$0.015 each = $0.40)
- Total: ~$0.44 per document + 10-15 minutes processing time

#### Solution: On-Demand Extraction
**Pre-caching is now DISABLED by default**

**New Flow**:
```
Upload → Textract (full doc) → Split Accounts → Save → ✅ DONE (1-2 min)
                                                          
When user clicks page → Extract that page only → Cache result
                        (2-3 seconds)            (reused next time)
```

*