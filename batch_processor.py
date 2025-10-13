#!/usr/bin/env python3
"""
batch_processor.py

Batch processing system for handling multiple documents efficiently
"""

import json
import boto3
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable
import logging
from datetime import datetime
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self, aws_region='us-east-1', max_workers=5):
        self.s3 = boto3.client('s3', region_name=aws_region)
        self.textract = boto3.client('textract', region_name=aws_region)
        self.bedrock = boto3.client('bedrock-runtime', region_name=aws_region)
        self.max_workers = max_workers
        
        # Processing statistics
        self.stats = {
            'total_documents': 0,
            'successful': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
    
    def process_folder_batch(self, folder_path: str, s3_bucket: str, 
                           processing_function: Callable) -> Dict:
        """Process all PDFs in a folder"""
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        # Find all PDF files
        pdf_files = list(folder.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        return self.process_files_batch(pdf_files, s3_bucket, processing_function)
    
    def process_files_batch(self, file_paths: List[Path], s3_bucket: str,
                          processing_function: Callable) -> Dict:
        """Process a list of PDF files in parallel"""
        self.stats['total_documents'] = len(file_paths)
        self.stats['start_time'] = datetime.now()
        
        # Create batch job ID
        batch_id = str(uuid.uuid4())[:8]
        logger.info(f"Starting batch job {batch_id} with {len(file_paths)} files")
        
        # Process files in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_file = {
                executor.submit(
                    self._process_single_file, 
                    file_path, s3_bucket, processing_function, batch_id
                ): file_path 
                for file_path in file_paths
            }
            
            # Collect results
            results = []
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result['success']:
                        self.stats['successful'] += 1
                        logger.info(f"✅ Processed {file_path.name}")
                    else:
                        self.stats['failed'] += 1
                        self.stats['errors'].append({
                            'file': str(file_path),
                            'error': result.get('error', 'Unknown error')
                        })
                        logger.error(f"❌ Failed {file_path.name}: {result.get('error')}")
                        
                except Exception as e:
                    self.stats['failed'] += 1
                    self.stats['errors'].append({
                        'file': str(file_path),
                        'error': str(e)
                    })
                    logger.error(f"❌ Exception processing {file_path.name}: {e}")
        
        self.stats['end_time'] = datetime.now()
        
        # Generate batch report
        batch_report = self._generate_batch_report(batch_id, results)
        
        return batch_report
    
    def _process_single_file(self, file_path: Path, s3_bucket: str,
                           processing_function: Callable, batch_id: str) -> Dict:
        """Process a single file"""
        try:
            # Upload to S3 with batch prefix
            s3_key = f"batch_processing/{batch_id}/{file_path.name}"
            self.s3.upload_file(str(file_path), s3_bucket, s3_key)
            
            # Process the file
            result = processing_function(s3_bucket, s3_key)
            
            # Add metadata
            result.update({
                'file_name': file_path.name,
                'batch_id': batch_id,
                's3_key': s3_key,
                'processed_at': datetime.now().isoformat()
            })
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'file_name': file_path.name,
                'batch_id': batch_id,
                'error': str(e),
                'processed_at': datetime.now().isoformat()
            }
    
    def _generate_batch_report(self, batch_id: str, results: List[Dict]) -> Dict:
        """Generate comprehensive batch processing report"""
        processing_time = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        report = {
            'batch_id': batch_id,
            'summary': {
                'total_files': self.stats['total_documents'],
                'successful': self.stats['successful'],
                'failed': self.stats['failed'],
                'success_rate': self.stats['successful'] / self.stats['total_documents'] if self.stats['total_documents'] > 0 else 0,
                'processing_time_seconds': processing_time,
                'avg_time_per_file': processing_time / self.stats['total_documents'] if self.stats['total_documents'] > 0 else 0
            },
            'start_time': self.stats['start_time'].isoformat(),
            'end_time': self.stats['end_time'].isoformat(),
            'errors': self.stats['errors'],
            'detailed_results': results
        }
        
        # Save report to file
        report_file = f"batch_report_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📊 Batch report saved to {report_file}")
        logger.info(f"🎉 Batch {batch_id} completed: {self.stats['successful']}/{self.stats['total_documents']} successful")
        
        return report

# Example processing functions
def textract_extraction_processor(s3_bucket: str, s3_key: str) -> Dict:
    """Example processor for Textract extraction"""
    textract = boto3.client('textract', region_name='us-east-1')
    
    try:
        # Start Textract job
        response = textract.start_document_analysis(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}},
            FeatureTypes=['FORMS', 'TABLES']
        )
        
        job_id = response['JobId']
        
        # Wait for completion
        while True:
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
                    'extracted_text': extracted_text,
                    'block_count': len(blocks)
                }
            elif status == 'FAILED':
                return {
                    'success': False,
                    'error': 'Textract job failed'
                }
            
            time.sleep(2)
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def document_classification_processor(s3_bucket: str, s3_key: str) -> Dict:
    """Example processor for document classification"""
    # This would use your enhanced classifier
    try:
        # Simulate processing
        time.sleep(1)  # Simulate processing time
        
        return {
            'success': True,
            'document_type': 'loan_agreement',
            'confidence': 0.95,
            'classification_method': 'ai_enhanced'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# CLI interface
def main():
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python batch_processor.py <folder_path> <s3_bucket> <processor_type>")
        print("Processor types: textract, classification")
        return
    
    folder_path = sys.argv[1]
    s3_bucket = sys.argv[2]
    processor_type = sys.argv[3]
    
    # Select processor
    processors = {
        'textract': textract_extraction_processor,
        'classification': document_classification_processor
    }
    
    if processor_type not in processors:
        print(f"Unknown processor type: {processor_type}")
        print(f"Available types: {list(processors.keys())}")
        return
    
    # Run batch processing
    batch_processor = BatchProcessor(max_workers=3)
    
    try:
        report = batch_processor.process_folder_batch(
            folder_path, 
            s3_bucket, 
            processors[processor_type]
        )
        
        print("\n" + "="*50)
        print("BATCH PROCESSING COMPLETE")
        print("="*50)
        print(f"Batch ID: {report['batch_id']}")
        print(f"Total Files: {report['summary']['total_files']}")
        print(f"Successful: {report['summary']['successful']}")
        print(f"Failed: {report['summary']['failed']}")
        print(f"Success Rate: {report['summary']['success_rate']:.2%}")
        print(f"Processing Time: {report['summary']['processing_time_seconds']:.2f} seconds")
        print(f"Avg Time per File: {report['summary']['avg_time_per_file']:.2f} seconds")
        
        if report['summary']['failed'] > 0:
            print("\nErrors:")
            for error in report['errors']:
                print(f"  - {error['file']}: {error['error']}")
        
    except Exception as e:
        print(f"Batch processing failed: {e}")

if __name__ == "__main__":
    main()