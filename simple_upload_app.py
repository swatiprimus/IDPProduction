#!/usr/bin/env python3
"""
Simple S3 Upload App - Just upload PDFs to S3
app_modular.py will automatically process them
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import boto3
import json
from datetime import datetime
import logging
import sys
import hashlib
import time

# Configure logging with flush
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
# Suppress boto3 debug logs
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

app = Flask(__name__, template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
CORS(app)

# S3 client
s3_client = boto3.client('s3', region_name='us-east-1')
BUCKET = 'aws-idp-uploads'

print("\n" + "="*80)
print("🚀 SIMPLE UPLOAD APP STARTING")
print("="*80)
print(f"Bucket: {BUCKET}")
print(f"Region: us-east-1")
print("="*80 + "\n")


@app.route('/')
def index():
    """Simple upload page"""
    logger.info("✅ GET / - Upload page accessed")
    return render_template('upload.html')


@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify backend is working"""
    logger.info("✅ GET /api/test - Test endpoint called")
    return jsonify({'status': 'ok', 'message': 'Backend is working'}), 200


@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def upload_files():
    """Upload files to S3"""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    print("\n" + "="*80)
    print("🚀 UPLOAD ENDPOINT CALLED")
    print("="*80)
    logger.info("🚀 UPLOAD ENDPOINT CALLED")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Content-Type: {request.content_type}")
    logger.info(f"Content-Length: {request.content_length}")
    print(f"Request method: {request.method}")
    print(f"Content-Type: {request.content_type}")
    print(f"Content-Length: {request.content_length}")
    
    try:
        # Debug: print all form data
        print(f"\n� REQUESlT DATA:")
        print(f"   Form keys: {list(request.form.keys())}")
        print(f"   Files keys: {list(request.files.keys())}")
        logger.info(f"Form keys: {list(request.form.keys())}")
        logger.info(f"Files keys: {list(request.files.keys())}")
        
        # Get files from request
        files = request.files.getlist('files')
        print(f"\n📥 FILES RECEIVED: {len(files)}")
        logger.info(f"📥 FILES RECEIVED: {len(files)}")
        
        # If no files, try alternative field names
        if len(files) == 0:
            print("   ⚠️ No files in 'files' field, trying alternatives...")
            files = request.files.getlist('file')
            print(f"   Trying 'file' field: {len(files)} files")
            logger.info(f"Trying 'file' field: {len(files)} files")
        
        if len(files) == 0:
            print("   ⚠️ Still no files, checking all request.files:")
            for key in request.files.keys():
                file_list = request.files.getlist(key)
                print(f"   - {key}: {len(file_list)} files")
                logger.info(f"   - {key}: {len(file_list)} files")
        
        if not files or len(files) == 0:
            logger.error("❌ NO FILES PROVIDED IN REQUEST")
            print("❌ NO FILES PROVIDED IN REQUEST")
            print("="*80 + "\n")
            return jsonify({'error': 'No files provided', 'success': False}), 400
        
        uploaded = []
        errors = []
        
        for idx, file in enumerate(files):
            try:
                print(f"\n📄 FILE {idx+1}/{len(files)}")
                print(f"   Filename: {file.filename}")
                print(f"   Content-Type: {file.content_type}")
                logger.info(f"📄 FILE {idx+1}/{len(files)}: {file.filename}")
                logger.info(f"   Content-Type: {file.content_type}")
                
                # Validate PDF
                if not file.filename.lower().endswith('.pdf'):
                    logger.warning(f"❌ Not a PDF: {file.filename}")
                    print(f"   ❌ Not a PDF: {file.filename}")
                    errors.append({'file': file.filename, 'error': 'Only PDF files allowed'})
                    continue
                
                # Read file content
                file_content = file.read()
                print(f"   Size: {len(file_content)} bytes")
                logger.info(f"   Size: {len(file_content)} bytes")
                
                # Upload to S3
                file_key = f"uploads/{file.filename}"
                print(f"   Uploading to S3: {file_key}")
                logger.info(f"   Uploading to S3: {file_key}")
                
                s3_client.put_object(
                    Bucket=BUCKET,
                    Key=file_key,
                    Body=file_content,
                    ContentType='application/pdf'
                )
                
                print(f"   ✅ Upload successful!")
                logger.info(f"   ✅ Upload successful!")
                
                # Generate unique ID for this document (same format as /process endpoint)
                # This ID will be used when S3 fetcher calls /process
                doc_id = hashlib.md5(f"{file.filename}{time.time()}".encode()).hexdigest()[:12]
                print(f"   Generated ID: {doc_id}")
                logger.info(f"   Generated ID: {doc_id}")
                
                # NOTE: Do NOT create a document record here!
                # The S3 fetcher will detect this file and call /process endpoint
                # The /process endpoint will create the document record with the proper ID
                # This prevents duplicate document entries
                
                print(f"   📋 Document will be processed by S3 fetcher (detected in ~30 seconds)")
                logger.info(f"   📋 Document will be processed by S3 fetcher (detected in ~30 seconds)")
                
                uploaded.append({
                    'file_name': file.filename,
                    'file_key': file_key,
                    'upload_time': datetime.now().isoformat(),
                    'message': 'Uploaded to S3 - will be processed by S3 fetcher'
                })
                
            except Exception as e:
                logger.error(f"   ❌ Error: {str(e)}", exc_info=True)
                print(f"   ❌ Error: {str(e)}")
                errors.append({'file': file.filename, 'error': str(e)})
        
        # Build response
        response = {
            'success': len(uploaded) > 0,
            'uploaded': uploaded,
            'errors': errors,
            'message': f'Uploaded {len(uploaded)} file(s)'
        }
        
        print(f"\n📊 UPLOAD SUMMARY")
        print(f"   Successful: {len(uploaded)}")
        print(f"   Errors: {len(errors)}")
        logger.info(f"📊 UPLOAD SUMMARY - Successful: {len(uploaded)}, Errors: {len(errors)}")
        print("="*80 + "\n")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"❌ UPLOAD ERROR: {str(e)}", exc_info=True)
        print(f"❌ UPLOAD ERROR: {str(e)}")
        print("="*80 + "\n")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Get all documents and their processing status"""
    try:
        logger.debug("📋 GET /api/documents - Fetching documents list")
        documents = []
        
        # List all uploaded documents
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET, Prefix='uploads/')
        
        doc_count = 0
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                file_name = key.split('/')[-1]
                doc_count += 1
                
                # Check if processed
                try:
                    status_response = s3_client.get_object(
                        Bucket=BUCKET,
                        Key=f"processing_logs/{key}.status.json"
                    )
                    status_data = json.loads(status_response['Body'].read())
                    status = status_data.get('status', 'pending')
                except:
                    status = 'pending'
                
                documents.append({
                    'file_name': file_name,
                    'file_key': key,
                    'size': obj['Size'],
                    'upload_time': obj['LastModified'].isoformat(),
                    'status': status
                })
        
        logger.debug(f"✅ Found {len(documents)} documents")
        return jsonify({
            'success': True,
            'documents': documents,
            'total': len(documents)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error getting documents: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete', methods=['POST'])
def delete_document():
    """Delete a document from S3"""
    try:
        data = request.get_json()
        file_key = data.get('file_key')
        
        if not file_key:
            return jsonify({'success': False, 'error': 'No file_key provided'}), 400
        
        logger.info(f"🗑️ Deleting document: {file_key}")
        
        # Delete the file
        s3_client.delete_object(Bucket=BUCKET, Key=file_key)
        
        # Delete the status file
        try:
            s3_client.delete_object(Bucket=BUCKET, Key=f"processing_logs/{file_key}.status.json")
        except:
            pass
        
        logger.info(f"✅ Document deleted: {file_key}")
        return jsonify({'success': True, 'message': 'Document deleted'}), 200
        
    except Exception as e:
        logger.error(f"❌ Error deleting document: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-all', methods=['POST'])
def delete_all_documents():
    """Delete all documents from S3"""
    try:
        logger.info("🗑️ Deleting ALL documents from S3...")
        
        deleted_count = 0
        
        # List all objects in uploads folder
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET, Prefix='uploads/')
        
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                
                # Delete the file
                s3_client.delete_object(Bucket=BUCKET, Key=key)
                
                # Delete the status file
                try:
                    s3_client.delete_object(Bucket=BUCKET, Key=f"processing_logs/{key}.status.json")
                except:
                    pass
                
                deleted_count += 1
                logger.info(f"   ✅ Deleted: {key}")
        
        logger.info(f"✅ All documents deleted: {deleted_count} files removed")
        return jsonify({'success': True, 'message': f'Deleted {deleted_count} documents', 'deleted_count': deleted_count}), 200
        
    except Exception as e:
        logger.error(f"❌ Error deleting all documents: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting Simple Upload App on port 5001")
    print("Starting Simple Upload App on port 5001")
    app.run(debug=True, port=5001, host='0.0.0.0')
