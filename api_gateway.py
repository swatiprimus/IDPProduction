#!/usr/bin/env python3
"""
api_gateway.py

RESTful API gateway for external systems to integrate with IDP platform
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import uuid
from datetime import datetime
import tempfile
from pathlib import Path
import boto3
from werkzeug.utils import secure_filename
import logging

# Import your existing modules
from mongodb_rag_indexer import MongoDBRAGIndexer, MONGODB_CONFIG
from enhanced_classifier import EnhancedDocumentClassifier
from quality_assessor import DocumentQualityAssessor

app = Flask(__name__)
CORS(app)  # Enable CORS for external access

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
indexer = MongoDBRAGIndexer(MONGODB_CONFIG)
classifier = EnhancedDocumentClassifier()
quality_assessor = DocumentQualityAssessor()
s3 = boto3.client('s3', region_name='us-east-1')
textract = boto3.client('textract', region_name='us-east-1')

# Configuration
API_CONFIG = {
    'max_file_size': 16 * 1024 * 1024,  # 16MB
    's3_bucket': 'awsidpdocs',
    'temp_prefix': 'api_uploads',
    'supported_formats': ['.pdf', '.png', '.jpg', '.jpeg']
}

# API Key validation (simple implementation)
VALID_API_KEYS = {
    'demo_key_123': {'name': 'Demo Client', 'permissions': ['read', 'write']},
    'readonly_key_456': {'name': 'Read Only Client', 'permissions': ['read']}
}

def validate_api_key():
    """Validate API key from request headers"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key not in VALID_API_KEYS:
        return False, None
    return True, VALID_API_KEYS[api_key]

def require_permission(permission):
    """Decorator to require specific permission"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            valid, client_info = validate_api_key()
            if not valid:
                return jsonify({'error': 'Invalid or missing API key'}), 401
            
            if permission not in client_info['permissions']:
                return jsonify({'error': f'Permission denied: {permission} required'}), 403
            
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ============================================================================
# DOCUMENT PROCESSING ENDPOINTS
# ============================================================================

@app.route('/api/v1/process/upload', methods=['POST'])
@require_permission('write')
def upload_and_process():
    """Upload and process a document"""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in API_CONFIG['supported_formats']:
            return jsonify({
                'error': f'Unsupported file format: {file_ext}',
                'supported_formats': API_CONFIG['supported_formats']
            }), 400
        
        # Generate processing ID
        process_id = str(uuid.uuid4())
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = Path(tempfile.gettempdir()) / f"{process_id}_{filename}"
        file.save(temp_path)
        
        # Upload to S3
        s3_key = f"{API_CONFIG['temp_prefix']}/{process_id}/{filename}"
        s3.upload_file(str(temp_path), API_CONFIG['s3_bucket'], s3_key)
        
        # Start processing
        processing_options = {
            'extract_text': request.form.get('extract_text', 'true').lower() == 'true',
            'classify_document': request.form.get('classify_document', 'true').lower() == 'true',
            'assess_quality': request.form.get('assess_quality', 'true').lower() == 'true',
            'custom_prompt': request.form.get('custom_prompt', '')
        }
        
        result = process_document_pipeline(s3_key, processing_options)
        
        # Clean up
        temp_path.unlink()
        
        return jsonify({
            'success': True,
            'process_id': process_id,
            'filename': filename,
            's3_key': s3_key,
            'result': result,
            'processed_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Upload processing error: {e}")
        return jsonify({'error': str(e)}), 500

def process_document_pipeline(s3_key: str, options: dict) -> dict:
    """Process document through the complete pipeline"""
    result = {
        'text_extraction': None,
        'classification': None,
        'quality_assessment': None,
        'custom_analysis': None
    }
    
    # Extract text if requested
    if options.get('extract_text'):
        result['text_extraction'] = extract_text_from_s3(s3_key)
    
    # Get extracted text for other processes
    extracted_text = ""
    if result['text_extraction'] and result['text_extraction'].get('success'):
        extracted_text = result['text_extraction']['text']
    
    # Classify document if requested
    if options.get('classify_document') and extracted_text:
        result['classification'] = classifier.classify_with_confidence(extracted_text)
    
    # Assess quality if requested
    if options.get('assess_quality') and extracted_text:
        document_type = None
        if result['classification']:
            document_type = result['classification'].get('final_classification')
        result['quality_assessment'] = quality_assessor.assess_quality(extracted_text, document_type)
    
    # Custom analysis if prompt provided
    if options.get('custom_prompt') and extracted_text:
        result['custom_analysis'] = perform_custom_analysis(extracted_text, options['custom_prompt'])
    
    return result

def extract_text_from_s3(s3_key: str) -> dict:
    """Extract text from document in S3 using Textract"""
    try:
        # Start Textract job
        response = textract.start_document_analysis(
            DocumentLocation={'S3Object': {'Bucket': API_CONFIG['s3_bucket'], 'Name': s3_key}},
            FeatureTypes=['FORMS', 'TABLES']
        )
        
        job_id = response['JobId']
        
        # Wait for completion (with timeout)
        import time
        max_wait = 300  # 5 minutes
        wait_time = 0
        
        while wait_time < max_wait:
            result = textract.get_document_analysis(JobId=job_id)
            status = result['JobStatus']
            
            if status == 'SUCCEEDED':
                # Extract text
                blocks = result['Blocks']
                text_lines = [block['Text'] for block in blocks if block['BlockType'] == 'LINE']
                extracted_text = '\n'.join(text_lines)
                
                return {
                    'success': True,
                    'job_id': job_id,
                    'text': extracted_text,
                    'block_count': len(blocks)
                }
            elif status == 'FAILED':
                return {
                    'success': False,
                    'error': 'Textract job failed'
                }
            
            time.sleep(5)
            wait_time += 5
        
        return {
            'success': False,
            'error': 'Textract job timeout'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def perform_custom_analysis(text: str, prompt: str) -> dict:
    """Perform custom analysis using provided prompt"""
    try:
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        
        # If no custom prompt provided, use the standard indexing prompt
        if not prompt.strip():
            full_prompt = f"""
            You are an expert in loan-file indexing. The following text is raw OCR from a PDF that may contain multiple accounts, multiple signers, and supporting documents.

            Return **only** a valid JSON array (do **not** wrap it in ```json or add any commentary).

            Indexing rules:
            1. One JSON object **per distinct account number**.
               - If no account number is found on a page, link the page to the account whose account holder's Name + PAN/Aadhaar/DOB already exists; otherwise create a new account object.

            2. Required fields for every account object:
               - Account Holder Names – array of strings (primary and co-borrowers there can be multiple names per account)
               - AccountNumber – string (primary key)
               - AccountType – string (e.g., "Business", "Personal", "Joint")
               - AccountPurpose – string (e.g., "Consumer", "Home Loan", "Car Loan", "Education Loan")
               - OwnershipType – string (e.g., "Single", "Joint", "Multiple")
               - WSFSAccountType – string (e.g., "WSFS Core Savings", "WSFS Checking", "WSFS Money Market")
               - StampDate – string (dd-mm-yyyy format)
               - MailingAddress – string (mailing address)
               - SSN – string (Social security number)
               - Attachments – array of objects with document type and information

            3. Date normalization rule:
               Any date you encounter – regardless of format – must be normalized to dd-mm-yyyy before it is stored.
               Acceptable incoming patterns include:
               - English-month variants: "DEC 262014", "Dec 26, 2014", "26 Dec 2014", "December 26 2014"
               - Numeric variants: "12/26/2014", "26-12-2014", "2014-12-26"
               - Special rule: Whenever you find a date that is not clearly tied to DateOpened, DateRevised, DOB, or any other specific field, always place it in StampDate (normalized to dd-mm-yyyy).

            4. Signers (guarantors, co-borrowers, or joint owners):
               Create an array Signers. Each signer object must contain:
               - SignerName – string
               - SSN – string
               - Address – string (full street address)
               - Mailing – string (mailing address if different)
               - HomePhone – string
               - WorkPhone – string
               - Employer – string
               - Occupation – string
               - DOB – string (dd-mm-yyyy)
               - BirthPlace – string
               - DLNumber – string
               - MMN – string (mother's maiden name)

            5. General extraction rules:
               - Preserve original spelling and casing
               - If a field is truly absent, supply an empty string or omit the key (never null)
               - Any date-like string should be normalized to dd-mm-yyyy
               - Page numbers are 1-based integers

            Document text:
            {text[:2000]}
            """
        else:
            full_prompt = f"""
            {prompt}
            
            Document text:
            {text[:2000]}
            
            Please provide your analysis in JSON format.
            """
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0,
            "messages": [{"role": "user", "content": full_prompt}]
        })
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            contentType="application/json",
            accept="application/json",
            body=body
        )
        
        result = json.loads(response["body"].read())
        ai_text = result["content"][0]["text"]
        
        return {
            'success': True,
            'prompt': prompt,
            'analysis': ai_text
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@app.route('/api/v1/search/documents', methods=['GET'])
@require_permission('read')
def search_documents():
    """Search documents"""
    try:
        query = request.args.get('q', '')
        search_type = request.args.get('type', 'traditional')  # traditional or semantic
        limit = int(request.args.get('limit', 10))
        
        # Build filters from query parameters
        filters = {}
        for key in ['account_number', 'document_type', 'customer_name']:
            if request.args.get(key):
                filters[key] = request.args.get(key)
        
        # Perform search
        if search_type == 'semantic':
            results = indexer.semantic_search(query, limit)
        else:
            results = indexer.search_documents(query, filters, limit)
        
        return jsonify({
            'success': True,
            'query': query,
            'search_type': search_type,
            'filters': filters,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/search/accounts/<account_number>', methods=['GET'])
@require_permission('read')
def get_account_details(account_number):
    """Get detailed account information"""
    try:
        summary = indexer.get_account_summary(account_number)
        
        return jsonify({
            'success': True,
            'account_number': account_number,
            'data': summary
        })
        
    except Exception as e:
        logger.error(f"Account lookup error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.route('/api/v1/analytics/stats', methods=['GET'])
@require_permission('read')
def get_analytics_stats():
    """Get platform analytics"""
    try:
        if not indexer.db:
            return jsonify({'error': 'Database not available'}), 503
        
        accounts_col = indexer.db[MONGODB_CONFIG['collections']['accounts']]
        documents_col = indexer.db[MONGODB_CONFIG['collections']['documents']]
        
        stats = {
            'total_accounts': accounts_col.count_documents({}),
            'total_documents': documents_col.count_documents({}),
            'last_updated': datetime.now().isoformat()
        }
        
        # Document type distribution
        pipeline = [{"$group": {"_id": "$document_type", "count": {"$sum": 1}}}]
        doc_types = list(documents_col.aggregate(pipeline))
        stats['document_types'] = {item['_id']: item['count'] for item in doc_types}
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'mongodb': 'healthy' if indexer.db else 'unhealthy',
            'textract': 'healthy',  # Assume healthy if no errors
            'bedrock': 'healthy',   # Assume healthy if no errors
            's3': 'healthy'         # Assume healthy if no errors
        }
    }
    
    # Overall status
    if any(status == 'unhealthy' for status in health_status['services'].values()):
        health_status['status'] = 'degraded'
    
    return jsonify(health_status)

@app.route('/api/v1/info', methods=['GET'])
def api_info():
    """API information and documentation"""
    return jsonify({
        'name': 'IDP Platform API',
        'version': '1.0.0',
        'description': 'RESTful API for Intelligent Document Processing',
        'endpoints': {
            'POST /api/v1/process/upload': 'Upload and process documents',
            'GET /api/v1/search/documents': 'Search documents',
            'GET /api/v1/search/accounts/<id>': 'Get account details',
            'GET /api/v1/analytics/stats': 'Get platform analytics',
            'GET /api/v1/health': 'Health check',
            'GET /api/v1/info': 'API information'
        },
        'authentication': 'API Key required in X-API-Key header',
        'supported_formats': API_CONFIG['supported_formats'],
        'max_file_size': f"{API_CONFIG['max_file_size'] // (1024*1024)}MB"
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    print("🚀 Starting IDP Platform API Gateway")
    print("📚 API Documentation available at: http://localhost:5005/api/v1/info")
    print("🔑 Demo API Key: demo_key_123")
    app.run(debug=True, host='0.0.0.0', port=5005)