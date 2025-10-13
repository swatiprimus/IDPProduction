#!/usr/bin/env python3
"""
unified_idp_ui.py

Unified IDP Platform UI - Complete document processing workflow
- Upload documents
- Check S3 cache for existing results
- Process with Textract + Bedrock if needed
- Classify, analyze, and perform RAG
- Save results to S3 for future use
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import boto3
import time
import tempfile
from pathlib import Path
import uuid
import hashlib
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

# Import our enhanced modules
from enhanced_classifier import EnhancedDocumentClassifier
from quality_assessor import DocumentQualityAssessor
from mongodb_rag_indexer import MongoDBRAGIndexer, MONGODB_CONFIG

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
AWS_CONFIG = {
    'region': 'us-east-1',
    'bucket': 'awsidpdocs',
    'cache_prefix': 'processed_cache',
    'temp_prefix': 'temp_uploads'
}

# Initialize AWS clients
s3 = boto3.client('s3', region_name=AWS_CONFIG['region'])
textract = boto3.client('textract', region_name=AWS_CONFIG['region'])
bedrock = boto3.client('bedrock-runtime', region_name=AWS_CONFIG['region'])

# Initialize processing modules
classifier = EnhancedDocumentClassifier(AWS_CONFIG['region'])
quality_assessor = DocumentQualityAssessor(AWS_CONFIG['region'])
mongodb_indexer = MongoDBRAGIndexer(MONGODB_CONFIG)

# Temporary storage for processing results
TEMP_DIR = Path("temp_processing")
TEMP_DIR.mkdir(exist_ok=True)

class DocumentProcessor:
    """Main document processing orchestrator"""
    
    def __init__(self):
        self.processing_stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'total_processed': 0
        }
    
    def get_document_hash(self, file_content: bytes) -> str:
        """Generate hash for document caching"""
        return hashlib.sha256(file_content).hexdigest()
    
    def check_cache(self, doc_hash: str) -> dict:
        """Check if document results exist in S3 cache"""
        cache_key = f"{AWS_CONFIG['cache_prefix']}/{doc_hash}/complete_results.json"
        
        try:
            response = s3.get_object(Bucket=AWS_CONFIG['bucket'], Key=cache_key)
            cached_results = json.loads(response['Body'].read().decode('utf-8'))
            
            logger.info(f"✅ Cache hit for document hash: {doc_hash}")
            self.processing_stats['cache_hits'] += 1
            
            return {
                'cache_hit': True,
                'results': cached_results,
                'cached_at': cached_results.get('processed_at'),
                'cache_key': cache_key
            }
            
        except Exception as e:
            logger.info(f"❌ Cache miss for document hash: {doc_hash}")
            self.processing_stats['cache_misses'] += 1
            
            return {
                'cache_hit': False,
                'error': str(e)
            }
    
    def save_to_cache(self, doc_hash: str, results: dict) -> str:
        """Save processing results to S3 cache"""
        cache_key = f"{AWS_CONFIG['cache_prefix']}/{doc_hash}/complete_results.json"
        
        try:
            # Add caching metadata
            results['cache_metadata'] = {
                'document_hash': doc_hash,
                'cached_at': datetime.now().isoformat(),
                'cache_key': cache_key
            }
            
            # Save to S3
            s3.put_object(
                Bucket=AWS_CONFIG['bucket'],
                Key=cache_key,
                Body=json.dumps(results, indent=2, default=str),
                ContentType='application/json'
            )
            
            logger.info(f"💾 Saved results to cache: {cache_key}")
            return cache_key
            
        except Exception as e:
            logger.error(f"❌ Failed to save to cache: {e}")
            return None
    
    def process_document_complete(self, file_content: bytes, filename: str, 
                                processing_options: dict) -> dict:
        """Complete document processing workflow"""
        
        # Generate document hash for caching
        doc_hash = self.get_document_hash(file_content)
        
        # Check cache first
        cache_result = self.check_cache(doc_hash)
        if cache_result['cache_hit'] and not processing_options.get('force_reprocess', False):
            return {
                'success': True,
                'from_cache': True,
                'document_hash': doc_hash,
                'filename': filename,
                'results': cache_result['results'],
                'processing_time': 0,
                'cost_saved': True
            }
        
        # Process document if not in cache
        start_time = time.time()
        
        try:
            # Step 1: Upload to S3 temporarily
            temp_key = f"{AWS_CONFIG['temp_prefix']}/{doc_hash}/{filename}"
            s3.put_object(
                Bucket=AWS_CONFIG['bucket'],
                Key=temp_key,
                Body=file_content
            )
            
            # Step 2: Extract text with Textract
            logger.info("🔍 Starting Textract extraction...")
            extraction_result = self.extract_text_with_textract(temp_key)
            
            if not extraction_result['success']:
                return {
                    'success': False,
                    'error': 'Text extraction failed',
                    'details': extraction_result
                }
            
            extracted_text = extraction_result['text']
            
            # Step 3: Classify document
            logger.info("📋 Classifying document...")
            classification_result = classifier.classify_with_confidence(extracted_text)
            
            # Step 4: Assess quality
            logger.info("⭐ Assessing document quality...")
            document_type = classification_result.get('final_classification')
            quality_result = quality_assessor.assess_quality(extracted_text, document_type)
            
            # Step 5: Perform custom analysis if requested
            custom_analysis = None
            if processing_options.get('custom_prompt'):
                logger.info("🤖 Performing custom analysis...")
                custom_analysis = self.perform_custom_analysis(
                    extracted_text, 
                    processing_options['custom_prompt']
                )
            
            # Step 6: Index in MongoDB for RAG
            logger.info("📚 Indexing for RAG search...")
            rag_indexing = self.index_for_rag(doc_hash, extracted_text, {
                'filename': filename,
                'classification': classification_result,
                'quality': quality_result,
                'custom_analysis': custom_analysis
            })
            
            # Compile complete results
            complete_results = {
                'document_info': {
                    'filename': filename,
                    'document_hash': doc_hash,
                    'file_size': len(file_content),
                    'processed_at': datetime.now().isoformat()
                },
                'text_extraction': extraction_result,
                'classification': classification_result,
                'quality_assessment': quality_result,
                'custom_analysis': custom_analysis,
                'rag_indexing': rag_indexing,
                'processing_metadata': {
                    'processing_time': time.time() - start_time,
                    'textract_job_id': extraction_result.get('job_id'),
                    'temp_s3_key': temp_key
                }
            }
            
            # Step 7: Save to cache
            cache_key = self.save_to_cache(doc_hash, complete_results)
            
            # Clean up temporary S3 file
            try:
                s3.delete_object(Bucket=AWS_CONFIG['bucket'], Key=temp_key)
            except:
                pass  # Ignore cleanup errors
            
            self.processing_stats['total_processed'] += 1
            
            return {
                'success': True,
                'from_cache': False,
                'document_hash': doc_hash,
                'filename': filename,
                'results': complete_results,
                'processing_time': time.time() - start_time,
                'cache_key': cache_key
            }
            
        except Exception as e:
            logger.error(f"❌ Document processing failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'document_hash': doc_hash,
                'filename': filename
            }
    
    def extract_text_with_textract(self, s3_key: str) -> dict:
        """Extract text using Textract"""
        try:
            # Start Textract job
            response = textract.start_document_analysis(
                DocumentLocation={'S3Object': {'Bucket': AWS_CONFIG['bucket'], 'Name': s3_key}},
                FeatureTypes=['FORMS', 'TABLES', 'LAYOUT']
            )
            
            job_id = response['JobId']
            
            # Wait for completion
            while True:
                result = textract.get_document_analysis(JobId=job_id)
                status = result['JobStatus']
                
                if status == 'SUCCEEDED':
                    # Get all blocks
                    all_blocks = result['Blocks']
                    
                    # Handle pagination
                    while 'NextToken' in result:
                        result = textract.get_document_analysis(
                            JobId=job_id, 
                            NextToken=result['NextToken']
                        )
                        all_blocks.extend(result['Blocks'])
                    
                    # Extract text
                    text_lines = [block['Text'] for block in all_blocks if block['BlockType'] == 'LINE']
                    extracted_text = '\n'.join(text_lines)
                    
                    # Extract forms data
                    forms_data = self.extract_forms_data(all_blocks)
                    
                    return {
                        'success': True,
                        'job_id': job_id,
                        'text': extracted_text,
                        'forms_data': forms_data,
                        'total_blocks': len(all_blocks),
                        'text_length': len(extracted_text)
                    }
                    
                elif status == 'FAILED':
                    return {
                        'success': False,
                        'error': 'Textract job failed',
                        'job_id': job_id
                    }
                
                time.sleep(3)  # Wait before checking again
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def extract_forms_data(self, blocks: list) -> dict:
        """Extract key-value pairs from Textract blocks"""
        block_map = {block['Id']: block for block in blocks}
        forms_data = {}
        
        for block in blocks:
            if block['BlockType'] == 'KEY_VALUE_SET' and 'KEY' in block.get('EntityTypes', []):
                key_text = self.get_text_from_block(block, block_map, 'KEY')
                value_text = self.get_text_from_block(block, block_map, 'VALUE')
                
                if key_text:
                    forms_data[key_text] = value_text
        
        return forms_data
    
    def get_text_from_block(self, block: dict, block_map: dict, entity_type: str) -> str:
        """Extract text from a specific block type"""
        text_parts = []
        
        for relationship in block.get('Relationships', []):
            if relationship['Type'] == 'CHILD' and entity_type == 'KEY':
                for child_id in relationship['Ids']:
                    if child_id in block_map and block_map[child_id]['BlockType'] == 'WORD':
                        text_parts.append(block_map[child_id]['Text'])
            elif relationship['Type'] == 'VALUE' and entity_type == 'VALUE':
                for value_id in relationship['Ids']:
                    if value_id in block_map:
                        value_block = block_map[value_id]
                        for value_rel in value_block.get('Relationships', []):
                            if value_rel['Type'] == 'CHILD':
                                for child_id in value_rel['Ids']:
                                    if child_id in block_map and block_map[child_id]['BlockType'] == 'WORD':
                                        text_parts.append(block_map[child_id]['Text'])
        
        return ' '.join(text_parts).strip()
    
    def perform_custom_analysis(self, text: str, prompt: str) -> dict:
        """Perform custom analysis using Bedrock"""
        try:
            full_prompt = f"""
            {prompt}
            
            Document text:
            {text[:3000]}  # Limit text to avoid token limits
            
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
                'analysis': ai_text,
                'model_used': 'claude-3-sonnet'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'prompt': prompt
            }
    
    def index_for_rag(self, doc_hash: str, text: str, metadata: dict) -> dict:
        """Index document for RAG search"""
        try:
            # Create a document record for MongoDB
            document_record = {
                'document_id': doc_hash,
                'text_content': text,
                'metadata': metadata,
                'indexed_at': datetime.now()
            }
            
            # Index in MongoDB (simplified - you can enhance this)
            if mongodb_indexer.db:
                collection = mongodb_indexer.db['rag_documents']
                collection.replace_one(
                    {'document_id': doc_hash},
                    document_record,
                    upsert=True
                )
                
                return {
                    'success': True,
                    'document_id': doc_hash,
                    'indexed_at': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': 'MongoDB not available'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

# Initialize processor
processor = DocumentProcessor()

@app.route('/')
def index():
    """Main upload and processing page"""
    return render_template('unified_idp.html')

@app.route('/api/process', methods=['POST'])
def process_document():
    """Process uploaded document through complete workflow"""
    try:
        # Check if file was uploaded
        if 'document' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['document']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        # Validate file type
        if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            return jsonify({
                'success': False, 
                'message': 'Unsupported file format. Please upload PDF, PNG, or JPG files.'
            })
        
        # Get processing options
        processing_options = {
            'custom_prompt': request.form.get('custom_prompt', '').strip(),
            'force_reprocess': request.form.get('force_reprocess', 'false').lower() == 'true',
            'enable_rag': request.form.get('enable_rag', 'true').lower() == 'true'
        }
        
        # Read file content
        file_content = file.read()
        filename = secure_filename(file.filename)
        
        # Process document
        result = processor.process_document_complete(file_content, filename, processing_options)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        return jsonify({
            'success': False,
            'message': f'Processing error: {str(e)}'
        })

@app.route('/api/search', methods=['POST'])
def search_documents():
    """Search processed documents using RAG"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        search_type = data.get('search_type', 'semantic')  # semantic or traditional
        limit = int(data.get('limit', 10))
        
        if not query:
            return jsonify({
                'success': False,
                'message': 'Please provide a search query'
            })
        
        # Perform search using MongoDB indexer
        if search_type == 'semantic':
            results = mongodb_indexer.semantic_search(query, limit)
        else:
            results = mongodb_indexer.search_documents(query, {}, limit)
        
        return jsonify({
            'success': True,
            'query': query,
            'search_type': search_type,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({
            'success': False,
            'message': f'Search error: {str(e)}'
        })

@app.route('/api/stats')
def get_stats():
    """Get processing statistics"""
    try:
        stats = {
            'processing_stats': processor.processing_stats,
            'cache_hit_rate': (
                processor.processing_stats['cache_hits'] / 
                max(processor.processing_stats['cache_hits'] + processor.processing_stats['cache_misses'], 1)
            ),
            'total_documents': processor.processing_stats['total_processed'],
            'mongodb_status': 'connected' if mongodb_indexer.db else 'disconnected'
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/download/<doc_hash>')
def download_results(doc_hash):
    """Download complete processing results"""
    try:
        cache_key = f"{AWS_CONFIG['cache_prefix']}/{doc_hash}/complete_results.json"
        
        # Get from S3
        response = s3.get_object(Bucket=AWS_CONFIG['bucket'], Key=cache_key)
        results = response['Body'].read()
        
        # Save to temporary file
        temp_file = TEMP_DIR / f"results_{doc_hash}.json"
        with open(temp_file, 'wb') as f:
            f.write(results)
        
        return send_file(
            temp_file,
            as_attachment=True,
            download_name=f"document_analysis_{doc_hash}.json",
            mimetype='application/json'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 404

if __name__ == '__main__':
    print("🚀 Starting Unified IDP Platform")
    print("📄 Upload documents at: http://localhost:5000")
    print("💾 Results cached in S3 for cost optimization")
    print("🔍 RAG search enabled for processed documents")
    
    app.run(debug=True, host='0.0.0.0', port=5000)