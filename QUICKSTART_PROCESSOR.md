# Quick Start - Document Processor

## 1. Start the Application

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the processor
python document_processor_app.py
```

You should see:
```
[INFO] Starting Document Processor
[INFO] AWS Region: us-east-1
[INFO] S3 Bucket: awsidpdocs
[INFO] Running on http://127.0.0.1:5016
```

## 2. Open in Browser

Navigate to: `http://127.0.0.1:5016`

## 3. Upload a PDF

- Drag and drop a PDF file onto the upload area, OR
- Click the upload area to select a file

## 4. Process

- Click "Upload & Process"
- Watch the progress bar
- Results will appear when complete

## 5. View Results

The results show:
- **Unique Accounts**: Number of different account numbers found
- **Total Pages**: Number of pages processed
- **Document ID**: Unique identifier for this document
- **Account List**: Each account with the pages it appears on

## 6. Check S3

Results are automatically saved to S3:

```
awsidpdocs/
├── page_ocr/{doc_id}/page_0.json          # Extracted text
└── document_results/{doc_id}/results.json  # Detection results
```

## Example Workflow

```
1. Upload: "invoice.pdf"
   ↓
2. Processing starts...
   - Extract text (30%)
   - Detect accounts (60%)
   - Save to S3 (100%)
   ↓
3. Results displayed:
   - Found 3 unique accounts
   - Accounts: 210656062, 468869904, 210701488
   - All on page 1
   ↓
4. Data saved to S3:
   - page_ocr/abc123/page_0.json
   - document_results/abc123/results.json
```

## API Usage (Advanced)

### Upload via curl

```bash
curl -X POST http://127.0.0.1:5016/api/process-document \
  -F "file=@document.pdf"
```

Response:
```json
{
  "success": true,
  "doc_id": "abc123def456",
  "message": "Document uploaded, processing started"
}
```

### Check Status via curl

```bash
curl http://127.0.0.1:5016/api/process-status/abc123def456
```

Response:
```json
{
  "success": true,
  "status": "completed",
  "progress": 100,
  "message": "Processing complete!",
  "accounts": [
    {"account_number": "210656062", "pages": [1]},
    {"account_number": "468869904", "pages": [1]}
  ],
  "total_pages": 1,
  "doc_id": "abc123def456"
}
```

## Troubleshooting

### Port already in use
If port 5016 is already in use, edit `document_processor_app.py`:
```python
app.run(debug=True, port=5017)  # Change to different port
```

### AWS credentials not found
Ensure AWS credentials are configured:
```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

### PDF extraction fails
- Try a different PDF file
- Ensure PDF is not password-protected
- Check if PDF is text-based (not scanned image)

### No accounts detected
- Check if PDF contains account numbers
- Verify account numbers match the regex patterns
- Review extracted text in S3 cache

## Next Steps

1. **Test with sample PDFs** - Upload various documents to test detection
2. **Check S3 results** - Verify data is being saved correctly
3. **Integrate with other systems** - Use the API endpoints
4. **Customize patterns** - Modify regex patterns in `app/services/regex_account_detector.py`
5. **Add multi-page support** - Extend to handle multi-page PDFs

## Files Reference

- `document_processor_app.py` - Main Flask application
- `templates/document_processor.html` - Web UI
- `app/services/regex_account_detector.py` - Account detection logic
- `DOCUMENT_PROCESSOR_README.md` - Full documentation

## Support

Check the console output for detailed logs of what's happening during processing.