# S3 Document Fetcher Integration with Skill-Based Processing

## Overview

The S3 Document Fetcher automatically polls your AWS S3 bucket for new documents and processes them using the skill-based document processing system. Documents fetched from S3 are processed exactly like documents uploaded through the UI and appear on the dashboard once processing completes.

## How It Works

### 1. **Automatic Polling**
- The fetcher runs in a background thread and checks S3 every 30 seconds
- It looks for unprocessed PDF files in the `uploads/` folder of your S3 bucket
- Only documents that haven't been processed before are picked up

### 2. **Skill-Based Processing**
When a document is found, the fetcher:
1. Downloads the PDF from S3
2. Calls the `/process` endpoint (same as UI upload)
3. The document goes through the **skill-based processing pipeline**:
   - **Document Type Detection** - Identifies if it's a loan document, death certificate, etc.
   - **Background Processing** - Queues document for multi-stage processing
   - **OCR Extraction** - Extracts text from PDF pages (with caching)
   - **Account Splitting** - For loan documents, splits into individual accounts
   - **LLM Extraction** - Extracts structured data using Claude/Bedrock
   - **UI Display** - Document appears on dashboard with extracted data

### 3. **Status Tracking**
- Processing status is saved to S3 at: `processing_logs/{file_key}.status.json`
- Local `processed_documents.json` is updated with document metadata
- Documents are marked as "completed" once processing finishes

## Configuration

### S3 Bucket Setup

1. **Create S3 bucket** (if not already created):
   ```bash
   aws s3 mb s3://aws-idp-uploads --region us-east-1
   ```

2. **Upload documents** to the `uploads/` folder:
   ```bash
   aws s3 cp document.pdf s3://aws-idp-uploads/uploads/
   ```

3. **Folder structure**:
   ```
   aws-idp-uploads/
   ├── uploads/                    # Where you upload documents
   │   ├── document1.pdf
   │   ├── document2.pdf
   │   └── ...
   ├── processing_logs/            # Status files (auto-created)
   │   ├── uploads/document1.pdf.status.json
   │   └── ...
   ├── results/                    # Processing results (auto-created)
   │   ├── document1.pdf.result.json
   │   └── ...
   └── processed/                  # Moved after processing (auto-created)
       ├── document1.pdf
       └── ...
   ```

### Application Configuration

The S3 fetcher is automatically started when you run the app:

```python
if __name__ == "__main__":
    print(f"[INFO] Starting Universal IDP - region: {AWS_REGION}, model: {MODEL_ID}")
    
    # Initialize background processor
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

### AWS Credentials

Make sure your AWS credentials are configured:

```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Option 3: IAM Role (if running on EC2)
# Attach IAM role with S3 permissions to EC2 instance
```

## Processing Flow

### Document Upload to UI Display

```
1. Document uploaded to S3 (uploads/ folder)
   ↓
2. S3 Fetcher detects new document (every 30 seconds)
   ↓
3. Fetcher downloads PDF from S3
   ↓
4. Fetcher calls /process endpoint
   ↓
5. Document type detected (loan, death cert, etc.)
   ↓
6. Placeholder document created immediately
   ↓
7. Document appears on UI dashboard
   ↓
8. Background processing starts:
   - OCR extraction (page-by-page with caching)
   - Account splitting (for loan documents)
   - LLM extraction (structured data)
   ↓
9. Processing completes
   ↓
10. Document updated on UI with extracted data
    ↓
11. Status saved to S3 (processing_logs/)
    ↓
12. Document moved to processed/ folder
```

## Monitoring

### Check Processing Status

**In Application Logs:**
```
[S3_FETCHER] 🚀 Initialized
[S3_FETCHER]    Bucket: aws-idp-uploads
[S3_FETCHER]    Region: us-east-1
[S3_FETCHER]    Check interval: 30s
[S3_FETCHER] ✅ Started - polling S3 every 30 seconds
[S3_FETCHER] 📋 Found 2 unprocessed document(s)
[S3_FETCHER] 🔄 Processing: document1.pdf
[S3_FETCHER]    📤 Calling /process endpoint with skill-based processing...
[S3_FETCHER]    ✅ Job submitted: abc123def456
[S3_FETCHER]    📋 Document will be processed with skill-based system
[S3_FETCHER]    🎯 Document will appear on UI dashboard once processing completes
[S3_FETCHER]    ⏳ Waiting for background processing to complete...
[S3_FETCHER]    📊 Progress: 40% - Stage: ocr_extraction
[S3_FETCHER]    📊 Progress: 60% - Stage: account_splitting
[S3_FETCHER]    📊 Progress: 90% - Stage: llm_extraction
[S3_FETCHER]    ✅ Processing complete!
[S3_FETCHER]    🎉 Document document1.pdf is now available on UI
```

**Check S3 Status Files:**
```bash
# List all processing status files
aws s3 ls s3://aws-idp-uploads/processing_logs/

# View status of specific document
aws s3 cp s3://aws-idp-uploads/processing_logs/uploads/document1.pdf.status.json - | jq .
```

**Check Local Database:**
```bash
# View processed_documents.json
cat processed_documents.json | jq '.[] | {filename, document_type, status}'
```

## Troubleshooting

### Documents Not Being Picked Up

1. **Check S3 bucket name and region:**
   ```python
   start_s3_fetcher(bucket_name="aws-idp-uploads", region="us-east-1")
   ```

2. **Verify AWS credentials:**
   ```bash
   aws s3 ls s3://aws-idp-uploads/uploads/
   ```

3. **Check document location:**
   - Documents must be in `uploads/` folder
   - Only `.pdf` files are processed
   - Check file permissions in S3

4. **Verify fetcher is running:**
   - Check application logs for `[S3_FETCHER]` messages
   - Ensure no exceptions in logs

### Processing Fails

1. **Check application logs** for error messages
2. **Verify document format** - must be valid PDF
3. **Check AWS permissions** - IAM role needs S3 and Textract access
4. **Check Bedrock access** - ensure Claude model is available in your region

### Documents Stuck in Processing

1. **Check background processor status:**
   ```bash
   curl http://localhost:5015/api/background-processor/status
   ```

2. **Restart background processor:**
   ```bash
   curl -X POST http://localhost:5015/api/background-processor/restart
   ```

3. **Check S3 cache** - may be stuck on OCR:
   ```bash
   aws s3 ls s3://aws-idp-uploads/page_ocr/
   ```

## Advanced Configuration

### Change Polling Interval

```python
# Check S3 every 60 seconds instead of 30
start_s3_fetcher(
    bucket_name="aws-idp-uploads",
    region="us-east-1",
    check_interval=60  # seconds
)
```

### Process Specific Folder

Modify `s3_document_fetcher.py` to change the prefix:

```python
# In _get_unprocessed_documents method
pages = paginator.paginate(
    Bucket=self.bucket_name,
    Prefix='uploads/'  # Change this to your folder
)
```

### Disable S3 Fetcher

Comment out the fetcher initialization:

```python
# start_s3_fetcher(bucket_name="aws-idp-uploads", region=AWS_REGION, check_interval=30)
```

## Performance Considerations

- **Polling interval**: 30 seconds (configurable)
- **Concurrent processing**: Limited by background processor (default: 5 workers)
- **OCR caching**: Reduces redundant Textract calls
- **S3 operations**: Batched where possible for efficiency

## Cost Optimization

The system tracks costs for:
- **Textract OCR** - Per page
- **Bedrock LLM** - Per token
- **S3 operations** - Per request and data transfer

View costs in the UI or via API:
```bash
curl http://localhost:5015/api/costs
```

## Integration with UI

Once documents are processed via S3 fetcher:

1. **Dashboard** - Documents appear in the main dashboard
2. **Skills Catalog** - Can be processed with additional skills
3. **Results** - Extracted data is displayed and editable
4. **Export** - Results can be exported to CSV/JSON

## API Endpoints

### Check Processing Status
```bash
curl http://localhost:5015/status/{job_id}
```

### Get Background Processor Status
```bash
curl http://localhost:5015/api/background-processor/status
```

### Get All Costs
```bash
curl http://localhost:5015/api/costs
```

## Next Steps

1. **Upload documents to S3** in the `uploads/` folder
2. **Start the application** - S3 fetcher will automatically start
3. **Monitor logs** for processing progress
4. **Check dashboard** for processed documents
5. **Review extracted data** and make corrections if needed
6. **Export results** when ready

## Support

For issues or questions:
1. Check application logs for error messages
2. Verify AWS credentials and permissions
3. Ensure S3 bucket exists and is accessible
4. Check Bedrock model availability in your region
5. Review CloudWatch logs for AWS service errors
