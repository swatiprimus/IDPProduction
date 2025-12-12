"""
Textract service for document text extraction
"""
import boto3
import io
import os
import time
from datetime import datetime

# AWS Configuration
AWS_REGION = "us-east-1"
textract = boto3.client("textract", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)
S3_BUCKET = "awsidpdocs"

# Create output directory for OCR results
OUTPUT_DIR = "ocr_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_text_with_textract_async(s3_bucket: str, s3_key: str):
    """Extract text from PDF using Textract async API (for scanned/multi-page PDFs)"""
    try:
        print(f"[TEXTRACT ASYNC] Starting async job for: {s3_key}")
        
        # Start async job
        response = textract.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
        )
        job_id = response['JobId']
        print(f"[TEXTRACT ASYNC] Job started: {job_id}")
        
        # Poll for completion
        max_wait = 300  # 5 minutes max
        wait_time = 0
        while wait_time < max_wait:
            time.sleep(5)
            wait_time += 5
            
            result = textract.get_document_text_detection(JobId=job_id)
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
                    result = textract.get_document_text_detection(
                        JobId=job_id, NextToken=next_token
                    )
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block['Text'] + "\n"
                            block_count += 1
                    next_token = result.get('NextToken')
                
                print(f"[TEXTRACT ASYNC] ✓ Completed: {block_count} lines, {len(extracted_text)} characters")
                return extracted_text
                
            elif status == 'FAILED':
                error_msg = result.get('StatusMessage', 'Unknown error')
                raise Exception(f"Textract async job failed: {error_msg}")
        
        raise Exception(f"Textract async job timed out after {max_wait} seconds")
        
    except Exception as e:
        print(f"[TEXTRACT ASYNC ERROR] ❌ {str(e)}")
        raise Exception(f"Textract async processing failed: {str(e)}")


def extract_text_with_textract(file_bytes: bytes, filename: str):
    """Extract text from document using Amazon Textract"""
    try:
        print(f"\n{'='*80}")
        print(f"[TEXTRACT] Starting OCR for: {filename}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = filename.lower().split('.')[-1]
        
        # Validate file size (Textract limits: 5MB for sync, 500MB for async via S3)
        file_size_mb = len(file_bytes) / (1024 * 1024)
        print(f"[TEXTRACT] File size: {file_size_mb:.2f} MB")
        print(f"[TEXTRACT] File type: {file_ext.upper()}")
        
        # For images (PNG, JPG, JPEG), use bytes directly
        if file_ext in ['png', 'jpg', 'jpeg']:
            print(f"[TEXTRACT] Processing image file...")
            if file_size_mb > 5:
                print(f"[TEXTRACT] Image > 5MB, uploading to S3...")
                # If larger than 5MB, upload to S3
                s3_key = f"uploads/{timestamp}_{filename}"
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=f'image/{file_ext}'
                )
                print(f"[TEXTRACT] ✓ Uploaded to S3: {s3_key}")
                print(f"[TEXTRACT] Calling Textract detect_document_text (S3)...")
                response = textract.detect_document_text(
                    Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}}
                )
            else:
                # Process directly from bytes
                print(f"[TEXTRACT] Calling Textract detect_document_text (bytes)...")
                response = textract.detect_document_text(
                    Document={'Bytes': file_bytes}
                )
            
            # Extract text from blocks
            print(f"[TEXTRACT] Extracting text from response blocks...")
            extracted_text = ""
            block_count = 0
            for block in response.get('Blocks', []):
                if block['BlockType'] == 'LINE':
                    extracted_text += block['Text'] + "\n"
                    block_count += 1
            print(f"[TEXTRACT] ✓ Extracted {block_count} text lines, {len(extracted_text)} characters")
        
        # For PDF, must use S3
        elif file_ext == 'pdf':
            print(f"[TEXTRACT] Processing PDF file...")
            # Validate PDF is not corrupted
            if file_bytes[:4] != b'%PDF':
                raise Exception("Invalid PDF file format. File may be corrupted.")
            
            if file_size_mb > 500:
                raise Exception(f"PDF file too large ({file_size_mb:.1f}MB). Maximum size is 500MB.")
            
            s3_key = f"uploads/{timestamp}_{filename}"
            
            # Upload to S3 with proper content type
            try:
                print(f"[TEXTRACT] Uploading PDF to S3...")
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType='application/pdf'
                )
                print(f"[TEXTRACT] ✓ Uploaded to S3: {s3_key}")
            except Exception as s3_error:
                raise Exception(f"S3 upload failed: {str(s3_error)}")
            
            # Try sync API first (faster for simple PDFs)
            try:
                print(f"[TEXTRACT] Trying sync API (detect_document_text)...")
                response = textract.detect_document_text(
                    Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}}
                )
                
                # Extract text from blocks
                print(f"[TEXTRACT] Extracting text from response blocks...")
                extracted_text = ""
                block_count = 0
                for block in response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        extracted_text += block['Text'] + "\n"
                        block_count += 1
                print(f"[TEXTRACT] ✓ Sync API succeeded: {block_count} lines, {len(extracted_text)} characters")
                        
            except Exception as sync_error:
                error_msg = str(sync_error)
                print(f"[TEXTRACT] Sync API failed: {error_msg}")
                if "UnsupportedDocumentException" in error_msg or "InvalidParameterException" in error_msg:
                    # PDF is scanned or multi-page, use async API
                    print(f"[TEXTRACT] Switching to async API (start_document_text_detection)...")
                    extracted_text = extract_text_with_textract_async(S3_BUCKET, s3_key)
                    print(f"[TEXTRACT] ✓ Async API succeeded: {len(extracted_text)} characters")
                else:
                    raise Exception(f"Textract processing failed: {error_msg}")
        
        else:
            raise Exception(f"Unsupported file format: {file_ext}. Supported: PDF, PNG, JPG, JPEG")
        
        if not extracted_text.strip():
            print(f"[TEXTRACT] ⚠️ No text detected in document")
            extracted_text = "[No text detected in document. Document may be blank or image quality too low.]"
        
        # Save extracted text to file
        output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        print(f"[TEXTRACT] ✓ Saved extracted text to: {output_filename}")
        print(f"{'='*80}\n")
        
        return extracted_text, output_filename
        
    except Exception as e:
        print(f"[TEXTRACT ERROR] ❌ OCR failed: {str(e)}")
        print(f"{'='*80}\n")
        # Save error info
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_file = f"{OUTPUT_DIR}/{timestamp}_{filename}_ERROR.txt"
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"OCR Error: {str(e)}\n")
            f.write(f"File: {filename}\n")
            f.write(f"Size: {len(file_bytes) / 1024:.2f} KB\n")
        
        raise Exception(f"Textract OCR failed: {str(e)}")


def try_extract_pdf_with_pypdf(file_bytes: bytes, filename: str):
    """Try to extract text from PDF using PyPDF2 as fallback"""
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
            return text, output_filename
        return None, None
    except:
        return None, None