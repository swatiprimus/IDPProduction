# Death Certificate Background Processing Fix

## Problem Identified

The background processing system was designed primarily for loan documents and wasn't working correctly for death certificates and other document types because:

1. **Pipeline Mismatch**: The system tried to run account splitting on death certificates (which don't have accounts)
2. **Update Logic**: The document update logic only handled loan documents with accounts
3. **Cache Structure**: The caching system was designed for page-by-page processing, not full document extraction

## ✅ Solution Implemented

### 1. **Dual Processing Pipelines**

**For Loan Documents:**
```
OCR → Account Splitting → Page Analysis → LLM Extraction (per page)
```

**For Other Documents (Death Certificates, etc.):**
```
OCR → Direct LLM Extraction (full document) → Field Extraction
```

### 2. **Document Type Detection**

Added `_get_document_type()` method that:
- Reads document type from the main document record
- Routes processing to the appropriate pipeline
- Handles unknown document types gracefully

### 3. **Direct LLM Extraction**

Added `_stage_direct_llm_extraction()` method that:
- Processes the entire document text at once (not page-by-page)
- Uses the comprehensive extraction prompt
- Caches results for the full document
- Extracts all fields in a single AI call

### 4. **Enhanced Document Updates**

Modified `_update_main_document_record()` to handle:
- **Loan documents**: Updates with accounts and account-based fields
- **Other documents**: Updates with extracted fields, accuracy scores, and field statistics
- **Field counting**: Calculates filled vs total fields for accuracy scoring
- **Review flags**: Sets needs_human_review based on accuracy score

### 5. **Improved API Endpoints**

Updated refresh endpoint to:
- Detect document type automatically
- Handle different result structures (accounts vs extracted fields)
- Return appropriate response format for each document type
- Check cached extraction results for non-loan documents

## 🚀 How It Works Now

### For Death Certificates:

1. **Upload**: Document uploaded → Type detected as "death_certificate"
2. **Background Processing**: 
   - Stage 1: OCR extraction of full document text
   - Stage 2: Account splitting (skipped)
   - Stage 3: Page analysis (skipped)  
   - Stage 4: Direct LLM extraction of all fields
3. **Caching**: Results cached as `document_extraction_cache/{doc_id}/full_extraction.json`
4. **Update**: Document record updated with extracted fields
5. **UI Access**: Fields immediately available when user opens document

### Processing Stages for Death Certificates:

- ✅ **OCR Extraction**: Extracts full document text
- ⏭️ **Account Splitting**: Skipped (not applicable)
- ⏭️ **Page Analysis**: Skipped (not applicable)
- ✅ **LLM Extraction**: Extracts all fields from full document text
- ✅ **Completed**: Document updated with extracted fields

## 🧪 Testing

### Run Death Certificate Test:
```bash
python test_death_certificate_processing.py
```

This will:
1. Find death certificate documents (or use any available document)
2. Force background processing
3. Monitor progress through all stages
4. Verify extracted fields are saved to document
5. Test page extraction using cached results

### Expected Results:

- **Death certificates**: Should extract fields like Full_Name, Date_of_Death, Certificate_Number, etc.
- **Other documents**: Should extract relevant fields based on document type
- **All documents**: Should show "background_processed": true when complete
- **UI**: Should display extracted fields immediately after processing

## 🔧 Key Changes Made

### 1. **Pipeline Routing** (`_process_document_pipeline`)
```python
if doc_type == "loan_document":
    # Use account-based pipeline
else:
    # Use direct extraction pipeline
```

### 2. **Direct Extraction** (`_stage_direct_llm_extraction`)
```python
# Extract from full document text, not individual pages
extracted_fields = self._extract_with_llm(full_text, "N/A", prompt)
```

### 3. **Document Updates** (`_update_main_document_record`)
```python
if doc_type == "loan_document":
    # Update with accounts
else:
    # Update with extracted fields
```

### 4. **API Response** (`refresh_document_from_background`)
```python
if doc_type == "loan_document":
    return accounts_response
else:
    return extracted_fields_response
```

## 📊 Benefits

1. **Universal Support**: Now works for all document types, not just loan documents
2. **Efficient Processing**: Death certificates processed in single AI call vs multiple page calls
3. **Proper Caching**: Full document extraction cached appropriately
4. **Accurate Updates**: Document records updated with correct field structure
5. **UI Integration**: Results immediately visible in UI after processing

## 🔍 Verification

### Check if it's working:

1. **Upload a death certificate** via the web interface
2. **Check background status**: `GET /api/document/{doc_id}/background-status`
3. **Monitor progress**: Should show stages completing (OCR → Direct LLM → Completed)
4. **Refresh document**: `POST /api/document/{doc_id}/refresh-from-background`
5. **Verify fields**: Document should have extracted fields like Full_Name, Date_of_Death, etc.
6. **Check UI**: Fields should be visible when opening the document

### Troubleshooting:

- **No fields extracted**: Check if LLM extraction completed successfully
- **Processing stuck**: Verify document type detection is working
- **Cache issues**: Check S3 for `document_extraction_cache/{doc_id}/full_extraction.json`
- **UI not updating**: Ensure refresh endpoint is being called after processing

The system now provides comprehensive background processing for all document types, with death certificates getting the same automatic processing as loan documents, but using the appropriate extraction method for their structure.