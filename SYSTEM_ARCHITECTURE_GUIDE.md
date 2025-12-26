# System Architecture Guide - Universal IDP

## Overview

The Universal IDP system consists of three main applications that work together to process documents:

1. **simple_upload_app.py** - Simple S3 uploader (port 5001)
2. **app_modular.py** - Main IDP application (port 5015)
3. **s3_document_fetcher.py** - Background S3 poller (runs in app_modular.py)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERFACES                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  simple_upload_app.py (Port 5001)    app_modular.py (Port 5015) │
│  ├─ Upload UI                        ├─ Dashboard UI             │
│  ├─ S3 Upload                        ├─ Skills Catalog           │
│  └─ Document List                    ├─ Results Dashboard        │
│                                      └─ Document Viewer          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT PROCESSING                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  process_job() Function                                          │
│  ├─ Generate unique ID (job_id)                                 │
│  ├─ Detect document type                                        │
│  ├─ Create placeholder document                                 │
│  ├─ Save to processed_documents.json                            │
│  └─ Queue for background processing                             │
│                                                                   │
│  BackgroundDocumentProcessor                                     │
│  ├─ OCR Extraction (Textract)                                   │
│  ├─ Account Splitting                                           │
│  ├─ Page Analysis                                               │
│  └─ LLM Extraction (Claude)                                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DATA STORAGE                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  processed_documents.json (Local)                                │
│  ├─ Document metadata                                           │
│  ├─ Processing status                                           │
│  ├─ Extracted data                                              │
│  └─ Document IDs                                                │
│                                                                   │
│  AWS S3 (Cloud)                                                  │
│  ├─ uploads/ - Original PDFs                                    │
│  ├─ processing_logs/ - Status files                             │
│  └─ ocr_results/ - OCR output                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Document ID System

### ID Generation

All documents receive a unique 12-character ID generated using:

```python
doc_id = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:12]
```

**Properties:**
- Unique: Combines filename + timestamp
- Deterministic: Same input produces same ID
- Short: 12 characters (manageable)
- Consistent: Used across all upload paths

### ID Assignment Points

| Upload Path | ID Assignment | Location |
|-------------|---------------|----------|
| simple_upload_app.py | On upload | `/api/upload` endpoint |
| app_modular.py | On upload | `/process` endpoint → `process_job()` |
| S3 fetcher | On fetch | `_process_document()` method |

### ID Storage

Documents are stored with ID in `processed_documents.json`:

```json
{
  "id": "a1b2c3d4e5f6",
  "filename": "document.pdf",
  "document_name": "My Document",
  "timestamp": "20251226_131549",
  "processed_date": "2025-12-26T13:15:56.226239",
  "status": "extracting",
  "can_view": true,
  "documents": [...]
}
```

## Upload Flows

### Flow 1: simple_upload_app.py → S3 → app_modular.py

```
User uploads PDF
    ↓
simple_upload_app.py generates ID
    ↓
Document record created with ID
    ↓
Saved to processed_documents.json
    ↓
File uploaded to S3 (uploads/ folder)
    ↓
app_modular.py loads document from JSON
    ↓
Document appears on dashboard
```

**Key Points:**
- ID generated immediately on upload
- Document record saved locally
- File stored in S3
- No processing happens in simple_upload_app.py

### Flow 2: app_modular.py UI Upload

```
User uploads PDF via app_modular.py
    ↓
/process endpoint receives file
    ↓
process_job() generates job_id
    ↓
Document type detected
    ↓
Placeholder document created
    ↓
Document saved to processed_documents.json with ID
    ↓
Background processing queued
    ↓
Document appears on dashboard
    ↓
Background processor extracts data
```

**Key Points:**
- ID = job_id (same as processing job)
- Placeholder created immediately
- Background processing starts automatically
- Document visible while processing

### Flow 3: S3 Fetcher

```
S3 fetcher polls S3 (every 30 seconds)
    ↓
Unprocessed documents detected
    ↓
Document downloaded from S3
    ↓
/process endpoint called
    ↓
process_job() generates job_id
    ↓
Document saved with ID
    ↓
Background processing starts
    ↓
Document appears on dashboard
```

**Key Points:**
- Automatic polling (no user action)
- Same processing as Flow 2
- Documents appear on dashboard automatically
- Runs in background thread

## Document Lookup System

### Safe Lookup Function

```python
def find_document_by_id(doc_id: str):
    """Safely find a document by ID"""
    if not doc_id or doc_id == "undefined":
        return None
    
    for doc in processed_documents:
        if doc.get("id") == doc_id:
            return doc
    
    return None
```

**Why Safe:**
- Uses `.get("id")` (no KeyError if missing)
- Returns None instead of exception
- Handles "undefined" IDs
- Graceful degradation

### Usage Throughout App

All document lookups use this pattern:

```python
# ✅ SAFE - Used everywhere in app_modular.py
doc = find_document_by_id(doc_id)
if doc:
    # Process document
else:
    # Handle missing document
```

**NOT Used:**
```python
# ❌ UNSAFE - Never used (would cause KeyError)
doc = next((d for d in processed_documents if d["id"] == doc_id), None)
```

## Background Processing Pipeline

### Processing Stages

1. **OCR Extraction** (40-55% progress)
   - Extract text from PDF pages
   - Use Textract for scanned documents
   - Cache results for reuse

2. **Account Splitting** (55-75% progress)
   - Detect account boundaries
   - Split pages by account
   - Map pages to accounts

3. **Page Analysis** (55-75% progress)
   - Analyze page content
   - Identify document sections
   - Prepare for LLM extraction

4. **LLM Extraction** (75-95% progress)
   - Extract structured data
   - Use Claude for intelligent extraction
   - Validate extracted data

5. **Completion** (95-100% progress)
   - Finalize processing
   - Update document status
   - Make document available

### Cost Optimization

The system uses several cost optimization techniques:

1. **OCR Caching**
   - Cache OCR results per page
   - Reuse cached results
   - Avoid duplicate OCR calls

2. **Batch Processing**
   - Process multiple pages in parallel
   - Use ThreadPoolExecutor
   - Optimize API calls

3. **Selective OCR**
   - Only OCR when needed
   - Skip text-based PDFs
   - Use PyPDF for text extraction first

## API Endpoints

### Upload Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/process` | POST | Upload file for processing |
| `/upload` | POST | Alias for `/process` |
| `/api/upload` | POST | (simple_upload_app.py) Upload to S3 |

### Status Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status/<job_id>` | GET | Get processing status |
| `/api/document/<doc_id>/background-status` | GET | Get background processing status |

### Document Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/document/<doc_id>/view` | GET | View document |
| `/api/document/<doc_id>/delete` | POST | Delete document |
| `/api/document/<doc_id>/pages` | GET | Get document pages |

## Configuration

### Environment Variables

```bash
AWS_REGION=us-east-1
AWS_BUCKET=aws-idp-uploads
MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### S3 Fetcher Configuration

```python
start_s3_fetcher(
    bucket_name="aws-idp-uploads",
    region="us-east-1",
    check_interval=30  # Check every 30 seconds
)
```

### Background Processor Configuration

```python
background_processor = BackgroundDocumentProcessor(
    max_workers=5  # Max parallel processing threads
)
```

## Error Handling

### Document Not Found

```python
doc = find_document_by_id(doc_id)
if not doc:
    return jsonify({"error": "Document not found"}), 404
```

### Missing ID Field

```python
# Safe - uses .get() instead of direct access
doc_id = doc.get("id")
if not doc_id:
    return jsonify({"error": "Document has no ID"}), 400
```

### Processing Errors

```python
try:
    # Process document
except Exception as e:
    # Log error
    # Update document status to "failed"
    # Return error response
```

## Monitoring and Debugging

### Logging

All components log to stdout with prefixes:

- `[INFO]` - General information
- `[DEBUG]` - Debug information
- `[WARNING]` - Warnings
- `[ERROR]` - Errors
- `[BG_PROCESSOR]` - Background processor
- `[S3_FETCHER]` - S3 fetcher

### Status Tracking

Document status values:

- `pending` - Waiting to be processed
- `extracting` - Currently being processed
- `completed` - Processing complete
- `failed` - Processing failed

### Progress Tracking

Progress ranges:

- 0-40%: Upload and document type detection
- 40-55%: OCR extraction
- 55-75%: Account splitting and page analysis
- 75-95%: LLM extraction
- 95-100%: Completion

## Best Practices

1. **Always use find_document_by_id()**
   - Never access document["id"] directly
   - Always check if document exists

2. **Generate IDs consistently**
   - Use same ID generation across all paths
   - Never manually assign IDs

3. **Save documents immediately**
   - Save to processed_documents.json on upload
   - Don't wait for processing to complete

4. **Handle missing documents gracefully**
   - Return 404 instead of 500
   - Log missing documents for debugging

5. **Monitor background processing**
   - Check processing status regularly
   - Handle timeouts gracefully
   - Provide user feedback on progress

## Troubleshooting

### KeyError: 'id'

**Cause:** Document missing ID field

**Solution:**
1. Check processed_documents.json
2. Add ID to document if missing
3. Use find_document_by_id() for lookups

### Document not appearing on dashboard

**Cause:** Document not saved to processed_documents.json

**Solution:**
1. Check upload endpoint logs
2. Verify process_job() is called
3. Check file permissions

### S3 fetcher not detecting documents

**Cause:** S3 fetcher not running or S3 access issues

**Solution:**
1. Check S3 fetcher logs
2. Verify AWS credentials
3. Check S3 bucket permissions
4. Verify bucket name and region

### Background processing stuck

**Cause:** Processing thread hung or error

**Solution:**
1. Check background processor logs
2. Restart background processor
3. Check AWS API limits
4. Check document file integrity

## Future Improvements

1. **Database Migration**
   - Replace JSON with database
   - Better concurrent access
   - Transaction support

2. **Distributed Processing**
   - Use message queue (SQS)
   - Horizontal scaling
   - Load balancing

3. **Enhanced Monitoring**
   - Real-time dashboards
   - Performance metrics
   - Error tracking

4. **Advanced Features**
   - Document versioning
   - Audit trails
   - Batch processing
   - Scheduled processing
