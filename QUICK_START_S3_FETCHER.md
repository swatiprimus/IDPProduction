# Quick Start: S3 Document Fetcher

## 5-Minute Setup

### 1. Configure AWS Credentials
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter default region: us-east-1
# Enter default output format: json
```

### 2. Create S3 Bucket (if needed)
```bash
aws s3 mb s3://aws-idp-uploads --region us-east-1
```

### 3. Upload Documents to S3
```bash
# Upload a single document
aws s3 cp my_document.pdf s3://aws-idp-uploads/uploads/

# Upload multiple documents
aws s3 cp *.pdf s3://aws-idp-uploads/uploads/
```

### 4. Start the Application
```bash
python app_modular.py
```

The S3 fetcher will automatically:
- ✅ Start polling S3 every 30 seconds
- ✅ Detect new documents in `uploads/` folder
- ✅ Download and process them with skill-based system
- ✅ Display results on the dashboard

## What Happens Next

### Processing Pipeline
```
Document in S3
    ↓
Fetcher detects it (every 30 seconds)
    ↓
Downloads from S3
    ↓
Calls /process endpoint
    ↓
Document appears on dashboard (immediately)
    ↓
Background processing starts:
  • OCR extraction
  • Document type detection
  • Account splitting (if loan document)
  • LLM data extraction
    ↓
Results updated on dashboard
    ↓
Status saved to S3
```

## Monitor Processing

### View Logs
```bash
# Watch application logs for S3_FETCHER messages
tail -f app.log | grep S3_FETCHER
```

### Check S3 Status
```bash
# List all processed documents
aws s3 ls s3://aws-idp-uploads/processing_logs/

# View status of specific document
aws s3 cp s3://aws-idp-uploads/processing_logs/uploads/document.pdf.status.json - | jq .
```

### Check Dashboard
- Open http://localhost:5015
- Documents appear in the main dashboard
- Click on document to view extracted data

## Example: Process Loan Documents

### Upload loan documents to S3
```bash
aws s3 cp loan_statement_1.pdf s3://aws-idp-uploads/uploads/
aws s3 cp loan_statement_2.pdf s3://aws-idp-uploads/uploads/
```

### Application automatically:
1. Detects they are loan documents
2. Extracts text from each page
3. Splits into individual accounts
4. Extracts account details (balance, interest rate, etc.)
5. Displays on dashboard with all accounts

### View results
- Open http://localhost:5015
- Click on loan document
- See all extracted accounts and details

## Example: Process Death Certificates

### Upload death certificates to S3
```bash
aws s3 cp death_cert_1.pdf s3://aws-idp-uploads/uploads/
aws s3 cp death_cert_2.pdf s3://aws-idp-uploads/uploads/
```

### Application automatically:
1. Detects they are death certificates
2. Extracts text from each page
3. Extracts key fields (name, date of death, etc.)
4. Displays on dashboard

### View results
- Open http://localhost:5015
- Click on death certificate
- See all extracted fields

## Troubleshooting

### Documents not appearing?

1. **Check S3 bucket exists:**
   ```bash
   aws s3 ls s3://aws-idp-uploads/
   ```

2. **Check documents are in uploads/ folder:**
   ```bash
   aws s3 ls s3://aws-idp-uploads/uploads/
   ```

3. **Check application logs:**
   ```bash
   # Look for [S3_FETCHER] messages
   # Should see "Found X unprocessed document(s)"
   ```

4. **Verify AWS credentials:**
   ```bash
   aws sts get-caller-identity
   ```

### Processing stuck?

1. **Check background processor:**
   ```bash
   curl http://localhost:5015/api/background-processor/status
   ```

2. **Restart processor:**
   ```bash
   curl -X POST http://localhost:5015/api/background-processor/restart
   ```

3. **Check Bedrock availability:**
   - Ensure Claude model is available in your region
   - Check AWS console for service limits

## Common Issues

| Issue | Solution |
|-------|----------|
| "No documents found" | Check documents are in `uploads/` folder, not root |
| "Access Denied" | Verify AWS credentials with `aws sts get-caller-identity` |
| "Processing timeout" | Increase timeout in `s3_document_fetcher.py` (line ~120) |
| "Textract error" | Ensure Textract is available in your region |
| "Bedrock error" | Verify Claude model access in Bedrock console |

## Next Steps

1. ✅ Configure AWS credentials
2. ✅ Create S3 bucket
3. ✅ Upload documents
4. ✅ Start application
5. ✅ Monitor processing
6. ✅ View results on dashboard
7. ✅ Export or edit results

## Advanced

### Change polling interval
Edit `app_modular.py`:
```python
start_s3_fetcher(
    bucket_name="aws-idp-uploads",
    region=AWS_REGION,
    check_interval=60  # Check every 60 seconds instead of 30
)
```

### Disable S3 fetcher
Comment out in `app_modular.py`:
```python
# start_s3_fetcher(bucket_name="aws-idp-uploads", region=AWS_REGION, check_interval=30)
```

### Process different S3 folder
Edit `s3_document_fetcher.py` in `_get_unprocessed_documents()`:
```python
pages = paginator.paginate(
    Bucket=self.bucket_name,
    Prefix='my_documents/'  # Change this
)
```

## Support

For detailed documentation, see: `S3_FETCHER_INTEGRATION.md`

For issues:
1. Check application logs
2. Verify AWS credentials
3. Ensure S3 bucket and documents exist
4. Check Bedrock model availability
