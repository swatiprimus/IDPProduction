# Complete Data Flow - ID Synchronization

## Upload Flow with ID Generation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIMPLE_UPLOAD_APP.PY                               │
│                                                                             │
│  1. User uploads PDF via web interface                                     │
│     ↓                                                                       │
│  2. POST /api/upload with file                                             │
│     ↓                                                                       │
│  3. Generate unique ID                                                      │
│     doc_id = hashlib.md5(f"{filename}{time.time()}").hexdigest()[:12]     │
│     Example: "abc123def456"                                                │
│     ↓                                                                       │
│  4. Upload to S3: uploads/{filename}                                       │
│     ↓                                                                       │
│  5. Create document record with ID                                         │
│     {                                                                       │
│       "id": "abc123def456",                                                │
│       "filename": "loan_statement.pdf",                                    │
│       "document_name": "loan_statement.pdf",                               │
│       "timestamp": "20250126_125601",                                      │
│       "file_key": "uploads/loan_statement.pdf",                            │
│       "status": "pending",                                                 │
│       "documents": [],                                                     │
│       "document_type_info": {...}                                          │
│     }                                                                       │
│     ↓                                                                       │
│  6. Save to processed_documents.json                                       │
│     ↓                                                                       │
│  7. Return response with ID                                                │
│     {                                                                       │
│       "success": true,                                                     │
│       "uploaded": [{                                                       │
│         "id": "abc123def456",                                              │
│         "file_name": "loan_statement.pdf",                                 │
│         "file_key": "uploads/loan_statement.pdf"                           │
│       }]                                                                    │
│     }                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         S3_DOCUMENT_FETCHER                                 │
│                                                                             │
│  1. Polls S3 every 30 seconds                                              │
│     ↓                                                                       │
│  2. Detects new document: uploads/loan_statement.pdf                       │
│     ↓                                                                       │
│  3. Downloads from S3                                                      │
│     ↓                                                                       │
│  4. Calls /process endpoint in app_modular.py                              │
│     ↓                                                                       │
│  5. Monitors processing progress                                           │
│     ↓                                                                       │
│  6. Updates status when complete                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APP_MODULAR.PY                                      │
│                                                                             │
│  1. Receives /process request                                              │
│     ↓                                                                       │
│  2. Generates job_id (same as doc_id from simple_upload_app)               │
│     ↓                                                                       │
│  3. Detects document type                                                  │
│     ↓                                                                       │
│  4. Creates placeholder document                                           │
│     ↓                                                                       │
│  5. Queues for background processing                                       │
│     ↓                                                                       │
│  6. Background processor runs:                                             │
│     - Stage 1: OCR extraction (page-by-page)                               │
│     - Stage 2: Account splitting (if loan document)                        │
│     - Stage 3: LLM extraction (structured data)                            │
│     ↓                                                                       │
│  7. Updates document record with results                                   │
│     ↓                                                                       │
│  8. Saves to processed_documents.json                                      │
│     ↓                                                                       │
│  9. Document now has:                                                      │
│     - id: "abc123def456"                                                   │
│     - status: "completed"                                                  │
│     - documents: [extracted data]                                          │
│     - accounts: [if loan document]                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SKILLS_CATALOG.HTML                                    │
│                                                                             │
│  1. Fetches /api/documents                                                 │
│     ↓                                                                       │
│  2. Receives documents with IDs                                            │
│     [                                                                       │
│       {                                                                     │
│         "id": "abc123def456",                                              │
│         "filename": "loan_statement.pdf",                                  │
│         "status": "completed",                                             │
│         "documents": [...]                                                 │
│       }                                                                     │
│     ]                                                                       │
│     ↓                                                                       │
│  3. Displays in table with ID                                              │
│     ↓                                                                       │
│  4. User clicks document                                                   │
│     ↓                                                                       │
│  5. Opens: /document/{skill.id}/pages                                      │
│     Example: /document/abc123def456/pages                                  │
│     ↓                                                                       │
│  6. View functions use find_document_by_id(doc_id)                         │
│     ↓                                                                       │
│  7. Document found and displayed                                           │
│     ↓                                                                       │
│  8. User can:                                                              │
│     - View pages                                                           │
│     - View accounts (if loan document)                                     │
│     - Edit fields                                                          │
│     - Delete document                                                      │
│     - Export results                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Structure Evolution

### Step 1: After Upload (simple_upload_app.py)
```json
{
  "id": "abc123def456",
  "filename": "loan_statement.pdf",
  "document_name": "loan_statement.pdf",
  "timestamp": "20250126_125601",
  "processed_date": "2025-01-26T12:56:01.123456",
  "file_key": "uploads/loan_statement.pdf",
  "status": "pending",
  "can_view": false,
  "documents": [],
  "document_type_info": {
    "type": "unknown",
    "name": "Unknown Document",
    "icon": "📄",
    "description": "Document uploaded - will be processed by app_modular.py"
  }
}
```

### Step 2: After Detection (app_modular.py - process_job)
```json
{
  "id": "abc123def456",
  "filename": "loan_statement.pdf",
  "document_name": "loan_statement.pdf",
  "timestamp": "20250126_125601",
  "processed_date": "2025-01-26T12:56:01.123456",
  "file_key": "uploads/loan_statement.pdf",
  "status": "extracting",
  "can_view": true,
  "pdf_path": "/path/to/pdf",
  "documents": [
    {
      "document_type": "loan_document",
      "document_type_display": "Loan/Account Document",
      "document_icon": "🏦",
      "extracted_fields": {
        "total_accounts": 0
      },
      "accounts": [],
      "accuracy_score": null
    }
  ],
  "document_type_info": {
    "type": "loan_document",
    "name": "Loan/Account Document",
    "icon": "🏦",
    "description": "Banking or loan account information"
  }
}
```

### Step 3: After Processing (app_modular.py - background processor)
```json
{
  "id": "abc123def456",
  "filename": "loan_statement.pdf",
  "document_name": "loan_statement.pdf",
  "timestamp": "20250126_125601",
  "processed_date": "2025-01-26T12:56:01.123456",
  "file_key": "uploads/loan_statement.pdf",
  "status": "completed",
  "can_view": true,
  "pdf_path": "/path/to/pdf",
  "total_pages": 5,
  "documents": [
    {
      "document_type": "loan_document",
      "document_type_display": "Loan/Account Document",
      "document_icon": "🏦",
      "extracted_fields": {
        "total_accounts": 3
      },
      "accounts": [
        {
          "account_type": "Checking",
          "account_number": "****1234",
          "balance": "$5,234.56",
          "interest_rate": "0.01%"
        },
        {
          "account_type": "Savings",
          "account_number": "****5678",
          "balance": "$12,456.78",
          "interest_rate": "4.50%"
        },
        {
          "account_type": "Credit Card",
          "account_number": "****9012",
          "balance": "$3,456.00",
          "interest_rate": "18.99%"
        }
      ],
      "accuracy_score": 0.95
    }
  ],
  "document_type_info": {
    "type": "loan_document",
    "name": "Loan/Account Document",
    "icon": "🏦",
    "description": "Banking or loan account information"
  },
  "processing_cost": {
    "textract_cost": 0.0015,
    "bedrock_cost": 0.0045,
    "s3_cost": 0.0001,
    "total_cost": 0.0061
  }
}
```

## API Endpoints Using ID

### Get All Documents
```
GET /api/documents
Response:
{
  "documents": [
    {
      "id": "abc123def456",
      "filename": "loan_statement.pdf",
      ...
    }
  ]
}
```

### Get Specific Document
```
GET /api/document/abc123def456
Response:
{
  "success": true,
  "document": {
    "id": "abc123def456",
    "filename": "loan_statement.pdf",
    ...
  }
}
```

### Delete Document
```
DELETE /api/document/abc123def456/delete
Response:
{
  "success": true,
  "message": "Document deleted successfully"
}
```

### View Document Pages
```
GET /document/abc123def456/pages
Opens: unified_page_viewer.html with document data
```

### View Account-Based
```
GET /document/abc123def456/accounts
Opens: account_based_viewer.html with accounts
```

## Error Handling

### Before Fix
```
KeyError: 'id'
Traceback:
  File "app_modular.py", line 4110, in view_document_pages
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
  File "app_modular.py", line 4110, in <genexpr>
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
KeyError: 'id'
```

### After Fix
```
Safe lookup:
  doc = find_document_by_id(doc_id)
  if not doc:
    return jsonify({"error": "Document not found"}), 404

Result: Proper error message, no KeyError
```

## Key Points

1. **ID Generation**: Unique ID created at upload time
2. **Immediate Record**: Document record saved immediately
3. **Safe Lookups**: All document lookups use safe helper
4. **Backward Compatible**: Old documents get IDs automatically
5. **Synchronized**: Both apps use same ID structure
6. **No Errors**: No more KeyError exceptions

## Testing the Flow

```bash
# 1. Start simple_upload_app.py
python simple_upload_app.py

# 2. Upload a document
curl -X POST http://localhost:5001/api/upload -F "files=@test.pdf"

# 3. Check document record
cat processed_documents.json | jq '.[-1]'

# 4. Start app_modular.py
python app_modular.py

# 5. Open dashboard
# http://localhost:5015

# 6. Document should appear with ID
# Click to open - should work without errors

# 7. Delete document
# Click delete button - should work without errors
```

## Summary

The complete flow ensures:
- ✅ All documents have unique IDs
- ✅ IDs are generated at upload time
- ✅ Both apps are synchronized
- ✅ No KeyError exceptions
- ✅ Seamless user experience
- ✅ Backward compatible
