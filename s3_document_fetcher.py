#!/usr/bin/env python3
"""
S3 Document Fetcher
Continuously polls S3 for new documents and processes them
Runs in background thread - completely separate from Flask app
"""

import boto3
import json
import time
import threading
import tempfile
import os
import hashlib
from datetime import datetime
from typing import Dict, Optional

# Import processing functions
from app.services.textract_service import extract_text_with_textract
from app.services.document_detector import detect_document_type

# Import global document queue
from document_queue import get_document_queue


class S3DocumentFetcher:
    """Fetches and processes documents from S3"""
    
    def __init__(self, bucket_name: str = "aws-idp-uploads", region: str = "us-east-1", check_interval: int = 30):
        """
        Initialize S3 Document Fetcher
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region
            check_interval: How often to check for new documents (seconds)
        """
        self.bucket_name = bucket_name
        self.region = region
        self.check_interval = check_interval
        self.s3_client = boto3.client('s3', region_name=region)
        self.is_running = False
        self.thread = None
        self.processing_map_file = '.s3_fetcher_processing_map.json'
        
        # Load persistent processing map
        self.processing_map = self._load_processing_map()
        
        print(f"[S3_FETCHER] 🚀 Initialized")
        print(f"[S3_FETCHER]    Bucket: {bucket_name}")
        print(f"[S3_FETCHER]    Region: {region}")
        print(f"[S3_FETCHER]    Check interval: {check_interval}s")
        print(f"[S3_FETCHER]    Tracking {len(self.processing_map)} documents in processing map")
    
    def start(self):
        """Start the document fetcher in background thread"""
        if self.is_running:
            print("[S3_FETCHER] ⚠️ Already running")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self.thread.start()
        print("[S3_FETCHER] ✅ Started - polling S3 every 30 seconds")
    
    def stop(self):
        """Stop the document fetcher"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[S3_FETCHER] ⏹️ Stopped")
    
    def _load_processing_map(self) -> dict:
        """Load persistent processing map from file"""
        try:
            if os.path.exists(self.processing_map_file):
                with open(self.processing_map_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[S3_FETCHER] ⚠️ Failed to load processing map: {str(e)}")
        return {}
    
    def _save_processing_map(self):
        """Save processing map to file"""
        try:
            with open(self.processing_map_file, 'w') as f:
                json.dump(self.processing_map, f, indent=2)
        except Exception as e:
            print(f"[S3_FETCHER] ⚠️ Failed to save processing map: {str(e)}")
    
    def _mark_processing(self, file_key: str):
        """Mark document as being processed"""
        self.processing_map[file_key] = {
            'status': 'processing',
            'started_at': datetime.now().isoformat()
        }
        self._save_processing_map()
    
    def _mark_completed(self, file_key: str):
        """Mark document as completed"""
        self.processing_map[file_key] = {
            'status': 'completed',
            'completed_at': datetime.now().isoformat()
        }
        self._save_processing_map()
    
    def _is_in_processing_map(self, file_key: str) -> bool:
        """Check if document is in processing map"""
        return file_key in self.processing_map
    
    def _get_processing_status(self, file_key: str) -> str:
        """Get processing status from map"""
        if file_key in self.processing_map:
            return self.processing_map[file_key].get('status', 'unknown')
        return 'unknown'
    
    
    def _fetch_loop(self):
        """Main polling loop - runs in background thread"""
        import sys
        print("[S3_FETCHER] 🔄 Fetch loop started", flush=True)
        sys.stdout.flush()
        
        while self.is_running:
            try:
                # Get list of unprocessed documents
                unprocessed = self._get_unprocessed_documents()
                
                if unprocessed:
                    print(f"[S3_FETCHER] 📋 Found {len(unprocessed)} unprocessed document(s)", flush=True)
                    sys.stdout.flush()
                    
                    # Process each document
                    for doc_key in unprocessed:
                        if not self.is_running:
                            break
                        
                        self._process_document(doc_key)
                else:
                    print(f"[S3_FETCHER] ✅ No new documents (checked at {datetime.now().strftime('%H:%M:%S')})", flush=True)
                    sys.stdout.flush()
                
                # Wait before next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[S3_FETCHER] ❌ Error in fetch loop: {str(e)}", flush=True)
                sys.stdout.flush()
                time.sleep(self.check_interval)
    
    def _get_unprocessed_documents(self) -> list:
        """
        Get list of unprocessed documents from S3
        Checks global document queue first to prevent duplicate processing
        
        Returns:
            List of S3 keys for unprocessed documents
        """
        import sys
        try:
            unprocessed = []
            doc_queue = get_document_queue()
            
            # List all objects in uploads folder
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix='uploads/'
            )
            
            total_files = 0
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    key = obj['Key']
                    total_files += 1
                    
                    # Skip if not a PDF
                    if not key.lower().endswith('.pdf'):
                        print(f"[S3_FETCHER]    ⏭️ Skipping non-PDF: {key}", flush=True)
                        sys.stdout.flush()
                        continue
                    
                    # Generate document ID from filename (same as simple_upload_app.py)
                    file_name = key.split('/')[-1]
                    # Note: We use the S3 key as the doc_id for tracking
                    # The actual job_id will be generated when /process is called
                    
                    # Check global document queue first (PRIMARY check)
                    # We check if ANY document with this filename is already being processed
                    queue_info = doc_queue.get_queue_info()
                    is_in_global_queue = False
                    
                    for processing_doc_id in queue_info['processing_docs']:
                        # Check if this is the same file
                        if file_name in processing_doc_id or processing_doc_id in file_name:
                            print(f"[S3_FETCHER]    ⏳ Already processing (global queue): {key}", flush=True)
                            sys.stdout.flush()
                            is_in_global_queue = True
                            break
                    
                    if is_in_global_queue:
                        continue
                    
                    # Check if already completed in global queue
                    for completed_doc_id in queue_info['completed_docs']:
                        if file_name in completed_doc_id or completed_doc_id in file_name:
                            print(f"[S3_FETCHER]    ✅ Already completed (global queue): {key}", flush=True)
                            sys.stdout.flush()
                            is_in_global_queue = True
                            break
                    
                    if is_in_global_queue:
                        continue
                    
                    # Check persistent processing map as backup
                    if self._is_in_processing_map(key):
                        status = self._get_processing_status(key)
                        if status == 'processing':
                            print(f"[S3_FETCHER]    ⏳ Already processing (local map): {key}", flush=True)
                        else:
                            print(f"[S3_FETCHER]    ✅ Already {status} (local map): {key}", flush=True)
                        sys.stdout.flush()
                        continue
                    
                    # Check S3 status file as backup
                    if self._is_processed(key):
                        status = self._get_document_status(key)
                        if status == 'processing':
                            print(f"[S3_FETCHER]    ⏳ Currently processing (S3): {key}", flush=True)
                            self._mark_processing(key)
                        else:
                            print(f"[S3_FETCHER]    ✅ Already {status} (S3): {key}", flush=True)
                            self._mark_completed(key)
                        sys.stdout.flush()
                        continue
                    
                    # This is an unprocessed document
                    print(f"[S3_FETCHER]    🆕 Found unprocessed: {key}", flush=True)
                    sys.stdout.flush()
                    unprocessed.append(key)
            
            print(f"[S3_FETCHER] 📊 S3 scan: {total_files} total files, {len(unprocessed)} unprocessed", flush=True)
            sys.stdout.flush()
            return unprocessed
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Error listing documents: {str(e)}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return []
    
    def _is_processed(self, file_key: str) -> bool:
        """
        Check if a document has already been processed or is currently being processed
        
        Args:
            file_key: S3 file key
            
        Returns:
            True if processed or processing, False otherwise
        """
        try:
            status_key = f"processing_logs/{file_key}.status.json"
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=status_key)
            status_data = json.loads(response['Body'].read())
            status = status_data.get('status', 'unknown')
            
            # Skip if already processed or currently processing
            if status in ['completed', 'failed', 'processing']:
                return True
            
            return False
        except:
            return False  # Status file doesn't exist = not processed
    
    def _get_document_status(self, file_key: str) -> str:
        """
        Get the current status of a document
        
        Args:
            file_key: S3 file key
            
        Returns:
            Status string (processing, completed, failed, unknown)
        """
        try:
            status_key = f"processing_logs/{file_key}.status.json"
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=status_key)
            status_data = json.loads(response['Body'].read())
            return status_data.get('status', 'unknown')
        except:
            return 'unknown'
    
    def _process_document(self, file_key: str) -> bool:
        """
        Process a single document by calling the /process endpoint
        This ensures the document is processed with skill-based processing
        
        Args:
            file_key: S3 file key
            
        Returns:
            True if successful, False otherwise
        """
        import sys
        import requests
        file_name = file_key.split('/')[-1]
        
        try:
            print(f"[S3_FETCHER] 🔄 Processing: {file_name}", flush=True)
            sys.stdout.flush()
            
            # CRITICAL: Mark as processing in persistent map BEFORE calling /process
            # This prevents the S3 fetcher from calling /process multiple times for the same file
            self._mark_processing(file_key)
            self._update_status(file_key, 'processing')
            
            print(f"[S3_FETCHER]    ✅ Marked as processing in local map", flush=True)
            sys.stdout.flush()
            
            # Download document
            pdf_bytes = self._download_document(file_key)
            if not pdf_bytes:
                self._update_status(file_key, 'failed', 'Download failed')
                return False
            
            # Create temporary file for upload
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            
            try:
                # Call the /process endpoint (same as UI upload)
                # This will trigger skillProcessDocument through the background processor
                print(f"[S3_FETCHER]    📤 Calling /process endpoint with skill-based processing...", flush=True)
                sys.stdout.flush()
                
                with open(tmp_path, 'rb') as f:
                    files = {'file': (file_name, f, 'application/pdf')}
                    # Add document_name to ensure it appears properly in UI
                    data = {'document_name': file_name}
                    response = requests.post('http://localhost:5015/process', files=files, data=data, timeout=300)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        job_id = data.get('job_id')
                        print(f"[S3_FETCHER]    ✅ Job submitted: {job_id}", flush=True)
                        print(f"[S3_FETCHER]    📋 Document will be processed with skill-based system", flush=True)
                        print(f"[S3_FETCHER]    🎯 Document will appear on UI dashboard once processing completes", flush=True)
                        sys.stdout.flush()
                        
                        # Wait for processing to complete (with timeout)
                        print(f"[S3_FETCHER]    ⏳ Waiting for background processing to complete...", flush=True)
                        sys.stdout.flush()
                        
                        max_wait = 600  # 10 minutes max wait
                        check_interval = 5  # Check every 5 seconds
                        elapsed = 0
                        
                        while elapsed < max_wait:
                            # Check processing status
                            status_response = requests.get(f'http://localhost:5015/status/{job_id}', timeout=30)
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                progress = status_data.get('progress', 0)
                                is_complete = status_data.get('is_complete', False)
                                stage = status_data.get('stage', 'unknown')
                                
                                print(f"[S3_FETCHER]    📊 Progress: {progress}% - Stage: {stage}", flush=True)
                                sys.stdout.flush()
                                
                                if is_complete:
                                    print(f"[S3_FETCHER]    ✅ Processing complete!", flush=True)
                                    print(f"[S3_FETCHER]    🎉 Document {file_name} is now available on UI", flush=True)
                                    sys.stdout.flush()
                                    self._update_status(file_key, 'completed', doc_type='skill_processed')
                                    # Mark as completed in persistent map
                                    self._mark_completed(file_key)
                                    return True
                            
                            time.sleep(check_interval)
                            elapsed += check_interval
                        
                        # Timeout reached
                        print(f"[S3_FETCHER]    ⚠️ Processing timeout after {max_wait}s", flush=True)
                        print(f"[S3_FETCHER]    📋 Document may still be processing in background", flush=True)
                        sys.stdout.flush()
                        self._update_status(file_key, 'completed', doc_type='skill_processed')
                        # Mark as completed in persistent map
                        self._mark_completed(file_key)
                        return True
                    else:
                        error = data.get('message', 'Unknown error')
                        print(f"[S3_FETCHER]    ❌ Process failed: {error}", flush=True)
                        sys.stdout.flush()
                        self._update_status(file_key, 'failed', error)
                        # Mark as completed (failed) in persistent map
                        self._mark_completed(file_key)
                        return False
                else:
                    print(f"[S3_FETCHER]    ❌ HTTP {response.status_code}: {response.text}", flush=True)
                    sys.stdout.flush()
                    self._update_status(file_key, 'failed', f'HTTP {response.status_code}')
                    # Mark as completed (failed) in persistent map
                    self._mark_completed(file_key)
                    return False
                    
            finally:
                # Clean up temp file
                import os
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Error processing {file_name}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            self._update_status(file_key, 'failed', str(e))
            # Mark as completed (failed) in persistent map
            self._mark_completed(file_key)
            return False
    
    def _save_document_result(self, file_name: str, file_key: str, doc_type: str, accounts: list, page_count: int):
        """Save document processing result to processed_documents.json"""
        import sys
        try:
            # Load existing documents
            if os.path.exists('processed_documents.json'):
                with open('processed_documents.json', 'r') as f:
                    documents = json.load(f)
                    if not isinstance(documents, list):
                        documents = []
            else:
                documents = []
            
            # Create document record
            doc_record = {
                'id': hashlib.md5(file_name.encode()).hexdigest()[:12],
                'filename': file_name,
                'document_name': file_name,
                'timestamp': datetime.now().strftime('%Y%m%d_%H%M%S'),
                'processed_date': datetime.now().isoformat(),
                'file_key': file_key,
                'document_type': doc_type,
                'total_pages': page_count,
                'accounts_found': len(accounts),
                'accounts': accounts,
                'status': 'completed',
                'can_view': True,
                'background_processed': True
            }
            
            # Check if document already exists
            found = False
            for doc in documents:
                if doc.get('filename') == file_name:
                    doc.update(doc_record)
                    found = True
                    break
            
            if not found:
                documents.append(doc_record)
            
            # Save back
            with open('processed_documents.json', 'w') as f:
                json.dump(documents, f, indent=2)
            
            print(f"[S3_FETCHER]    📝 Saved to processed_documents.json", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Failed to save document result: {str(e)}", flush=True)
            sys.stdout.flush()
    
    def _download_document(self, file_key: str) -> Optional[bytes]:
        """
        Download document from S3
        
        Args:
            file_key: S3 file key
            
        Returns:
            Document bytes or None if failed
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_key)
            return response['Body'].read()
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Download failed: {str(e)}")
            return None
    
    def _update_status(self, file_key: str, status: str, error: str = None, doc_type: str = None):
        """
        Update processing status in S3 and local JSON
        
        Args:
            file_key: S3 file key
            status: Processing status (processing, completed, failed)
            error: Error message if failed
            doc_type: Document type if completed
        """
        import sys
        try:
            status_key = f"processing_logs/{file_key}.status.json"
            
            status_data = {
                'file_key': file_key,
                'file_name': file_key.split('/')[-1],
                'status': status,
                'processed_date': datetime.now().isoformat()
            }
            
            if error:
                status_data['error'] = error
            
            if doc_type:
                status_data['document_type'] = doc_type
            
            # Save to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=status_key,
                Body=json.dumps(status_data),
                ContentType='application/json'
            )
            
            # Also save to local processed_documents.json
            self._save_to_local_json(status_data)
            
            print(f"[S3_FETCHER]    💾 Status saved: {status}", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Failed to update status: {str(e)}", flush=True)
            sys.stdout.flush()
    
    def _save_to_local_json(self, status_data: dict):
        """Save document status to local processed_documents.json"""
        import sys
        try:
            # Load existing documents
            if os.path.exists('processed_documents.json'):
                with open('processed_documents.json', 'r') as f:
                    documents = json.load(f)
                    if not isinstance(documents, list):
                        documents = []
            else:
                documents = []
            
            # Find and update or add document
            file_name = status_data.get('file_name')
            found = False
            for doc in documents:
                if doc.get('file_name') == file_name:
                    # Ensure document has an ID
                    if 'id' not in doc:
                        doc['id'] = hashlib.md5(f"{file_name}{doc.get('processed_date', '')}".encode()).hexdigest()[:12]
                    doc.update(status_data)
                    found = True
                    break
            
            if not found:
                # Generate ID for new document
                doc_id = hashlib.md5(f"{file_name}{status_data.get('processed_date', '')}".encode()).hexdigest()[:12]
                status_data['id'] = doc_id
                documents.append(status_data)
            
            # Save back
            with open('processed_documents.json', 'w') as f:
                json.dump(documents, f, indent=2)
            
            print(f"[S3_FETCHER]    📝 Updated processed_documents.json", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            print(f"[S3_FETCHER] ❌ Failed to save to local JSON: {str(e)}", flush=True)
            sys.stdout.flush()


# Global fetcher instance
_fetcher = None


def start_s3_fetcher(bucket_name: str = "aws-idp-uploads", region: str = "us-east-1", check_interval: int = 30):
    """
    Start the S3 document fetcher
    
    Args:
        bucket_name: S3 bucket name
        region: AWS region
        check_interval: How often to check for new documents (seconds)
    """
    global _fetcher
    
    if _fetcher is None:
        _fetcher = S3DocumentFetcher(bucket_name, region, check_interval)
    
    _fetcher.start()
    return _fetcher


def stop_s3_fetcher():
    """Stop the S3 document fetcher"""
    global _fetcher
    
    if _fetcher:
        _fetcher.stop()


def get_s3_fetcher() -> Optional[S3DocumentFetcher]:
    """Get the global fetcher instance"""
    global _fetcher
    return _fetcher
