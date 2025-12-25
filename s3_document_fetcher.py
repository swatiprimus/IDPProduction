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
from datetime import datetime
from typing import Dict, Optional

# Import processing functions
from app.services.textract_service import extract_text_with_textract
from app.services.document_detector import detect_document_type


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
        
        print(f"[S3_FETCHER] 🚀 Initialized")
        print(f"[S3_FETCHER]    Bucket: {bucket_name}")
        print(f"[S3_FETCHER]    Region: {region}")
        print(f"[S3_FETCHER]    Check interval: {check_interval}s")
    
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
        
        Returns:
            List of S3 keys for unprocessed documents
        """
        import sys
        try:
            unprocessed = []
            
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
                    
                    # Check if already processed
                    if self._is_processed(key):
                        print(f"[S3_FETCHER]    ✅ Already processed: {key}", flush=True)
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
        Check if a document has already been processed
        
        Args:
            file_key: S3 file key
            
        Returns:
            True if processed, False otherwise
        """
        try:
            status_key = f"processing_logs/{file_key}.status.json"
            self.s3_client.head_object(Bucket=self.bucket_name, Key=status_key)
            return True  # Status file exists = already processed
        except:
            return False  # Status file doesn't exist = not processed
    
    def _process_document(self, file_key: str) -> bool:
        """
        Process a single document by calling the /process endpoint
        
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
            
            # Mark as processing
            self._update_status(file_key, 'processing')
            
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
                print(f"[S3_FETCHER]    📤 Calling /process endpoint...", flush=True)
                sys.stdout.flush()
                
                with open(tmp_path, 'rb') as f:
                    files = {'file': (file_name, f, 'application/pdf')}
                    response = requests.post('http://localhost:5015/process', files=files, timeout=300)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        job_id = data.get('job_id')
                        print(f"[S3_FETCHER]    ✅ Job submitted: {job_id}", flush=True)
                        sys.stdout.flush()
                        self._update_status(file_key, 'completed', doc_type='processing')
                        return True
                    else:
                        error = data.get('message', 'Unknown error')
                        print(f"[S3_FETCHER]    ❌ Process failed: {error}", flush=True)
                        sys.stdout.flush()
                        self._update_status(file_key, 'failed', error)
                        return False
                else:
                    print(f"[S3_FETCHER]    ❌ HTTP {response.status_code}: {response.text}", flush=True)
                    sys.stdout.flush()
                    self._update_status(file_key, 'failed', f'HTTP {response.status_code}')
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
                    doc.update(status_data)
                    found = True
                    break
            
            if not found:
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
