#!/usr/bin/env python3
"""
Standalone Document Processor
Uploads PDFs, extracts OCR, detects accounts, and saves to S3
"""

import os
import sys
import json
import uuid
import boto3
import tempfile
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor

# Add app/services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'services'))

from regex_account_detector import RegexAccountDetector

# Configuration
AWS_REGION = "us-east-1"
S3_BUCKET = "awsidpdocs"
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Initialize AWS clients
s3_client = boto3.client('s3', region_name=AWS_REGION)
textract_client = boto3.client('textract', region_name=AWS_REGION)

# Initialize detector
detector = RegexAccountDetector()

# Processing status tracker
processing_status = {}
executor = ThreadPoolExecutor(max_workers=3)


def allowed_file(filename):
    """Check if file is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_with_textract_async_with_progress(s3_bucket, s3_key, doc_id):
    """Extract text from PDF using AWS Textract async API with progress updates"""
    try:
        print(f"[TEXTRACT ASYNC] Starting async job for: {s3_key}")
        
        # Start async job
        response = textract_client.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
        )
        job_id = response['JobId']
        print(f"[TEXTRACT ASYNC] Job started: {job_id}")
        
        # Poll for completion with progress updates
        max_wait = 600  # 10 minutes max
        wait_time = 0
        poll_interval = 5
        
        while wait_time < max_wait:
            time.sleep(poll_interval)
            wait_time += poll_interval
            
            result = textract_client.get_document_text_detection(JobId=job_id)
            status = result['JobStatus']
            
            # Calculate progress: 20% (upload) + 20-50% (textract polling)
            progress = 20 + (wait_time / max_wait) * 30
            progress = min(progress, 50)  # Cap at 50%
            
            # Update status with progress
            if doc_id in processing_status:
                processing_status[doc_id]['progress'] = int(progress)
                processing_status[doc_id]['message'] = f'Extracting text with Textract... ({wait_time}s elapsed)'
            
            print(f"[TEXTRACT ASYNC] Status: {status} (waited {wait_time}s, progress {progress:.0f}%)")
            
            if status == 'SUCCEEDED':
                # Extract text from all pages
                extracted_text = ""
                block_count = 0
                
                # Get first page
                for block in result.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        extracted_text += block['Text'] + "\n"
                        block_count += 1
                
                # Get additional pages if any
                next_token = result.get('NextToken')
                while next_token:
                    result = textract_client.get_document_text_detection(
                        JobId=job_id, NextToken=next_token
                    )
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block['Text'] + "\n"
                            block_count += 1
                    next_token = result.get('NextToken')
                
                print(f"[TEXTRACT ASYNC] ✓ Completed: {block_count} lines, {len(extracted_text)} characters")
                return extracted_text if extracted_text.strip() else None
                
            elif status == 'FAILED':
                error_msg = result.get('StatusMessage', 'Unknown error')
                print(f"[TEXTRACT ASYNC] Job failed: {error_msg}")
                return None
        
        print(f"[TEXTRACT ASYNC] Job timed out after {max_wait} seconds")
        return None
        
    except Exception as e:
        print(f"[TEXTRACT ASYNC ERROR] {str(e)}")
        return None


def extract_text_with_textract_async(s3_bucket, s3_key):
    """Extract text from PDF using AWS Textract async API (for multi-page PDFs)"""
    try:
        print(f"[TEXTRACT ASYNC] Starting async job for: {s3_key}")
        
        # Start async job
        response = textract_client.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
        )
        job_id = response['JobId']
        print(f"[TEXTRACT ASYNC] Job started: {job_id}")
        
        # Poll for completion
        max_wait = 600  # 10 minutes max
        wait_time = 0
        while wait_time < max_wait:
            time.sleep(5)
            wait_time += 5
            
            result = textract_client.get_document_text_detection(JobId=job_id)
            status = result['JobStatus']
            print(f"[TEXTRACT ASYNC] Status: {status} (waited {wait_time}s)")
            
            if status == 'SUCCEEDED':
                # Extract text from all pages
                extracted_text = ""
                block_count = 0
                
                # Get first page
                for block in result.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        extracted_text += block['Text'] + "\n"
                        block_count += 1
                
                # Get additional pages if any
                next_token = result.get('NextToken')
                while next_token:
                    result = textract_client.get_document_text_detection(
                        JobId=job_id, NextToken=next_token
                    )
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block['Text'] + "\n"
                            block_count += 1
                    next_token = result.get('NextToken')
                
                print(f"[TEXTRACT ASYNC] ✓ Completed: {block_count} lines, {len(extracted_text)} characters")
                return extracted_text if extracted_text.strip() else None
                
            elif status == 'FAILED':
                error_msg = result.get('StatusMessage', 'Unknown error')
                print(f"[TEXTRACT ASYNC] Job failed: {error_msg}")
                return None
        
        print(f"[TEXTRACT ASYNC] Job timed out after {max_wait} seconds")
        return None
        
    except Exception as e:
        print(f"[TEXTRACT ASYNC ERROR] {str(e)}")
        return None


def extract_text_with_textract(pdf_path):
    """Extract text from PDF using AWS Textract sync API"""
    try:
        with open(pdf_path, 'rb') as f:
            file_bytes = f.read()
        
        # For small files, try sync API first
        if len(file_bytes) < 5 * 1024 * 1024:  # < 5MB
            try:
                response = textract_client.detect_document_text(Document={'Bytes': file_bytes})
                
                text = ""
                for block in response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        text += block.get('Text', '') + "\n"
                
                return text if text.strip() else None
            except Exception as e:
                print(f"[WARN] Textract sync failed: {e}, trying async...")
                return None
        else:
            print(f"[WARN] File > 5MB, use async API")
            return None
            
    except Exception as e:
        print(f"[WARN] Textract extraction failed: {e}")
        return None


def extract_text_with_pypdf(pdf_path):
    """Extract text from PDF using PyPDF2"""
    try:
        import PyPDF2
        
        text = ""
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        return text if text.strip() else None
    except Exception as e:
        print(f"[WARN] PyPDF2 extraction failed: {e}")
        return None


def extract_text_with_fitz(pdf_path):
    """Extract text from PDF using PyMuPDF (fitz)"""
    try:
        import fitz
        
        text = ""
        pdf_doc = fitz.open(pdf_path)
        for page in pdf_doc:
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"
        pdf_doc.close()
        
        return text if text.strip() else None
    except Exception as e:
        print(f"[WARN] PyMuPDF extraction failed: {e}")
        return None


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF - try multiple methods"""
    # Try Textract first
    text = extract_text_with_textract(pdf_path)
    if text and len(text.strip()) > 100:
        return text, "textract"
    
    # Fallback to PyPDF2
    text = extract_text_with_pypdf(pdf_path)
    if text and len(text.strip()) > 100:
        return text, "pypdf2"
    
    return None, None


def process_document_background(doc_id, pdf_path, filename):
    """Background processing of document"""
    try:
        print(f"[PROCESSOR] Starting processing for {doc_id}")
        
        # Update status
        processing_status[doc_id] = {
            'status': 'processing',
            'progress': 10,
            'message': 'Uploading PDF to S3...',
            'accounts': [],
            'total_pages': 0
        }
        
        # Upload PDF to S3 for async processing
        s3_key = f"uploads/{doc_id}/{filename}"
        with open(pdf_path, 'rb') as f:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=f.read()
            )
        print(f"[PROCESSOR] Uploaded PDF to S3: {s3_key}")
        
        # Update status
        processing_status[doc_id]['progress'] = 20
        processing_status[doc_id]['message'] = 'Extracting text with Textract async...'
        
        # Extract text using async Textract with progress updates
        text = extract_text_with_textract_async_with_progress(S3_BUCKET, s3_key, doc_id)
        method = "textract_async"
        
        # Fallback to sync/pypdf if async fails
        if not text:
            print(f"[PROCESSOR] Async Textract failed, trying sync methods...")
            processing_status[doc_id]['message'] = 'Trying alternative extraction methods...'
            text, method = extract_text_from_pdf(pdf_path)
        
        if not text:
            raise Exception("Failed to extract text from PDF")
        
        print(f"[PROCESSOR] Extracted text using {method}")
        
        # Update status
        processing_status[doc_id]['progress'] = 30
        processing_status[doc_id]['message'] = 'Detecting accounts...'
        
        # Detect accounts
        accounts = detector.extract_accounts_from_text(text)
        print(f"[PROCESSOR] Found {len(accounts)} unique accounts")
        
        # Save OCR text to S3
        ocr_cache_key = f"page_ocr/{doc_id}/page_0.json"
        ocr_data = {
            'page_text': text,
            'extraction_method': method,
            'extracted_at': datetime.now().isoformat(),
            'total_pages': 1
        }
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=ocr_cache_key,
            Body=json.dumps(ocr_data),
            ContentType='application/json'
        )
        print(f"[PROCESSOR] Saved OCR cache to S3: {ocr_cache_key}")
        
        # Update status
        processing_status[doc_id]['progress'] = 60
        processing_status[doc_id]['message'] = 'Saving results...'
        
        # Build results
        results = {
            'doc_id': doc_id,
            'filename': filename,
            'accounts': [{'account_number': acc, 'pages': [1]} for acc in accounts],
            'total_pages': 1,
            'total_accounts': len(accounts),
            'extraction_method': method,
            'processed_at': datetime.now().isoformat()
        }
        
        # Save results to S3
        results_key = f"document_results/{doc_id}/results.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=results_key,
            Body=json.dumps(results),
            ContentType='application/json'
        )
        print(f"[PROCESSOR] Saved results to S3: {results_key}")
        
        # Update status to completed
        processing_status[doc_id] = {
            'status': 'completed',
            'progress': 100,
            'message': 'Processing complete!',
            'accounts': results['accounts'],
            'total_pages': 1,
            'doc_id': doc_id,
            'filename': filename
        }
        
        print(f"[PROCESSOR] Completed processing for {doc_id}")
        
    except Exception as e:
        print(f"[ERROR] Processing failed for {doc_id}: {e}")
        processing_status[doc_id] = {
            'status': 'error',
            'progress': 0,
            'message': str(e),
            'accounts': [],
            'total_pages': 0
        }


@app.route('/')
def index():
    """Main page"""
    return render_template('document_processor.html')


@app.route('/api/process-document', methods=['POST'])
def process_document():
    """Upload and process document"""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Only PDF files are allowed'}), 400
        
        # Generate document ID
        doc_id = str(uuid.uuid4())[:12]
        
        # Save file temporarily
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"{doc_id}.pdf")
        file.save(temp_path)
        
        print(f"[API] Received document: {file.filename} -> {doc_id}")
        
        # Start background processing
        executor.submit(process_document_background, doc_id, temp_path, file.filename)
        
        # Initialize status
        processing_status[doc_id] = {
            'status': 'queued',
            'progress': 5,
            'message': 'Queued for processing...',
            'accounts': [],
            'total_pages': 0
        }
        
        return jsonify({
            'success': True,
            'doc_id': doc_id,
            'message': 'Document uploaded, processing started'
        })
        
    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/process-status/<doc_id>', methods=['GET'])
def get_process_status(doc_id):
    """Get processing status"""
    try:
        if doc_id not in processing_status:
            return jsonify({'success': False, 'message': 'Document not found'}), 404
        
        status = processing_status[doc_id]
        return jsonify({
            'success': True,
            'status': status['status'],
            'progress': status['progress'],
            'message': status['message'],
            'accounts': status.get('accounts', []),
            'total_pages': status.get('total_pages', 0),
            'doc_id': doc_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    print(f"[INFO] Starting Document Processor")
    print(f"[INFO] AWS Region: {AWS_REGION}")
    print(f"[INFO] S3 Bucket: {S3_BUCKET}")
    print(f"[INFO] Running on http://127.0.0.1:5016")
    
    app.run(debug=True, port=5016)