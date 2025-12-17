# Standalone Document Processor

A separate, independent document processing application that uploads PDFs, extracts OCR results, detects account numbers using regex patterns, and saves everything to S3.

## Features

- 📤 **Upload PDFs** - Drag and drop or click to upload PDF documents
- 🔍 **OCR Extraction** - Extracts text using AWS Textract (with PyPDF2 fallback)
- 🏦 **Account Detection** - Uses regex-based account number detection
- 💾 **S3 Storage** - Saves OCR results and detection results to S3
- 📊 **Real-time Progress** - Shows processing progress in real-time
- 🎨 **Beautiful UI** - Modern, responsive web interface

## Architecture

### Files

1. **document_processor_app.py** - Flask backend server
   - Handles file uploads
   - Manages OCR extraction
   - Detects accounts using regex patterns
   - Saves results to S3
   - Tracks processing status

2. **templates/document_processor.html** - Frontend UI
   - Drag-and-drop file upload
   - Real-time progress tracking
   - Results display with account details

## Installation

```bash
# Install dependencies
pip install flask boto3 PyPDF2

# Or use the existing venv
source .venv/bin/activate
```

## Usage

### Start the Server

```bash
source .venv/bin/activate
python document_processor_app.py
```

The application will start on `http://127.0.0.1:5016`

### Upload and Process

1. Open `http://127.0.0.1:5016` in your browser
2. Drag and drop a PDF file or click to select
3. Click "Upload & Process"
4. Wait for processing to complete
5. View detected accounts and their page numbers

## S3 Storage Structure

Results are saved to S3 in the following structure:

```
awsidpdocs/
├── page_ocr/{doc_id}/
│   └── page_0.json          # OCR text extracted from PDF
└── document_results/{doc_id}/
    └── results.json         # Detection results with accounts
```

### page_0.json Structure

```json
{
  "page_text": "Full extracted text from PDF...",
  "extraction_method": "textract or pypdf2",
  "extracted_at": "2025-12-17T15:30:00.000000",
  "total_pages": 1
}
```

### results.json Structure

```json
{
  "doc_id": "abc123def456",
  "filename": "document.pdf",
  "accounts": [
    {
      "account_number": "210656062",
      "pages": [1]
    },
    {
      "account_number": "468869904",
      "pages": [1]
    }
  ],
  "total_pages": 1,
  "total_accounts": 2,
  "extraction_method": "textract",
  "processed_at": "2025-12-17T15:30:00.000000"
}
```

## API Endpoints

### Upload Document

```
POST /api/process-document
Content-Type: multipart/form-data

Body:
- file: <PDF file>

Response:
{
  "success": true,
  "doc_id": "abc123def456",
  "message": "Document uploaded, processing started"
}
```

### Get Processing Status

```
GET /api/process-status/{doc_id}

Response:
{
  "success": true,
  "status": "completed|processing|error",
  "progress": 0-100,
  "message": "Status message",
  "accounts": [...],
  "total_pages": 1,
  "doc_id": "abc123def456"
}
```

## Account Detection

The processor uses the `RegexAccountDetector` class which:

- Looks for explicit account number labels (ACCOUNT NUMBER:, ACCOUNT NO:, etc.)
- Supports multiline formats (label on one line, number on next)
- Normalizes account numbers (removes leading zeros)
- Filters out false positives (SSNs, ZIP codes, test numbers)

### Supported Patterns

- `ACCOUNT NUMBER: 123456789`
- `ACCOUNT NO: 123456789`
- `ACCOUNT #: 123456789`
- `CD ACCOUNT NUMBER: 123456789`
- Multiline formats with newlines between label and number

## Error Handling

- Invalid file types are rejected
- File size is limited to 100MB
- OCR extraction failures fall back to PyPDF2
- Processing errors are tracked and reported
- All errors are logged to console

## Performance

- Single-threaded OCR extraction (can be parallelized)
- ThreadPoolExecutor for background processing
- S3 operations are asynchronous
- Real-time progress updates via polling

## Limitations

- Currently processes single-page PDFs (can be extended for multi-page)
- Requires AWS credentials configured
- Textract has rate limits (can be handled with retry logic)

## Future Enhancements

- [ ] Multi-page PDF support
- [ ] Batch processing
- [ ] Account number validation rules
- [ ] Custom regex patterns
- [ ] Export results to CSV/Excel
- [ ] Processing history/dashboard
- [ ] Webhook notifications
- [ ] Rate limiting and authentication

## Troubleshooting

### "No file provided" error
- Ensure you're uploading a PDF file
- Check file size (max 100MB)

### "Failed to extract text from PDF"
- PDF might be image-based (scanned)
- Try uploading a text-based PDF

### S3 errors
- Check AWS credentials are configured
- Verify S3 bucket name and region
- Check IAM permissions

### No accounts detected
- PDF might not contain account numbers
- Check if account numbers match the regex patterns
- Review the extracted text in S3 cache

## Support

For issues or questions, check:
1. Console logs in the terminal
2. S3 cache files for extracted text
3. Processing status via API endpoint