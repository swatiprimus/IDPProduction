"""OCR service for text extraction from documents."""

import boto3
import json
import fitz  # PyMuPDF
import io
import tempfile
import os
from datetime import datetime
from typing import Tuple, Optional
import logging
from services.aws_services import aws_services
from config import OUTPUT_DIR, S3_BUCKET

logger = logging.getLogger(__name__)

class OCRService:
    """Handles OCR extraction from various document formats."""
    
    def __init__(self):
        self.s3_bucket = S3_BUCKET
        
    def extract_text_with_textract(self, file_bytes: bytes, filename: str) -> Tuple[str, str]:
        """Extract text from document using Amazon Textract."""
        try:
            logger.info(f"Starting OCR for: {filename}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = filename.lower().split('.')[-1]
            
            # Validate file size
            file_size_mb = len(file_bytes) / (1024 * 1024)
            logger.info(f"File size: {file_size_mb:.2f} MB, Type: {file_ext.upper()}")
            
            # Handle different file types
            if file_ext in ['png', 'jpg', 'jpeg']:
                extracted_text = self._process_image(file_bytes, filename, timestamp, file_size_mb)
            elif file_ext == 'pdf':
                extracted_text = self._process_pdf(file_bytes, filename, timestamp, file_size_mb)
            else:
                raise Exception(f"Unsupported file format: {file_ext}")
            
            # Save extracted text
            output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            
            logger.info(f"OCR completed successfully: {len(extracted_text)} characters")
            return extracted_text, output_filename
            
        except Exception as e:
            logger.error(f"OCR failed: {str(e)}")
            raise Exception(f"Textract OCR failed: {str(e)}")
    
    def _process_image(self, file_bytes: bytes, filename: str, timestamp: str, file_size_mb: float) -> str:
        """Process image files with Textract."""
        if file_size_mb > 5:
            # Upload to S3 for large images
            s3_key = f"uploads/{timestamp}_{filename}"
            aws_services.upload_to_s3(self.s3_bucket, s3_key, file_bytes, f'image/{filename.split(".")[-1]}')
            
            response = aws_services.textract.detect_document_text(
                Document={'S3Object': {'Bucket': self.s3_bucket, 'Name': s3_key}}
            )
        else:
            # Process directly from bytes
            response = aws_services.textract.detect_document_text(
                Document={'Bytes': file_bytes}
            )
        
        # Extract text from response
        extracted_text = ""
        for block in response.get('Blocks', []):
            if block['BlockType'] == 'LINE':
                extracted_text += block.get('Text', '') + "\n"
        
        return extracted_text
    
    def _process_pdf(self, file_bytes: bytes, filename: str, timestamp: str, file_size_mb: float) -> str:
        """Process PDF files with Textract."""
        # Validate PDF format
        if file_bytes[:4] != b'%PDF':
            raise Exception("Invalid PDF file format. File may be corrupted.")
        
        if file_size_mb > 500:
            raise Exception(f"PDF file too large ({file_size_mb:.1f}MB). Maximum size is 500MB.")
        
        # Upload to S3 (required for PDFs)
        s3_key = f"uploads/{timestamp}_{filename}"
        aws_services.upload_to_s3(self.s3_bucket, s3_key, file_bytes, 'application/pdf')
        
        try:
            # Try sync API first (faster for simple PDFs)
            response = aws_services.textract.detect_document_text(
                Document={'S3Object': {'Bucket': self.s3_bucket, 'Name': s3_key}}
            )
            
            # Extract text from response
            extracted_text = ""
            for block in response.get('Blocks', []):
                if block['BlockType'] == 'LINE':
                    extracted_text += block.get('Text', '') + "\n"
            
            logger.info(f"Sync API succeeded: {len(extracted_text)} characters")
            return extracted_text
            
        except Exception as sync_error:
            error_msg = str(sync_error)
            logger.warning(f"Sync API failed: {error_msg}")
            
            if "UnsupportedDocumentException" in error_msg or "InvalidParameterException" in error_msg:
                # Use async API for scanned/multi-page PDFs
                logger.info("Switching to async API for PDF processing")
                return self._extract_text_with_textract_async(s3_key)
            else:
                raise Exception(f"Textract processing failed: {error_msg}")
    
    def _extract_text_with_textract_async(self, s3_key: str) -> str:
        """Extract text from PDF using Textract async API."""
        try:
            # Start async job
            response = aws_services.textract.start_document_text_detection(
                DocumentLocation={'S3Object': {'Bucket': self.s3_bucket, 'Name': s3_key}}
            )
            
            job_id = response['JobId']
            logger.info(f"Started async Textract job: {job_id}")
            
            # Poll for completion
            max_attempts = 60
            attempt = 0
            
            while attempt < max_attempts:
                import time
                time.sleep(5)
                
                result = aws_services.textract.get_document_text_detection(JobId=job_id)
                status = result['JobStatus']
                
                if status == 'SUCCEEDED':
                    # Extract text from all pages
                    extracted_text = ""
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block.get('Text', '') + "\n"
                    
                    # Handle pagination
                    next_token = result.get('NextToken')
                    while next_token:
                        result = aws_services.textract.get_document_text_detection(
                            JobId=job_id,
                            NextToken=next_token
                        )
                        for block in result.get('Blocks', []):
                            if block['BlockType'] == 'LINE':
                                extracted_text += block.get('Text', '') + "\n"
                        next_token = result.get('NextToken')
                    
                    logger.info(f"Async API succeeded: {len(extracted_text)} characters")
                    return extracted_text
                
                elif status == 'FAILED':
                    raise Exception(f"Textract async job failed: {result.get('StatusMessage', 'Unknown error')}")
                
                attempt += 1
            
            raise Exception("Textract async job timed out after 5 minutes")
            
        except Exception as e:
            logger.error(f"Async Textract processing failed: {str(e)}")
            raise Exception(f"Textract async processing failed: {str(e)}")
    
    def try_extract_pdf_with_pypdf(self, file_bytes: bytes, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Try to extract text from PDF using PyPDF2 as fallback."""
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            if text.strip():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}_pypdf.txt"
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                logger.info(f"PyPDF2 extraction successful: {len(text)} characters")
                return text, output_filename
            
            return None, None
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {str(e)}")
            return None, None

# Global OCR service instance
ocr_service = OCRService()