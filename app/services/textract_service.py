"""
Textract Service - Handles all AWS Textract OCR operations
"""
import boto3
import time
from datetime import datetime
import os

# AWS Configuration
AWS_REGION = "us-east-1"
textract = boto3.client("textract", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)
S3_BUCKET = "awsidpdocs"
OUTPUT_DIR = "ocr_results"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_text_with_textract_async(s3_bucket: str, s3_key: str):
    """Extract text from PDF using Textract async API (for scanned/multi-page PDFs)"""
    try:
        print(f"[TEXTRACT_ASYNC] Starting async job for: {s3_key}")
        
        # Start async job
        response = textract.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
        )
        
        job_id = response['JobId']
        print(f"[TEXTRACT_ASYNC] Job started: {job_id}")
        print(f"[TEXTRACT_ASYNC] Polling for completion (this may take 1-3 minutes)...")
        
        # Poll for completion
        max_attempts = 180  # 3 minutes max (180 * 1 second)
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            time.sleep(1)
            
            result = textract.get_document_text_detection(JobId=job_id)
            status = result['JobStatus']
            
            if attempt % 10 == 0:  # Log every 10 seconds
                print(f"[TEXTRACT_ASYNC] Status: {status} (attempt {attempt}/{max_attempts})")
            
            if status == 'SUCCEEDED':
                print(f"[TEXTRACT_ASYNC] ✓ Job completed successfully after {attempt} seconds")
                
                # Extract text from all pages
                extracted_text = ""
                next_token = None
                page_count = 0
                
                while True:
                    if next_token:
                        result = textract.get_document_text_detection(
                            JobId=job_id,
                            NextToken=next_token
                        )
                    
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block['Text'] + "\n"
                    
                    page_count += 1
                    
                    next_token = result.get('NextToken')
                    if not next_token:
                        break
                
                print(f"[TEXTRACT_ASYNC] ✓ Extracted text from {page_count} page(s)")
                print(f"[TEXTRACT_ASYNC] ✓ Total characters: {len(extracted_text)}")
                return extracted_text
                
            elif status == 'FAILED':
                error_msg = result.get('StatusMessage', 'Unknown error')
                print(f"[TEXTRACT_ASYNC] ❌ Job failed: {error_msg}")
                raise Exception(f"Textract async job failed: {error_msg}")
        
        print(f"[TEXTRACT_ASYNC] ❌ Timeout after {max_attempts} seconds")
        raise Exception(f"Textract async job timeout after {max_attempts} seconds")
        
    except Exception as e:
        print(f"[TEXTRACT_ASYNC ERROR] ❌ {str(e)}")
        raise Exception(f"Textract async processing failed: {str(e)}")


def extract_text_with_textract(file_bytes: bytes, filename: str):
    """Extract text from document using Amazon Textract with S3 caching"""
    try:
        print(f"\n{'='*80}")
        print(f"[TEXTRACT] Starting OCR for: {filename}")
        
        # OPTIMIZATION #3: Check S3 cache first to avoid re-processing
        import hashlib
        file_hash = hashlib.md5(file_bytes).hexdigest()
        cache_key = f"textract_cache/{file_hash}.txt"
        
        try:
            print(f"[OPTIMIZATION] Checking cache for file hash: {file_hash[:8]}...")
            cached_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_text = cached_response['Body'].read().decode('utf-8')
            
            if cached_text and len(cached_text) > 100:
                print(f"[OPTIMIZATION] ✅ CACHE HIT! Using cached Textract result")
                print(f"[OPTIMIZATION] ✅ Saved ~$0.04 by not re-running Textract")
                
                # Save to local file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(cached_text)
                print(f"[TEXTRACT] ✓ Retrieved from cache: {len(cached_text)} characters")
                print(f"{'='*80}\n")
                return cached_text, output_filename
        except s3_client.exceptions.NoSuchKey:
            print(f"[OPTIMIZATION] Cache miss - will process with Textract and cache result")
        except Exception as cache_err:
            print(f"[OPTIMIZATION] Cache check failed: {str(cache_err)} - proceeding with Textract")
        
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
        
        # OPTIMIZATION #3: Save to S3 cache for future use
        try:
            print(f"[OPTIMIZATION] Caching Textract result to S3: {cache_key}")
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=extracted_text.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'original_filename': filename,
                    'processed_date': timestamp,
                    'file_hash': file_hash
                }
            )
            print(f"[OPTIMIZATION] ✅ Cached to S3 - future uploads of same file will be FREE")
        except Exception as cache_save_err:
            print(f"[WARNING] Failed to cache result: {str(cache_save_err)}")
        
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
    """Fallback: Try to extract text from PDF using PyPDF2"""
    try:
        print(f"[PYPDF2] Attempting PyPDF2 extraction as fallback...")
        import PyPDF2
        import io
        
        pdf_file = io.BytesIO(file_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            text += page_text + "\n"
            print(f"[PYPDF2] Extracted page {page_num + 1}/{len(pdf_reader.pages)}")
        
        if not text.strip():
            print(f"[PYPDF2] ⚠️ No text extracted - PDF may be scanned")
            return None, None
        
        # Save extracted text
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"[PYPDF2] ✓ Extracted {len(text)} characters")
        print(f"[PYPDF2] ✓ Saved to: {output_filename}")
        return text, output_filename
        
    except Exception as e:
        print(f"[PYPDF2 ERROR] ❌ PyPDF2 extraction failed: {str(e)}")
        return None, None
