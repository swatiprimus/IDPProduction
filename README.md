# 🤖 Unified IDP Platform

A comprehensive Intelligent Document Processing platform that combines AWS AI services with advanced search capabilities and cost optimization through intelligent caching.

## 🌟 Features

### Core Processing
- **📄 Document Upload**: Support for PDF, PNG, JPG files up to 50MB
- **🔍 Text Extraction**: AWS Textract with forms and tables detection
- **🤖 AI Classification**: Enhanced document classification with confidence scoring
- **⭐ Quality Assessment**: Automated document quality and completeness analysis
- **💾 S3 Caching**: Intelligent caching to reduce processing costs
- **🔍 RAG Search**: Semantic and traditional search across processed documents

### Advanced Features
- **📊 Real-time Analytics**: Processing statistics and performance metrics
- **🔄 Batch Processing**: Handle multiple documents efficiently
- **🌐 REST API**: Complete API for external integrations
- **📈 Quality Scoring**: Document completeness and accuracy assessment
- **🎯 Custom Analysis**: User-defined prompts for specific extraction needs

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirement.txt
```

### 2. Configure AWS
```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and region (us-east-1)
```

### 3. Start the Platform
```bash
python start_idp_platform.py
```

### 4. Access the UI
Open your browser to: `http://localhost:5000`

## 📋 System Requirements

### Required
- Python 3.8+
- AWS Account with configured credentials
- AWS Services: Textract, Bedrock, S3

### Optional (for enhanced features)
- MongoDB Atlas (for RAG search)
- Elasticsearch (for advanced search)

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web UI        │    │  Document        │    │   AWS Services  │
│                 │────│  Processor       │────│                 │
│ • Upload        │    │                  │    │ • Textract      │
│ • Search        │    │ • Caching        │    │ • Bedrock       │
│ • Analytics     │    │ • Classification │    │ • S3            │
└─────────────────┘    │ • Quality Check  │    └─────────────────┘
                       └──────────────────┘
                                │
                       ┌──────────────────┐
                       │   Data Storage   │
                       │                  │
                       │ • MongoDB (RAG)  │
                       │ • S3 (Cache)     │
                       │ • Local (Temp)   │
                       └──────────────────┘
```

## 💡 Usage Examples

### Basic Document Processing
1. **Upload Document**: Drag & drop or click to select a PDF/image
2. **Add Custom Prompt** (optional): "Extract all financial information"
3. **Process**: Click "Process Document" 
4. **View Results**: Classification, quality score, and extracted data
5. **Download**: Get complete JSON results

### RAG Search
1. **Process Documents**: Upload and process several documents first
2. **Search**: Use natural language queries like:
   - "Find all loan documents"
   - "Show me driver licenses from Delaware"
   - "Documents with high loan amounts"
3. **Results**: Get semantically relevant documents with similarity scores

### Cost Optimization
- **Automatic Caching**: Results saved to S3 automatically
- **Cache Hits**: Identical documents return cached results instantly
- **Force Reprocess**: Option to bypass cache when needed
- **Statistics**: Monitor cache hit rate and cost savings

## 🔧 Configuration

### AWS Configuration
```python
AWS_CONFIG = {
    'region': 'us-east-1',
    'bucket': 'awsidpdocs',
    'cache_prefix': 'processed_cache',
    'temp_prefix': 'temp_uploads'
}
```

### MongoDB Configuration (Optional)
```python
MONGODB_CONFIG = {
    'connection_string': 'your_mongodb_connection_string',
    'database_name': 'document_analysis',
    'embedding_model': 'all-MiniLM-L6-v2'
}
```

## 📊 Available Endpoints

### Web UI
- `GET /` - Main processing interface
- `GET /dashboard` - Skills catalog dashboard
- `GET /codebase` - Codebase documentation
- `POST /process` - Process uploaded document
- `GET /status/<job_id>` - Get processing status
- `GET /document/<doc_id>` - View document details

### API Endpoints
- `GET /api/documents` - Get all processed documents
- `GET /api/document/<doc_id>` - Get specific document details
- `DELETE /api/document/<doc_id>/delete` - Delete a document
- `POST /api/documents/cleanup` - Delete all documents and OCR files

### Additional Services
- `http://localhost:5003` - Analytics Dashboard
- `http://localhost:5005` - REST API Gateway
- `http://localhost:5015` - Universal IDP (Main)
- `http://localhost:5016` - Multi-Document Processor

## 🎯 Document Types Supported

### Hierarchical Classification System
The platform uses a decision tree-based classification system for accurate document type detection:

#### WSFS Bank Forms
- Business Card Order Form
- Account Withdrawal Form
- Name Change Request
- Tax ID Change Form
- Joint Account Signature Card
- ATM/Debit Card Request

#### Vital Records
- Delaware Death Certificate
- Pennsylvania Death Certificate
- Marriage Certificate

#### Legal Documents
- Register of Wills
- Letters Testamentary
- Letters of Administration
- Small Estate Affidavit
- Power of Attorney
- Contracts

#### Identity Documents
- Driver's Licenses (all states)
- State IDs
- Passports

#### Financial Documents
- Loan agreements
- Bank statements
- Tax forms (1040, W-2, 1099)
- Financial statements
- Account opening documents

#### Business Documents
- Invoices
- Funeral invoices
- Purchase orders
- Business licenses
- Receipts

#### Other Documents
- Insurance policies
- Medical records

See [DOCUMENT_CLASSIFICATION_GUIDE.md](DOCUMENT_CLASSIFICATION_GUIDE.md) for detailed classification logic.

## 📈 Performance & Costs

### Processing Times
- **Cache Hit**: < 1 second
- **New Document**: 30-120 seconds (depending on complexity)
- **Batch Processing**: Parallel processing for efficiency

### Cost Optimization
- **S3 Caching**: Avoid reprocessing identical documents
- **Smart Indexing**: Only index when needed
- **Efficient APIs**: Minimize API calls through caching

## 🗂️ Document Management

### Upload & Process
1. **Single Document**: Upload PDF, PNG, JPG, or JPEG files
2. **Auto-Classification**: Hierarchical decision tree for accurate type detection
3. **OCR Processing**: Amazon Textract for scanned documents
4. **Field Extraction**: AI-powered data extraction based on document type

### View & Organize
- **Dashboard View**: See all processed documents as skills
- **Document Details**: View extracted fields and accuracy scores
- **Search & Filter**: Find documents by type, date, or content
- **Download Results**: Export as JSON or ODF format

### Cleanup & Maintenance
- **Delete Individual Documents**: Remove specific documents and their OCR files
- **Bulk Cleanup**: Clear all processed documents at once
- **Storage Management**: Monitor OCR results directory size
- **Automatic Cleanup**: Configure retention policies

### API Examples

**Delete a Document:**
```bash
curl -X DELETE http://localhost:5015/api/document/<doc_id>/delete
```

**Cleanup All Documents:**
```bash
curl -X POST http://localhost:5015/api/documents/cleanup
```

**Get All Documents:**
```bash
curl http://localhost:5015/api/documents
```

## 🔍 Search Capabilities

### Semantic Search
- Natural language queries
- Concept-based matching
- Similarity scoring
- Context understanding

### Traditional Search
- Keyword matching
- Field-specific filters
- Boolean operators
- Exact matches

### Search Examples
```javascript
// Semantic search
"Find all customers from Delaware with high-value loans"

// Traditional search
account_number: "123456" AND document_type: "loan_agreement"
```

## 🛠️ Development

### Project Structure
```
├── unified_idp_ui.py          # Main application
├── enhanced_classifier.py     # Document classification
├── quality_assessor.py        # Quality assessment
├── mongodb_rag_indexer.py     # RAG search functionality
├── analytics_dashboard.py     # Analytics interface
├── api_gateway.py            # REST API
├── batch_processor.py        # Batch processing
├── start_idp_platform.py     # Startup script
├── templates/                # HTML templates
└── temp_processing/          # Temporary files
```

### Adding New Document Types
1. Update `enhanced_classifier.py` patterns
2. Add quality criteria in `quality_assessor.py`
3. Update UI document type list

### Custom Analysis Prompts
The platform supports custom prompts for specific extraction needs:
- Financial analysis
- Compliance checking
- Data validation
- Custom field extraction

## 🔒 Security Considerations

- **AWS IAM**: Use least-privilege access policies
- **API Keys**: Implement proper authentication for production
- **Data Encryption**: S3 encryption at rest
- **Temporary Files**: Automatic cleanup of uploaded files
- **Access Logs**: Monitor document access patterns

## 🚨 Troubleshooting

### Common Issues

**AWS Credentials Error**
```bash
aws configure
# Ensure correct region (us-east-1)
```

**MongoDB Connection Failed**
- Check connection string
- Verify network access
- RAG search will be limited but platform still works

**Textract Job Failed**
- Check document format and size
- Verify S3 bucket permissions
- Ensure document is not corrupted

**High Processing Costs**
- Monitor cache hit rate
- Use batch processing for multiple documents
- Consider document preprocessing

## 📚 Complete Documentation

### Core Documentation
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - Complete project overview with architecture
- **[DEMO_GUIDE.md](DEMO_GUIDE.md)** - Comprehensive demo script and presentation guide
- **[TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md)** - Detailed technical architecture
- **[LLM_TECHNOLOGY_GUIDE.md](LLM_TECHNOLOGY_GUIDE.md)** - Claude 3.5 Sonnet implementation details

### Classification System
- **[DOCUMENT_CLASSIFICATION_GUIDE.md](DOCUMENT_CLASSIFICATION_GUIDE.md)** - Classification logic and decision tree
- **[ENHANCED_CLASSIFICATION_UPDATE.md](ENHANCED_CLASSIFICATION_UPDATE.md)** - Recent enhancements
- **[QUICK_START_CLASSIFICATION.md](QUICK_START_CLASSIFICATION.md)** - Quick reference guide

### Implementation & Status
- **[SYSTEM_STATUS.md](SYSTEM_STATUS.md)** - Current system status
- **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - Implementation summary
- **[READY_TO_USE.md](READY_TO_USE.md)** - Getting started guide

### Feature Documentation
- **[LARGE_DOCUMENT_PROCESSING.md](LARGE_DOCUMENT_PROCESSING.md)** - Large document handling
- **[DOCUMENT_SUPPORT.md](DOCUMENT_SUPPORT.md)** - Supported document types
- **[PROCESSING_OPTIMIZATION.md](PROCESSING_OPTIMIZATION.md)** - Performance optimization
- **[UPLOAD_PROGRESS_FEATURE.md](UPLOAD_PROGRESS_FEATURE.md)** - Upload progress tracking

## 📞 Support

For issues and questions:
1. Check the comprehensive documentation above
2. Review the troubleshooting section
3. Check AWS service limits
4. Verify all dependencies are installed
5. Review application logs for detailed error messages
6. Run the test suite: `python test_classification.py`

## 🎉 Success Metrics

Track your IDP platform success:
- **Cache Hit Rate**: Target >70% for cost efficiency
- **Processing Accuracy**: Monitor classification confidence
- **Search Relevance**: User feedback on search results
- **Processing Speed**: Average time per document
- **Cost Savings**: Compare with/without caching

---

**Ready to process your documents intelligently? Start with `python start_idp_platform.py`** 🚀