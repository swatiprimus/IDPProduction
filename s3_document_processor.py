#!/usr/bin/env python3
"""
S3 Document Processor
Picks documents from S3 bucket (aws-idp-uploads), processes them with app_modular.py,
saves results, and marks documents as processed.
"""

import boto3
import json
import time
import threading
import hashlib
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from botocore.exceptions import ClientError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('s3_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class S3DocumentProcessor:
    """Process documents from S3 bucket"""
    
    def __init__(self, bucket_name: str = "aws-idp-uploads", region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client('s3', region_name=region)
        self.processed_prefix = "processed/"
        self.results_prefix = "results/"
        self.processing_log_prefix = "processing_logs/"
        
        logger.info(f"🚀 S3 Document Processor initialized")
        logger.info(f"   Bucket: {bucket_name}")
        logger.info(f"   Region: {region}")
    
    def list_unprocessed_documents(self) -> List[Dict]:
        """
        List all unprocessed documents in S3 bucket
        Only returns documents that have NOT been processed yet
        
        Returns:
            List of unprocessed document info
        """
        try:
            unprocessed = []
            
            # List all objects in bucket
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    key = obj['Key']
                    
                    # Skip if already processed (moved to processed folder)
                    if key.startswith(self.processed_prefix):
                        continue
                    
                    # Skip if not a PDF
                    if not key.lower().endswith('.pdf'):
                        continue
                    
                    # Skip if in results or logs directory
                    if key.startswith(self.results_prefix) or key.startswith(self.processing_log_prefix):
                        continue
                    
                    # Check if processing status exists
                    status = self._get_processing_status(key)
                    
                    # CRITICAL: Only process if status is 'pending' (never processed before)
                    # Skip if already completed or failed
                    if status.get('status') in ['completed', 'failed', 'processing']:
                        logger.debug(f"⏭️ Skipping {key} - already {status.get('status')}")
                        continue
                    
                    # Only add if truly pending (no status file exists)
                    if status.get('status') == 'pending':
                        unprocessed.append({
                            'key': key,
                            'file_name': key.split('/')[-1],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'status': 'pending'
                        })
            
            logger.info(f"📋 Found {len(unprocessed)} unprocessed documents")
            return unprocessed
            
        except Exception as e:
            logger.error(f"❌ Error listing documents: {str(e)}")
            return []
    
    def _get_processing_status(self, file_key: str) -> Dict:
        """Get processing status of a file"""
        try:
            status_key = f"{self.processing_log_prefix}{file_key}.status.json"
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=status_key)
            status = json.loads(response['Body'].read())
            return status
        except:
            return {'status': 'pending'}
    
    def download_document(self, file_key: str, local_path: str) -> bool:
        """
        Download document from S3 to local storage
        
        Args:
            file_key: S3 file key
            local_path: Local file path to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"📥 Downloading: {file_key}")
            
            self.s3_client.download_file(
                self.bucket_name,
                file_key,
                local_path
            )
            
            logger.info(f"✅ Downloaded: {file_key} -> {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error downloading {file_key}: {str(e)}")
            return False
    
    def process_document(self, file_key: str, local_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Process document using app_modular.py logic
        
        Args:
            file_key: S3 file key
            local_path: Local file path
            
        Returns:
            Tuple of (success, result_data)
        """
        try:
            logger.info(f"🔄 Processing: {file_key}")
            
            # Import processing functions from service modules
            try:
                from app.services.textract_service import extract_text_with_textract
                from app.services.document_detector import detect_document_type
                from app.services.loan_processor import process_loan_document
            except ImportError as e:
                logger.error(f"❌ Failed to import service modules: {str(e)}")
                logger.info("   Make sure you're running from the correct directory with app/ folder")
                return False, None
            
            # Read file
            with open(local_path, 'rb') as f:
                file_bytes = f.read()
            
            file_name = file_key.split('/')[-1]
            
            # Extract text
            logger.info(f"📄 Extracting text from {file_name}")
            full_text, _ = extract_text_with_textract(file_bytes, file_name)
            
            # Detect document type
            logger.info(f"🔍 Detecting document type")
            doc_type = detect_document_type(full_text)
            logger.info(f"   Document type: {doc_type}")
            
            # Process based on type
            result = {
                'file_key': file_key,
                'file_name': file_name,
                'document_type': doc_type,
                'processing_date': datetime.now().isoformat(),
                'text_length': len(full_text),
                'extracted_data': {}
            }
            
            if doc_type == "loan_document":
                logger.info(f"💼 Processing as loan document")
                loan_result = process_loan_document(full_text)
                result['extracted_data'] = loan_result
                
            else:
                logger.info(f"📋 Processing as {doc_type}")
                # For other document types, extract basic fields
                result['extracted_data'] = {
                    'document_type': doc_type,
                    'text_preview': full_text[:500]
                }
            
            logger.info(f"✅ Processing complete: {file_key}")
            return True, result
            
        except Exception as e:
            logger.error(f"❌ Error processing {file_key}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def save_result(self, file_key: str, result: Dict) -> bool:
        """
        Save processing result to S3
        
        Args:
            file_key: Original S3 file key
            result: Processing result data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"💾 Saving result for: {file_key}")
            
            # Create result key
            file_name = file_key.split('/')[-1]
            result_key = f"{self.results_prefix}{file_name}.result.json"
            
            # Save result
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=result_key,
                Body=json.dumps(result, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"✅ Result saved: {result_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving result: {str(e)}")
            return False
    
    def mark_as_processed(self, file_key: str, result: Dict, success: bool) -> bool:
        """
        Mark document as processed in S3
        
        Args:
            file_key: S3 file key
            result: Processing result
            success: Whether processing was successful
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"🏁 Marking as processed: {file_key}")
            
            # Create processing log
            file_name = file_key.split('/')[-1]
            log_key = f"{self.processing_log_prefix}{file_key}.status.json"
            
            status = {
                'file_key': file_key,
                'file_name': file_name,
                'status': 'completed' if success else 'failed',
                'processed_date': datetime.now().isoformat(),
                'success': success,
                'result_key': f"{self.results_prefix}{file_name}.result.json" if success else None,
                'error': result.get('error') if not success else None
            }
            
            # Save status
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=log_key,
                Body=json.dumps(status, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"✅ Marked as processed: {file_key}")
            
            # Move file to processed folder (copy and delete)
            if success:
                processed_key = f"{self.processed_prefix}{file_name}"
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource={'Bucket': self.bucket_name, 'Key': file_key},
                    Key=processed_key
                )
                logger.info(f"📦 Moved to processed: {processed_key}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error marking as processed: {str(e)}")
            return False
    
    def process_single_document(self, file_key: str, temp_dir: str = "temp_downloads") -> bool:
        """
        Process a single document end-to-end
        
        Args:
            file_key: S3 file key
            temp_dir: Temporary directory for downloads
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create temp directory
            os.makedirs(temp_dir, exist_ok=True)
            
            # Download
            local_path = os.path.join(temp_dir, file_key.split('/')[-1])
            if not self.download_document(file_key, local_path):
                self.mark_as_processed(file_key, {'error': 'Download failed'}, False)
                return False
            
            # Process
            success, result = self.process_document(file_key, local_path)
            if not success:
                self.mark_as_processed(file_key, {'error': 'Processing failed'}, False)
                if os.path.exists(local_path):
                    os.remove(local_path)
                return False
            
            # Save result
            if not self.save_result(file_key, result):
                self.mark_as_processed(file_key, {'error': 'Save failed'}, False)
                if os.path.exists(local_path):
                    os.remove(local_path)
                return False
            
            # Mark as processed
            if not self.mark_as_processed(file_key, result, True):
                if os.path.exists(local_path):
                    os.remove(local_path)
                return False
            
            # Clean up
            if os.path.exists(local_path):
                os.remove(local_path)
            
            logger.info(f"🎉 Document processed successfully: {file_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in process_single_document: {str(e)}")
            return False
    
    def process_all_documents(self, max_workers: int = 3, delay: int = 5) -> Dict:
        """
        Process all unprocessed documents
        
        Args:
            max_workers: Maximum concurrent processing threads
            delay: Delay between checks (seconds)
            
        Returns:
            Processing summary
        """
        try:
            logger.info(f"🚀 Starting batch processing (max_workers={max_workers})")
            
            summary = {
                'total': 0,
                'processed': 0,
                'failed': 0,
                'start_time': datetime.now().isoformat(),
                'documents': []
            }
            
            # Get unprocessed documents
            documents = self.list_unprocessed_documents()
            summary['total'] = len(documents)
            
            if summary['total'] == 0:
                logger.info("✅ No documents to process")
                return summary
            
            logger.info(f"📋 Processing {summary['total']} documents")
            
            # Process with thread pool
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                
                for doc in documents:
                    future = executor.submit(self.process_single_document, doc['key'])
                    futures[future] = doc
                
                # Collect results
                completed = 0
                for future in as_completed(futures):
                    doc = futures[future]
                    completed += 1
                    
                    try:
                        success = future.result()
                        if success:
                            summary['processed'] += 1
                            logger.info(f"✅ [{completed}/{summary['total']}] Processed: {doc['file_name']}")
                        else:
                            summary['failed'] += 1
                            logger.error(f"❌ [{completed}/{summary['total']}] Failed: {doc['file_name']}")
                        
                        summary['documents'].append({
                            'file_name': doc['file_name'],
                            'status': 'completed' if success else 'failed'
                        })
                        
                    except Exception as e:
                        summary['failed'] += 1
                        logger.error(f"❌ Error processing {doc['file_name']}: {str(e)}")
                        summary['documents'].append({
                            'file_name': doc['file_name'],
                            'status': 'error'
                        })
            
            summary['end_time'] = datetime.now().isoformat()
            
            logger.info(f"🎉 Batch processing complete")
            logger.info(f"   Total: {summary['total']}")
            logger.info(f"   Processed: {summary['processed']}")
            logger.info(f"   Failed: {summary['failed']}")
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error in process_all_documents: {str(e)}")
            return summary
    
    def start_continuous_processing(self, interval: int = 300, max_workers: int = 3):
        """
        Start continuous processing in background thread
        
        Args:
            interval: Check interval in seconds (default: 5 minutes)
            max_workers: Maximum concurrent processing threads
        """
        def process_loop():
            logger.info(f"🔄 Starting continuous processing (interval: {interval}s)")
            
            while True:
                try:
                    logger.info(f"📋 Checking for unprocessed documents...")
                    documents = self.list_unprocessed_documents()
                    
                    if documents:
                        logger.info(f"🚀 Found {len(documents)} documents to process")
                        self.process_all_documents(max_workers=max_workers)
                    else:
                        logger.info(f"✅ No documents to process")
                    
                    logger.info(f"⏳ Next check in {interval} seconds...")
                    time.sleep(interval)
                    
                except Exception as e:
                    logger.error(f"❌ Error in processing loop: {str(e)}")
                    time.sleep(interval)
        
        # Start in background thread
        thread = threading.Thread(target=process_loop, daemon=True)
        thread.start()
        logger.info(f"✅ Continuous processing started in background")
        
        return thread
    
    def get_processing_summary(self) -> Dict:
        """Get summary of all processed documents"""
        try:
            summary = {
                'total_processed': 0,
                'total_failed': 0,
                'documents': []
            }
            
            # List all status files
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=self.processing_log_prefix
            )
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    try:
                        response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        status = json.loads(response['Body'].read())
                        
                        if status.get('status') == 'completed':
                            summary['total_processed'] += 1
                        else:
                            summary['total_failed'] += 1
                        
                        summary['documents'].append(status)
                    except:
                        continue
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error getting summary: {str(e)}")
            return {}


# Global processor instance
processor = S3DocumentProcessor(bucket_name="aws-idp-uploads", region="us-east-1")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='S3 Document Processor')
    parser.add_argument('--action', choices=['list', 'process', 'continuous', 'summary'],
                       default='list', help='Action to perform')
    parser.add_argument('--file', help='Specific file key to process')
    parser.add_argument('--interval', type=int, default=300, help='Continuous processing interval (seconds)')
    parser.add_argument('--workers', type=int, default=3, help='Maximum concurrent workers')
    
    args = parser.parse_args()
    
    if args.action == 'list':
        logger.info("📋 Listing unprocessed documents...")
        documents = processor.list_unprocessed_documents()
        for doc in documents:
            print(f"  • {doc['file_name']} ({doc['size']} bytes)")
    
    elif args.action == 'process':
        if args.file:
            logger.info(f"🔄 Processing single file: {args.file}")
            processor.process_single_document(args.file)
        else:
            logger.info(f"🚀 Processing all documents...")
            summary = processor.process_all_documents(max_workers=args.workers)
            print(json.dumps(summary, indent=2))
    
    elif args.action == 'continuous':
        logger.info(f"🔄 Starting continuous processing...")
        processor.start_continuous_processing(interval=args.interval, max_workers=args.workers)
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("⏹️ Stopping continuous processing")
    
    elif args.action == 'summary':
        logger.info("📊 Getting processing summary...")
        summary = processor.get_processing_summary()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
