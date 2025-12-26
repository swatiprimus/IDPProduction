# Developer Quick Reference - Universal IDP

## Quick Start

### Starting the Applications

```bash
# Terminal 1: Start main app (port 5015)
python app_modular.py

# Terminal 2: Start upload app (port 5001)
python simple_upload_app.py
```

### Accessing the Applications

- **Main Dashboard**: http://localhost:5015
- **Upload Interface**: http://localhost:5001
- **Skills Catalog**: http://localhost:5015/skills_catalog

## Document ID System - Quick Reference

### How IDs are Generated

```python
import hashlib
import time

doc_id = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:12]
# Example: "a1b2c3d4e5f6"
```

### Where IDs are Generated

| Component | Location | Function |
|-----------|----------|----------|
| simple_upload_app.py | `/api/upload` | Line ~120 |
| app_modular.py | `/process` → `process_job()` | Line ~3799 |
| s3_document_fetcher.py | `_process_document()` | Uses `/process` endpoint |

### Safe Document Lookup

```python
# ✅ ALWAYS USE THIS
doc = find_document_by_id(doc_id)
if doc:
    # Process document
else:
    return jsonify({"error": "Document not found"}), 404

# ❌ NEVER USE THIS (causes KeyError)
doc = next((d for d in processed_documents if d["id"] == doc_id), None)
```

## Common Tasks

### Add a New Document Endpoint

```python
@app.route("/api/document/<doc_id>/my-endpoint", methods=["GET"])
def my_endpoint(doc_id):
    """My new endpoint"""
    # ✅ Use safe lookup
    doc = find_document_by_id(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    
    # Process document
    return jsonify({"success": True, "data": doc})
```

### Process a Document in Background

```python
# Queue document for background processing
background_processor.queue_document_for_processing(
    doc_id=doc_id,
    pdf_path=pdf_path,
    priority=1  # 1=high, 2=normal
)
```

### Get Processing Status

```python
# Get background processing status
status = background_processor.get_document_status(doc_id)
if status:
    stage = status.get("stage")
    progress = status.get("progress")
    print(f"Stage: {stage}, Progress: {progress}%")
```

### Save Document Changes

```python
# Update document in memory
doc["status"] = "completed"
doc["extracted_data"] = {...}

# Save to disk
save_documents_db(processed_documents)
```

## File Structure

```
project/
├── app_modular.py              # Main application
├── simple_upload_app.py        # Upload interface
├── s3_document_fetcher.py      # S3 polling
├── prompts.py                  # LLM prompts
├── processed_documents.json    # Document database
├── app/
│   └── services/
│       ├── textract_service.py
│       ├── document_detector.py
│       ├── account_splitter.py
│       ├── loan_processor.py
│       ├── cost_optimized_processor.py
│       ├── ocr_cache_manager.py
│       └── cost_tracker.py
├── templates/
│   ├── home.html
│   ├── skills_catalog.html
│   ├── results_dashboard.html
│   ├── upload.html
│   └── ...
├── static/
│   ├── upload.js
│   ├── upload.css
│   ├── results_dashboard.js
│   └── results_dashboard.css
└── ocr_results/                # OCR output files
```

## Key Functions

### find_document_by_id()

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

**Usage:**
```python
doc = find_document_by_id("a1b2c3d4e5f6")
```

### process_job()

```python
def process_job(job_id, file_bytes, filename, use_ocr, document_name=None):
    """Background worker to process documents"""
    # 1. Save PDF locally
    # 2. Detect document type
    # 3. Create placeholder document
    # 4. Save to processed_documents.json
    # 5. Queue for background processing
```

**Called by:**
- `/process` endpoint
- S3 fetcher

### load_documents_db()

```python
def load_documents_db():
    """Load documents from processed_documents.json"""
    if os.path.exists('processed_documents.json'):
        with open('processed_documents.json', 'r') as f:
            return json.load(f)
    return []
```

### save_documents_db()

```python
def save_documents_db(documents):
    """Save documents to processed_documents.json"""
    with open('processed_documents.json', 'w') as f:
        json.dump(documents, f, indent=2)
```

## API Quick Reference

### Upload Document

```bash
curl -X POST http://localhost:5015/process \
  -F "file=@document.pdf" \
  -F "document_name=My Document"
```

**Response:**
```json
{
  "success": true,
  "job_id": "a1b2c3d4e5f6",
  "message": "File uploaded successfully. Processing started."
}
```

### Get Processing Status

```bash
curl http://localhost:5015/status/a1b2c3d4e5f6
```

**Response:**
```json
{
  "status": "🤖 LLM Processing in progress...",
  "progress": 85,
  "is_complete": false,
  "stage": "llm_extraction"
}
```

### Get Document

```bash
curl http://localhost:5015/api/document/a1b2c3d4e5f6/view
```

**Response:**
```json
{
  "id": "a1b2c3d4e5f6",
  "filename": "document.pdf",
  "status": "completed",
  "documents": [...]
}
```

### Delete Document

```bash
curl -X POST http://localhost:5015/api/document/a1b2c3d4e5f6/delete
```

## Debugging Tips

### Check Document in Database

```python
# In Python shell
import json
with open('processed_documents.json', 'r') as f:
    docs = json.load(f)
    for doc in docs:
        print(f"ID: {doc.get('id')}, Name: {doc.get('filename')}")
```

### Check Processing Status

```python
# In Python shell
status = background_processor.get_document_status("a1b2c3d4e5f6")
print(f"Status: {status}")
```

### Check S3 Fetcher Status

```python
# In Python shell
fetcher = get_s3_fetcher()
print(f"Running: {fetcher.is_running}")
print(f"Bucket: {fetcher.bucket_name}")
```

### Enable Debug Logging

```python
# In app_modular.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Common Errors and Solutions

### KeyError: 'id'

**Error:**
```
KeyError: 'id'
File "app_modular.py", line 4110, in view_document_pages
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
```

**Solution:**
```python
# ❌ Wrong
doc = next((d for d in processed_documents if d["id"] == doc_id), None)

# ✅ Right
doc = find_document_by_id(doc_id)
```

### Document Not Found

**Error:**
```
Document not found on dashboard
```

**Solution:**
1. Check if document is in processed_documents.json
2. Verify document has ID field
3. Check if upload completed successfully
4. Check browser console for errors

### S3 Fetcher Not Working

**Error:**
```
S3 fetcher not detecting new documents
```

**Solution:**
1. Check S3 fetcher logs in console
2. Verify AWS credentials
3. Check S3 bucket name and region
4. Verify bucket has documents in `uploads/` folder
5. Check if status files exist in `processing_logs/` folder

### Background Processing Stuck

**Error:**
```
Document stuck at 50% progress
```

**Solution:**
1. Check background processor logs
2. Restart the application
3. Check AWS API rate limits
4. Check document file integrity
5. Check CloudWatch logs for errors

## Performance Tips

1. **Batch Processing**
   - Process multiple documents together
   - Use ThreadPoolExecutor for parallel processing

2. **Caching**
   - OCR results are cached per page
   - Reuse cached results to save costs

3. **Selective OCR**
   - Skip OCR for text-based PDFs
   - Use PyPDF for text extraction first

4. **Async Processing**
   - Use background processor for long tasks
   - Don't block user requests

## Security Considerations

1. **Input Validation**
   - Validate file types (PDF only)
   - Validate file sizes
   - Sanitize filenames

2. **Access Control**
   - Verify user permissions
   - Check document ownership
   - Validate document IDs

3. **Data Protection**
   - Encrypt sensitive data
   - Secure S3 bucket
   - Use IAM roles for AWS access

4. **Error Handling**
   - Don't expose internal errors
   - Log errors securely
   - Return generic error messages

## Testing

### Unit Tests

```python
def test_find_document_by_id():
    """Test safe document lookup"""
    doc = find_document_by_id("a1b2c3d4e5f6")
    assert doc is not None
    assert doc["id"] == "a1b2c3d4e5f6"

def test_find_document_not_found():
    """Test missing document"""
    doc = find_document_by_id("nonexistent")
    assert doc is None

def test_find_document_undefined():
    """Test undefined ID"""
    doc = find_document_by_id("undefined")
    assert doc is None
```

### Integration Tests

```python
def test_upload_and_process():
    """Test complete upload flow"""
    # 1. Upload document
    # 2. Check document appears on dashboard
    # 3. Check document has ID
    # 4. Check background processing starts
    # 5. Check processing completes
```

## Resources

- **AWS Documentation**: https://docs.aws.amazon.com/
- **Claude API**: https://docs.anthropic.com/
- **Flask Documentation**: https://flask.palletsprojects.com/
- **Boto3 Documentation**: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html

## Support

For issues or questions:

1. Check the logs in console
2. Review FINAL_VERIFICATION_COMPLETE.md
3. Review SYSTEM_ARCHITECTURE_GUIDE.md
4. Check processed_documents.json for data issues
5. Verify AWS credentials and permissions
