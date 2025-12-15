"""Account splitting logic for loan documents."""

import re
import logging
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime

from services.aws_services import aws_services
from config import OUTPUT_DIR, S3_BUCKET

logger = logging.getLogger(__name__)

class AccountSplitter:
    """Handles splitting loan documents into individual accounts."""
    
    def __init__(self):
        # Regex patterns for account number detection
        self.ACCOUNT_INLINE_RE = re.compile(r"^ACCOUNT NUMBER[:\s]*([0-9]{6,15})\b")
        self.ACCOUNT_LINE_RE = re.compile(r"^[0-9]{6,15}\b$")
        self.ACCOUNT_HEADER_RE = re.compile(r"^ACCOUNT NUMBER:?\s*$")
        self.ACCOUNT_HOLDER_RE = re.compile(r"^Account Holder Names:?\s*$")
    
    def split_accounts_strict(self, text: str) -> List[Dict[str, str]]:
        """
        Smart splitter for loan documents:
        - Handles both inline and multi-line 'ACCOUNT NUMBER' formats.
        - Accumulates text for the same account number if repeated.
        """
        logger.info(f"Starting account splitting... Input text length: {len(text)} characters")
        
        lines = text.splitlines()
        logger.info(f"Total lines: {len(lines)}")
        
        account_chunks = {}
        current_account = None
        buffer = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i].strip()

            # Case 1: Inline account number
            inline_match = self.ACCOUNT_INLINE_RE.match(line)
            if inline_match:
                acc = inline_match.group(1)
                logger.info(f"Line {i+1}: Found inline account number: {acc}")
                
                # Save previous buffer if moving to a new account
                if current_account and buffer:
                    account_chunks[current_account] = (
                        account_chunks.get(current_account, "") + "\n" + "\n".join(buffer)
                    )
                    buffer = []
                
                current_account = acc
                i += 1
                continue

            # Case 2: Multi-line header format
            if self.ACCOUNT_HEADER_RE.match(line):
                # Look ahead for "Account Holder Names:" then a number
                j = i + 1
                while j < n and lines[j].strip() == "":
                    j += 1
                
                if j < n and self.ACCOUNT_HOLDER_RE.match(lines[j].strip()):
                    k = j + 1
                    while k < n and lines[k].strip() == "":
                        k += 1
                    
                    if k < n and self.ACCOUNT_LINE_RE.match(lines[k].strip()):
                        acc = lines[k].strip()
                        logger.info(f"Line {i+1}: Found multi-line account number: {acc}")
                        
                        if current_account and buffer:
                            account_chunks[current_account] = (
                                account_chunks.get(current_account, "") + "\n" + "\n".join(buffer)
                            )
                            buffer = []
                        
                        current_account = acc
                        i = k + 1
                        continue

            # Default: add to current account buffer
            if current_account:
                buffer.append(lines[i])
            i += 1

        # Save last buffer
        if current_account and buffer:
            account_chunks[current_account] = (
                account_chunks.get(current_account, "") + "\n" + "\n".join(buffer)
            )

        # Convert to structured list
        chunks = [{"accountNumber": acc, "text": txt.strip()} for acc, txt in account_chunks.items()]
        
        logger.info(f"✓ Found {len(chunks)} unique accounts")
        for idx, chunk in enumerate(chunks):
            acc_num = chunk.get("accountNumber", "")
            text_len = len(chunk.get("text", ""))
            logger.info(f"   Account {idx+1}: {acc_num} ({text_len} chars)")
        
        return chunks
    
    def scan_and_map_pages(self, doc_id: str, pdf_path: str, accounts: List[Dict[str, Any]]) -> Dict[int, str]:
        """Scan pages and create a mapping of page_num -> account_number."""
        import fitz
        
        if not pdf_path or not os.path.exists(pdf_path):
            logger.warning(f"PDF path not found for scanning: {pdf_path}")
            return {}
        
        pdf_doc = fitz.open(pdf_path)
        total_pages = len(pdf_doc)
        pdf_doc.close()
        
        page_to_account = {}
        accounts_found = set()
        ocr_text_cache = {}
        
        logger.info(f"FAST PARALLEL scanning {total_pages} pages to find account boundaries")
        
        # Prepare arguments for parallel processing
        page_args = [(page_num, pdf_path, doc_id, accounts) for page_num in range(total_pages)]
        
        # Process pages in parallel
        max_workers = min(10, total_pages)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._process_single_page_scan, args) for args in page_args]
            
            for future in as_completed(futures):
                try:
                    page_num, page_text, matched_account = future.result()
                    
                    if page_text:
                        ocr_text_cache[page_num] = page_text
                    
                    if matched_account:
                        page_to_account[page_num] = matched_account
                        accounts_found.add(matched_account)
                        logger.info(f"Page {page_num + 1} -> Account {matched_account}")
                        
                except Exception as e:
                    logger.error(f"Future failed: {str(e)}")
        
        logger.info(f"PARALLEL scan complete: Found {len(accounts_found)} accounts on {len(page_to_account)} pages")
        
        # Cache OCR text to S3
        try:
            cache_key = f"ocr_cache/{doc_id}/text_cache.json"
            aws_services.upload_to_s3(
                S3_BUCKET, 
                cache_key, 
                json.dumps(ocr_text_cache).encode('utf-8'),
                'application/json'
            )
            logger.info(f"Cached OCR text for {len(ocr_text_cache)} pages to S3")
        except Exception as e:
            logger.warning(f"Failed to cache OCR text: {str(e)}")
        
        return page_to_account
    
    def _process_single_page_scan(self, args) -> tuple:
        """Helper function to process a single page (for parallel processing)."""
        page_num, pdf_path, doc_id, accounts = args
        
        try:
            # Open PDF for this thread
            pdf_doc = fitz.open(pdf_path)
            page = pdf_doc[page_num]
            page_text = page.get_text()
            pdf_doc.close()
            
            # Check if page has watermark
            has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
            
            # If no text, has watermark, or very little text - do OCR
            if not page_text or len(page_text.strip()) < 20 or has_watermark:
                try:
                    pdf_doc = fitz.open(pdf_path)
                    page = pdf_doc[page_num]
                    # SPEED: Use lower resolution (1x) for scanning - faster and cheaper
                    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
                    pdf_doc.close()
                    
                    temp_image_path = os.path.join(OUTPUT_DIR, f"temp_scan_{doc_id}_{page_num}.png")
                    pix.save(temp_image_path)
                    
                    with open(temp_image_path, 'rb') as image_file:
                        image_bytes = image_file.read()
                    
                    # SPEED: Use detect_document_text (sync) for faster processing
                    textract_response = aws_services.textract.detect_document_text(
                        Document={'Bytes': image_bytes}
                    )
                    
                    page_text = ""
                    for block in textract_response.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            page_text += block.get('Text', '') + "\n"
                    
                    if os.path.exists(temp_image_path):
                        os.remove(temp_image_path)
                        
                except Exception as ocr_err:
                    logger.error(f"OCR failed on page {page_num + 1}: {str(ocr_err)}")
                    return page_num, None, None
            
            if not page_text or len(page_text.strip()) < 20:
                return page_num, page_text, None
            
            # Check which account appears on this page
            matched_account = None
            for acc in accounts:
                acc_num = acc.get("accountNumber", "").strip()
                normalized_text = re.sub(r'[\s\-]', '', page_text)
                normalized_acc = re.sub(r'[\s\-]', '', acc_num)
                
                if normalized_acc and normalized_acc in normalized_text:
                    matched_account = acc_num
                    break
            
            return page_num, page_text, matched_account
            
        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {str(e)}")
            return page_num, None, None

# Global account splitter instance
account_splitter = AccountSplitter()