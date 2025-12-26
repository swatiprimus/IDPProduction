# S3 Document Fetcher - Code Examples

## How It Works: Complete Flow

### 1. Application Startup

When you run `python app_modular.py`:

```python
if __name__ == "__main__":
    print(f"[INFO] Starting Universal IDP - region: {AWS_REGION}, model: {MODEL_ID}")
    
    # Initialize background processor for skill-based processing
    init_background_processor()
    
    # Start S3 document fetcher (polls S3 every 30 seconds)
    from s3_document_fetcher import start_s3_fetcher, stop_s3_fetcher
    start_s3_fetcher(bucket_name="aws-idp-uploads", region=AWS_REGION, check_interval=30)
    
    try:
        app.run(debug=True, port=5015)
    except KeyboardInterrupt:
        print("[INFO] Application interrupted by user")
    finally:
        stop_s3_fetcher()
        cleanup_background_processor()
```

**Output:**
```
[INFO] Starting Universal IDP - region: us-east-1, model: anthropic.claude-3-sonnet-20240229-v1:0
[BG_PROCESSOR] 🚀 Advanced background processor initialized with multi-stage pipeline
[BG_PROCESSOR] 🟢 Background processing system started and monitoring for documents
[S3_FETCHER] 🚀 Initialized
[S3_FETCHER]    Bucket: aws-idp-uploads
[S3_FETCHER]    Region: us-east-1
[S3_FETCHER]    Check interval: 30s
[S3_FETCHER] ✅ Started - polling S3 every 30 seconds
```

### 2. S3 Fetcher Polling Loop

Every 30 seconds, the fetcher checks S3:

```python
def _fetch_loop(self):
    """Main polling loop - runs in background thread"""
    while self.is_running:
        try:
            # Get list of unprocessed documents
            unprocessed = self._get_unprocessed_documents()
            
            if unprocessed:
                print(f"[S3_FETCHER] 📋 Found {len(unprocessed)} unprocessed document(s)")
                
                # Process each document
                for doc_key in unprocessed:
                    if not self.is_running:
                        break
                    
                    self._process_document(doc_key)
            else:
                print(f"[S3_FETCHER] ✅ No new documents (checked at {datetime.now().strftime('%H:%M:%S')})")
            
            # Wait before next check
            time.sleep(self.check_interval)
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Error in fetch loop: {str(e)}")
            time.sleep(self.check_interval)
```

**Output when documents found:**
```
[S3_FETCHER] 📋 Found 2 unprocessed document(s)
[S3_FETCHER]    🆕 Found unprocessed: uploads/loan_statement.pdf
[S3_FETCHER]    🆕 Found unprocessed: uploads/death_cert.pdf
[S3_FETCHER] 📊 S3 scan: 5 total files, 2 unprocessed
```

### 3. Document Detection

For each unprocessed document:

```python
def _get_unprocessed_documents(self) -> list:
    """Get list of unprocessed documents from S3"""
    unprocessed = []
    
    # List all objects in uploads folder
    paginator = self.s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(
        Bucket=self.bucket_name,
        Prefix='uploads/'
    )
    
    for page in pages:
        if 'Contents' not in page:
            continue
        
        for obj in page['Contents']:
            key = obj['Key']
            
            # Skip if not a PDF
            if not key.lower().endswith('.pdf'):
                print(f"[S3_FETCHER]    ⏭️ Skipping non-PDF: {key}")
                continue
            
            # Check if already processed
            if self._is_processed(key):
                print(f"[S3_FETCHER]    ✅ Already processed: {key}")
                continue
            
            # This is an unprocessed document
            print(f"[S3_FETCHER]    🆕 Found unprocessed: {key}")
            unprocessed.append(key)
    
    return unprocessed
```

### 4. Document Processing with Skill-Based System

When a document is found, it's processed through the skill system:

```python
def _process_document(self, file_key: str) -> bool:
    """
    Process a single document by calling the /process endpoint
    This ensures the document is processed with skill-based processing
    """
    file_name = file_key.split('/')[-1]
    
    try:
        print(f"[S3_FETCHER] 🔄 Processing: {file_name}")
        
        # Mark as processing
        self._update_status(file_key, 'processing')
        
        # Download document
        pdf_bytes = self._download_document(file_key)
        if not pdf_bytes:
            self._update_status(file_key, 'failed', 'Download failed')
            return False
        
        # Create temporary file for upload
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            # Call the /process endpoint (same as UI upload)
            # This will trigger skillProcessDocument through the background processor
            print(f"[S3_FETCHER]    📤 Calling /process endpoint with skill-based processing...")
            
            with open(tmp_path, 'rb') as f:
                files = {'file': (file_name, f, 'application/pdf')}
                data = {'document_name': file_name}
                response = requests.post('http://localhost:5015/process', files=files, data=data, timeout=300)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    job_id = data.get('job_id')
                    print(f"[S3_FETCHER]    ✅ Job submitted: {job_id}")
                    print(f"[S3_FETCHER]    📋 Document will be processed with skill-based system")
                    print(f"[S3_FETCHER]    🎯 Document will appear on UI dashboard once processing completes")
                    
                    # Wait for processing to complete
                    print(f"[S3_FETCHER]    ⏳ Waiting for background processing to complete...")
                    
                    max_wait = 600  # 10 minutes max wait
                    check_interval = 5  # Check every 5 seconds
                    elapsed = 0
                    
                    while elapsed < max_wait:
                        # Check processing status
                        status_response = requests.get(f'http://localhost:5015/status/{job_id}', timeout=30)
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            progress = status_data.get('progress', 0)
                            is_complete = status_data.get('is_complete', False)
                            stage = status_data.get('stage', 'unknown')
                            
                            print(f"[S3_FETCHER]    📊 Progress: {progress}% - Stage: {stage}")
                            
                            if is_complete:
                                print(f"[S3_FETCHER]    ✅ Processing complete!")
                                print(f"[S3_FETCHER]    🎉 Document {file_name} is now available on UI")
                                self._update_status(file_key, 'completed', doc_type='skill_processed')
                                return True
                        
                        time.sleep(check_interval)
                        elapsed += check_interval
                    
                    # Timeout reached
                    print(f"[S3_FETCHER]    ⚠️ Processing timeout after {max_wait}s")
                    print(f"[S3_FETCHER]    📋 Document may still be processing in background")
                    self._update_status(file_key, 'completed', doc_type='skill_processed')
                    return True
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        
    except Exception as e:
        print(f"[S3_FETCHER] ❌ Error processing {file_name}: {str(e)}")
        self._update_status(file_key, 'failed', str(e))
        return False
```

**Output during processing:**
```
[S3_FETCHER] 🔄 Processing: loan_statement.pdf
[S3_FETCHER]    📤 Calling /process endpoint with skill-based processing...
[S3_FETCHER]    ✅ Job submitted: abc123def456
[S3_FETCHER]    📋 Document will be processed with skill-based system
[S3_FETCHER]    🎯 Document will appear on UI dashboard once processing completes
[S3_FETCHER]    ⏳ Waiting for background processing to complete...
[S3_FETCHER]    📊 Progress: 40% - Stage: ocr_extraction
[S3_FETCHER]    📊 Progress: 50% - Stage: ocr_extraction
[S3_FETCHER]    📊 Progress: 60% - Stage: account_splitting
[S3_FETCHER]    📊 Progress: 75% - Stage: llm_extraction
[S3_FETCHER]    📊 Progress: 90% - Stage: llm_extraction
[S3_FETCHER]    ✅ Processing complete!
[S3_FETCHER]    🎉 Document loan_statement.pdf is now available on UI
```

### 5. Background Processing Pipeline

Once `/process` is called, the document goes through the skill-based pipeline:

```python
def process_job(job_id: str, file_bytes: bytes, filename: str, use_ocr: bool, document_name: str = None):
    """Background worker to process documents - FAST upload with placeholder creation"""
    
    # 1. Save PDF locally
    saved_pdf_path = f"{OUTPUT_DIR}/{timestamp}_{filename}"
    with open(saved_pdf_path, 'wb') as f:
        f.write(file_bytes)
    
    # 2. Detect document type
    detected_doc_type = detect_document_type(first_page_text)
    print(f"[INFO] ✅ Detected document type: {detected_doc_type}")
    
    # 3. Create placeholder document immediately
    document_record = {
        "id": job_id,
        "filename": filename,
        "document_type": detected_doc_type,
        "status": "extracting",
        "can_view": True  # Allow immediate viewing
    }
    processed_documents.append(document_record)
    save_documents_db(processed_documents)
    
    # 4. Queue for background processing
    background_processor.queue_document_for_processing(job_id, saved_pdf_path, priority=1)
    print(f"[BG_PROCESSOR] 🚀 Starting background processing for {job_id}")
```

### 6. Multi-Stage Background Processing

The background processor handles the skill-based extraction:

```python
def _process_document_pipeline(self, doc_id: str):
    """Complete processing pipeline for a document"""
    
    # Stage 1: Page-by-page OCR with caching
    print(f"[BG_PROCESSOR] ⚡ Stage 1/4: Starting page-by-page OCR with smart caching...")
    page_ocr_results, total_pages = self._stage_page_by_page_ocr(doc_id, pdf_path)
    
    # Stage 2-4: Cost-optimized processing (account discovery + data extraction)
    print(f"[BG_PROCESSOR] 🚀 Stage 2-4 COMBINED: Starting cost-optimized processing...")
    accounts, page_mapping = self._stage_cost_optimized_processing(doc_id, page_ocr_results, total_pages, doc_type)
    
    # Update document with results
    self._update_main_document_record(doc_id, accounts, total_pages, doc_type)
    
    print(f"[BG_PROCESSOR] 🎉 PIPELINE COMPLETED for {doc_id}")
```

### 7. Results on Dashboard

Once processing completes, the document appears on the dashboard with extracted data:

```
Dashboard View:
┌─────────────────────────────────────────┐
│ 🏦 Loan Statement                       │
│ loan_statement.pdf                      │
│ Processed: 2024-01-15 14:30:45         │
│                                         │
│ Accounts Found: 3                       │
│ ├─ Checking Account (****1234)         │
│ │  Balance: $5,234.56                  │
│ │  Interest Rate: 0.01%                │
│ ├─ Savings Account (****5678)          │
│ │  Balance: $12,456.78                 │
│ │  Interest Rate: 4.50%                │
│ └─ Credit Card (****9012)              │
│    Balance: $3,456.00                  │
│    Interest Rate: 18.99%               │
│                                         │
│ [View Details] [Export] [Edit]         │
└─────────────────────────────────────────┘
```

## Example: Complete Workflow

### Step 1: Upload to S3
```bash
aws s3 cp my_loan_statement.pdf s3://aws-idp-uploads/uploads/
```

### Step 2: Application Detects and Processes
```
[S3_FETCHER] 🔄 Processing: my_loan_statement.pdf
[S3_FETCHER]    📤 Calling /process endpoint with skill-based processing...
[S3_FETCHER]    ✅ Job submitted: abc123def456
[S3_FETCHER]    ⏳ Waiting for background processing to complete...

[BG_PROCESSOR] 🚀 Starting OPTIMIZED processing pipeline for abc123def456
[BG_PROCESSOR] 📋 Document type detected: loan_document
[BG_PROCESSOR] ⚡ Stage 1/4: Starting page-by-page OCR with smart caching...
[BG_PROCESSOR] ✅ Stage 1/4: Page-by-page OCR completed (5 pages)
[BG_PROCESSOR] 🚀 Stage 2-4 COMBINED: Starting cost-optimized processing...
[BG_PROCESSOR] ✅ Stage 2-4 COMBINED: Cost-optimized processing completed (3 accounts)
[BG_PROCESSOR] 🎉 PIPELINE COMPLETED for abc123def456

[S3_FETCHER]    ✅ Processing complete!
[S3_FETCHER]    🎉 Document my_loan_statement.pdf is now available on UI
```

### Step 3: View on Dashboard
- Open http://localhost:5015
- Document appears with all extracted accounts
- Click to view details, edit, or export

## Monitoring and Debugging

### Check S3 Status Files
```bash
# View processing status
aws s3 cp s3://aws-idp-uploads/processing_logs/uploads/my_loan_statement.pdf.status.json - | jq .

# Output:
{
  "file_key": "uploads/my_loan_statement.pdf",
  "file_name": "my_loan_statement.pdf",
  "status": "completed",
  "processed_date": "2024-01-15T14:35:22.123456",
  "success": true,
  "result_key": "results/my_loan_statement.pdf.result.json"
}
```

### Check Processing Results
```bash
# View extracted data
aws s3 cp s3://aws-idp-uploads/results/my_loan_statement.pdf.result.json - | jq .

# Output:
{
  "file_key": "uploads/my_loan_statement.pdf",
  "file_name": "my_loan_statement.pdf",
  "document_type": "loan_document",
  "processing_date": "2024-01-15T14:35:22.123456",
  "extracted_data": {
    "accounts": [
      {
        "account_type": "Checking",
        "account_number": "****1234",
        "balance": "$5,234.56",
        "interest_rate": "0.01%"
      },
      ...
    ]
  }
}
```

### Check Local Database
```bash
# View processed documents
cat processed_documents.json | jq '.[] | {filename, document_type, status, accounts_found}'

# Output:
{
  "filename": "my_loan_statement.pdf",
  "document_type": "loan_document",
  "status": "completed",
  "accounts_found": 3
}
```

## Performance Metrics

### Processing Time
- **OCR Extraction**: ~2-5 seconds per page
- **Account Splitting**: ~1-2 seconds per document
- **LLM Extraction**: ~3-5 seconds per page
- **Total**: ~30-60 seconds for 5-page loan document

### Cost Tracking
```bash
curl http://localhost:5015/api/costs | jq .

# Output:
{
  "textract_cost": 0.0015,
  "bedrock_cost": 0.0045,
  "s3_cost": 0.0001,
  "total_cost": 0.0061
}
```

## Troubleshooting Examples

### Issue: Document not appearing on dashboard

**Check logs:**
```bash
# Look for S3_FETCHER messages
tail -f app.log | grep S3_FETCHER

# Should see:
# [S3_FETCHER] 🔄 Processing: document.pdf
# [S3_FETCHER]    ✅ Job submitted: abc123def456
```

**Check S3:**
```bash
aws s3 ls s3://aws-idp-uploads/uploads/
# Should show your document
```

**Check status:**
```bash
curl http://localhost:5015/status/abc123def456
# Should show progress
```

### Issue: Processing stuck at certain stage

**Check background processor:**
```bash
curl http://localhost:5015/api/background-processor/status

# Output:
{
  "is_running": true,
  "active_documents": 1,
  "documents": {
    "abc123def456": {
      "stage": "llm_extraction",
      "progress": 75,
      "pages_processed": 3,
      "total_pages": 5
    }
  }
}
```

**Restart if needed:**
```bash
curl -X POST http://localhost:5015/api/background-processor/restart
```

## Next Steps

1. Upload documents to S3
2. Monitor processing in logs
3. View results on dashboard
4. Export or edit as needed
5. Adjust configuration if needed

For more details, see `S3_FETCHER_INTEGRATION.md`
