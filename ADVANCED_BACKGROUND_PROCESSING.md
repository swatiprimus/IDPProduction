# Advanced Background Processing System

## Overview

The Universal IDP system now features a sophisticated background processing pipeline that automatically handles **OCR + Account Splitting + LLM Extraction** in separate threads with intelligent caching. This ensures documents are fully processed even when users don't interact with them, and provides instant results when they do.

## 🚀 Key Features

### Multi-Stage Pipeline
1. **OCR Extraction** - Full document text extraction with caching
2. **Account Splitting** - Intelligent document segmentation for loan documents  
3. **Page Analysis** - Maps pages to specific accounts
4. **LLM Extraction** - Parallel page-by-page data extraction with AI

### Intelligent Caching
- **S3-Based Cache** - All results stored in AWS S3 for persistence
- **Instant Retrieval** - Cached pages return results immediately
- **Cache Validation** - Version-aware caching prevents stale data
- **Background Population** - Cache populated automatically without user interaction

### Parallel Processing
- **Document-Level Threading** - Each document processes in its own thread
- **Page-Level Parallelism** - Multiple pages processed simultaneously
- **Priority Queue** - Loan documents get higher processing priority
- **Non-Blocking** - User interface remains responsive during processing

## 🏗️ Architecture

### BackgroundDocumentProcessor Class

```python
class BackgroundDocumentProcessor:
    - max_workers: int = 5          # Parallel processing threads
    - processing_queue: PriorityQueue  # Document processing queue
    - document_threads: Dict        # Active processing threads
    - document_status: Dict         # Real-time processing status
    - page_cache: Dict             # In-memory page cache
    - stage_progress: Dict         # Per-stage progress tracking
```

### Processing Stages

```python
class DocumentProcessingStage:
    OCR_EXTRACTION = "ocr_extraction"      # Stage 1: Extract full text
    ACCOUNT_SPLITTING = "account_splitting" # Stage 2: Split into accounts  
    PAGE_ANALYSIS = "page_analysis"        # Stage 3: Map pages to accounts
    LLM_EXTRACTION = "llm_extraction"      # Stage 4: Extract data with AI
    COMPLETED = "completed"                # Stage 5: All processing done
```

## 🔄 Processing Flow

### 1. Document Upload
```
User uploads document → Fast placeholder creation → Background processing queued
```

### 2. Background Pipeline
```
OCR Extraction → Account Splitting → Page Analysis → LLM Extraction (parallel)
     ↓              ↓                 ↓               ↓
   Cache          Cache             Cache         Cache each page
```

### 3. User Interaction
```
User opens page → Check cache → Return cached data OR processing status
```

## 📡 API Endpoints

### Background Processing Control
- `GET /api/document/{doc_id}/background-status` - Get processing status
- `POST /api/document/{doc_id}/force-background-processing` - Force start processing
- `GET /api/background-processor/status` - Overall processor status
- `POST /api/background-processor/restart` - Restart processor

### Cached Data Access
- `GET /api/document/{doc_id}/page/{page_num}/cached-data` - Get cached page data
- `GET /api/document/{doc_id}/page/{page_num}/extract` - Extract with cache fallback
- `GET /api/document/{doc_id}/account/{account_index}/page/{page_num}/data` - Account page with cache

## 🎯 Usage Examples

### 1. Check Processing Status
```bash
curl http://localhost:5015/api/document/abc123/background-status
```

Response:
```json
{
  "success": true,
  "status": {
    "stage": "llm_extraction",
    "progress": 75,
    "pages_processed": 15,
    "total_pages": 20,
    "accounts": [...],
    "stages": {
      "ocr_extraction": {"status": "completed", "progress": 100},
      "account_splitting": {"status": "completed", "progress": 100},
      "page_analysis": {"status": "completed", "progress": 100},
      "llm_extraction": {"status": "processing", "progress": 75}
    }
  }
}
```

### 2. Get Cached Page Data
```bash
curl http://localhost:5015/api/document/abc123/page/5/cached-data
```

Response (if cached):
```json
{
  "success": true,
  "cached": true,
  "data": {
    "Account_Number": "123456789",
    "Account_Holders": ["John Doe"],
    "Phone_Number": "555-1234"
  },
  "account_number": "123456789",
  "extraction_time": 1640995200
}
```

Response (if processing):
```json
{
  "success": true,
  "cached": false,
  "processing": true,
  "stage": "llm_extraction",
  "progress": 60,
  "pages_processed": 12,
  "total_pages": 20
}
```

### 3. Force Background Processing
```bash
curl -X POST http://localhost:5015/api/document/abc123/force-background-processing
```

## 🔧 Configuration

### Adjust Worker Count
```python
# In app_modular.py
background_processor = BackgroundDocumentProcessor(max_workers=10)
```

### Processing Priorities
```python
# High priority (loan documents)
background_processor.queue_document_for_processing(doc_id, pdf_path, priority=0)

# Normal priority (other documents)  
background_processor.queue_document_for_processing(doc_id, pdf_path, priority=1)

# Low priority (batch processing)
background_processor.queue_document_for_processing(doc_id, pdf_path, priority=2)
```

### Cache Configuration
```python
# Cache keys used:
- f"ocr_cache/{doc_id}/full_text.json"           # Full document OCR
- f"account_cache/{doc_id}/accounts.json"        # Account splitting results
- f"page_mapping/{doc_id}/mapping.json"          # Page-to-account mapping
- f"page_data/{doc_id}/page_{page_num}.json"     # Individual page extractions
```

## 🧪 Testing

### Run Test Script
```bash
python test_advanced_background_processing.py
```

This will:
1. Check existing documents
2. Force background processing
3. Monitor progress in real-time
4. Test cached data retrieval
5. Verify page extraction integration

### Manual Testing Steps

1. **Upload Document**: Upload a PDF via web interface
2. **Check Status**: Use API to monitor background processing
3. **Open Pages**: Navigate to document pages in UI
4. **Verify Cache**: Pages should load instantly if cached
5. **Monitor Progress**: Watch real-time processing updates

## 💡 Benefits

### For Users
- **Instant Results** - Cached pages load immediately
- **No Waiting** - Processing happens automatically in background
- **Real-time Updates** - See processing progress live
- **Reliable Performance** - Cached results are always available

### For System
- **Efficient Resource Usage** - Parallel processing maximizes throughput
- **Scalable Architecture** - Easy to add more workers
- **Fault Tolerance** - Individual page failures don't stop processing
- **Cache Persistence** - Results survive server restarts

### For Developers
- **Clean API** - Simple endpoints for status and data
- **Extensible Design** - Easy to add new processing stages
- **Comprehensive Logging** - Detailed processing logs
- **Error Handling** - Graceful failure recovery

## 🔍 Monitoring & Debugging

### Processing Logs
```
[BG_PROCESSOR] Starting complete pipeline for abc123
[BG_PROCESSOR] Stage 1: OCR extraction for abc123
[BG_PROCESSOR] ✓ Cached OCR result for abc123
[BG_PROCESSOR] Stage 2: Account splitting for abc123  
[BG_PROCESSOR] ✓ Cached account split for abc123 (3 accounts)
[BG_PROCESSOR] Stage 3: Page analysis for abc123 (25 pages)
[BG_PROCESSOR] ✓ Cached page mapping for abc123
[BG_PROCESSOR] Stage 4: LLM extraction for abc123
[BG_PROCESSOR] ✓ Processed and cached page 0 for abc123
[BG_PROCESSOR] ✅ Completed full pipeline for abc123
```

### Status Monitoring
```bash
# Check overall processor status
curl http://localhost:5015/api/background-processor/status

# Monitor specific document
curl http://localhost:5015/api/document/abc123/background-status

# Check if page is cached
curl http://localhost:5015/api/document/abc123/page/5/cached-data
```

## 🚨 Troubleshooting

### Processing Not Starting
- Check if background processor is running: `/api/background-processor/status`
- Restart processor: `POST /api/background-processor/restart`
- Verify PDF file exists and is readable

### Cache Issues
- Cache is stored in S3 - check AWS credentials
- Cache keys are version-aware - old cache is automatically invalidated
- Manual cache clearing: Delete S3 objects with prefix `page_data/{doc_id}/`

### Performance Issues
- Reduce `max_workers` if system is overloaded
- Monitor S3 API limits and costs
- Check CloudWatch logs for AWS service issues

## 🔮 Future Enhancements

- **Batch Processing** - Process multiple documents simultaneously
- **Smart Prioritization** - ML-based priority assignment
- **Distributed Processing** - Multi-server processing cluster
- **Real-time Notifications** - WebSocket updates for processing status
- **Advanced Caching** - Redis integration for faster cache access

This advanced background processing system transforms the Universal IDP from a reactive system to a proactive one, ensuring documents are always ready when users need them while providing complete transparency into the processing pipeline.