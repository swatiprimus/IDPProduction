#!/usr/bin/env python3
"""
Universal IDP - Modular Version
Uses clean modular services instead of monolithic code
"""

from flask import Flask, render_template, request, jsonify, send_file
import boto3
import json
import time
import threading
import hashlib
import os
import re
from datetime import datetime
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import modular services
from app.services.textract_service import extract_text_with_textract, try_extract_pdf_with_pypdf
from app.services.account_splitter import split_accounts_strict
from app.services.document_detector import detect_document_type, SUPPORTED_DOCUMENT_TYPES
from app.services.loan_processor import process_loan_document

app = Flask(__name__)

# AWS & Model Configuration
AWS_REGION = "us-east-1"
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
textract = boto3.client("textract", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)
MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
S3_BUCKET = "awsidpdocs"

# In-memory Job Tracker
job_status_map = {}

# Create output directory for OCR results
OUTPUT_DIR = "ocr_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Persistent storage for processed documents
DOCUMENTS_DB_FILE = "processed_documents.json"

def load_documents_db():
    """Load processed documents from file"""
    if os.path.exists(DOCUMENTS_DB_FILE):
        with open(DOCUMENTS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_documents_db(documents):
    """Save processed documents to file"""
    with open(DOCUMENTS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(documents, indent=2, fp=f)

# Load existing documents on startup
processed_documents = load_documents_db()

def find_existing_document_by_account(account_number):
    """Find existing document by account number"""
    if not account_number:
        return None
    
    # Normalize account number for comparison (remove spaces, dashes)
    normalized_search = re.sub(r'[\s\-]', '', str(account_number))
    
    for doc in processed_documents:
        # Check in basic_fields
        if doc.get("basic_fields", {}).get("account_number"):
            existing_acc = re.sub(r'[\s\-]', '', str(doc["basic_fields"]["account_number"]))
            if existing_acc == normalized_search:
                return doc
        
        # Check in documents array (for loan documents with accounts)
        for sub_doc in doc.get("documents", []):
            # Check extracted_fields
            if sub_doc.get("extracted_fields", {}).get("account_number"):
                existing_acc = re.sub(r'[\s\-]', '', str(sub_doc["extracted_fields"]["account_number"]))
                if existing_acc == normalized_search:
                    return doc
            
            # Check accounts array (for loan documents)
            for account in sub_doc.get("accounts", []):
                if account.get("accountNumber"):
                    existing_acc = re.sub(r'[\s\-]', '', str(account["accountNumber"]))
                    if existing_acc == normalized_search:
                        return doc
    
    return None

def merge_document_fields(existing_doc, new_doc):
    """Merge new document fields into existing document, tracking changes"""
    changes = []
    
    # Helper function to compare and merge fields
    def merge_fields(existing_fields, new_fields, path=""):
        field_changes = []
        for key, new_value in new_fields.items():
            # Skip empty values and metadata fields
            if new_value == "" or new_value is None:
                continue
            if key in ["total_accounts", "accounts_processed", "account_numbers"]:
                continue
                
            if key not in existing_fields:
                # New field added
                existing_fields[key] = new_value
                field_changes.append({
                    "field": f"{path}{key}",
                    "change_type": "added",
                    "new_value": new_value
                })
            elif existing_fields[key] != new_value:
                # Field value changed (skip if both are empty)
                old_value = existing_fields[key]
                if old_value == "" and new_value == "":
                    continue
                existing_fields[key] = new_value
                field_changes.append({
                    "field": f"{path}{key}",
                    "change_type": "updated",
                    "old_value": old_value,
                    "new_value": new_value
                })
        return field_changes
    
    # Merge basic_fields
    if new_doc.get("basic_fields"):
        if not existing_doc.get("basic_fields"):
            existing_doc["basic_fields"] = {}
        changes.extend(merge_fields(existing_doc["basic_fields"], new_doc["basic_fields"], "basic_fields."))
    
    # Merge documents array
    if new_doc.get("documents"):
        if not existing_doc.get("documents"):
            existing_doc["documents"] = []
        
        for new_sub_doc in new_doc["documents"]:
            # Find matching document by type
            doc_type = new_sub_doc.get("document_type")
            existing_sub_doc = next((d for d in existing_doc["documents"] if d.get("document_type") == doc_type), None)
            
            if existing_sub_doc:
                # Merge extracted_fields
                if new_sub_doc.get("extracted_fields"):
                    if not existing_sub_doc.get("extracted_fields"):
                        existing_sub_doc["extracted_fields"] = {}
                    changes.extend(merge_fields(existing_sub_doc["extracted_fields"], new_sub_doc["extracted_fields"], f"documents[{doc_type}].extracted_fields."))
                
                # Merge accounts array (for loan documents)
                if new_sub_doc.get("accounts"):
                    if not existing_sub_doc.get("accounts"):
                        existing_sub_doc["accounts"] = []
                    
                    for new_account in new_sub_doc["accounts"]:
                        acc_num = new_account.get("accountNumber")
                        existing_account = next((a for a in existing_sub_doc["accounts"] if a.get("accountNumber") == acc_num), None)
                        
                        if existing_account:
                            # Merge account result fields
                            if new_account.get("result"):
                                if not existing_account.get("result"):
                                    existing_account["result"] = {}
                                changes.extend(merge_fields(existing_account["result"], new_account["result"], f"accounts[{acc_num}].result."))
                        else:
                            # New account added
                            existing_sub_doc["accounts"].append(new_account)
                            changes.append({
                                "field": f"accounts[{acc_num}]",
                                "change_type": "added",
                                "new_value": acc_num
                            })
            else:
                # New document type added - add it to the existing document
                existing_doc["documents"].append(new_sub_doc)
                
                # Track all fields from the new document type as changes
                if new_sub_doc.get("extracted_fields"):
                    for field_name, field_value in new_sub_doc["extracted_fields"].items():
                        # Skip metadata fields
                        if field_name not in ["total_accounts", "accounts_processed", "account_numbers"]:
                            changes.append({
                                "field": f"documents[{doc_type}].extracted_fields.{field_name}",
                                "change_type": "added",
                                "new_value": field_value
                            })
    
    # Update metadata
    existing_doc["last_updated"] = datetime.now().isoformat()
    existing_doc["update_source_filename"] = new_doc.get("filename")
    existing_doc["needs_review"] = True
    existing_doc["changes"] = changes
    
    return existing_doc, changes

def _process_single_page_scan(args):
    """Helper function to process a single page (for parallel processing)"""
    page_num, pdf_path, doc_id, accounts = args
    import fitz
    import re
    
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
                # Use higher resolution (2x) for better OCR accuracy
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pdf_doc.close()
                
                temp_image_path = os.path.join(OUTPUT_DIR, f"temp_scan_{doc_id}_{page_num}.png")
                pix.save(temp_image_path)
                
                with open(temp_image_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                
                print(f"[SCAN] Running OCR on page {page_num + 1} (watermark: {has_watermark}, little text: {len(page_text.strip()) < 20})")
                
                # Use detect_document_text for OCR
                textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                
                ocr_text = ""
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        ocr_text += block.get('Text', '') + "\n"
                
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                
                if ocr_text.strip():
                    page_text = ocr_text
                    print(f"[SCAN] OCR extracted {len(page_text)} chars from page {page_num + 1}")
                else:
                    print(f"[SCAN] OCR returned no text for page {page_num + 1}")
                    
            except Exception as ocr_err:
                print(f"[ERROR] OCR failed on page {page_num + 1}: {str(ocr_err)}")
                return page_num, None, None
        
        if not page_text or len(page_text.strip()) < 20:
            return page_num, page_text, None
        
        # Check which account appears on this page - use more flexible matching
        matched_account = None
        for acc in accounts:
            acc_num = acc.get("accountNumber", "").strip()
            if not acc_num:
                continue
                
            # Try multiple matching strategies
            found = False
            
            # Strategy 1: Exact match (no spaces/dashes)
            normalized_text = re.sub(r'[\s\-\.]', '', page_text)
            normalized_acc = re.sub(r'[\s\-\.]', '', acc_num)
            if normalized_acc in normalized_text:
                found = True
                print(f"[SCAN] Found account {acc_num} on page {page_num + 1} (exact match)")
            
            # Strategy 2: Partial match (first 6 digits)
            if not found and len(acc_num) >= 6:
                partial_acc = acc_num[:6]
                if partial_acc in normalized_text:
                    found = True
                    print(f"[SCAN] Found account {acc_num} on page {page_num + 1} (partial match: {partial_acc})")
            
            # Strategy 3: Regex pattern matching for account-like numbers
            if not found:
                # Look for the account number with possible formatting
                pattern = r'\b' + re.escape(acc_num) + r'\b'
                if re.search(pattern, page_text, re.IGNORECASE):
                    found = True
                    print(f"[SCAN] Found account {acc_num} on page {page_num + 1} (regex match)")
            
            # Strategy 4: Look for any 9-digit number that matches
            if not found and len(acc_num) == 9:
                nine_digit_pattern = r'\b\d{9}\b'
                matches = re.findall(nine_digit_pattern, page_text)
                if acc_num in matches:
                    found = True
                    print(f"[SCAN] Found account {acc_num} on page {page_num + 1} (9-digit pattern)")
            
            if found:
                matched_account = acc_num
                break
        
        return page_num, page_text, matched_account
        
    except Exception as e:
        print(f"[ERROR] Failed to process page {page_num + 1}: {str(e)}")
        return page_num, None, None


def scan_and_map_pages(doc_id, pdf_path, accounts):
    """Scan pages and create a mapping of page_num -> account_number (PARALLEL + CACHED)"""
    import fitz
    
    pdf_doc = fitz.open(pdf_path)
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    page_to_account = {}
    accounts_found = set()
    ocr_text_cache = {}
    
    print(f"[INFO] FAST PARALLEL scanning {total_pages} pages to find account boundaries")
    print(f"[INFO] Looking for accounts: {[acc.get('accountNumber', 'N/A') for acc in accounts]}")
    
    # SPEED OPTIMIZATION: Process pages in parallel (up to 10 workers)
    max_workers = min(10, total_pages)
    
    # Prepare arguments for parallel processing
    page_args = [(page_num, pdf_path, doc_id, accounts) for page_num in range(total_pages)]
    
    # Process pages in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_single_page_scan, args) for args in page_args]
        
        for future in as_completed(futures):
            try:
                page_num, page_text, matched_account = future.result()
                
                if page_text:
                    ocr_text_cache[page_num] = page_text
                
                if matched_account:
                    page_to_account[page_num] = matched_account
                    accounts_found.add(matched_account)
                    print(f"[INFO] Page {page_num + 1} -> Account {matched_account}")
                    
            except Exception as e:
                print(f"[ERROR] Future failed: {str(e)}")
    
    print(f"[INFO] PARALLEL scan complete: Found {len(accounts_found)} accounts on {len(page_to_account)} pages")
    print(f"[INFO] Page to account mapping: {page_to_account}")
    print(f"[INFO] Accounts found: {accounts_found}")
    
    # OPTIMIZATION: Save OCR cache to S3 to avoid re-running OCR
    try:
        cache_key = f"ocr_cache/{doc_id}/text_cache.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=cache_key,
            Body=json.dumps(ocr_text_cache),
            ContentType='application/json'
        )
        print(f"[INFO] Cached OCR text for {len(ocr_text_cache)} pages to S3")
    except Exception as e:
        print(f"[WARNING] Failed to cache OCR text: {str(e)}")
    
    return page_to_account


def get_comprehensive_extraction_prompt():
    """Get comprehensive prompt for extracting ALL fields from any page"""
    return """
You are a data extraction expert. Extract ALL fields and their values from this document.

🔴🔴🔴 CRITICAL PRIORITY #1: VERIFICATION DETECTION 🔴🔴🔴
**THIS IS THE MOST IMPORTANT TASK - NEVER SKIP VERIFICATION DETECTION**

**STEP 1: MANDATORY VERIFICATION SCAN (DO THIS FIRST):**
Before extracting any other data, you MUST scan the ENTIRE page for verification indicators:

1. **SEARCH FOR "VERIFIED" TEXT EVERYWHERE:**
   - Look for "VERIFIED" stamps, seals, or text ANYWHERE on the page
   - Look for "VERIFICATION" text or stamps  
   - Look for "VERIFY" or "VERIFIED BY" text
   - Look for checkboxes or boxes marked with "VERIFIED"
   - Look for "✓ VERIFIED" or similar checkmark combinations
   - Search in margins, corners, stamps, seals, form fields, and document body
   - Extract as: Verified: {"value": "VERIFIED", "confidence": 95}

2. **SEARCH FOR NAMES NEAR VERIFICATION:**
   - Look for names immediately after "VERIFIED" (like "VERIFIED - RENDA")
   - Look for "VERIFIED BY: [NAME]" patterns
   - Look for names in verification stamps or seals
   - Extract as: Verified_By: {"value": "Name", "confidence": 85}
   
3. **SEARCH FOR VERIFICATION DATES:**
   - Look for dates on or near verification stamps
   - Look for "VERIFIED ON: [DATE]" patterns
   - Extract as: Verified_Date: {"value": "Date", "confidence": 85}

**OTHER CRITICAL FIELDS:**
4. **PHONE NUMBERS** - Look for "610-485-4979", "610- 485- 4979", "(302) 834-0382" - Extract as Phone_Number
5. **STAMP DATES** - Look for "MAR 21 2016", "DEC 26 2014", "MAR 2 5 2015" - Extract as Stamp_Date  
6. **REFERENCE NUMBERS** - Look for "#652", "#357", "#298" - Extract as Reference_Number
7. **ACCOUNT NUMBERS** - Any 8-10 digit numbers - Extract as Account_Number
8. **HANDWRITTEN TEXT** - Any handwritten numbers or text

🔴🔴🔴 VERIFICATION SEARCH INSTRUCTIONS 🔴🔴🔴
- **ALWAYS** scan the ENTIRE page text for the word "VERIFIED" (case-insensitive)
- **ALWAYS** scan for "VERIFICATION" text
- **ALWAYS** look for verification stamps, seals, or checkmarks
- **NEVER** skip verification detection - it must be checked on every page
- If you find "VERIFIED" anywhere, ALWAYS extract it as a field
- Look in margins, corners, stamps, seals, and form fields

CRITICAL: Extract EVERYTHING you see - printed text, handwritten text, stamps, seals, and marks.

IMPORTANT: Use SIMPLE, SHORT field names. Do NOT copy the entire label text from the document.
- Example: "DATE PRONOUNCED DEAD" → use "Death_Date" (NOT "Date_Pronounced_Dead")
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "Account_Holder_Names")
- Example: If you see "VERIFIED" stamp → use "Verified" with value "Yes" or "VERIFIED"
- Example: If you see handwritten "4630" near "Account" → use "Account_Number" with value "4630"
- Simplify all verbose labels to their core meaning

SPECIAL ATTENTION REQUIRED:
🔴 **HANDWRITTEN TEXT:** Extract ALL handwritten numbers and text - these are CRITICAL data points
   - Handwritten numbers are often account numbers, reference numbers, or IDs
   - **HANDWRITTEN PHONE NUMBERS:** Look for patterns like "610-485-4979", "610- 485- 4979", "(610) 485-4979"
   - Extract them with appropriate field names (Account_Number, Reference_Number, Phone_Number, Contact_Phone, etc.)
   
🔴 **STAMPS & SEALS:** Extract ALL stamps, seals, and verification marks
   - "VERIFIED" stamp → Verified: "Yes" or "VERIFIED"
   - Date stamps → Stamp_Date or Verified_Date (look for formats like "MAR 21 2016", "DEC 26 2014", "JAN 15 2023")
   - Reference numbers with stamps → Reference_Number (look for "#652", "#357", "Ref #123")
   - Names in stamps → Verified_By or Stamped_By
   - Official seals → Official_Seal: "Present" or description
   
🔴 **MULTIPLE NUMBERS:** Documents often have MULTIPLE number types - extract ALL of them
   - **Account_Number** (PRIMARY IDENTIFIER - handwritten or printed account/billing number)
   - Certificate_Number (printed certificate ID - ONLY if clearly labeled as "Certificate Number")
   - File_Number (state file number)
   - Reference_Number (reference or tracking number)

🔴🔴🔴 CRITICAL FOR DEATH CERTIFICATES 🔴🔴🔴
- **ANY LARGE NUMBER (8-10 digits) on a death certificate should be extracted as Account_Number**
- **Examples: 463085233, 468431466 → ALWAYS use Account_Number (NOT Certificate_Number)**
- **Only use Certificate_Number if you see explicit labels like "Certificate Number:" or "Cert #:"**
- **When in doubt on death certificates, use Account_Number for the main identifying number**

PRIORITY ORDER (Extract in this order):
1. **HANDWRITTEN NUMBERS** - These are often the most important (account numbers, IDs)
2. **STAMPS & VERIFICATION MARKS** - Verified stamps, date stamps, official seals
3. **IDENTIFYING NUMBERS** - Certificate numbers, file numbers, license numbers
4. **NAMES** - All person names (full names, witness names, registrar names, stamped names)
5. **DATES** - All dates (issue dates, birth dates, death dates, stamp dates)
6. **LOCATIONS** - Cities, states, counties, countries, addresses
7. **FORM FIELDS** - All labeled fields with values
8. **CHECKBOXES** - Checkbox states (Yes/No, checked/unchecked)
9. **ANY OTHER VISIBLE DATA** - Extract everything else you can see

🔴🔴🔴 CRITICAL PHONE NUMBER EXTRACTION RULES 🔴🔴🔴
- **PHONE NUMBERS ARE CRITICAL** - Look for ALL phone number patterns in the document
- **COMMON PHONE NUMBER FORMATS:**
  * "610-485-4979" (standard format with dashes)
  * "610- 485- 4979" (with spaces around dashes - common in handwritten)
  * "(302) 834-0382" (with parentheses and space)
  * "302.834.0382" (with dots)
  * "3028340382" (no separators)
- **HANDWRITTEN PHONE NUMBERS:** Often have irregular spacing - still extract them
- **WHERE TO FIND:** Can appear anywhere on the document - margins, forms, handwritten notes
- **FIELD NAMES:** Use Phone_Number, Contact_Phone, Mobile_Phone, or Signer1_Phone as appropriate

🔴🔴🔴 CRITICAL STAMP DATE EXTRACTION RULES 🔴🔴🔴
- **STAMP DATES ARE CRITICAL** - Look for standalone dates that appear to be stamped on the document
- **COMMON STAMP DATE FORMATS:**
  * "MAR 21 2016" (month abbreviation, day, year)
  * "DEC 26 2014" (month abbreviation, day, year)  
  * "MAR 2 5 2015" (month abbreviation, day with space, year)
  * "JAN 15 2023" (month abbreviation, day, year)
- **STAMP REFERENCE NUMBERS:** Look for numbers with # symbol like "#652", "#357", "#298"
- **WHERE TO FIND STAMPS:** Usually in margins, corners, or separate sections of certificates
- **EXTRACT BOTH:** If you see a stamp date, also look for an associated reference number nearby

CRITICAL RULES:
- Extract EVERY field you can see - printed, handwritten, stamped, or sealed
- **HANDWRITTEN TEXT IS CRITICAL** - Never skip handwritten numbers or text
- **STAMPS ARE DATA** - Extract stamp text as actual field values, not descriptions
- Include ALL identifying numbers (license #, certificate #, file #, reference #, account #, etc.)
- Extract ALL names, even if they appear multiple times in different contexts
- Extract ALL dates in their original format
- Do NOT extract long legal text, disclaimers, or authorization paragraphs
- Do NOT extract instructions about how to fill the form
- Extract actual DATA, not explanatory text

WHAT TO EXTRACT:
✓ **IDENTIFYING NUMBERS (Extract ALL - Documents can have multiple number types):**
  - **ALWAYS match the field name to the LABEL on the document**
  - **A document can have MULTIPLE number types** (e.g., both Certificate_Number AND Account_Number)
  - **Certificate_Number:** Use when you see "Certificate Number", "Certificate No", "Cert #"
  - **Account_Number:** Use when you see "Account Number", "Account No", "Acct #", "Acct Number" (may be handwritten or printed)
  - **File_Number:** Use when you see "File Number", "File No", "State File Number"
  - **License_Number:** Use when you see "License Number", "License No", "DL #"
  - **Reference_Number:** Use when you see "Reference Number", "Ref #", "Reference No"
  - **Registration_Number:** Use when you see "Registration Number", "Registration No"
  - **IMPORTANT:** Extract ALL numbers you find - don't skip any!
  - **Example:** A death certificate might have BOTH Certificate_Number (for the certificate) AND Account_Number (handwritten for billing)
  - **Rule:** If you see "Account" or "Acct" label → ALWAYS extract as Account_Number (even on certificates)
✓ **ALL OTHER IDENTIFYING NUMBERS:**
  - Document_Number, Reference_Number, Case_Number
  - Any number with a label or identifier
✓ **ALL NAMES:**
  - Full_Name, Spouse_Name, Witness_Names, Registrar_Name
  - Father_Name, Mother_Name, Maiden_Name
  - Any person's name mentioned in the document
✓ **ALL DATES:**
  - Issue_Date, Birth_Date, Marriage_Date, Death_Date
  - Expiration_Date, Filing_Date, Registration_Date
  - Stamp_Date (look for stamps like "DEC 26 2014", "JAN 15 2023", "MAR 21 2016", "MAR 2 5 2015")
  - Reference_Number (look for "#652", "#357", "Ref #123", numbers with # symbol)
✓ **ALL LOCATIONS:**
  - City, State, County, Country
  - Place_of_Birth, Place_of_Marriage, Place_of_Death
  - Address, Residence
✓ **FORM FIELDS:**
  - Business_Name, Account_Number
  - Card_Details, Abbreviations_Needed
  - Branch_Name, Associate_Name
  - ALL other form fields with labels
✓ **SIGNER INFORMATION (if applicable):**
  - If ONE signer: Signer1_Name, Signer1_SSN, Signer1_DateOfBirth, Signer1_Address, Signer1_Phone, Signer1_DriversLicense
  - If TWO signers: Add Signer2_Name, Signer2_SSN, Signer2_DateOfBirth, Signer2_Address, Signer2_Phone, Signer2_DriversLicense
  - If THREE+ signers: Continue with Signer3_, Signer4_, etc.
✓ **VERIFICATION & CERTIFICATION FIELDS:**
  - Verified (Yes/No or checkbox state)
  - Verified_By (name of person who verified)
  - Verified_Date (date of verification)
  - Certification_Date, Certified_By
  - Registrar_Name, Registrar_Signature
  - Official_Seal, Stamp_Date
  - Any verification stamps or certification marks
✓ **CHECKBOXES & STATUS FIELDS:**
  - Extract ALL checkbox states (checked/unchecked, Yes/No, True/False)
  - Status fields (Approved, Pending, Verified, etc.)
  - Any marked or selected options
✓ **PHONE NUMBERS & CONTACT INFO:**
  - Phone_Number, Contact_Phone, Mobile_Phone (look for patterns like "610-485-4979", "610- 485- 4979", "(302) 834-0382")
  - Fax_Number, Email_Address
  - **CRITICAL:** Extract ALL phone numbers, even if handwritten or have unusual spacing
✓ **ALL OTHER VISIBLE FIELDS**

WHAT NOT TO EXTRACT:
✗ Long authorization paragraphs
✗ Legal disclaimers
✗ "NOTE:" sections with instructions
✗ "AUTHORIZATION:" sections with legal text
✗ Form filling instructions
✗ Page numbers
✗ Headers and footers (unless they contain data)

FIELD NAMING:
- Use SIMPLE, SHORT field names (not the full label text)
- Replace spaces with underscores
- **MATCH THE LABEL ON THE DOCUMENT:**
  * If document says "Certificate Number" → use "Certificate_Number"
  * If document says "Account Number" → use "Account_Number"
  * If document says "License Number" → use "License_Number"
  * If document says "File Number" → use "File_Number"
- Example: "License Number" → "License_Number"
- Example: "Date of Birth" → "Date_Of_Birth"
- Example: "DATE PRONOUNCED DEAD" → "Death_Date"
- Example: "ACTUAL OR PRESUMED DATE OF DEATH" → "Death_Date"
- Simplify verbose labels to their core meaning, but keep the field type accurate

EXAMPLES OF MULTIPLE NUMBER TYPES:

Example 1: Death Certificate with handwritten account number
- Document shows: "Certificate Number: 2025-12345" (printed)
- Document shows: "Account No: 987654321" (handwritten)
- Extract BOTH:
{
  "Certificate_Number": {"value": "2025-12345", "confidence": 95},
  "Account_Number": {"value": "987654321", "confidence": 75}
}

Example 2: Bank document with multiple numbers
- Document shows: "Account Number: 1234567890"
- Document shows: "Reference #: 298"
- Extract BOTH:
{
  "Account_Number": {"value": "1234567890", "confidence": 95},
  "Reference_Number": {"value": "298", "confidence": 90}
}

RETURN FORMAT:
Return a JSON object where each field has both a value and a confidence score (0-100):

{
  "Field_Name": {
    "value": "extracted value",
    "confidence": 95
  },
  "Phone_Number": {
    "value": "610-485-4979",
    "confidence": 85
  },
  "Stamp_Date": {
    "value": "MAR 21 2016",
    "confidence": 90
  },
  "Reference_Number": {
    "value": "#357",
    "confidence": 95
  }
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

IMPORTANT:
- Only include fields with actual values (omit empty fields)
- Every field MUST have both "value" and "confidence"
- Be honest about confidence - if text is unclear, use a lower score
- Extract the phone number "610- 485- 4979" as "Phone_Number": {"value": "610-485-4979", "confidence": 75}

EXTRACT EVERYTHING - BE THOROUGH AND COMPLETE!
"""

def get_drivers_license_prompt():
    """Get specialized prompt for extracting driver's license / ID card information"""
    return """
You are a data extraction expert specializing in government-issued identification documents.

Extract ALL information from this Driver's License or ID Card.

CRITICAL FIELDS TO EXTRACT:
1. **PERSONAL INFORMATION:**
   - Full_Name (as shown on license)
   - First_Name, Middle_Name, Last_Name
   - Date_of_Birth (DOB)
   - Sex / Gender
   - Height
   - Weight
   - Eye_Color
   - Hair_Color

2. **LICENSE INFORMATION:**
   - License_Number (DL #, ID #)
   - State / Issuing_State
   - License_Class (Class A, B, C, D, etc.)
   - Issue_Date (ISS)
   - Expiration_Date (EXP)
   - Restrictions (if any)
   - Endorsements (if any)

3. **ADDRESS:**
   - Street_Address
   - City
   - State
   - ZIP_Code
   - Full_Address (complete address as shown)

4. **ADDITIONAL INFORMATION:**
   - Document_Type (Driver License, ID Card, etc.)
   - Card_Number (if different from license number)
   - DD_Number (Document Discriminator)
   - Organ_Donor (Yes/No if indicated)
   - Veteran (if indicated)
   - Any_Barcodes or QR_Codes
   - Any_Other_Numbers or identifiers

EXTRACTION RULES:
- Extract EVERY visible field on the ID card
- Include all numbers, dates, and text
- Preserve exact formatting of license numbers and dates
- Extract address exactly as shown
- Include any stamps, seals, or watermarks mentioned
- If a field is partially visible or unclear, still extract it and note "unclear" or "partially visible"
- Look for information on BOTH front and back of the card if visible

FIELD NAMING:
- Use descriptive names with underscores
- Example: "DL #" → "License_Number"
- Example: "DOB" → "Date_of_Birth"
- Example: "ISS" → "Issue_Date"
- Example: "EXP" → "Expiration_Date"

RETURN FORMAT:
Return ONLY valid JSON in this exact format where EVERY field has both value and confidence:
{
  "documents": [
    {
      "document_id": "dl_001",
      "document_type": "drivers_license",
      "document_type_display": "Driver's License / ID Card",
      "document_icon": "🪪",
      "document_description": "Government-issued identification",
      "extracted_fields": {
        "Document_Type": {
          "value": "Driver License",
          "confidence": 95
        },
        "State": {
          "value": "Delaware",
          "confidence": 100
        },
        "License_Number": {
          "value": "1234567",
          "confidence": 95
        },
        "Full_Name": {
          "value": "John Doe",
          "confidence": 98
        },
        "Date_of_Birth": {
          "value": "01/15/1980",
          "confidence": 100
        },
        "Address": {
          "value": "123 Main St",
          "confidence": 95
        },
        "City": {
          "value": "Wilmington",
          "confidence": 100
        },
        "Issue_Date": {
          "value": "12/03/2012",
          "confidence": 100
        },
        "Expiration_Date": {
          "value": "12/03/2020",
          "confidence": 100
        }
      }
    }
  ]
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL REQUIREMENTS:
- EVERY field MUST have both "value" and "confidence"
- Only include fields that are VISIBLE in the document
- Do not use "N/A" or empty strings
- Extract EVERYTHING you can see on the ID card - be thorough and complete!
"""

def get_loan_document_prompt():
    """Get the specialized prompt for loan/account documents"""
    # PROMPT VERSION: Increment this when prompt changes to invalidate old cache
    # Current version: v7 (enhanced VERIFIED detection for loan documents)
    return """
You are an AI assistant that extracts ALL structured data from loan account documents.

🔴🔴🔴 CRITICAL: RETURN ALL FIELDS WITH CONFIDENCE SCORES 🔴🔴🔴
**EVERY field MUST be returned in this format:**
```json
{
  "Field_Name": {
    "value": "extracted value",
    "confidence": 95
  }
}
```

**CONFIDENCE SCORE GUIDELINES:**
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

🔴🔴🔴 CRITICAL PRIORITY #1: VERIFICATION DETECTION 🔴🔴🔴
**THIS IS THE MOST IMPORTANT TASK - NEVER SKIP VERIFICATION DETECTION**

**STEP 1: MANDATORY VERIFICATION SCAN (DO THIS FIRST):**
Before extracting any other data, you MUST scan the ENTIRE page for verification indicators:

1. **SEARCH FOR "VERIFIED" TEXT EVERYWHERE:**
   - Look for "VERIFIED" stamps, seals, or text ANYWHERE on the page
   - Look for "VERIFICATION" text or stamps  
   - Look for "VERIFY" or "VERIFIED BY" text
   - Look for checkboxes or boxes marked with "VERIFIED"
   - Look for "✓ VERIFIED" or similar checkmark combinations
   - Search in margins, corners, stamps, seals, form fields, and document body
   - Extract as: Verified: {"value": "VERIFIED", "confidence": 95}

2. **SEARCH FOR NAMES NEAR VERIFICATION:**
   - Look for names immediately after "VERIFIED" (like "VERIFIED - RENDA")
   - Look for "VERIFIED BY: [NAME]" patterns
   - Look for names in verification stamps or seals
   - Extract as: Verified_By: {"value": "Name", "confidence": 85}
   
3. **SEARCH FOR VERIFICATION DATES:**
   - Look for dates on or near verification stamps
   - Look for "VERIFIED ON: [DATE]" patterns
   - Extract as: Verified_Date: {"value": "Date", "confidence": 85}

🚨 **VERIFICATION DETECTION RULES:**
- **NEVER** skip verification detection - it must be checked on EVERY page
- **ALWAYS** scan the ENTIRE page text for "VERIFIED" (case-insensitive)
- **ALWAYS** extract verification fields if found, even if unclear
- If you find ANY verification indicator, you MUST extract it
- Look in ALL parts of the page: headers, footers, margins, stamps, seals, form fields

🔴🔴🔴 VERIFICATION EXAMPLES - STUDY THESE PATTERNS 🔴🔴🔴

**COMMON VERIFICATION PATTERNS TO LOOK FOR:**
- "VERIFIED" (standalone stamp)
- "VERIFIED - [NAME]" (stamp with name)
- "VERIFIED BY: [NAME]" (formal verification)
- "✓ VERIFIED" (checkmark with verified)
- "VERIFICATION COMPLETE" (process completion)
- "DOCUMENT VERIFIED" (document validation)
- "IDENTITY VERIFIED" (identity confirmation)
- "SIGNATURE VERIFIED" (signature validation)

**EXAMPLE EXTRACTIONS:**
- Text: "VERIFIED" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}
- Text: "VERIFIED - RENDA" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "RENDA", "confidence": 90}
- Text: "VERIFIED BY: MARIA SANTOS" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "MARIA SANTOS", "confidence": 90}
- Text: "✓ VERIFIED 03/15/2024" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_Date: {"value": "03/15/2024", "confidence": 90}
- Text: "VERIFICATION COMPLETE" → Extract: Verified: {"value": "VERIFIED", "confidence": 90}

🚨 **CRITICAL REMINDER:**
- Verification detection is MANDATORY on every page
- Even if the text is unclear, extract it with lower confidence
- Look in ALL areas of the page, not just the main content
- If you're unsure, extract it anyway - better to have false positives than miss verification

🔴🔴🔴 MOST IMPORTANT - EXTRACT ALL ACCOUNT AND SIGNER FIELDS 🔴🔴🔴

**CRITICAL ACCOUNT FIELDS TO EXTRACT:**
1. **Account_Number** - Look for "ACCOUNT NUMBER:", "Account Number:", or similar labels
2. **Account_Holders** - Look for "Account Holder Names:", "ACCOUNT HOLDER NAMES:", or names listed as account owners
3. **Mailing_Address** - Look for "Mailing Address:", complete address with street, city, state, zip
4. **Phone_Number** - Look for "Home Phone:", "Work Phone:", or any phone numbers
5. **Date_Opened** - Look for "DATE OPENED:", "Date Opened:", opening date
6. **CIF_Number** - Look for "CIF Number", "CIF #", customer identification number
7. **Branch** - Look for branch name, location, or office name
8. **Verified_By** - Look for "VERIFIED BY:", "Verified By:", name of verifier
9. **Opened_By** - Look for "OPENED BY:", name of person who opened account
10. **Signatures_Required** - Look for "Number of Signatures Required:", signature requirements

**CRITICAL SIGNER FIELDS TO EXTRACT:**
For EACH signer, you MUST extract EVERY piece of information visible:
- Name, SSN, Date of Birth, Address (complete with street, city, state, zip)
- Phone, Email, Driver's License, Citizenship, Occupation, Employer
- DO NOT skip any signer fields - extract EVERYTHING you see
- If a field exists for a signer, YOU MUST INCLUDE IT in the output

**EXAMPLE FIELD MAPPINGS FROM DOCUMENT:**
- "Account Holder Names: DANETTE EBERLY OR R BRUCE EBERLY" → Account_Holders: ["DANETTE EBERLY", "R BRUCE EBERLY"]
- "Mailing Address: 512 PONDEROSA DR, BEAR, DE, 19701-2155" → Mailing_Address: "512 PONDEROSA DR, BEAR, DE, 19701-2155"
- "Home Phone: (302) 834-0382" → Phone_Number: "(302) 834-0382"
- "CIF Number 00000531825" → CIF_Number: "00000531825"
- "VERIFIED BY: Kasie Mears" → Verified_By: "Kasie Mears"
- "468869904" followed by "WSFS Core Savings" → WSFS_Account_Type: "WSFS Core Savings"

🔴🔴🔴 CRITICAL PARSING RULES - READ THESE FIRST 🔴🔴🔴

**RULE 1: WSFS PRODUCT NAME EXTRACTION**
Look for this EXACT pattern in the text:
```
ACCOUNT NUMBER:
Account Holder Names:
468869904
WSFS Core Savings
```
When you see an account number followed by "WSFS Core Savings" (or similar product name), extract it as:
WSFS_Account_Type: "WSFS Core Savings"

**RULE 2: COMBINED OCR TEXT PARSING**
The OCR often reads form labels and values together without spaces. You MUST parse them correctly:

IF YOU SEE THIS IN THE TEXT:
- "PurposeConsumer" or "Purpose:Consumer" or "Purpose: Consumer" → Extract as: "Account_Purpose": "Consumer"
- "TypePersonal" or "Type:Personal" or "Type: Personal" → Extract as: "Account_Type": "Personal"
- "PurposeConsumer Personal" or "Purpose:Consumer Type:Personal" → Extract as TWO fields:
  * "Account_Purpose": "Consumer"
  * "Account_Type": "Personal"

PARSING RULES:
1. Look for the word "Purpose" followed by a value (Consumer, Checking, Savings, etc.) → Extract as Account_Purpose
2. Look for the word "Type" followed by a value (Personal, Business, etc.) → Extract as Account_Type
3. These are ALWAYS separate fields even if they appear together in the text
4. NEVER combine them into one field

WRONG ❌:
{
  "Account_Purpose": "Consumer Personal"
}

CORRECT ✅:
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal"
}

IF THE TEXT SAYS "PurposeConsumer Personal", PARSE IT AS:
- Find "Purpose" → Next word is "Consumer" → Account_Purpose: "Consumer"
- Find "Personal" (after Consumer) → This is the Type value → Account_Type: "Personal"

CRITICAL: Use SIMPLE, SHORT field names. Do NOT copy verbose labels from the document.
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "AccountHolderNames")
- Example: "DATE OF BIRTH" → use "DOB" or "Birth_Date" (NOT "DateOfBirth")
- Example: "SOCIAL SECURITY NUMBER" → use "SSN" (NOT "SocialSecurityNumber")
- Keep field names concise and readable

**CRITICAL ACCOUNT NUMBER DETECTION RULES (FOR BANK/LOAN DOCUMENTS ONLY):**
- This prompt is for BANK/LOAN documents, so Account_Number is the primary identifier
- Account numbers may be HANDWRITTEN or printed on the document
- Look for labels like: "Account", "Acct", "Account #", "Account No", "Acct Number", "Account Number"
- Account numbers are typically 8-12 digits, may have dashes or spaces
- If you see a handwritten number near an "Account" label, extract it as Account_Number
- DO NOT use Account_Number for:
  * Death/Birth/Marriage certificates (use Certificate_Number instead)
  * Driver's licenses (use License_Number instead)
  * File reference numbers (use File_Number instead)
- ONLY use Account_Number if the document is clearly a bank/loan/account document

Extract EVERY piece of information from the document and return it as valid JSON.

REQUIRED FIELDS (extract if present):

REQUIRED FIELDS TO EXTRACT (if present in document):
{
  "Account_Number": "string (e.g., 468869904)",
  "Account_Holders": ["name1", "name2"] (e.g., ["DANETTE EBERLY", "R BRUCE EBERLY"]),
  "Account_Purpose": "string (e.g., Consumer)",
  "Account_Category": "string (e.g., Personal)", 
  "Account_Type": "string (for backward compatibility)",
  "WSFS_Account_Type": "string (e.g., WSFS Core Savings)",
  "Ownership_Type": "string (e.g., Joint Owners)",
  "Mailing_Address": "string (complete address)",
  "Phone_Number": "string (e.g., (302) 834-0382)",
  "Work_Phone": "string (if different from home phone)",
  "Date_Opened": "string (e.g., 12/24/2014)",
  "Date_Revised": "string (if present)",
  "CIF_Number": "string (e.g., 00000531825)",
  "Branch": "string (e.g., College Square)",
  "Verified_By": "string (e.g., Kasie Mears)",
  "Opened_By": "string (if present)",
  "Signatures_Required": "string (e.g., 1)",
  "Special_Instructions": "string (if present)",
  "Form_Number": "string (if present)",
  "Stamp_Date": "string (e.g., DEC 26 2014)",
  "Reference_Number": "string (e.g., #298)",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DOB": "string",
  "Signer1_Address": "string",
  "Signer1_Phone": "string",
  "Signer1_DriversLicense": "string",
  "Signer2_Name": "string (if multiple signers)",
  "Signer2_SSN": "string",
  "Signer2_DOB": "string",
  "Signer2_Address": "string",
  "Signer2_Phone": "string",
  "Signer2_DriversLicense": "string"
}

For documents with MULTIPLE signers, add Signer2_, Signer3_, etc.:
{
  "Account_Number": "string",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DOB": "string",
  "Signer2_Name": "string",
  "Signer2_SSN": "string",
  "Signer2_DOB": "string"
}

FIELD DEFINITIONS - READ CAREFULLY:

🔴 CRITICAL: Account_Purpose and Account_Type are TWO SEPARATE FIELDS - NEVER combine them!

1. Account_Purpose: The CATEGORY or CLASSIFICATION of the account.
   LOOK FOR: The word "Purpose" in the text (may appear as "Purpose:", "PurposeConsumer", "Purpose Consumer", etc.)
   EXTRACT: The value that comes AFTER "Purpose"
   POSSIBLE VALUES:
   - "Consumer" (consumer banking)
   - "Checking" (checking account)
   - "Savings" (savings account)
   - "Money Market" (money market account)
   - "CD" or "Certificate of Deposit"
   - "IRA" or "Retirement"
   - "Loan" (loan account)
   - "Mortgage" (mortgage account)
   
   PARSING EXAMPLES:
   - Text: "Purpose: Consumer" → Account_Purpose: "Consumer"
   - Text: "PurposeConsumer" → Account_Purpose: "Consumer"
   - Text: "Purpose:Consumer Type:Personal" → Account_Purpose: "Consumer" (extract ONLY the Purpose value)
   - Text: "PurposeConsumer Personal" → Account_Purpose: "Consumer" (extract ONLY "Consumer", NOT "Consumer Personal")

2. Account_Type: The USAGE TYPE or WHO uses the account.
   LOOK FOR: The word "Type" in the text (may appear as "Type:", "TypePersonal", "Type Personal", etc.)
   EXTRACT: The value that comes AFTER "Type"
   POSSIBLE VALUES:
   - "Personal" (for individual/family use)
   - "Business" (for business operations)
   - "Commercial" (for commercial purposes)
   - "Corporate" (for corporation)
   - "Trust" (trust account)
   - "Estate" (estate account)
   
   PARSING EXAMPLES:
   - Text: "Type: Personal" → Account_Type: "Personal"
   - Text: "TypePersonal" → Account_Type: "Personal"
   - Text: "Purpose:Consumer Type:Personal" → Account_Type: "Personal" (extract ONLY the Type value)
   - Text: "PurposeConsumer Personal" → Account_Type: "Personal" (extract ONLY "Personal", which comes after "Consumer")

3. WSFS_Account_Type: The SPECIFIC internal bank account type code or classification. Look for:
   - Specific product names like "Premier Checking", "Platinum Savings", "Gold CD", "WSFS Saving Core"
   - Internal codes or account classifications
   - Branded account names unique to the bank
   - **IMPORTANT**: This field often appears WITHOUT a header label - just the value written on the form
   - Look for bank-specific product names like "WSFS Saving Core", "WSFS Checking Plus", etc.
   - These are usually written in a specific area of the form, even without a label
   - If you see "WSFS Saving Core" or similar bank product names, extract as WSFS_Account_Type
   - This is SEPARATE from Account_Type (Personal/Business) and Account_Purpose (Consumer/Checking)

4. Ownership_Type: WHO owns the account legally. Common values:
   - "Individual" or "Single Owner" (single owner)
   - "Joint" or "Joint Owners" (multiple owners with equal rights)
   - "Joint with Rights of Survivorship"
   - "Trust" (held in trust)
   - "Estate" (estate account)
   - "Custodial" (for minor)
   - "Business" or "Corporate"
- DO NOT create a field called "Purpose" with value "Consumer Personal"
- These are ALWAYS separate fields even if they appear together on the form

🔴🔴🔴 SPECIFIC EXTRACTION PATTERNS FOR WSFS DOCUMENTS 🔴🔴🔴

**ACCOUNT HOLDER NAMES EXTRACTION:**
- Look for "Account Holder Names:" followed by names
- Look for "ACCOUNT HOLDER NAMES:" in all caps
- Names may be separated by "OR", "AND", or commas
- Example: "DANETTE EBERLY OR R BRUCE EBERLY" → Account_Holders: ["DANETTE EBERLY", "R BRUCE EBERLY"]

**ADDRESS EXTRACTION:**
- Look for "Mailing Address:" followed by complete address
- Extract the full address including street, city, state, zip
- Example: "Mailing Address: 512 PONDEROSA DR, BEAR, DE, 19701-2155"

**PHONE NUMBER EXTRACTION:**
- Look for "Home Phone:", "Work Phone:", or just phone number patterns
- Extract with proper formatting: (302) 834-0382
- May appear as handwritten numbers

🔴🔴🔴 CRITICAL BANK PRODUCT EXTRACTION 🔴🔴🔴
**WSFS PRODUCT NAMES - EXTRACT THESE IMMEDIATELY:**
- Look for "WSFS Core Savings", "WSFS Checking Plus", "WSFS Money Market", "WSFS Premier Checking"
- These appear RIGHT AFTER the account number, often on the same line or next line
- They appear WITHOUT any field label - just the product name
- **PATTERN**: "ACCOUNT NUMBER: 468869904" followed by "WSFS Core Savings" on next line
- **CRITICAL**: Extract as WSFS_Account_Type even if no label is present
- **EXAMPLE**: If you see "468869904" followed by "WSFS Core Savings" → WSFS_Account_Type: "WSFS Core Savings"

**OTHER BANK PRODUCTS TO LOOK FOR:**
- "Premier Checking", "Platinum Savings", "Gold CD", "Business Checking"
- "Money Market", "Certificate of Deposit", "IRA Savings"
- Any product name that appears near account information

**BRANCH AND STAFF EXTRACTION:**
- Look for "VERIFIED BY:", "OPENED BY:" followed by staff names
- Look for branch names like "College Square", "Main Branch"
- Extract staff names and branch locations

EXTRACTION RULES - EXTRACT EVERYTHING COMPLETELY:
- 🔴 CRITICAL: Extract EVERY field visible in the document with COMPLETE information
- 🔴 DO NOT skip any fields or partial information - extract EVERYTHING you see
- Include ALL form fields, checkboxes, dates, amounts, addresses, phone numbers, emails
- Extract ALL names, titles, positions, relationships with FULL details
- Include ALL dates (opened, closed, effective, expiration, birth dates, etc.)
- Extract COMPLETE addresses (street, city, state, zip) - not just partial
- Extract COMPLETE phone numbers with area codes
- Extract COMPLETE SSNs, license numbers, account numbers
- **IMPORTANT: Extract ALL STAMP DATES** - Look for date stamps like "DEC 26 2014", "JAN 15 2023", "MAR 21 2016", "MAR 2 5 2015", etc.
  * These often appear as standalone dates on certificates
  * May be accompanied by reference numbers like "#652", "#357"
  * Extract both the stamp date AND any associated reference numbers
- **IMPORTANT: Extract REFERENCE NUMBERS** - Look for numbers like "#298", "Ref #123", "#652", "#357", etc.
  * These often appear near stamp dates on certificates
  * Extract any number preceded by # symbol
  * Common on death certificates and other official documents
- Extract ALL identification numbers (SSN, Tax ID, License numbers, etc.)
- **CRITICAL: SEPARATE COMBINED VALUES** - If you see values combined without clear separation:
  * "PurposeConsumer Personal" → Account_Purpose: "Consumer", Account_Type: "Personal"
  * "TypeBusiness Commercial" → Account_Type: "Business", WSFS_Account_Type: "Commercial"
  * Look for capital letters in the middle of text as indicators of separate fields
  * Split combined values into their proper fields based on field definitions above
- **🔴 CRITICAL: EXTRACT WSFS PRODUCT NAMES WITHOUT HEADERS 🔴** - Look for bank product names that appear without field labels:
  * "WSFS Core Savings" (no header) → WSFS_Account_Type: "WSFS Core Savings"
  * "WSFS Checking Plus" (no header) → WSFS_Account_Type: "WSFS Checking Plus"
  * "WSFS Money Market" (no header) → WSFS_Account_Type: "WSFS Money Market"
  * "Premier Checking" (no header) → WSFS_Account_Type: "Premier Checking"
  * **PATTERN TO LOOK FOR**: Account number followed immediately by product name
  * **EXAMPLE**: "ACCOUNT NUMBER: 468869904" then "WSFS Core Savings" on next line
  * These product names are usually written RIGHT AFTER the account number
  * Extract them even if they don't have a field label like "Account Type:" or "Product:"
  * This is SEPARATE from Account_Type (Personal/Business) and Account_Purpose (Consumer/Checking)
  * **DO NOT SKIP THESE** - They are critical bank product identifiers
- Include ALL financial information (balances, limits, rates, fees)
- Extract ALL addresses (mailing, physical, business, home)
- Include ALL contact information (phone, fax, email, website)
- **CRITICAL FOR PHONE NUMBERS:** Look for patterns like "610-485-4979", "610- 485- 4979", "(302) 834-0382"
- Extract phone numbers even if they have unusual spacing or are handwritten
- Extract ALL signatures, initials, and authorization details
- **CRITICAL: Extract ALL SUPPORTING DOCUMENTS** - Look for:
  * Driver's License (with number, state, expiration)
  * Passport (with number, country)
  * OFAC checks (with date and result)
  * Background checks (with date and result)
  * Verification stamps (with date and verifier name)
  * ID verification (with type and details)
  * Any other documents mentioned or verified
- Extract ALL compliance information (OFAC, background checks, verifications)
- Include ALL checkboxes and their states (checked/unchecked, Yes/No)
- Extract ALL special instructions, notes, or comments
- **IMPORTANT: Look for STAMPS, SEALS, and WATERMARKS** - Extract any visible stamps with dates, numbers, or text
- Return ONLY valid JSON, no additional text before or after
- **CRITICAL: DO NOT include fields that are NOT present in the document**
- **CRITICAL: DO NOT use "N/A" or empty strings - ONLY include fields with actual values found in the document**
- **CRITICAL: If a field is not visible in the document, DO NOT include it in the JSON response**
- For Account_Holders: Return as array even if single name, e.g., ["John Doe"]
- 🔴🔴🔴 CRITICAL FOR SIGNERS - EXTRACT COMPLETE INFORMATION - DO NOT SKIP ANYTHING 🔴🔴🔴
  * SIGNERS ARE THE MOST IMPORTANT PART - Extract EVERY SINGLE piece of information for EACH signer
  * DO NOT skip any signer fields - extract EVERYTHING you see
  * For EACH signer, you MUST extract ALL of these fields if they are visible:
    
    SIGNER 1 - EXTRACT ALL OF THESE:
    - Signer1_Name (full name - first, middle, last)
    - Signer1_SSN (social security number - complete 9 digits)
    - Signer1_DOB (date of birth in any format)
    - Signer1_Address (COMPLETE address: street number, street name, apartment/unit, city, state, zip code)
    - Signer1_Phone (phone number with area code)
    - Signer1_Email (email address)
    - Signer1_Drivers_License (driver's license number AND state)
    - Signer1_Drivers_License_Expiration (expiration date if shown)
    - Signer1_Citizenship (citizenship status: US Citizen, Permanent Resident, etc.)
    - Signer1_Occupation (job title or occupation)
    - Signer1_Employer (employer name and address if shown)
    - Signer1_Employer_Phone (employer phone if shown)
    - Signer1_Mothers_Maiden_Name (if shown)
    - Signer1_Relationship (relationship to account: Owner, Joint Owner, etc.)
    - Signer1_Signature (if signature is present, note "Signed" or "Signature present")
    - Signer1_Signature_Date (date of signature if shown)
    - ANY other signer-specific information you see
    
    SIGNER 2 - EXTRACT ALL OF THESE (if second signer exists):
    - Signer2_Name, Signer2_SSN, Signer2_DOB, Signer2_Address, Signer2_Phone, Signer2_Email
    - Signer2_Drivers_License, Signer2_Drivers_License_Expiration, Signer2_Citizenship
    - Signer2_Occupation, Signer2_Employer, Signer2_Employer_Phone
    - Signer2_Mothers_Maiden_Name, Signer2_Relationship, Signer2_Signature, Signer2_Signature_Date
    - ANY other information for signer 2
    
    SIGNER 3+ - Continue with Signer3_, Signer4_, etc. if more signers exist
  
  * 🔴 CRITICAL RULES FOR SIGNERS:
    - DO NOT USE NESTED OBJECTS - Use FLAT fields with underscore naming
    - WRONG ❌: "Signer1": {"Name": "John", "SSN": "123"}
    - CORRECT ✅: "Signer1_Name": "John", "Signer1_SSN": "123"
    - Extract COMPLETE addresses - not just street, include city, state, zip
    - Extract COMPLETE phone numbers - include area code
    - Extract COMPLETE SSNs - all 9 digits
    - If a signer field is visible, YOU MUST EXTRACT IT - do not skip anything
    - Look in ALL sections of the document for signer information (may be in multiple places)
    
  * 🔴🔴🔴 REMINDER: SIGNERS ARE THE MOST IMPORTANT PART 🔴🔴🔴
    - Extract EVERY field for EVERY signer
    - Do NOT be conservative - extract ALL information you see
    - Missing signer information is a CRITICAL ERROR
    - If you see a signer's name, you MUST extract ALL their other information too
- For Supporting_Documents: Create separate objects for EACH document type found
- Preserve exact account numbers and SSNs as they appear
- If you see multiple account types mentioned, use the most specific one
- Look carefully at the entire document text for ALL fields
- Pay special attention to compliance sections, checkboxes, verification stamps, and date stamps
- **REMEMBER: Only extract what you can SEE in the document. Do not invent or assume fields.**

EXAMPLES OF CORRECT FIELD SEPARATION:

Example 1: Document shows "Purpose: Consumer" and "Type: Personal"
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal"
}

Example 2: Document shows "Purpose: Consumer", "Type: Personal", and "WSFS Saving Core" (no header for WSFS)
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal",
  "WSFS_Account_Type": "WSFS Saving Core"
}

Example 3: Document shows combined text "PurposeConsumer Personal" (NO SPACES)
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal"
}

Example 4: Document shows "Purpose: Consumer Type: Business" and also has "WSFS Checking Plus" written somewhere
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Business",
  "WSFS_Account_Type": "WSFS Checking Plus"
}

Example 5: Document says "Premier Checking Account for Business Operations, Consumer Banking"
{
  "Account_Type": "Business",
  "WSFS_Account_Type": "Premier Checking",
  "Account_Purpose": "Consumer"
}

Example 6: Document says "Personal IRA Savings Account"
{
  "Account_Type": "Personal",
  "WSFS_Account_Type": "IRA Savings",
  "Account_Purpose": "Retirement"
}

❌ WRONG: DO NOT combine them like this: {"Purpose": "Consumer Personal"}
✅ CORRECT: Always separate: {"Account_Purpose": "Consumer", "Account_Type": "Personal", "WSFS_Account_Type": "WSFS Saving Core"}

Example 4: Supporting_Documents with OFAC check and verification
{
  "Supporting_Documents": [
    {
      "Type": "Driver's License",
      "Details": "DE #1234567, Expires: 12/03/2020"
    },
    {
      "Type": "OFAC Check",
      "Details": "Completed on 3/18/2016 - No match found"
    },
    {
      "Type": "Background Check",
      "Details": "Verified by Sara Halttunen on 12/24/2014"
    },
    {
      "Type": "ID Verification",
      "Details": "Drivers License #9243231 verified"
    }
  ]
}

Example 5: Multiple supporting documents
{
  "Supporting_Documents": [
    {
      "Type": "Driver's License",
      "Details": "State: DE, Number: 719077, Issued: 12-03-2012, Expires: 12-03-2020"
    },
    {
      "Type": "OFAC Screening",
      "Details": "Date: 12/24/2014, Result: No match found, Verified by: System"
    },
    {
      "DocumentType": "Signature Verification",
      "Details": "Verified on 12/24/2014 by branch staff"
    }
  ]
}

Example 6: Multiple signers (CORRECT FORMAT - FLAT fields, NOT nested objects)
{
  "AccountNumber": "468869904",
  "AccountType": "Personal",
  "DateOpened": "12/24/2014",
  "Signer1_Name": "Danette Eberly",
  "Signer1_SSN": "222-50-2263",
  "Signer1_DateOfBirth": "12/3/1956",
  "Signer1_Address": "512 PONDEROSA DR, BEAR, DE, 19701-2155",
  "Signer1_Phone": "(302) 834-0382",
  "Signer1_DriversLicense": "719077",
  "Signer2_Name": "R Bruce Eberly",
  "Signer2_SSN": "199400336",
  "Signer2_DateOfBirth": "11/17/1949",
  "Signer2_Address": "512 PONDEROSA DR, BEAR, DE, 19701-2155",
  "Signer2_Phone": "(302) 834-0382",
  "Signer2_DriversLicense": "651782"
}

WRONG FORMAT (DO NOT USE):
{
  "Signer1": {
    "Name": "Danette Eberly",
    "SSN": "222-50-2263"
  }
}

CORRECT FORMAT (USE THIS):
{
  "Signer1_Name": "Danette Eberly",
  "Signer1_SSN": "222-50-2263"
}

RETURN FORMAT WITH CONFIDENCE SCORES:
Return JSON where each field has both a value and confidence score (0-100):

{
  "Account_Number": {
    "value": "0210630620",
    "confidence": 95
  },
  "Signer1_Name": {
    "value": "John Doe",
    "confidence": 90
  },
  "Signer1_SSN": {
    "value": "123-45-6789",
    "confidence": 85
  }
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL RULES:
1. ONLY extract fields that are VISIBLE in the document
2. DO NOT include fields with "N/A" or empty values
3. For multiple signers, use Signer1_, Signer2_, Signer3_ prefixes
4. Each signer's information should be separate fields, not nested objects
5. Every field MUST have both "value" and "confidence"

🔴 FINAL REMINDER - DO NOT FORGET 🔴
Account_Purpose and Account_Type are ALWAYS TWO SEPARATE FIELDS!
NEVER combine them like "Account_Purpose": "Consumer Personal"
ALWAYS separate: "Account_Purpose": "Consumer", "Account_Type": "Personal"
"""

# Supported Document Types with Expected Fields
SUPPORTED_DOCUMENT_TYPES = {
    "marriage_certificate": {
        "name": "Marriage Certificate",
        "icon": "💍",
        "description": "Official marriage registration document",
        "expected_fields": ["bride_name", "groom_name", "marriage_date", "location", "certificate_number", "county", "state", "officiant", "witness_names"],
        "keywords": ["marriage", "bride", "groom", "matrimony", "wedding", "spouse"]
    },
    "death_certificate": {
        "name": "Death Certificate",
        "icon": "📜",
        "description": "Official death registration document",
        "expected_fields": ["deceased_name", "date_of_death", "place_of_death", "cause_of_death", "certificate_number", "account_number", "age", "date_of_birth", "social_security_number", "state_file_number", "registrar", "date_pronounced_dead", "time_of_death", "manner_of_death", "license_number_for"],
        "keywords": ["death", "deceased", "decedent", "demise", "passed away", "mortality", "certification of vital record", "certificate of death", "local registrar"]
    },
    "business_card": {
        "name": "Business Card / Card Order Form",
        "icon": "💼",
        "description": "Professional contact information or card order form",
        "expected_fields": ["company_name", "contact_name", "job_title", "phone", "email", "address", "website", "card_details", "authorization"],
        "keywords": ["business card", "company", "phone", "email", "contact", "card order form", "business details", "mailing details", "atm", "debit card", "card request"]
    },
    "invoice": {
        "name": "Invoice / Withdrawal Form",
        "icon": "🧾",
        "description": "Payment request or withdrawal document",
        "expected_fields": ["invoice_number", "vendor_name", "customer_name", "invoice_date", "due_date", "total_amount", "items", "tax", "payment_terms", "account_number", "withdrawal_amount"],
        "keywords": ["invoice", "bill", "payment", "amount due", "total", "vendor", "withdrawal", "funeral", "statement", "charges", "services"]
    },
    "loan_document": {
        "name": "Loan/Account Document",
        "icon": "🏦",
        "description": "Banking or loan account information",
        "expected_fields": ["account_number", "account_holder_names", "account_type", "ownership_type", "ssn", "signers", "balance", "interest_rate"],
        "keywords": ["account", "loan", "bank", "balance", "account holder", "signature", "banking", "account number", "account documentation", "bank account", "checking", "savings", "deposit", "financial institution", "account opening", "account information", "signer", "ownership", "wsfs", "consumer", "business account", "account type", "ownership type", "account purpose", "wsfs account type", "account holder names", "signature card", "joint account"]
    },
    "drivers_license": {
        "name": "Driver's License / ID Card",
        "icon": "🪪",
        "description": "Government-issued identification",
        "expected_fields": ["full_name", "license_number", "date_of_birth", "address", "issue_date", "expiration_date", "state", "class", "height", "weight", "eye_color"],
        "keywords": ["driver", "license", "identification", "ID", "DMV", "driver's license", "drivers license", "id card", "identification card"]
    },
    "passport": {
        "name": "Passport",
        "icon": "🛂",
        "description": "International travel document",
        "expected_fields": ["full_name", "passport_number", "nationality", "date_of_birth", "place_of_birth", "issue_date", "expiration_date", "sex"],
        "keywords": ["passport", "travel document", "nationality", "immigration"]
    },
    "contract": {
        "name": "Contract/Legal Document",
        "icon": "📝",
        "description": "Legal agreement or official document",
        "expected_fields": ["contract_title", "parties", "effective_date", "expiration_date", "terms", "signatures", "contract_number", "estate_name", "decedent_name", "executor"],
        "keywords": ["contract", "agreement", "parties", "terms", "conditions", "hereby", "register of wills", "letters testamentary", "letters of administration", "affidavit", "small estate", "name change", "tax id change", "tin change"]
    },
    "receipt": {
        "name": "Receipt",
        "icon": "🧾",
        "description": "Proof of purchase",
        "expected_fields": ["merchant_name", "date", "time", "items", "total_amount", "payment_method", "transaction_id"],
        "keywords": ["receipt", "purchase", "transaction", "paid", "merchant"]
    },
    "tax_form": {
        "name": "Tax Form",
        "icon": "📋",
        "description": "Tax-related document",
        "expected_fields": ["form_type", "tax_year", "taxpayer_name", "ssn", "income", "deductions", "tax_owed", "refund"],
        "keywords": ["tax", "IRS", "W-2", "1099", "return", "federal", "tax identification"]
    },
    "medical_record": {
        "name": "Medical Record",
        "icon": "🏥",
        "description": "Healthcare document",
        "expected_fields": ["patient_name", "date_of_birth", "medical_record_number", "date_of_service", "diagnosis", "treatment", "provider_name"],
        "keywords": ["patient", "medical", "diagnosis", "treatment", "doctor", "hospital"]
    },
    "insurance_policy": {
        "name": "Insurance Policy",
        "icon": "🛡️",
        "description": "Insurance coverage document",
        "expected_fields": ["policy_number", "policyholder_name", "coverage_type", "effective_date", "expiration_date", "premium", "coverage_amount"],
        "keywords": ["insurance", "policy", "coverage", "premium", "insured", "beneficiary"]
    }
}

# Persistent storage for processed documents
DOCUMENTS_DB_FILE = "processed_documents.json"

def load_documents_db():
    """Load processed documents from file"""
    if os.path.exists(DOCUMENTS_DB_FILE):
        with open(DOCUMENTS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_documents_db(documents):
    """Save processed documents to file"""
    with open(DOCUMENTS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(documents, indent=2, fp=f)

# Load existing documents on startup
processed_documents = load_documents_db()


def parse_combined_ocr_fields(text):
    """
    Parse combined OCR text that reads form labels and values together without spaces
    Examples: "PurposeConsumer Personal" → Account_Purpose: "Consumer", Account_Category: "Personal"
    """
    results = {}
    print(f"[PARSE_COMBINED] Input text: '{text}'")
    
    # CRITICAL: Handle the exact case the user is experiencing
    # "Purpose Consumer Personal" → Account_Purpose: "Consumer", Account_Category: "Personal"
    if "Purpose Consumer Personal" in text:
        print(f"[PARSE_COMBINED] Found 'Purpose Consumer Personal' pattern - EXACT USER CASE")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Personal"
        return results
    
    # Handle "Consumer Personal" pattern (space-separated)
    if "Consumer Personal" in text:
        print(f"[PARSE_COMBINED] Found 'Consumer Personal' pattern")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Personal"
        return results
    elif "Consumer Business" in text:
        print(f"[PARSE_COMBINED] Found 'Consumer Business' pattern")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Business"
        return results
    
    # Handle Purpose + Type combinations (no spaces)
    if "PurposeConsumer" in text:
        print(f"[PARSE_COMBINED] Found 'PurposeConsumer' pattern")
        results["Account_Purpose"] = "Consumer"
        # Check what comes after Consumer
        if "Personal" in text:
            results["Account_Category"] = "Personal"
            print(f"[PARSE_COMBINED] Also found 'Personal'")
        elif "Business" in text:
            results["Account_Category"] = "Business"
            print(f"[PARSE_COMBINED] Also found 'Business'")
    
    # Handle other Purpose types
    if "PurposeChecking" in text:
        print(f"[PARSE_COMBINED] Found 'PurposeChecking' pattern")
        results["Account_Purpose"] = "Checking"
    elif "PurposeSavings" in text:
        print(f"[PARSE_COMBINED] Found 'PurposeSavings' pattern")
        results["Account_Purpose"] = "Savings"
    
    # Handle Type patterns
    if "TypePersonal" in text:
        print(f"[PARSE_COMBINED] Found 'TypePersonal' pattern")
        results["Account_Category"] = "Personal"
    elif "TypeBusiness" in text:
        print(f"[PARSE_COMBINED] Found 'TypeBusiness' pattern")
        results["Account_Category"] = "Business"
    
    # Handle Ownership patterns
    if "OwnershipJoint" in text:
        print(f"[PARSE_COMBINED] Found 'OwnershipJoint' pattern")
        results["Ownership_Type"] = "Joint"
    elif "OwnershipIndividual" in text:
        print(f"[PARSE_COMBINED] Found 'OwnershipIndividual' pattern")
        results["Ownership_Type"] = "Individual"
    
    print(f"[PARSE_COMBINED] Results: {results}")
    return results


def extract_wsfs_product_from_text(text):
    """
    Extract WSFS product names from raw OCR text as a fallback
    """
    if not isinstance(text, str):
        return None
    
    # Common WSFS product patterns
    wsfs_products = [
        "WSFS Core Savings",
        "WSFS Checking Plus", 
        "WSFS Money Market",
        "WSFS Premier Checking",
        "Premier Checking",
        "Platinum Savings",
        "Gold CD",
        "Business Checking",
        "Money Market Account",
        "Certificate of Deposit"
    ]
    
    # Look for product names in the text
    for product in wsfs_products:
        if product in text:
            print(f"[WSFS_EXTRACT] Found product in text: {product}")
            return product
    
    return None


def ensure_consistent_field_structure(data, original_text=None):
    """
    Ensure consistent field structure by standardizing field names and values
    This is called after normalization to guarantee consistency
    """
    if not isinstance(data, dict):
        return data
    
    print(f"[CONSISTENCY] Input data: {data}")
    
    # Standard field mappings for loan documents
    standard_fields = {
        "Account_Number": None,
        "Account_Holders": None,
        "Account_Purpose": None,
        "Account_Category": None,
        "Account_Type": None,  # Keep for backward compatibility
        "WSFS_Account_Type": None,
        "Ownership_Type": None,
        "Address": None,
        "Phone_Number": None,
        "Work_Phone": None,
        "Date_Opened": None,
        "Date_Revised": None,
        "CIF_Number": None,
        "Branch": None,
        "Verified_By": None,
        "Opened_By": None,
        "Signatures_Required": None,
        "Special_Instructions": None,
        "Form_Number": None,
        "Reference_Number": None,
        "Stamp_Date": None,
        "Signer1_Name": None,
        "Signer1_SSN": None,
        "Signer1_DOB": None,
        "Signer1_Address": None,
        "Signer1_Phone": None,
        "Signer1_DriversLicense": None,
        "Signer2_Name": None,
        "Signer2_SSN": None,
        "Signer2_DOB": None,
        "Signer2_Address": None,
        "Signer2_Phone": None,
        "Signer2_DriversLicense": None
    }
    
    # Copy existing fields
    result = {}
    for key, value in data.items():
        # Skip empty values
        if value == "" or value is None:
            continue
        result[key] = value
    
    # Ensure we have the critical separated fields
    if "Account_Purpose" not in result and "Account_Category" not in result:
        # Look for any field that might contain combined values
        for key, value in result.items():
            actual_value = value
            if isinstance(value, dict) and "value" in value:
                actual_value = value["value"]
            
            if isinstance(actual_value, str):
                confidence_score = value.get("confidence", 100) if isinstance(value, dict) else 100
                
                if "Consumer Personal" in actual_value:
                    result["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
                    result["Account_Category"] = {"value": "Personal", "confidence": confidence_score}
                    # Remove the combined field
                    if key in ["Purpose", "Type", "Account_Type"]:
                        del result[key]
                    break
                elif "Consumer Business" in actual_value:
                    result["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
                    result["Account_Category"] = {"value": "Business", "confidence": confidence_score}
                    # Remove the combined field
                    if key in ["Purpose", "Type", "Account_Type"]:
                        del result[key]
                    break
    
    # CRITICAL: Try to extract WSFS product type if missing
    if "WSFS_Account_Type" not in result and original_text:
        wsfs_product = extract_wsfs_product_from_text(original_text)
        if wsfs_product:
            result["WSFS_Account_Type"] = {"value": wsfs_product, "confidence": 85}
            print(f"[CONSISTENCY] Added missing WSFS product: {wsfs_product}")
    
    print(f"[CONSISTENCY] Final result: {result}")
    return result


def normalize_extraction_result(data):
    """
    Normalize extraction results to ensure consistency across different extractions
    """
    if not data or not isinstance(data, dict):
        return data
    
    print(f"[NORMALIZE] Input data: {data}")
    normalized = {}
    
    # Field name mappings to standardize variations
    field_mappings = {
        # Address variations
        "Mailing_Address": "Address",
        "mailing_address": "Address", 
        "Street_Address": "Address",
        
        # Signature variations  
        "Required_Signatures": "Signatures_Required",
        "required_signatures": "Signatures_Required",
        "Signature_Required": "Signatures_Required",
        "Number_of_Signatures_Required": "Signatures_Required",
        
        # Phone variations - normalize format
        "phone_number": "Phone_Number",
        "contact_phone": "Phone_Number",
        "Home_Phone": "Phone_Number",
        "home_phone": "Phone_Number",
        
        # Account category
        "account_category": "Account_Category",
        "AccountCategory": "Account_Category",
        
        # Account holder variations
        "Account_Holder_Names": "Account_Holders",
        "account_holder_names": "Account_Holders",
        "AccountHolderNames": "Account_Holders",
        
        # CIF variations
        "CIF_Number": "CIF_Number",
        "cif_number": "CIF_Number",
        "CIFNumber": "CIF_Number",
        
        # Date variations
        "Date_Opened": "Date_Opened",
        "date_opened": "Date_Opened",
        "DateOpened": "Date_Opened",
        
        # Verification variations
        "Verified_By": "Verified_By",
        "verified_by": "Verified_By",
        "VerifiedBy": "Verified_By"
    }
    
    # Process each field
    for key, value in data.items():
        print(f"[NORMALIZE] Processing field: {key} = {value}")
        
        # CRITICAL: Handle confidence objects first
        actual_value = value
        confidence_score = 100  # Default confidence
        is_confidence_object = False
        
        if isinstance(value, dict) and "value" in value:
            actual_value = value["value"]
            confidence_score = value.get("confidence", 100)
            is_confidence_object = True
            print(f"[NORMALIZE] Extracted value from confidence object: {actual_value} (confidence: {confidence_score})")
        
        # CRITICAL FIX: Handle specific field names with combined values
        if key in ["Purpose", "Account_Purpose", "AccountPurpose"] and isinstance(actual_value, str):
            print(f"[NORMALIZE] Found Purpose field: {key} = {actual_value}")
            if "Consumer Personal" in actual_value:
                print(f"[NORMALIZE] Parsing 'Consumer Personal' into separate fields")
                normalized["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
                normalized["Account_Category"] = {"value": "Personal", "confidence": confidence_score}
                continue
            elif "Consumer Business" in actual_value:
                print(f"[NORMALIZE] Parsing 'Consumer Business' into separate fields")
                normalized["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
                normalized["Account_Category"] = {"value": "Business", "confidence": confidence_score}
                continue
            elif "Consumer" in actual_value:
                print(f"[NORMALIZE] Found Consumer, checking for additional category")
                normalized["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
                # Try to extract category from remaining text
                remaining = actual_value.replace("Consumer", "").strip()
                print(f"[NORMALIZE] Remaining text after removing 'Consumer': '{remaining}'")
                if remaining:
                    if "Personal" in remaining:
                        normalized["Account_Category"] = {"value": "Personal", "confidence": confidence_score}
                        print(f"[NORMALIZE] Found Personal in remaining text")
                    elif "Business" in remaining:
                        normalized["Account_Category"] = {"value": "Business", "confidence": confidence_score}
                        print(f"[NORMALIZE] Found Business in remaining text")
                continue
        
        # Handle Type field variations - map to Account_Category for consistency
        if key in ["Type", "Account_Type", "AccountType", "Account_Category", "AccountCategory"] and isinstance(actual_value, str):
            print(f"[NORMALIZE] Found Type/Category field: {key} = {actual_value}")
            if "Personal" in actual_value and "Consumer" not in actual_value:
                normalized["Account_Category"] = {"value": "Personal", "confidence": confidence_score}
                continue
            elif "Business" in actual_value and "Consumer" not in actual_value:
                normalized["Account_Category"] = {"value": "Business", "confidence": confidence_score}
                continue
            else:
                # If it's already Account_Type, map it to Account_Category for consistency
                if key in ["Account_Type", "AccountType"]:
                    normalized["Account_Category"] = {"value": actual_value, "confidence": confidence_score}
                else:
                    normalized["Account_Category"] = {"value": actual_value, "confidence": confidence_score}
                continue
        
        # CRITICAL FIX: Handle combined OCR field names and values
        combined_text = f"{key} {actual_value}" if isinstance(actual_value, str) else key
        parsed_fields = parse_combined_ocr_fields(combined_text)
        
        # If we parsed combined fields, add them and skip the original
        if parsed_fields:
            print(f"[NORMALIZE] Parsed combined fields: {parsed_fields}")
            normalized.update(parsed_fields)
            continue
        
        # Apply field name mapping
        normalized_key = field_mappings.get(key, key)
        
        # Normalize phone number format
        if "phone" in normalized_key.lower() and isinstance(actual_value, str):
            # Remove extra formatting and standardize
            phone = actual_value.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
            if len(phone) == 10:
                actual_value = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
        
        print(f"[NORMALIZE] Adding field: {normalized_key} = {actual_value}")
        # Preserve confidence format
        if is_confidence_object or confidence_score != 100:
            normalized[normalized_key] = {"value": actual_value, "confidence": confidence_score}
        else:
            normalized[normalized_key] = actual_value
    
    # Ensure consistent field ordering
    ordered_fields = {}
    field_order = [
        "Account_Number", "Account_Category", "Account_Purpose", "Account_Type", 
        "Address", "Phone_Number", "Branch", "CIF_Number", "Date_Opened",
        "Form_Number", "Ownership_Type", "Signatures_Required", "Reference_Number",
        "Stamp_Date", "Verified_By", "Signer1_Name", "Signer1_SSN", "Signer1_DOB",
        "Signer1_DriversLicense", "Signer2_Name", "Signer2_SSN", "Signer2_DOB", 
        "Signer2_DriversLicense"
    ]
    
    # Add fields in preferred order
    for field in field_order:
        if field in normalized:
            ordered_fields[field] = normalized[field]
    
    # Add any remaining fields
    for key, value in normalized.items():
        if key not in ordered_fields:
            ordered_fields[key] = value
    
    # FINAL CLEANUP: Handle any remaining combined values that slipped through
    final_cleaned = {}
    for key, value in ordered_fields.items():
        # Extract actual value from confidence objects
        actual_value = value
        if isinstance(value, dict) and "value" in value:
            actual_value = value["value"]
        
        # Skip fields that contain combined values we should have parsed
        if isinstance(actual_value, str) and ("Consumer Personal" in actual_value or "Consumer Business" in actual_value):
            # These should have been parsed into separate fields already
            print(f"[NORMALIZE] Skipping combined field that should have been parsed: {key} = {actual_value}")
            continue
        final_cleaned[key] = value
    
    # Ensure we have the essential separated fields
    if "Account_Purpose" not in final_cleaned and "Account_Category" not in final_cleaned:
        # Look for any field that might contain the combined value
        for key, value in ordered_fields.items():
            actual_value = value
            if isinstance(value, dict) and "value" in value:
                actual_value = value["value"]
                
            if isinstance(actual_value, str) and "Consumer Personal" in actual_value:
                print(f"[NORMALIZE] Emergency parsing of combined field: {key} = {actual_value}")
                final_cleaned["Account_Purpose"] = "Consumer"
                final_cleaned["Account_Category"] = "Personal"
                break
            elif isinstance(actual_value, str) and "Consumer Business" in actual_value:
                print(f"[NORMALIZE] Emergency parsing of combined field: {key} = {actual_value}")
                final_cleaned["Account_Purpose"] = "Consumer"
                final_cleaned["Account_Category"] = "Business"
                break
    
    # FINAL SAFETY CHECK: Ensure no combined "Consumer Personal" fields remain
    safety_checked = {}
    for key, value in final_cleaned.items():
        # Extract actual value from confidence objects
        actual_value = value
        confidence_score = 100
        
        if isinstance(value, dict) and "value" in value:
            actual_value = value["value"]
            confidence_score = value.get("confidence", 100)
        
        # If we find ANY field with "Consumer Personal", force split it
        if isinstance(actual_value, str) and "Consumer Personal" in actual_value:
            print(f"[NORMALIZE] SAFETY CHECK: Found remaining combined field {key} = {actual_value}")
            # Don't add this field, instead add the split fields
            if "Account_Purpose" not in safety_checked:
                safety_checked["Account_Purpose"] = {"value": "Consumer", "confidence": confidence_score}
            if "Account_Category" not in safety_checked:
                safety_checked["Account_Category"] = {"value": "Personal", "confidence": confidence_score}
            print(f"[NORMALIZE] SAFETY CHECK: Forced split into Account_Purpose=Consumer, Account_Category=Personal")
        else:
            safety_checked[key] = value
    
    print(f"[NORMALIZE] Final output after safety check: {safety_checked}")
    return safety_checked


def normalize_confidence_format(data):
    """
    Normalize data to separate values and confidence scores.
    Input: {"Field": {"value": "text", "confidence": 95}}
    Output: ({"Field": "text"}, {"Field": 95})
    """
    if not isinstance(data, dict):
        return data, {}
    
    values = {}
    confidences = {}
    
    for key, value in data.items():
        if isinstance(value, dict) and "value" in value and "confidence" in value:
            # New format with confidence scores
            values[key] = value["value"]
            confidences[key] = value["confidence"]
        elif isinstance(value, dict) and "value" in value:
            # Has value but no confidence
            values[key] = value["value"]
            confidences[key] = 100  # Default to 100 if not specified
        else:
            # Old format without confidence scores
            values[key] = value
            confidences[key] = 100  # Default to 100 for backward compatibility
    
    return values, confidences


def is_confidence_object(obj):
    """Check if an object is a confidence object {value: X, confidence: Y}"""
    return (isinstance(obj, dict) and 
            "value" in obj and 
            "confidence" in obj and 
            len(obj) == 2)

def flatten_nested_objects(data):
    """
    Flatten nested objects like Signer1: {Name: "John"} to Signer1_Name: "John"
    Also handles arrays of signer objects and other nested structures
    CRITICAL: Preserves confidence objects {value: X, confidence: Y} at all levels
    """
    if not isinstance(data, dict):
        return data
    
    flattened = {}
    
    for key, value in data.items():
        # FIRST: Check if this value itself is a confidence object
        if is_confidence_object(value):
            flattened[key] = value
            print(f"[DEBUG] Preserved top-level confidence object: {key}")
            continue
        
        # Check if this is a signer object (Signer1, Signer2, etc.)
        if (key.startswith("Signer") and isinstance(value, dict) and 
            any(char.isdigit() for char in key)):
            # Flatten the signer object
            print(f"[DEBUG] Flattening signer object: {key} with {len(value)} fields")
            for sub_key, sub_value in value.items():
                flat_key = f"{key}_{sub_key}"
                # Preserve confidence objects
                if is_confidence_object(sub_value):
                    flattened[flat_key] = sub_value
                    print(f"[DEBUG] Preserved signer confidence: {flat_key}")
                else:
                    flattened[flat_key] = sub_value
                    print(f"[DEBUG] Flattened signer field: {flat_key}")
            continue
        
        # Handle arrays of signer objects
        if isinstance(value, list) and len(value) > 0:
            key_lower = key.lower().replace('_', '').replace(' ', '')
            is_signer_array = any(keyword in key_lower for keyword in ['signer', 'signature', 'accountholder'])
            first_item = value[0]
            is_object_array = isinstance(first_item, dict)
            
            if is_object_array and is_signer_array:
                print(f"[DEBUG] Found signer array '{key}' with {len(value)} signers")
                for idx, signer_obj in enumerate(value):
                    signer_num = idx + 1
                    for sub_key, sub_value in signer_obj.items():
                        flat_key = f"Signer{signer_num}_{sub_key}"
                        # Preserve confidence objects
                        if is_confidence_object(sub_value):
                            flattened[flat_key] = sub_value
                            print(f"[DEBUG] Preserved array signer confidence: {flat_key}")
                        else:
                            flattened[flat_key] = sub_value
                continue
            else:
                # Keep other arrays as-is
                flattened[key] = value
                continue
        
        # Keep primitives as-is
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[key] = value
            continue
        
        # Handle nested dicts
        if isinstance(value, dict):
            # Check if it's a special structure to preserve
            if key in ["SupportingDocuments", "AccountHolderNames", "Supporting_Documents", "Account_Holders"]:
                flattened[key] = value
                continue
            
            # Flatten other nested objects
            for sub_key, sub_value in value.items():
                flat_key = f"{key}_{sub_key}"
                # Preserve confidence objects at nested level
                if is_confidence_object(sub_value):
                    flattened[flat_key] = sub_value
                    print(f"[DEBUG] Preserved nested confidence: {flat_key}")
                else:
                    flattened[flat_key] = sub_value
            continue
        
        # Default: keep as-is
        flattened[key] = value
    
    print(f"[DEBUG] Flattening complete: {len(data)} input fields -> {len(flattened)} output fields")
    return flattened


def call_bedrock(prompt: str, text: str, max_tokens: int = 8192):
    """Call AWS Bedrock with Claude - using maximum token limit"""
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": f"{prompt}\n\n{text}"}]}
        ],
    }
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(payload))
    return json.loads(resp["body"].read())["content"][0]["text"]


def extract_basic_fields(text: str, num_fields: int = 100):
    """Extract ALL fields from any document (up to 100 fields) - BE THOROUGH"""
    # USE THE SAME PROMPT AS get_comprehensive_extraction_prompt() FOR CONSISTENCY
    prompt = get_comprehensive_extraction_prompt()
    
    try:
        # Ensure consistent text input by comprehensive normalization
        def normalize_text_for_consistency(text):
            """Normalize text to ensure identical processing regardless of source"""
            # Remove extra whitespace and normalize line endings
            text = re.sub(r'\r\n', '\n', text)  # Normalize line endings
            text = re.sub(r'\r', '\n', text)    # Handle old Mac line endings
            text = re.sub(r'\n+', '\n', text)   # Remove multiple consecutive newlines
            text = re.sub(r'[ \t]+', ' ', text) # Normalize spaces and tabs
            text = text.strip()                 # Remove leading/trailing whitespace
            return text
        
        normalized_text = normalize_text_for_consistency(text)[:10000]  # Consistent truncation
        
        # Create a deterministic prompt hash to ensure consistency
        import hashlib
        # Use a stable prompt identifier + normalized text for hashing
        prompt_stable = prompt.replace(str(num_fields), "NUM_FIELDS")  # Remove dynamic numbers
        text_hash = hashlib.md5(f"{prompt_stable[:200]}{normalized_text}".encode()).hexdigest()
        print(f"[EXTRACT_BASIC] Input hash: {text_hash[:8]} (for consistency tracking)")
        
        # Check if we have a cached result for this exact input
        cache_key = f"extraction_cache/{text_hash}.json"
        try:
            cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_data = json.loads(cached_result['Body'].read())
            print(f"[EXTRACT_BASIC] ✓ Using cached result (hash: {text_hash[:8]}) - GUARANTEED CONSISTENT")
            return cached_data
        except:
            print(f"[EXTRACT_BASIC] No cache found, extracting fresh (hash: {text_hash[:8]}) - WILL CACHE FOR CONSISTENCY")
        
        response = call_bedrock(prompt, normalized_text, max_tokens=8192)  # Use maximum tokens for comprehensive extraction
        
        # Find JSON content
        json_start = response.find('{')
        json_end = response.rfind('}')
        
        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON object found in response")
        
        json_str = response[json_start:json_end + 1]
        result = json.loads(json_str)
        
        # Log the number of fields extracted for consistency tracking
        field_count = len(result) if result else 0
        print(f"[EXTRACT_BASIC] ✓ Extracted {field_count} fields (hash: {text_hash[:8]})")
        
        # Cache the result for future consistency
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(result),
                ContentType='application/json'
            )
            print(f"[EXTRACT_BASIC] ✓ Cached result for future consistency")
        except Exception as cache_error:
            print(f"[EXTRACT_BASIC] ⚠️ Failed to cache result: {cache_error}")
        
        # Ensure we have at least some fields
        if not result or len(result) == 0:
            return {"document_content": "Unable to extract structured fields"}
        
        return result
    except Exception as e:
        return {
            "error": str(e),
            "note": "Failed to extract structured fields from document"
        }


def detect_and_extract_documents(text: str):
    """
    Dynamically detect document types and extract relevant fields
    AI decides what fields to extract based on document type
    """
    # First detect document type
    doc_type = detect_document_type(text)
    doc_info = SUPPORTED_DOCUMENT_TYPES.get(doc_type, {
        "name": "Unknown Document",
        "icon": "📄",
        "description": "Unidentified document type",
        "expected_fields": []
    })
    
    # Use specialized prompts for specific document types
    if doc_type == "drivers_license":
        # Use specialized driver's license prompt
        prompt = get_drivers_license_prompt()
    elif doc_type == "loan_document":
        # Use specialized loan document prompt
        prompt = get_loan_document_prompt()
    else:
        # Build extraction prompt based on document type
        if doc_type != "unknown" and doc_info.get("expected_fields"):
            expected_fields_str = ", ".join(doc_info["expected_fields"])
            field_instructions = f"""
This is a {doc_info['name']}.
Extract ALL of these fields if present: {expected_fields_str}

Also extract any other relevant information you find in the document.
"""
        else:
            field_instructions = f"""
This appears to be a {doc_info['name']}.
Extract all relevant fields you can identify from the document.
"""
        
        prompt = f"""
{field_instructions}

YOU ARE A METICULOUS DATA EXTRACTION EXPERT. YOUR GOAL IS TO EXTRACT ABSOLUTELY EVERYTHING FROM THIS DOCUMENT.

CRITICAL: Use SIMPLE, SHORT field names. Do NOT copy the entire label text from the document.
- Example: "DATE PRONOUNCED DEAD" → use "Death_Date" (NOT "Date_Pronounced_Dead")
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "Account_Holder_Names")
- Example: "DATE OF ISSUE" → use "Issue_Date" (NOT "Date_Of_Issue")
- Simplify all verbose labels to their core meaning

CRITICAL EXTRACTION RULES - EXTRACT EVERYTHING:
1. ALL IDENTIFYING NUMBERS:
   - Certificate numbers, file numbers, case numbers, reference numbers
   - License numbers, registration numbers, document numbers
   - Social security numbers, tax IDs, account numbers
   - ANY number with a label or identifier (K1-0000608, K1-0011267, etc.)

2. ALL DATES AND TIMES:
   - Issue dates, filing dates, registration dates, effective dates
   - Birth dates, death dates, marriage dates, expiration dates
   - Timestamps (22:29, 14:30, etc.)
   - Date stamps (01/09/2016, January 9, 2016, etc.)
   - Extract in ORIGINAL format as shown

3. ALL NAMES:
   - Full names, first names, middle names, last names, maiden names
   - Witness names, registrar names, physician names, funeral director names
   - Father's name, mother's name, spouse's name
   - Informant names, certifier names, pronouncer names
   - ANY person's name mentioned ANYWHERE in the document

4. ALL LOCATIONS:
   - Cities, towns, townships, counties, states, countries
   - Place of birth, place of death, place of marriage, place of residence
   - Street addresses with house numbers, apartment numbers
   - Zip codes, postal codes
   - Hospital names, facility names, institution names

5. ALL FORM FIELDS WITH LABELS:
   - Look for patterns like "FIELD_NAME: value" or "FIELD_NAME value"
   - Extract checkbox fields (checked/unchecked, Yes/No)
   - Extract dropdown selections
   - Extract text fields, even if partially filled
   - Extract signature fields and who signed

6. ALL CODES AND CLASSIFICATIONS:
   - Cause of death codes, ICD codes, classification codes
   - Occupation codes, industry codes
   - Race codes, ethnicity codes, marital status codes
   - ANY coded information

7. ALL CONTACT INFORMATION:
   - Phone numbers, fax numbers, mobile numbers
   - Email addresses, websites
   - Mailing addresses, physical addresses

8. ALL ADMINISTRATIVE DATA:
   - Form numbers, version numbers, revision dates
   - Page numbers, section numbers
   - Barcode numbers, QR code data
   - Watermark text, stamp text
   - "LICENSE NUMBER FOR" fields
   - "SIGNATURE OF" fields
   - "DATE PRONOUNCED DEAD" fields
   - "ACTUAL OR PRESUMED DATE OF DEATH" fields
   - "CAUSE OF DEATH" fields
   - ANY field with a label, even if it seems minor

EXTRACTION STRATEGY:
- Read the document line by line, field by field
- Extract EVERY labeled field you see
- Extract EVERY number that has a label or context
- Extract EVERY date in any format
- Extract EVERY name in any context
- Do NOT skip fields because they seem unimportant
- Do NOT skip fields because they are partially visible
- Do NOT skip fields because they are handwritten
- Include fields even if the value is unclear (mark as "Illegible" or "Unclear")

FIELD NAMING:
- Use SIMPLE, SHORT field names (not the full label text from the document)
- Replace spaces with underscores
- Simplify verbose labels to their core meaning
- Examples:
  * "LICENSE NUMBER FOR" → "License_Number"
  * "DATE PRONOUNCED DEAD" → "Death_Date"
  * "ACTUAL OR PRESUMED DATE OF DEATH" → "Death_Date"
  * "CAUSE OF DEATH" → "Cause_Of_Death"
  * "K1-0011267" → "Case_Number" or "File_Number"
  * "ACCOUNT HOLDER NAMES" → "Account_Holders"
  * "DATE OF ISSUE" → "Issue_Date"

CRITICAL NAMING FOR DEATH CERTIFICATES:
- The main certificate number (often handwritten, like "468431466" or "K1-0011267") MUST be extracted as "Account_Number"
- DO NOT use "Certificate_Number" - use "Account_Number" instead
- Example: If you see "468431466" or "K1-0011267" as the primary certificate identifier:
  * Extract it as "Account_Number": "468431466"
  * NOT as "Certificate_Number"

EXTRACT ABSOLUTELY EVERYTHING - MISS NOTHING:
- Read EVERY line of the document
- Extract EVERY field with a label
- Extract EVERY number (even if handwritten or unclear)
- Extract EVERY date and time
- Extract EVERY name (deceased, witnesses, physicians, funeral directors, registrars)
- Extract EVERY location (place of death, residence, city, county, state)
- Extract EVERY checkbox value (Yes/No, checked/unchecked)
- Extract EVERY signature field and date
- Extract license numbers, file numbers, reference numbers
- If a field is partially visible or unclear, still extract it and mark as "unclear" or "illegible"

Return ONLY valid JSON in this exact format where EVERY field has both value and confidence:
{{
  "documents": [
    {{
      "document_id": "doc_001",
      "document_type": "{doc_type}",
      "document_type_display": "{doc_info['name']}",
      "document_icon": "{doc_info['icon']}",
      "document_description": "{doc_info['description']}",
      "extracted_fields": {{
        "Field_Name": {{
          "value": "exact_value_from_document",
          "confidence": 95
        }},
        "Another_Field": {{
          "value": "another_value",
          "confidence": 85
        }},
        "SupportingDocuments": [
          {{
            "DocumentType": "type of document",
            "Details": "relevant details"
          }}
        ]
      }}
    }}
  ]
}}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL: EVERY field (except SupportingDocuments array) MUST have both "value" and "confidence"

For SupportingDocuments, ONLY include:
- Driver's License or State ID (with ID numbers)
- Death Certificates, Birth Certificates, Marriage Certificates
- OFAC checks or compliance verifications
- Passport or other government-issued IDs
- Attached copies of actual documents

DO NOT include as SupportingDocuments:
- Standard terms and conditions (e.g., "Deposit Account Agreement")
- Generic disclosures (e.g., "Regulation E Disclosure", "Privacy Policy")
- Legal disclaimers or authorization text
- Standard bank forms or agreements mentioned in fine print
- Any document that is just referenced in legal text but not actually attached

If there are NO actual supporting documents attached or specifically referenced with details, OMIT the SupportingDocuments field entirely.

CRITICAL: Do NOT use "N/A" or empty strings - ONLY include fields that have ACTUAL VALUES in the document.
If a field is not present or has no value, DO NOT include it in the JSON at all.
Only extract fields where you can see a clear, definite value in the document.
"""
    
    # For driver's license and loan documents, the prompt is already complete
    # For other documents, we need to wrap the response format
    if doc_type not in ["drivers_license", "loan_document"]:
        # The generic prompt needs the full format instructions which are already included above
        pass
    
    try:
        response = call_bedrock(prompt, text, max_tokens=8192)
        
        # Clean up response - remove markdown code blocks if present
        response = response.strip()
        
        # Find JSON content - look for the first { and last }
        json_start = response.find('{')
        json_end = response.rfind('}')
        
        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON object found in response")
        
        json_str = response[json_start:json_end + 1]
        
        # Try to parse JSON
        result = json.loads(json_str)
        
        # Ensure documents array exists
        if "documents" not in result:
            result = {"documents": [result]}
        
        # Calculate accuracy for each document and identify fields needing review
        for doc in result.get("documents", []):
            # Ensure extracted_fields exists
            if "extracted_fields" not in doc:
                doc["extracted_fields"] = {}
            
            # CRITICAL: Flatten nested objects in extracted_fields
            doc["extracted_fields"] = flatten_nested_objects(doc["extracted_fields"])
            
            fields = doc.get("extracted_fields", {})
            
            # POST-PROCESSING: For death certificates, rename certificate_number to account_number
            doc_type = doc.get("document_type", "")
            if doc_type == "death_certificate":
                # If certificate_number exists but account_number doesn't, rename it
                if "certificate_number" in fields and "account_number" not in fields:
                    fields["account_number"] = fields["certificate_number"]
                    del fields["certificate_number"]
                # Also check for variations
                if "Certificate_Number" in fields and "Account_Number" not in fields:
                    fields["Account_Number"] = fields["Certificate_Number"]
                    del fields["Certificate_Number"]
            filled_fields = sum(1 for v in fields.values() if v and v != "N/A" and v != "")
            total_fields = len(fields) if fields else 1
            doc["accuracy_score"] = round((filled_fields / total_fields) * 100, 1)
            doc["total_fields"] = total_fields
            doc["filled_fields"] = filled_fields
            
            # Calculate average confidence score
            confidence_scores = []
            for field_name, value in fields.items():
                # Check if value is a confidence object
                if isinstance(value, dict) and "confidence" in value:
                    confidence_scores.append(value["confidence"])
            
            if confidence_scores:
                doc["confidence_score"] = round(sum(confidence_scores) / len(confidence_scores), 1)
            else:
                doc["confidence_score"] = None
            
            # Identify fields needing review
            fields_needing_review = []
            for field_name, value in fields.items():
                if not value or value == "N/A" or value == "" or (isinstance(value, list) and len(value) == 0):
                    fields_needing_review.append({
                        "field_name": field_name,
                        "reason": "Missing or not found in document",
                        "current_value": value if value else "Not extracted"
                    })
            
            doc["fields_needing_review"] = fields_needing_review
            doc["needs_human_review"] = doc["accuracy_score"] < 100
            
            # Ensure required fields exist
            if "document_id" not in doc:
                doc["document_id"] = f"doc_{int(time.time())}"
            if "document_type" not in doc:
                doc["document_type"] = "unknown"
            if "document_type_display" not in doc:
                doc["document_type_display"] = "Unknown Document"
        
        return result
    except json.JSONDecodeError as e:
        return {
            "documents": [{
                "document_id": "error_001",
                "document_type": "error",
                "document_type_display": "JSON Parse Error",
                "error": f"Failed to parse AI response: {str(e)}",
                "raw_response": response[:500] if 'response' in locals() else "No response",
                "extracted_fields": {},
                "accuracy_score": 0,
                "total_fields": 0,
                "filled_fields": 0
            }]
        }
    except Exception as e:
        return {
            "documents": [{
                "document_id": "error_002",
                "document_type": "error",
                "document_type_display": "Processing Error",
                "error": str(e),
                "extracted_fields": {},
                "accuracy_score": 0,
                "total_fields": 0,
                "filled_fields": 0
            }]
        }


def pre_cache_all_pages(job_id: str, pdf_path: str, accounts: list):
    """
    Pre-cache all page data during initial upload to avoid re-running OCR on every click.
    This extracts text and data from all pages once and stores in S3.
    OPTIMIZED: Reuses OCR text cache to avoid duplicate OCR calls.
    """
    import fitz
    import json
    
    if not pdf_path or not os.path.exists(pdf_path):
        print(f"[WARNING] PDF path not found for pre-caching: {pdf_path}")
        return
    
    print(f"[INFO] Starting pre-cache for all pages in document {job_id}")
    
    try:
        # OPTIMIZATION: Try to load OCR cache first
        ocr_text_cache = {}
        try:
            cache_key = f"ocr_cache/{job_id}/text_cache.json"
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            ocr_text_cache = json.loads(cache_response['Body'].read().decode('utf-8'))
            # Convert string keys to int
            ocr_text_cache = {int(k): v for k, v in ocr_text_cache.items()}
            print(f"[INFO] Loaded OCR cache with {len(ocr_text_cache)} pages - will reuse to save costs")
        except Exception as cache_err:
            print(f"[INFO] No OCR cache found, will extract text: {str(cache_err)}")
        
        pdf_doc = fitz.open(pdf_path)
        total_pages = len(pdf_doc)
        
        # First, scan and map pages to accounts
        page_to_account = {}
        accounts_found = set()
        
        print(f"[INFO] Scanning {total_pages} pages to map accounts...")
        
        for page_num in range(total_pages):
            # OPTIMIZATION: Check cache first
            if page_num in ocr_text_cache:
                page_text = ocr_text_cache[page_num]
                print(f"[DEBUG] Reusing cached OCR for page {page_num + 1} ({len(page_text)} chars)")
            else:
                page = pdf_doc[page_num]
                page_text = page.get_text()
                
                # Check if page needs OCR
                has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
                
                if not page_text or len(page_text.strip()) < 20 or has_watermark:
                    # Extract with OCR
                    try:
                        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
                        temp_image_path = os.path.join(OUTPUT_DIR, f"temp_precache_{job_id}_{page_num}.png")
                        pix.save(temp_image_path)
                        
                        with open(temp_image_path, 'rb') as image_file:
                            image_bytes = image_file.read()
                        
                        textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                        
                        page_text = ""
                        for block in textract_response.get('Blocks', []):
                            if block['BlockType'] == 'LINE':
                                page_text += block.get('Text', '') + "\n"
                        
                        if os.path.exists(temp_image_path):
                            os.remove(temp_image_path)
                            
                    except Exception as ocr_err:
                        print(f"[ERROR] OCR failed on page {page_num + 1}: {str(ocr_err)}")
                        continue
                
                # Cache for later reuse
                ocr_text_cache[page_num] = page_text
            
            # Map page to account
            for acc_idx, acc in enumerate(accounts):
                acc_num = acc.get("accountNumber", "").strip()
                normalized_text = re.sub(r'[\s\-]', '', page_text)
                normalized_acc = re.sub(r'[\s\-]', '', acc_num)
                
                if normalized_acc and normalized_acc in normalized_text:
                    page_to_account[page_num] = (acc_idx, acc_num)
                    accounts_found.add(acc_num)
                    break
        
        print(f"[INFO] Mapped {len(page_to_account)} pages to {len(accounts_found)} accounts")
        
        # SPEED OPTIMIZATION: Extract and cache data for pages in PARALLEL
        def _extract_page_data(page_info):
            """Helper to extract data from a single page"""
            page_num, account_index, account_number = page_info
            try:
                print(f"[INFO] Pre-caching page {page_num + 1} for account {account_number}")
                
                # OPTIMIZATION: Reuse cached OCR text
                if page_num in ocr_text_cache:
                    page_text = ocr_text_cache[page_num]
                    print(f"[DEBUG] Reusing cached text for page {page_num + 1} - saved OCR call!")
                else:
                    # Fallback: extract if not in cache
                    import fitz
                    pdf_doc_local = fitz.open(pdf_path)
                    page = pdf_doc_local[page_num]
                    page_text = page.get_text()
                    pdf_doc_local.close()
                    
                    # Check if needs OCR
                    has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
                    
                    if not page_text or len(page_text.strip()) < 20 or has_watermark:
                        pdf_doc_local = fitz.open(pdf_path)
                        page = pdf_doc_local[page_num]
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        pdf_doc_local.close()
                        
                        temp_image_path = os.path.join(OUTPUT_DIR, f"temp_extract_{job_id}_{page_num}.png")
                        pix.save(temp_image_path)
                        
                        with open(temp_image_path, 'rb') as image_file:
                            image_bytes = image_file.read()
                        
                        textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                        
                        page_text = ""
                        for block in textract_response.get('Blocks', []):
                            if block['BlockType'] == 'LINE':
                                page_text += block.get('Text', '') + "\n"
                        
                        if os.path.exists(temp_image_path):
                            os.remove(temp_image_path)
                
                # Detect document type on this page
                detected_type = detect_document_type(page_text)
                
                # Use appropriate prompt based on detected type
                if detected_type == "drivers_license":
                    page_extraction_prompt = get_drivers_license_prompt()
                else:
                    page_extraction_prompt = get_comprehensive_extraction_prompt()
                
                # Extract data using AI
                response = call_bedrock(page_extraction_prompt, page_text, max_tokens=8192)
                
                # Parse JSON
                json_start = response.find('{')
                json_end = response.rfind('}')
                
                if json_start != -1 and json_end != -1:
                    json_str = response[json_start:json_end + 1]
                    parsed = json.loads(json_str)
                    
                    # Handle driver's license format
                    if detected_type == "drivers_license" and "documents" in parsed:
                        if len(parsed["documents"]) > 0:
                            doc_data = parsed["documents"][0]
                            if "extracted_fields" in doc_data:
                                parsed = doc_data["extracted_fields"]
                            else:
                                parsed = doc_data
                    
                    # CRITICAL: Flatten nested objects
                    parsed = flatten_nested_objects(parsed)
                    
                    parsed["Account_Number"] = account_number
                    
                    # Cache to S3
                    cache_key = f"page_data/{job_id}/account_{account_index}/page_{page_num}.json"
                    cache_data = {
                        "account_number": account_number,
                        "data": parsed,
                        "extracted_at": datetime.now().isoformat(),
                        "pre_cached": True,
                        "prompt_version": "v5_enhanced_verified"  # Version to invalidate old cache
                    }
                    
                    s3_client.put_object(
                        Bucket=S3_BUCKET,
                        Key=cache_key,
                        Body=json.dumps(cache_data),
                        ContentType='application/json'
                    )
                    
                    print(f"[INFO] Cached page {page_num + 1} data to S3: {cache_key}")
                    return True
                    
            except Exception as page_error:
                print(f"[ERROR] Failed to pre-cache page {page_num + 1}: {str(page_error)}")
                return False
        
        # Prepare page info for parallel processing
        page_infos = [(page_num, account_index, account_number) 
                      for page_num, (account_index, account_number) in page_to_account.items()]
        
        # PARALLEL PROCESSING: Extract data from multiple pages simultaneously
        # Use up to 5 workers for LLM calls (to avoid rate limits)
        max_workers = min(5, len(page_infos))
        print(f"[INFO] PARALLEL extraction: Processing {len(page_infos)} pages with {max_workers} workers")
        
        success_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_extract_page_data, page_info) for page_info in page_infos]
            
            for future in as_completed(futures):
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    print(f"[ERROR] Future failed: {str(e)}")
        
        print(f"[INFO] PARALLEL pre-caching completed: {success_count}/{len(page_infos)} pages cached successfully")
        
    except Exception as e:
        print(f"[ERROR] Pre-caching failed: {str(e)}")


def process_job(job_id: str, file_bytes: bytes, filename: str, use_ocr: bool, document_name: str = None, original_file_path: str = None):
    """Background worker to process documents - FAST upload with placeholder creation"""
    global processed_documents
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Use document_name if provided, otherwise use filename
        if not document_name:
            document_name = filename
        
        # Save PDF file locally for viewing
        saved_pdf_path = None
        if filename.lower().endswith('.pdf'):
            saved_pdf_path = f"{OUTPUT_DIR}/{timestamp}_{filename}"
            with open(saved_pdf_path, 'wb') as f:
                f.write(file_bytes)
            print(f"[INFO] Saved PDF to: {saved_pdf_path}")
        
        # Log processing start
        print(f"[INFO] Starting FAST upload for job {job_id}: {filename}")
        print(f"[INFO] File size: {len(file_bytes) / 1024:.2f} KB")
        
        # Initialize job status
        job_status_map[job_id] = {
            "status": "Creating placeholder document...",
            "progress": 20
        }
        
        # FAST UPLOAD: Create placeholder document immediately with document type detection
        detected_doc_type = "unknown"
        doc_icon = "📄"
        doc_description = "Document uploaded - extraction will start when opened"
        
        if filename.lower().endswith('.pdf') and saved_pdf_path:
            job_status_map[job_id].update({
                "status": "Detecting document type...",
                "progress": 40
            })
            
            # Quick document type detection using first page text
            try:
                import fitz
                pdf_doc = fitz.open(saved_pdf_path)
                if len(pdf_doc) > 0:
                    first_page_text = pdf_doc[0].get_text()
                    print(f"[DEBUG] First page text extracted: {len(first_page_text)} characters")
                    print(f"[DEBUG] First 200 chars: {first_page_text[:200]}")
                    
                    # If insufficient text found (scanned PDF or poor text extraction), use OCR on first page only
                    if len(first_page_text.strip()) < 300:
                        print(f"[INFO] First page has little text ({len(first_page_text)} chars), using OCR for document type detection...")
                        
                        try:
                            # Convert first page to image and OCR it
                            page = pdf_doc[0]
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution
                            
                            temp_image_path = os.path.join(OUTPUT_DIR, f"temp_detection_{job_id}_page0.png")
                            pix.save(temp_image_path)
                            
                            with open(temp_image_path, 'rb') as image_file:
                                image_bytes = image_file.read()
                            
                            # Use Textract for OCR on first page only
                            textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                            
                            ocr_text = ""
                            for block in textract_response.get('Blocks', []):
                                if block['BlockType'] == 'LINE':
                                    ocr_text += block.get('Text', '') + "\n"
                            
                            # Clean up temp file
                            if os.path.exists(temp_image_path):
                                os.remove(temp_image_path)
                            
                            if ocr_text.strip():
                                first_page_text = ocr_text
                                print(f"[INFO] ✓ OCR extracted {len(first_page_text)} characters for document type detection")
                            else:
                                print(f"[WARNING] OCR failed to extract text from first page")
                                
                        except Exception as ocr_error:
                            print(f"[WARNING] OCR failed for document type detection: {str(ocr_error)}")
                    
                    # Detect document type using the extracted text
                    if len(first_page_text.strip()) > 10:
                        detected_doc_type = detect_document_type(first_page_text)
                        
                        # Get document info
                        if detected_doc_type in SUPPORTED_DOCUMENT_TYPES:
                            doc_info = SUPPORTED_DOCUMENT_TYPES[detected_doc_type]
                            doc_icon = doc_info["icon"]
                            doc_description = doc_info["description"]
                        
                        print(f"[INFO] ✅ Detected document type: {detected_doc_type}")
                    else:
                        print(f"[WARNING] Insufficient text for document type detection ({len(first_page_text)} chars)")
                    
                pdf_doc.close()
            except Exception as detection_error:
                print(f"[WARNING] Document type detection failed: {str(detection_error)}")
                detected_doc_type = "unknown"
        
        # Create placeholder document immediately - NO OCR, NO EXTRACTION
        job_status_map[job_id].update({
            "status": "Creating placeholder document...",
            "progress": 80
        })
        
        # Create placeholder document structure
        if detected_doc_type == "loan_document":
            # For loan documents, create simple placeholder - accounts will be extracted when document is opened
            print(f"[UPLOAD] Creating loan document placeholder - accounts will be extracted when opened")
            placeholder_doc = {
                "document_id": "loan_doc_001",
                "document_type": "loan_document",
                "document_type_display": "Loan/Account Document",
                "document_icon": "🏦",
                "document_description": "Banking or loan account information",
                "extracted_fields": {
                    "total_accounts": 0,
                    "accounts_processed": 0
                },
                "accounts": [],  # Empty - will be populated when document is opened
                "accuracy_score": None,
                "filled_fields": 0,
                "total_fields": 0,
                "fields_needing_review": [],
                "needs_human_review": False,
                "optimized": True
            }
        else:
            # For other documents, create simple placeholder
            placeholder_doc = {
                "document_type": detected_doc_type,
                "document_type_display": SUPPORTED_DOCUMENT_TYPES.get(detected_doc_type, {}).get("name", "Unknown Document"),
                "document_icon": doc_icon,
                "document_description": doc_description,
                "extracted_fields": {},
                "total_fields": 0,
                "filled_fields": 0,
                "needs_human_review": False
            }
        
        # Create document record
        document_record = {
            "id": job_id,
            "filename": filename,
            "document_name": document_name,
            "timestamp": timestamp,
            "processed_date": datetime.now().isoformat(),
            "ocr_file": None,  # No OCR file yet
            "ocr_method": "Deferred - will extract when opened",
            "basic_fields": {},
            "documents": [placeholder_doc],
            "document_type_info": {
                "type": detected_doc_type,
                "name": SUPPORTED_DOCUMENT_TYPES.get(detected_doc_type, {}).get("name", "Unknown Document"),
                "icon": doc_icon,
                "description": doc_description,
                "expected_fields": SUPPORTED_DOCUMENT_TYPES.get(detected_doc_type, {}).get("expected_fields", []),
                "is_supported": detected_doc_type in SUPPORTED_DOCUMENT_TYPES
            },
            "use_ocr": use_ocr,
            "pdf_path": saved_pdf_path,
            "status": "extracting",  # Show as extracting
            "can_view": True  # Allow immediate viewing
        }
        
        # Add document to database immediately
        processed_documents.append(document_record)
        save_documents_db(processed_documents)
        
        # Mark job as complete
        job_status_map[job_id] = {
            "status": "✅ Document uploaded successfully",
            "progress": 100,
            "result": {"documents": [placeholder_doc]},
            "document_id": job_id
        }
        
        print(f"[INFO] ✅ FAST upload completed - document {job_id} ready for viewing")
        print(f"[INFO] Document type: {detected_doc_type} - extraction will happen when pages are opened")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        
        job_status_map[job_id] = {
            "status": f"❌ Error: {str(e)}",
            "progress": 0,
            "error": str(e),
            "error_details": error_details
        }
        
        # Log error to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_log = f"{OUTPUT_DIR}/{timestamp}_processing_error.log"
        with open(error_log, 'w', encoding='utf-8') as f:
            f.write(f"Job ID: {job_id}\n")
            f.write(f"Filename: {filename}\n")
            f.write(f"Error: {str(e)}\n\n")
            f.write(f"Traceback:\n{error_details}\n")


@app.route("/")
def index():
    """Main page - Skills Catalog Dashboard"""
    return render_template("skills_catalog.html")


@app.route("/dashboard")
def dashboard():
    """Dashboard - Shows all processed documents as skills"""
    return render_template("skills_catalog.html")


@app.route("/codebase")
def codebase():
    """Codebase documentation"""
    return render_template("codebase_docs.html")


@app.route("/api/documents")
def get_all_documents():
    """API endpoint to get all processed documents"""
    response = jsonify({"documents": processed_documents, "total": len(processed_documents)})
    
    # Add cache-busting headers to ensure fresh data
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response


@app.route("/api/document/<doc_id>")
def get_document_detail(doc_id):
    """Get details of a specific document"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return jsonify({"success": True, "document": doc})
    return jsonify({"success": False, "message": "Document not found"}), 404


@app.route("/api/document/<doc_id>/process-loan", methods=["POST"])
def process_loan_document_endpoint(doc_id):
    """Process loan document to split into accounts - called when loan document is first opened"""
    try:
        # Find the document
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Check if it's a loan document
        doc_type = doc.get("document_type_info", {}).get("type")
        if doc_type != "loan_document":
            return jsonify({"success": False, "message": "Not a loan document"}), 400
        
        # Check if already processed (has accounts)
        doc_data = doc.get("documents", [{}])[0]
        existing_accounts = doc_data.get("accounts", [])
        if existing_accounts and len(existing_accounts) > 0:
            return jsonify({
                "success": True, 
                "message": "Already processed", 
                "accounts": existing_accounts,
                "total_accounts": len(existing_accounts)
            })
        
        # Get PDF path
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        print(f"[LOAN_PROCESSING] Processing loan document {doc_id} for account splitting...")
        
        # Extract text from entire PDF using fast OCR
        try:
            # Read PDF file bytes
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            # Use fast OCR extraction
            print(f"[LOAN_PROCESSING] Using fast OCR for account detection...")
            full_text, _ = extract_text_with_textract(pdf_bytes, os.path.basename(pdf_path))
            
            # Fallback to PyPDF if OCR fails
            if not full_text or len(full_text.strip()) < 100:
                print(f"[LOAN_PROCESSING] OCR failed, trying PyPDF as fallback...")
                full_text, _ = try_extract_pdf_with_pypdf(pdf_bytes, os.path.basename(pdf_path))
            
            print(f"[LOAN_PROCESSING] Extracted {len(full_text)} characters from PDF")
            
        except Exception as text_error:
            print(f"[LOAN_PROCESSING] Text extraction failed: {str(text_error)}")
            return jsonify({"success": False, "message": f"Text extraction failed: {str(text_error)}"}), 500
        
        if not full_text or len(full_text.strip()) < 100:
            return jsonify({"success": False, "message": "Insufficient text extracted from PDF"}), 400
        
        # Process with loan processor to split into accounts
        try:
            loan_result = process_loan_document(full_text)
            
            if not loan_result or "documents" not in loan_result:
                return jsonify({"success": False, "message": "Loan processing failed"}), 500
            
            loan_doc_data = loan_result["documents"][0]
            accounts = loan_doc_data.get("accounts", [])
            
            print(f"[LOAN_PROCESSING] ✓ Found {len(accounts)} accounts")
            print(f"[LOAN_PROCESSING] Loan result structure: {loan_result}")
            print(f"[LOAN_PROCESSING] Accounts to save: {accounts}")
            
            # Update the document with account information
            update_data = {
                "extracted_fields": loan_doc_data.get("extracted_fields", {}),
                "accounts": accounts,
                "total_fields": loan_doc_data.get("total_fields", 0),
                "filled_fields": loan_doc_data.get("filled_fields", 0),
                "needs_human_review": loan_doc_data.get("needs_human_review", False),
                "optimized": True
            }
            
            print(f"[LOAN_PROCESSING] Update data: {update_data}")
            print(f"[LOAN_PROCESSING] Document before update: {doc['documents'][0]}")
            
            doc["documents"][0].update(update_data)
            
            print(f"[LOAN_PROCESSING] Document after update: {doc['documents'][0]}")
            
            # Save updated document
            save_documents_db(processed_documents)
            print(f"[LOAN_PROCESSING] ✓ Document saved to database")
            
            return jsonify({
                "success": True,
                "message": f"Successfully processed {len(accounts)} accounts",
                "accounts": accounts,
                "total_accounts": len(accounts)
            })
            
        except Exception as process_error:
            print(f"[LOAN_PROCESSING] Processing failed: {str(process_error)}")
            return jsonify({"success": False, "message": f"Processing failed: {str(process_error)}"}), 500
        
    except Exception as e:
        print(f"[LOAN_PROCESSING] Endpoint error: {str(e)}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/document/<doc_id>/pages")
def view_document_pages(doc_id):
    """View document with unified page-by-page viewer"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("unified_page_viewer.html", document=doc)
    return "Document not found", 404


@app.route("/document/<doc_id>/accounts")
def view_account_based(doc_id):
    """View document with account-based interface"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("account_based_viewer.html", document=doc)
    return "Document not found", 404


@app.route("/api/document/<doc_id>/changes", methods=["GET"])
def get_document_changes(doc_id):
    """Get the list of changes for a document"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    changes = doc.get("changes", [])
    return jsonify({
        "success": True,
        "changes": changes,
        "needs_review": doc.get("needs_review", False),
        "update_source": doc.get("update_source_filename", "Unknown")
    })


@app.route("/api/document/<doc_id>/apply-changes", methods=["POST"])
def apply_selected_changes(doc_id):
    """Apply only the selected changes to the document"""
    global processed_documents
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        data = request.get_json()
        selected_indices = data.get("selected_changes", [])
        
        if not selected_indices:
            return jsonify({"success": False, "message": "No changes selected"}), 400
        
        changes = doc.get("changes", [])
        applied_changes = []
        
        # Apply only selected changes
        for idx in selected_indices:
            if 0 <= idx < len(changes):
                change = changes[idx]
                applied_changes.append(change)
                
                # Apply the change to the document
                field_path = change["field"].split(".")
                
                # Navigate to the field and update it
                current = doc
                for i, key in enumerate(field_path[:-1]):
                    # Handle array indices like "accounts[468869904]"
                    if "[" in key and "]" in key:
                        base_key = key.split("[")[0]
                        array_key = key.split("[")[1].split("]")[0]
                        
                        if base_key not in current:
                            current[base_key] = []
                        
                        # Find the item in array
                        if base_key == "accounts":
                            item = next((a for a in current[base_key] if a.get("accountNumber") == array_key), None)
                            if item:
                                current = item
                    else:
                        if key not in current:
                            current[key] = {}
                        current = current[key]
                
                # Set the final value
                final_key = field_path[-1]
                if change["change_type"] == "added" or change["change_type"] == "updated":
                    current[final_key] = change["new_value"]
        
        # Mark as reviewed and move to history
        doc["needs_review"] = False
        doc["reviewed_at"] = datetime.now().isoformat()
        doc["changes_history"] = doc.get("changes_history", [])
        doc["changes_history"].append({
            "applied_changes": applied_changes,
            "rejected_changes": [c for i, c in enumerate(changes) if i not in selected_indices],
            "reviewed_at": doc["reviewed_at"]
        })
        doc["changes"] = []
        
        save_documents_db(processed_documents)
        
        return jsonify({
            "success": True,
            "message": f"Applied {len(applied_changes)} changes",
            "applied_count": len(applied_changes)
        })
    
    except Exception as e:
        print(f"[ERROR] Failed to apply changes: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Failed: {str(e)}"}), 500


@app.route("/api/document/<doc_id>/mark-reviewed", methods=["POST"])
def mark_document_reviewed(doc_id):
    """Mark a document as reviewed without applying changes (reject all)"""
    global processed_documents
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        # Clear review flags
        doc["needs_review"] = False
        doc["reviewed_at"] = datetime.now().isoformat()
        
        # Keep changes history but mark as reviewed
        if "changes" in doc:
            doc["changes_history"] = doc.get("changes_history", [])
            doc["changes_history"].append({
                "rejected_changes": doc["changes"],
                "reviewed_at": doc["reviewed_at"]
            })
            doc["changes"] = []
        
        save_documents_db(processed_documents)
        
        return jsonify({"success": True, "message": "Document marked as reviewed (all changes rejected)"})
    
    except Exception as e:
        print(f"[ERROR] Failed to mark document as reviewed: {str(e)}")
        return jsonify({"success": False, "message": f"Failed: {str(e)}"}), 500


@app.route("/api/document/<doc_id>/pages")
def get_document_pages(doc_id):
    """Get all pages of a document as images using PyMuPDF with account mapping"""
    import fitz  # PyMuPDF
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # Create pages directory if it doesn't exist
        pages_dir = os.path.join(OUTPUT_DIR, "pages", doc_id)
        os.makedirs(pages_dir, exist_ok=True)
        
        # Check if pages already exist
        existing_pages = sorted([f for f in os.listdir(pages_dir) if f.endswith('.png')])
        
        if not existing_pages:
            # Convert PDF to images using PyMuPDF
            print(f"[INFO] Converting PDF to images for document {doc_id}")
            pdf_document = fitz.open(pdf_path)
            
            # Convert each page to image
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # Render page to image (zoom=2 for 200 DPI equivalent)
                mat = fitz.Matrix(2, 2)  # 2x zoom = ~200 DPI
                pix = page.get_pixmap(matrix=mat)
                
                # Save as PNG
                page_path = os.path.join(pages_dir, f"page_{page_num+1}.png")
                pix.save(page_path)
                existing_pages.append(f"page_{page_num+1}.png")
            
            pdf_document.close()
            print(f"[INFO] Created {len(existing_pages)} page images")
        
        # Check if this is a loan document with accounts
        doc_data = doc.get("documents", [{}])[0]
        has_accounts = doc_data.get("accounts") is not None and len(doc_data.get("accounts", [])) > 0
        
        # Create page-to-account mapping for loan documents
        page_account_mapping = {}
        if has_accounts:
            accounts = doc_data.get("accounts", [])
            # Simple mapping: distribute pages evenly across accounts
            # For better accuracy, you could analyze page content to detect account numbers
            pages_per_account = max(1, len(existing_pages) // len(accounts))
            
            for i, page_file in enumerate(existing_pages):
                account_index = min(i // pages_per_account, len(accounts) - 1)
                page_account_mapping[i] = {
                    "account_index": account_index,
                    "account_number": accounts[account_index].get("accountNumber", "Unknown")
                }
        
        # Return page URLs with account mapping
        pages = [
            {
                "page_number": i + 1,
                "url": f"/api/document/{doc_id}/page/{i}",
                "thumbnail": f"/api/document/{doc_id}/page/{i}/thumbnail",
                "account_index": page_account_mapping.get(i, {}).get("account_index"),
                "account_number": page_account_mapping.get(i, {}).get("account_number")
            }
            for i in range(len(existing_pages))
        ]
        
        return jsonify({
            "success": True,
            "pages": pages,
            "total_pages": len(pages),
            "has_accounts": has_accounts,
            "total_accounts": len(doc_data.get("accounts", [])) if has_accounts else 0
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to get pages for {doc_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Failed to get pages: {str(e)}"}), 500


@app.route("/api/document/<doc_id>/page/<int:page_num>")
@app.route("/api/document/<doc_id>/page/<int:page_num>/image")
def get_document_page(doc_id, page_num):
    """Get a specific page image"""
    from flask import send_file
    
    pages_dir = os.path.join(OUTPUT_DIR, "pages", doc_id)
    page_path = os.path.join(pages_dir, f"page_{page_num+1}.png")
    
    if os.path.exists(page_path):
        return send_file(page_path, mimetype='image/png')
    
    return "Page not found", 404


@app.route("/api/document/<doc_id>/page/<int:page_num>/thumbnail")
def get_document_page_thumbnail(doc_id, page_num):
    """Get a thumbnail of a specific page"""
    from flask import send_file
    from PIL import Image
    import tempfile
    
    pages_dir = os.path.join(OUTPUT_DIR, "pages", doc_id)
    page_path = os.path.join(pages_dir, f"page_{page_num+1}.png")
    
    if not os.path.exists(page_path):
        return "Page not found", 404
    
    try:
        # Create thumbnail
        img = Image.open(page_path)
        img.thumbnail((150, 200))
        
        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        img.save(temp_file.name, 'PNG')
        temp_file.close()
        
        return send_file(temp_file.name, mimetype='image/png')
    except Exception as e:
        print(f"[ERROR] Failed to create thumbnail: {str(e)}")
        return "Failed to create thumbnail", 500


@app.route("/api/document/<doc_id>/account/<int:account_index>/pages")
def get_account_pages(doc_id, account_index):
    """Get pages for a specific account by detecting account numbers on pages"""
    import fitz
    import re
    import json
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        # Get PDF info
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # Get account info
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if not accounts or len(accounts) == 0:
            return jsonify({"success": False, "message": "No accounts found"}), 404
        
        if account_index >= len(accounts):
            return jsonify({"success": False, "message": "Account index out of range"}), 400
        
        target_account_number = accounts[account_index].get("accountNumber", "").strip()
        
        # Check cache first
        cache_key = f"page_mapping/{doc_id}/mapping.json"
        page_to_account = None
        
        try:
            print(f"[INFO] Checking cache for page mapping: {cache_key}")
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_mapping = json.loads(cache_response['Body'].read().decode('utf-8'))
            page_to_account = {int(k): v for k, v in cached_mapping.items()}
            print(f"[INFO] Loaded cached page mapping with {len(page_to_account)} pages")
        except s3_client.exceptions.NoSuchKey:
            print(f"[INFO] No cached mapping found, will scan pages")
        except Exception as cache_error:
            print(f"[WARNING] Cache load failed: {str(cache_error)}, will scan pages")
        
        # If no cache, scan pages and create mapping
        if page_to_account is None:
            page_to_account = scan_and_map_pages(doc_id, pdf_path, accounts)
            
            # Save to cache
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=cache_key,
                    Body=json.dumps(page_to_account),
                    ContentType='application/json'
                )
                print(f"[INFO] Cached page mapping to S3: {cache_key}")
            except Exception as s3_error:
                print(f"[WARNING] Failed to cache mapping: {str(s3_error)}")
        
        # Now assign pages to the target account using the mapping
        pdf_doc = fitz.open(pdf_path)
        total_pages = len(pdf_doc)
        pdf_doc.close()
        
        # Assign pages to the target account using the correct logic:
        # 1. Find the first page where this account appears
        # 2. Assign all pages from that point until the next account appears
        # 3. Exclude pages before any account is found
        
        account_pages = []
        
        print(f"[DEBUG] Page to account mapping: {page_to_account}")
        print(f"[DEBUG] Looking for account: {target_account_number}")
        
        # Get all pages where any account is found, sorted by page number
        all_account_pages = sorted([p for p in page_to_account.keys()])
        print(f"[DEBUG] All pages with accounts: {all_account_pages}")
        
        if all_account_pages:
            # Find the first page where this specific account appears
            target_account_pages = [p for p in all_account_pages if page_to_account[p] == target_account_number]
            print(f"[DEBUG] Pages with target account {target_account_number}: {target_account_pages}")
            
            if target_account_pages:
                first_page = target_account_pages[0]
                print(f"[DEBUG] First page with account {target_account_number}: {first_page}")
                
                # Find where the next different account starts (or end of document)
                next_account_page = total_pages  # Default to end of document
                
                for page_num in range(first_page + 1, total_pages):
                    # If we find a page with a different account, that's where this account ends
                    if page_num in page_to_account and page_to_account[page_num] != target_account_number:
                        next_account_page = page_num
                        print(f"[DEBUG] Next different account found at page {page_num + 1}")
                        break
                
                # Include all pages from first_page to next_account_page (exclusive)
                account_pages = list(range(first_page, next_account_page))
                
                print(f"[DEBUG] Account {target_account_number} range: {first_page} to {next_account_page}")
                print(f"[DEBUG] Final assigned pages (0-based): {account_pages}")
                print(f"[DEBUG] Final assigned pages (1-based): {[p+1 for p in account_pages]}")
            else:
                print(f"[DEBUG] Account {target_account_number} not found on any page")
        else:
            print(f"[DEBUG] No accounts found on any pages - page_to_account is empty")
        
        # If no pages found, fall back to even distribution but exclude obvious non-account pages
        if not account_pages:
            print(f"[WARNING] No pages found for account {target_account_number}, using smart distribution")
            
            # Check for pages that should be excluded (document prep, cover pages, etc.)
            excluded_pages = set()
            
            # Check each page for exclusion criteria
            pdf_doc = fitz.open(pdf_path)
            for page_num in range(total_pages):
                try:
                    page = pdf_doc[page_num]
                    page_text = page.get_text()
                    
                    # If no text or watermarked, use OCR
                    has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
                    if not page_text or len(page_text.strip()) < 50 or has_watermark:
                        print(f"[SMART] Page {page_num + 1} needs OCR for exclusion check")
                        try:
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            temp_image_path = os.path.join(OUTPUT_DIR, f"temp_exclude_{doc_id}_{page_num}.png")
                            pix.save(temp_image_path)
                            
                            with open(temp_image_path, 'rb') as image_file:
                                image_bytes = image_file.read()
                            
                            textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                            ocr_text = ""
                            for block in textract_response.get('Blocks', []):
                                if block['BlockType'] == 'LINE':
                                    ocr_text += block.get('Text', '') + "\n"
                            
                            if os.path.exists(temp_image_path):
                                os.remove(temp_image_path)
                            
                            if ocr_text.strip():
                                page_text = ocr_text
                                print(f"[SMART] OCR extracted {len(page_text)} chars for exclusion check on page {page_num + 1}")
                        
                        except Exception as ocr_err:
                            print(f"[WARNING] OCR failed for exclusion check on page {page_num + 1}: {str(ocr_err)}")
                    
                    # Check if this looks like a document prep or cover page
                    prep_indicators = [
                        "document prep", "step #1", "cis work", "associate:",
                        "# of documents", "count includes separator", 
                        "cover sheet", "preparation", "processing", "scanning process"
                    ]
                    
                    page_text_lower = page_text.lower()
                    is_prep_page = any(indicator in page_text_lower for indicator in prep_indicators)
                    
                    if is_prep_page:
                        excluded_pages.add(page_num)
                        print(f"[SMART] Excluding page {page_num + 1} (document prep/cover page)")
                        print(f"[SMART] Found indicators: {[ind for ind in prep_indicators if ind in page_text_lower]}")
                
                except Exception as e:
                    print(f"[WARNING] Could not check page {page_num} for exclusion: {str(e)}")
            
            pdf_doc.close()
            
            # Calculate available pages (excluding prep pages)
            available_pages = [p for p in range(total_pages) if p not in excluded_pages]
            
            if available_pages:
                pages_per_account = max(1, len(available_pages) // len(accounts))
                start_idx = account_index * pages_per_account
                end_idx = start_idx + pages_per_account if account_index < len(accounts) - 1 else len(available_pages)
                account_pages = available_pages[start_idx:end_idx]
                print(f"[SMART] Assigned {len(account_pages)} pages to account {target_account_number}: {[p+1 for p in account_pages]}")
            else:
                # Fallback to original logic if no pages available
                pages_per_account = max(1, total_pages // len(accounts))
                start_page = account_index * pages_per_account
                end_page = start_page + pages_per_account if account_index < len(accounts) - 1 else total_pages
                account_pages = list(range(start_page, end_page))
                print(f"[FALLBACK] No available pages after exclusion, using original distribution: {[p+1 for p in account_pages]}")
            
            # Also clear the cache since it's not working properly
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
                print(f"[FALLBACK] Cleared faulty cache: {cache_key}")
            except:
                pass
        
        # Display page numbers as 1-based for clarity
        display_pages = [p + 1 for p in account_pages]
        print(f"[INFO] Account {target_account_number} has {len(account_pages)} page(s): {display_pages}")
        
        response_data = {
            "success": True,
            "total_pages": len(account_pages),
            "pages": account_pages,  # Already 0-based page numbers for JavaScript
            "account_number": target_account_number
        }
        print(f"[INFO] Final account_pages (0-based): {account_pages}")
        print(f"[INFO] Returning response: {response_data}")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[ERROR] Failed to get account pages: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/clear-page-cache", methods=["POST"])
def clear_page_cache(doc_id):
    """Clear page mapping cache for a document"""
    try:
        cache_key = f"page_mapping/{doc_id}/mapping.json"
        s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
        print(f"[CACHE] Cleared page mapping cache: {cache_key}")
        return jsonify({"success": True, "message": "Page cache cleared"})
    except s3_client.exceptions.NoSuchKey:
        return jsonify({"success": True, "message": "No cache to clear"})
    except Exception as e:
        print(f"[ERROR] Failed to clear cache: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>")
def get_account_page_image(doc_id, account_index, page_num):
    """Get specific page image for an account"""
    import fitz
    from flask import send_file
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return "Document not found", 404
    
    pages_dir = os.path.join(OUTPUT_DIR, "pages", doc_id)
    page_path = os.path.join(pages_dir, f"page_{page_num+1}.png")
    
    # If page doesn't exist, generate it
    if not os.path.exists(page_path):
        try:
            pdf_path = doc.get("pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                return "PDF file not found", 404
            
            os.makedirs(pages_dir, exist_ok=True)
            
            # Open PDF and render the specific page
            pdf_doc = fitz.open(pdf_path)
            if page_num >= len(pdf_doc):
                return "Page number out of range", 404
            
            page = pdf_doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pix.save(page_path)
            pdf_doc.close()
            
        except Exception as e:
            print(f"[ERROR] Failed to generate page {page_num}: {str(e)}")
            return f"Failed to generate page: {str(e)}", 500
    
    if os.path.exists(page_path):
        return send_file(page_path, mimetype='image/png')
    
    return "Page not found", 404


@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>/data")
def get_account_page_data(doc_id, account_index, page_num):
    """Extract data for a specific page of an account - with S3 caching"""
    import fitz
    import json
    
    print(f"[DEBUG] get_account_page_data called: doc_id={doc_id}, account_index={account_index}, page_num={page_num}")
    
    # CONSISTENCY FIX: Check for document-level extraction cache first
    doc_cache_key = f"document_extraction_cache/{doc_id}_account_{account_index}_page_{page_num}.json"
    try:
        cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=doc_cache_key)
        cached_data = json.loads(cached_result['Body'].read())
        print(f"[DEBUG] ✓ Using document-level cached result for account {account_index} page {page_num} - GUARANTEED CONSISTENT")
        
        # Add cache headers to prevent browser caching issues
        response = jsonify(cached_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"[DEBUG] No document-level cache found for account {account_index} page {page_num}, extracting fresh: {str(e)}")
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        print(f"[ERROR] Document not found: {doc_id}")
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    print(f"[DEBUG] Document found, pdf_path={doc.get('pdf_path')}")
    
    try:
        # Check S3 cache first
        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
        
        try:
            print(f"[DEBUG] Checking S3 cache: {cache_key}")
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
            
            # Check prompt version - invalidate old cache
            cached_version = cached_data.get("prompt_version", "v1")
            current_version = "v5_enhanced_verified"  # Updated to match new version
            
            if cached_version != current_version:
                print(f"[DEBUG] Cache version mismatch ({cached_version} vs {current_version}) - will re-extract")
                raise Exception("Cache version outdated")
            
            print(f"[DEBUG] Found cached data in S3 (version {cached_version})")
            
            # CRITICAL: Apply flattening to cached data too!
            cached_fields = cached_data.get("data", {})
            cached_fields = flatten_nested_objects(cached_fields)
            print(f"[DEBUG] Applied flattening to cached data")
            
            response = jsonify({
                "success": True,
                "page_number": page_num + 1,
                "account_number": cached_data.get("account_number"),
                "data": cached_fields,
                "cached": True,
                "prompt_version": cached_version
            })
            # Prevent browser caching - always fetch fresh data
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        except s3_client.exceptions.NoSuchKey:
            print(f"[DEBUG] No cache found, will extract data")
        except Exception as cache_error:
            print(f"[DEBUG] Cache check failed: {str(cache_error)}, will extract data")
        
        # Get PDF path
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # OPTIMIZATION: Try to load OCR text from cache first
        page_text = None
        try:
            cache_key = f"ocr_cache/{doc_id}/text_cache.json"
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            ocr_cache = json.loads(cache_response['Body'].read().decode('utf-8'))
            page_text = ocr_cache.get(str(page_num))
            if page_text:
                print(f"[DEBUG] Loaded page {page_num} text from OCR cache ({len(page_text)} chars)")
        except Exception as cache_err:
            print(f"[DEBUG] No OCR cache found, will extract text: {str(cache_err)}")
        
        # If not in cache, extract text from PDF
        if not page_text:
            print(f"[DEBUG] Opening PDF: {pdf_path}")
            pdf_doc = fitz.open(pdf_path)
            print(f"[DEBUG] PDF has {len(pdf_doc)} pages")
            
            if page_num >= len(pdf_doc):
                print(f"[ERROR] Page number {page_num} out of range (total pages: {len(pdf_doc)})")
                return jsonify({"success": False, "message": "Page number out of range"}), 404
            
            page = pdf_doc[page_num]
            page_text = page.get_text()
            
            print(f"[DEBUG] Extracted {len(page_text)} characters from page {page_num}")
            print(f"[DEBUG] Page text preview: {page_text[:200]}")
            
            # Check if page has watermark or is mostly garbage text
            has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
            is_mostly_single_chars = page_text.count('\n') > len(page_text) / 3  # Too many line breaks
            
            # If no text found, has watermark, or is likely an image - use OCR
            if not page_text or len(page_text.strip()) < 50 or has_watermark or is_mostly_single_chars:
                print(f"[DEBUG] Page {page_num} has no text layer, using OCR...")
                
                # Save page as image temporarily
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                temp_image_path = os.path.join(OUTPUT_DIR, f"temp_page_{doc_id}_{page_num}.png")
                pix.save(temp_image_path)
                
                # Use Textract to extract text from the image
                try:
                    with open(temp_image_path, 'rb') as image_file:
                        image_bytes = image_file.read()
                    
                    textract_response = textract.detect_document_text(
                        Document={'Bytes': image_bytes}
                    )
                    
                    # Extract text from Textract response
                    page_text = ""
                    for block in textract_response.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            page_text += block.get('Text', '') + "\n"
                    
                    print(f"[DEBUG] OCR extracted {len(page_text)} characters from page {page_num}")
                    
                    # Clean up temp file
                    if os.path.exists(temp_image_path):
                        os.remove(temp_image_path)
                        
                except Exception as ocr_error:
                    print(f"[ERROR] OCR failed: {str(ocr_error)}")
                    pdf_doc.close()
                    return jsonify({"success": False, "message": f"OCR failed: {str(ocr_error)}"}), 500
            else:
                print(f"[DEBUG] Extracted {len(page_text)} characters from page {page_num}")
            
            pdf_doc.close()
        
        # Get account info to know what account number this page belongs to
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if account_index >= len(accounts):
            return jsonify({"success": False, "message": "Account index out of range"}), 400
        
        account = accounts[account_index]
        account_number = account.get("accountNumber", "Unknown")
        
        # CONSISTENCY FIX: Create content-based cache key for deterministic results
        import hashlib
        content_hash = hashlib.md5(page_text.encode('utf-8')).hexdigest()[:12]
        content_cache_key = f"content_extraction_cache/{content_hash}_account_{account_index}_page_{page_num}.json"
        
        # Check content-based cache first
        try:
            cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=content_cache_key)
            cached_data = json.loads(cached_result['Body'].read())
            print(f"[DEBUG] ✓ Using content-based cached result (hash: {content_hash}) - GUARANTEED SAME CONTENT = SAME RESULT")
            
            # Still cache it in document-level cache for faster access
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=doc_cache_key,
                    Body=json.dumps(cached_data),
                    ContentType='application/json'
                )
            except:
                pass
            
            response = jsonify(cached_data)
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        except Exception as e:
            print(f"[DEBUG] No content-based cache found (hash: {content_hash}), will extract fresh")
        
        # Extract data from this specific page using AI
        print(f"[DEBUG] Calling AI to extract data from page {page_num}")
        
        # Detect document type on this page
        detected_type = detect_document_type(page_text)
        print(f"[DEBUG] Detected document type on page {page_num}: {detected_type}")
        
        # Use appropriate prompt based on detected type
        if detected_type == "drivers_license":
            page_extraction_prompt = get_drivers_license_prompt()
            print(f"[DEBUG] Using specialized DL prompt for page {page_num}")
        else:
            page_extraction_prompt = get_comprehensive_extraction_prompt()
            print(f"[DEBUG] Using comprehensive prompt for page {page_num}")
        
        print(f"[DEBUG] Got page extraction prompt, calling Bedrock...")
        response = call_bedrock(page_extraction_prompt, page_text, max_tokens=8192)
        print(f"[DEBUG] Got response from Bedrock, length: {len(response)}")
        
        # Parse JSON response
        json_start = response.find('{')
        json_end = response.rfind('}')
        
        if json_start != -1 and json_end != -1:
            json_str = response[json_start:json_end + 1]
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON parse error: {str(e)}")
                print(f"[ERROR] AI Response: {response[:500]}")
                return jsonify({
                    "success": False,
                    "message": f"Failed to parse AI response: {str(e)}",
                    "raw_response": response[:500]
                }), 500
            
            # Handle driver's license format: unwrap documents array if present
            if detected_type == "drivers_license" and "documents" in parsed:
                if len(parsed["documents"]) > 0:
                    doc_data = parsed["documents"][0]
                    # Extract the fields from extracted_fields
                    if "extracted_fields" in doc_data:
                        parsed = doc_data["extracted_fields"]
                        print(f"[DEBUG] Unwrapped driver's license data: {len(parsed)} fields")
                    else:
                        parsed = doc_data
            
            # MANDATORY: Always check for VERIFIED text using regex fallback
            import re
            
            # Check for VERIFIED text in the page content
            verified_patterns = [
                r'\bVERIFIED\b',
                r'\bVERIFICATION\b', 
                r'\bVERIFY\b',
                r'✓\s*VERIFIED',
                r'VERIFIED\s*[-–]\s*([A-Z\s]+)',  # VERIFIED - NAME pattern
            ]
            
            verification_found = False
            verified_by_name = None
            
            for pattern in verified_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    verification_found = True
                    print(f"[REGULAR] FALLBACK: Found VERIFIED text with pattern '{pattern}': {matches}")
                    
                    # Check for name after VERIFIED
                    name_match = re.search(r'VERIFIED\s*[-–]\s*([A-Z][A-Z\s]{2,20})', page_text, re.IGNORECASE)
                    if name_match:
                        verified_by_name = name_match.group(1).strip()
                        print(f"[REGULAR] FALLBACK: Found verified by name: {verified_by_name}")
                    break
            
            # Add VERIFIED fields if found but not extracted by Claude
            if verification_found:
                if not any(key.lower().startswith('verified') for key in parsed.keys()):
                    print(f"[REGULAR] FALLBACK: Adding missing VERIFIED field")
                    parsed["Verified"] = {
                        "value": "VERIFIED",
                        "confidence": 90
                    }
                    
                if verified_by_name and not any('verified_by' in key.lower() for key in parsed.keys()):
                    print(f"[REGULAR] FALLBACK: Adding missing Verified_By field: {verified_by_name}")
                    parsed["Verified_By"] = {
                        "value": verified_by_name,
                        "confidence": 85
                    }

            # CRITICAL: Flatten nested objects (Signer1: {Name: "John"} -> Signer1_Name: "John")
            parsed = flatten_nested_objects(parsed)
            print(f"[DEBUG] Flattened nested objects in parsed data")
            
            # Add account number to the result
            parsed["Account_Number"] = account_number
            
            # Cache the result in S3
            cache_data = {
                "account_number": account_number,
                "data": parsed,
                "extracted_at": datetime.now().isoformat()
            }
            
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=cache_key,
                    Body=json.dumps(cache_data),
                    ContentType='application/json'
                )
                print(f"[DEBUG] Cached data to S3: {cache_key}")
            except Exception as s3_error:
                print(f"[WARNING] Failed to cache to S3: {str(s3_error)}")
            
            result_data = {
                "success": True,
                "page_number": page_num + 1,
                "account_number": account_number,
                "data": parsed,
                "cached": False,
                "prompt_version": "v5_enhanced_verified"
            }
            
            # CONSISTENCY FIX: Normalize field names and values before caching
            print(f"[DEBUG] RAW AI RESPONSE BEFORE NORMALIZATION: {parsed}")
            normalized_data = normalize_extraction_result(parsed)
            print(f"[DEBUG] NORMALIZED DATA AFTER PROCESSING: {normalized_data}")
            
            # CONSISTENCY FIX: Ensure consistent field structure
            consistent_data = ensure_consistent_field_structure(normalized_data, page_text)
            print(f"[DEBUG] CONSISTENT DATA AFTER STRUCTURE CHECK: {consistent_data}")
            
            # CONSISTENCY FIX: Log field count for debugging
            field_count = len(consistent_data)
            print(f"[DEBUG] FINAL FIELD COUNT: {field_count} fields")
            print(f"[DEBUG] FIELD NAMES: {list(consistent_data.keys())}")
            
            result_data["data"] = consistent_data
            
            # Cache the result at document level for future consistency
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=doc_cache_key,
                    Body=json.dumps(result_data),
                    ContentType='application/json'
                )
                print(f"[DEBUG] ✓ Cached document-level result for account {account_index} page {page_num} - ENSURES CONSISTENCY")
            except Exception as cache_error:
                print(f"[WARNING] Failed to cache document-level result: {cache_error}")
            
            # CONSISTENCY FIX: Also cache by content hash for deterministic results
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=content_cache_key,
                    Body=json.dumps(result_data),
                    ContentType='application/json'
                )
                print(f"[DEBUG] ✓ Cached content-based result (hash: {content_hash}) - ENSURES SAME CONTENT = SAME RESULT")
            except Exception as cache_error:
                print(f"[WARNING] Failed to cache content-based result: {cache_error}")
            
            response = jsonify(result_data)
            # Prevent browser caching - always fetch fresh data
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        else:
            return jsonify({
                "success": False,
                "message": "Failed to parse AI response"
            }), 500
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] Failed to extract page data: {str(e)}")
        print(f"[ERROR] Traceback: {error_trace}")
        return jsonify({"success": False, "message": str(e), "traceback": error_trace}), 500


@app.route("/api/document/<doc_id>/page/<int:page_num>/extract")
def extract_page_data(doc_id, page_num):
    """Extract data from a specific page - works for any document type"""
    import fitz
    import json
    
    print(f"[DEBUG] extract_page_data called: doc_id={doc_id}, page_num={page_num}")
    
    # CONSISTENCY FIX: Check for document-level extraction cache first
    doc_cache_key = f"document_extraction_cache/{doc_id}_page_{page_num}.json"
    try:
        cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=doc_cache_key)
        cached_data = json.loads(cached_result['Body'].read())
        print(f"[DEBUG] ✓ Using document-level cached result for page {page_num} - GUARANTEED CONSISTENT")
        return jsonify(cached_data)
    except:
        print(f"[DEBUG] No document-level cache found for page {page_num}, extracting fresh")
    
    # Check if force re-extraction is requested
    force = request.args.get('force', 'false').lower() == 'true'
    
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        # For single-page documents or first page, use the document's extracted_fields if available
        # This ensures all data from initial processing is shown
        # BUT: If cache was cleared, force re-extraction
        cache_was_cleared = doc.get("cache_cleared", False)
        
        if page_num == 0 and not force and not cache_was_cleared:
            doc_data = doc.get("documents", [{}])[0] if doc.get("documents") else doc
            extracted_fields = doc_data.get("extracted_fields", {})
            
            if extracted_fields and len(extracted_fields) > 0:
                print(f"[DEBUG] Using document's extracted_fields for page 0 ({len(extracted_fields)} fields)")
                
                # POST-PROCESSING: For death certificates, rename certificate_number to account_number
                doc_type = doc_data.get("document_type", "")
                if doc_type == "death_certificate" or "death" in doc.get("document_name", "").lower():
                    if "certificate_number" in extracted_fields and "account_number" not in extracted_fields:
                        extracted_fields["account_number"] = extracted_fields["certificate_number"]
                        del extracted_fields["certificate_number"]
                        print(f"[DEBUG] Renamed certificate_number to account_number: {extracted_fields['account_number']}")
                    if "Certificate_Number" in extracted_fields and "Account_Number" not in extracted_fields:
                        extracted_fields["Account_Number"] = extracted_fields["Certificate_Number"]
                        del extracted_fields["Certificate_Number"]
                        print(f"[DEBUG] Renamed Certificate_Number to Account_Number: {extracted_fields['Account_Number']}")
                
                # Cache this data to S3 for consistency
                cache_key = f"page_data/{doc_id}/page_{page_num}.json"
                cache_data = {
                    "data": extracted_fields,
                    "extracted_at": datetime.now().isoformat(),
                    "source": "document_fields"
                }
                
                try:
                    s3_client.put_object(
                        Bucket=S3_BUCKET,
                        Key=cache_key,
                        Body=json.dumps(cache_data),
                        ContentType='application/json'
                    )
                    print(f"[DEBUG] Cached document fields to S3: {cache_key}")
                except Exception as s3_error:
                    print(f"[WARNING] Failed to cache to S3: {str(s3_error)}")
                
                return jsonify({
                    "success": True,
                    "page_number": page_num + 1,
                    "data": extracted_fields,
                    "cached": False,
                    "source": "document_fields"
                })
        
        # Check S3 cache first (unless force=true)
        cache_key = f"page_data/{doc_id}/page_{page_num}.json"
        
        if not force:
            try:
                print(f"[DEBUG] Checking S3 cache: {cache_key}")
                cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
                cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
                print(f"[DEBUG] Found cached data in S3")
                
                # CRITICAL: Apply flattening to cached data too!
                cached_fields = cached_data.get("data", {})
                cached_fields = flatten_nested_objects(cached_fields)
                print(f"[DEBUG] Applied flattening to cached data")
                
                return jsonify({
                    "success": True,
                    "page_number": page_num + 1,
                    "data": cached_fields,
                    "cached": True,
                    "edited": cached_data.get("edited", False)
                })
            except s3_client.exceptions.NoSuchKey:
                print(f"[DEBUG] No cache found, will extract data")
            except Exception as cache_error:
                print(f"[DEBUG] Cache check failed: {str(cache_error)}, will extract data")
        else:
            print(f"[DEBUG] Force re-extraction requested, skipping cache")
        
        # Get PDF path
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # Extract text from the specific page
        print(f"[DEBUG] Opening PDF: {pdf_path}")
        pdf_doc = fitz.open(pdf_path)
        
        if page_num >= len(pdf_doc):
            return jsonify({"success": False, "message": "Page number out of range"}), 404
        
        page = pdf_doc[page_num]
        page_text = page.get_text()
        
        # If no text found, use OCR
        if not page_text or len(page_text.strip()) < 50:
            print(f"[DEBUG] Page {page_num} has no text layer, using OCR...")
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            temp_image_path = os.path.join(OUTPUT_DIR, f"temp_page_{doc_id}_{page_num}.png")
            pix.save(temp_image_path)
            
            try:
                with open(temp_image_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                
                textract_response = textract.detect_document_text(
                    Document={'Bytes': image_bytes}
                )
                
                page_text = ""
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        page_text += block.get('Text', '') + "\n"
                
                print(f"[DEBUG] OCR extracted {len(page_text)} characters from page {page_num}")
                
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    
            except Exception as ocr_error:
                print(f"[ERROR] OCR failed: {str(ocr_error)}")
                pdf_doc.close()
                return jsonify({"success": False, "message": f"OCR failed: {str(ocr_error)}"}), 500
        
        pdf_doc.close()
        
        # Extract data using AI
        print(f"[DEBUG] Calling AI to extract data from page {page_num}")
        
        # Detect document type on this page
        detected_type = detect_document_type(page_text)
        print(f"[DEBUG] Detected document type: {detected_type}")
        
        # Use appropriate prompt
        if detected_type == "drivers_license":
            page_extraction_prompt = get_drivers_license_prompt()
            print(f"[DEBUG] Using specialized driver's license prompt")
        else:
            page_extraction_prompt = get_comprehensive_extraction_prompt()
            print(f"[DEBUG] Using comprehensive extraction prompt")
        
        response = call_bedrock(page_extraction_prompt, page_text, max_tokens=8192)
        print(f"[DEBUG] Got response from Bedrock, length: {len(response)}")
        
        # Parse JSON response
        json_start = response.find('{')
        json_end = response.rfind('}')
        
        if json_start != -1 and json_end != -1:
            json_str = response[json_start:json_end + 1]
            parsed = json.loads(json_str)
            
            # Handle driver's license format: unwrap documents array if present
            if detected_type == "drivers_license" and "documents" in parsed:
                if len(parsed["documents"]) > 0:
                    doc_data = parsed["documents"][0]
                    # Extract the fields from extracted_fields
                    if "extracted_fields" in doc_data:
                        parsed = doc_data["extracted_fields"]
                        print(f"[DEBUG] Unwrapped driver's license data: {len(parsed)} fields")
                    else:
                        parsed = doc_data
            
            # KEEP confidence format intact - don't normalize
            # The frontend expects {value: "X", confidence: 95} format
            print(f"[DEBUG] Keeping confidence format intact for frontend processing")
            
            # POST-PROCESSING: For death certificates, rename certificate_number to account_number
            if doc.get("document_type") == "death_certificate" or "death" in doc.get("document_name", "").lower():
                if "certificate_number" in parsed and "account_number" not in parsed:
                    parsed["account_number"] = parsed["certificate_number"]
                    del parsed["certificate_number"]
                if "Certificate_Number" in parsed and "Account_Number" not in parsed:
                    parsed["Account_Number"] = parsed["Certificate_Number"]
                    del parsed["Certificate_Number"]
            
            # Cache the result in S3
            cache_data = {
                "data": parsed,
                "extracted_at": datetime.now().isoformat()
            }
            
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=cache_key,
                    Body=json.dumps(cache_data),
                    ContentType='application/json'
                )
                print(f"[DEBUG] Cached data to S3: {cache_key}")
            except Exception as s3_error:
                print(f"[WARNING] Failed to cache to S3: {str(s3_error)}")
            
            # CONSISTENCY FIX: Cache the result at document level for future consistency
            # CONSISTENCY FIX: Normalize field names and values before caching
            normalized_data = normalize_extraction_result(parsed)
            
            result_data = {
                "success": True,
                "page_number": page_num + 1,
                "data": normalized_data,
                "cached": False
            }
            
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=doc_cache_key,
                    Body=json.dumps(result_data),
                    ContentType='application/json'
                )
                print(f"[DEBUG] ✓ Cached document-level result for page {page_num} - ENSURES CONSISTENCY")
            except Exception as cache_error:
                print(f"[WARNING] Failed to cache document-level result: {cache_error}")
            
            return jsonify(result_data)
        else:
            return jsonify({
                "success": False,
                "message": "Failed to parse AI response"
            }), 500
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] Failed to extract page data: {str(e)}")
        print(f"[ERROR] Traceback: {error_trace}")
        return jsonify({"success": False, "message": str(e)}), 500



@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_index>/extract-progressive", methods=["POST"])
def extract_page_progressive(doc_id, account_index, page_index):
    """Progressive page extraction - extract one page at a time in background"""
    import json
    import time
    from datetime import datetime
    
    print(f"[PROGRESSIVE] Starting extraction for doc {doc_id}, account {account_index}, page {page_index}")
    
    try:
        # Get request data
        data = request.get_json() or {}
        priority = data.get('priority', 2)
        
        # Find the document
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get account info
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if account_index >= len(accounts):
            return jsonify({"success": False, "message": "Account index out of range"}), 400
        
        account = accounts[account_index]
        account_number = account.get("accountNumber", "N/A")
        
        # Get PDF path
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # Use the actual PDF page number for cache key to match regular /data endpoint
        # The page_index parameter is the actual PDF page number from the frontend
        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_index}.json"
        try:
            cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_data = json.loads(cached_result['Body'].read())
            
            # Check prompt version - invalidate old cache
            cached_version = cached_data.get("prompt_version", "v1")
            current_version = "v5_enhanced_verified"
            
            if cached_version != current_version:
                print(f"[PROGRESSIVE] Cache version mismatch ({cached_version} vs {current_version}) - will re-extract")
                raise Exception("Cache version outdated")
            
            # Check if cached data contains only errors or is invalid
            cached_fields = cached_data.get("data", {})
            if isinstance(cached_fields, dict):
                # Skip cache if it only contains error messages
                if len(cached_fields) == 1 and "error" in cached_fields:
                    print(f"[PROGRESSIVE] Cached data contains only error, re-extracting for account {account_number}, page {page_index}")
                    raise Exception("Cached data is invalid, re-extract")
                
                # Skip cache if error message mentions watermarks
                error_msg = cached_fields.get("error", "")
                if "watermark" in str(error_msg).lower() or "pdf-xchange" in str(error_msg).lower():
                    print(f"[PROGRESSIVE] Cached data contains watermark error, re-extracting for account {account_number}, page {page_index}")
                    raise Exception("Cached data contains watermark error, re-extract")
            
            # Always re-extract to get fresh data with enhanced VERIFIED detection
            print(f"[PROGRESSIVE] Forcing fresh extraction for account {account_number}, page {page_index}")
            raise Exception("Force fresh extraction")
                
        except Exception as e:
            print(f"[PROGRESSIVE] Extracting fresh for account {account_number}, page {page_index}: {str(e)}")
        
        # Extract text from the specific page
        import fitz
        pdf_doc = fitz.open(pdf_path)
        
        print(f"[PROGRESSIVE] PDF has {len(pdf_doc)} pages, extracting page {page_index} (0-based)")
        
        if page_index >= len(pdf_doc):
            pdf_doc.close()
            return jsonify({"success": False, "message": f"Page index {page_index} out of range (PDF has {len(pdf_doc)} pages)"}), 400
        
        page = pdf_doc[page_index]
        page_text = page.get_text()
        
        print(f"[PROGRESSIVE] Extracted {len(page_text)} characters from page {page_index}")
        print(f"[PROGRESSIVE] First 200 chars: {page_text[:200]}")
        
        # Check for watermark content and apply OCR if needed
        has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
        has_little_text = len(page_text.strip()) < 100
        
        if has_watermark or has_little_text:
            print(f"[PROGRESSIVE] Page {page_index} needs OCR (watermark: {has_watermark}, little text: {has_little_text})")
            
            try:
                # Convert page to image with higher resolution for better OCR
                # Note: PDF is still open, so we can access the page
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution
                
                temp_image_path = os.path.join(OUTPUT_DIR, f"temp_progressive_{doc_id}_{page_index}.png")
                pix.save(temp_image_path)
                
                with open(temp_image_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                
                print(f"[PROGRESSIVE] Running Textract OCR on page {page_index}...")
                
                # Use Textract for OCR
                textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                
                ocr_text = ""
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        ocr_text += block.get('Text', '') + "\n"
                
                # Clean up temp file
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                
                if ocr_text.strip() and len(ocr_text.strip()) > len(page_text.strip()):
                    page_text = ocr_text
                    print(f"[PROGRESSIVE] ✓ OCR extracted {len(page_text)} characters from page {page_index}")
                    print(f"[PROGRESSIVE] OCR first 200 chars: {page_text[:200]}")
                else:
                    print(f"[PROGRESSIVE] OCR didn't improve text for page {page_index}")
                    
            except Exception as ocr_error:
                print(f"[PROGRESSIVE] OCR error on page {page_index}: {str(ocr_error)}")
        
        # Close PDF after text extraction and OCR
        pdf_doc.close()
        
        if not page_text.strip():
            return jsonify({"success": False, "message": "No text found on page"}), 400
        
        # Use Claude AI to extract data from this page
        import boto3
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        # Get document type for appropriate prompt
        doc_type = doc.get("document_type_info", {}).get("type", "unknown")
        
        # Use comprehensive extraction prompt with enhanced VERIFIED detection
        prompt = """
You are a data extraction expert. Extract ALL structured data from this document page.

🔴🔴🔴 CRITICAL PRIORITY #1: VERIFICATION DETECTION 🔴🔴🔴
**THIS IS THE MOST IMPORTANT TASK - NEVER SKIP VERIFICATION DETECTION**

**STEP 1: MANDATORY VERIFICATION SCAN (DO THIS FIRST):**
Before extracting any other data, you MUST scan the ENTIRE page for verification indicators:

1. **SEARCH FOR "VERIFIED" TEXT EVERYWHERE:**
   - Look for "VERIFIED" stamps, seals, or text ANYWHERE on the page
   - Look for "VERIFICATION" text or stamps  
   - Look for "VERIFY" or "VERIFIED BY" text
   - Look for checkboxes or boxes marked with "VERIFIED"
   - Look for "✓ VERIFIED" or similar checkmark combinations
   - Search in margins, corners, stamps, seals, form fields, and document body
   - Extract as: Verified: {"value": "VERIFIED", "confidence": 95}

2. **SEARCH FOR NAMES NEAR VERIFICATION:**
   - Look for names immediately after "VERIFIED" (like "VERIFIED - RENDA", "VERIFIED BRENDA HALLSTEAT")
   - Look for "VERIFIED BY: [NAME]" patterns
   - Look for names in verification stamps or seals
   - Extract as: Verified_By: {"value": "Name", "confidence": 85}
   
3. **SEARCH FOR VERIFICATION DATES:**
   - Look for dates on or near verification stamps
   - Look for "VERIFIED ON: [DATE]" patterns
   - Extract as: Verified_Date: {"value": "Date", "confidence": 85}

🚨 **VERIFICATION DETECTION RULES:**
- **NEVER** skip verification detection - it must be checked on EVERY page
- **ALWAYS** scan the ENTIRE page text for "VERIFIED" (case-insensitive)
- **ALWAYS** extract verification fields if found, even if unclear
- If you find ANY verification indicator, you MUST extract it
- Look in ALL parts of the page: headers, footers, margins, stamps, seals, form fields

🔴🔴🔴 VERIFICATION EXAMPLES - STUDY THESE PATTERNS 🔴🔴🔴

**COMMON VERIFICATION PATTERNS TO LOOK FOR:**
- "VERIFIED" (standalone stamp)
- "VERIFIED - [NAME]" (stamp with name)
- "VERIFIED BY: [NAME]" (formal verification)
- "VERIFIED [FULL NAME]" (like "VERIFIED BRENDA HALLSTEAT")
- "✓ VERIFIED" (checkmark with verified)
- "VERIFICATION COMPLETE" (process completion)
- "DOCUMENT VERIFIED" (document validation)
- "IDENTITY VERIFIED" (identity confirmation)
- "SIGNATURE VERIFIED" (signature validation)

**EXAMPLE EXTRACTIONS:**
- Text: "VERIFIED" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}
- Text: "VERIFIED - RENDA" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "RENDA", "confidence": 90}
- Text: "VERIFIED BRENDA HALLSTEAT" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "BRENDA HALLSTEAT", "confidence": 90}
- Text: "VERIFIED BY: MARIA SANTOS" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "MARIA SANTOS", "confidence": 90}
- Text: "✓ VERIFIED 03/15/2024" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_Date: {"value": "03/15/2024", "confidence": 90}
- Text: "VERIFICATION COMPLETE" → Extract: Verified: {"value": "VERIFIED", "confidence": 90}

🚨 **CRITICAL REMINDER:**
- Verification detection is MANDATORY on every page
- Even if the text is unclear, extract it with lower confidence
- Look in ALL areas of the page, not just the main content
- If you're unsure, extract it anyway - better to have false positives than miss verification

**STEP 2: OTHER CRITICAL FIELDS (AFTER VERIFICATION):**
After completing verification detection, extract these fields:

4. **IDENTIFYING NUMBERS** - Extract ALL significant numbers:
   - Certificate Numbers (like "22156777") - Extract as Certificate_Number
   - Account Numbers - Extract as Account_Number
   - File Numbers - Extract as File_Number
   - State File Numbers - Extract as State_File_Number
   - Any 6-12 digit numbers - Extract as Account_Number

5. **NAMES** - All person names:
   - Main person name - Extract as Full_Name or Deceased_Name
   - Registrar names - Extract as Registrar_Name
   - Any other names - Extract with appropriate field names

6. **ADDRESSES** - Full addresses - Extract as Address, Residence_Address, etc.

7. **DATES** - All dates:
   - Birth dates - Extract as Date_of_Birth
   - Death dates - Extract as Date_of_Death
   - Issue dates - Extract as Issue_Date
   - Stamp dates - Extract as Stamp_Date

8. **OTHER INFORMATION:**
   - Phone numbers - Extract as Phone_Number
   - SSN - Extract as SSN
   - Places - Extract as Place_of_Birth, Place_of_Death, etc.

Return ONLY valid JSON in this format:
{
  "Field_Name": {
    "value": "extracted value",
    "confidence": 95
  }
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain

🔴 REMEMBER: ALWAYS check for "VERIFIED" text on EVERY page - this is mandatory!
"""
        
        # Call Claude AI
        claude_request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": f"{prompt}\n\nPage text:\n{page_text}"
            }]
        }
        
        start_time = time.time()
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(claude_request)
        )
        
        response_body = json.loads(response['body'].read())
        claude_response = response_body['content'][0]['text']
        
        # Parse extracted data with better error handling
        try:
            print(f"[PROGRESSIVE] Claude response length: {len(claude_response)}")
            print(f"[PROGRESSIVE] Claude response preview: {claude_response[:300]}...")
            
            if not claude_response.strip():
                print(f"[PROGRESSIVE] Empty response from Claude AI")
                return jsonify({"success": False, "message": "Empty response from Claude AI"}), 500
            
            # Clean up Claude response - sometimes it includes extra text
            claude_response_clean = claude_response.strip()
            
            # Try to extract JSON from the response
            json_start = claude_response_clean.find('{')
            json_end = claude_response_clean.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = claude_response_clean[json_start:json_end]
                extracted_fields = json.loads(json_text)
            else:
                # Fallback: try to parse the entire response
                extracted_fields = json.loads(claude_response_clean)
            
            # MANDATORY: Always check for VERIFIED text using regex fallback with enhanced name detection
            import re
            
            # ENHANCED VERIFIED DETECTION - Check for VERIFIED text in the page content with comprehensive patterns
            verified_patterns = [
                r'\bVERIFIED\b',
                r'\bVERIFICATION\b', 
                r'\bVERIFY\b',
                r'✓\s*VERIFIED',
                r'VERIFIED\s*[-–]\s*([A-Z][A-Z\s]{2,30})',  # VERIFIED - NAME pattern
                r'VERIFIED\s*BY\s*:?\s*([A-Z][A-Z\s]{2,30})',  # VERIFIED BY: NAME pattern
                r'VERIFIED\s*:\s*([A-Z][A-Z\s]{2,30})',  # VERIFIED: NAME pattern
                r'VERIFIED\s+([A-Z][A-Z\s]{2,30})',        # VERIFIED FULL NAME (like "VERIFIED BRENDA HALLSTEAT")
                r'☑\s*VERIFIED',  # Checkbox with VERIFIED
                r'✓.*VERIFIED',   # Checkmark with VERIFIED
                r'VERIFIED.*✓',   # VERIFIED with checkmark
            ]
            
            verification_found = False
            verified_by_name = None
            
            # Check each pattern and log what we find
            for pattern in verified_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    verification_found = True
                    print(f"[PROGRESSIVE] FALLBACK: Found VERIFIED text with pattern '{pattern}': {matches}")
                    
                    # Try to extract name from the match if it's a capturing group
                    if matches and isinstance(matches[0], str) and len(matches[0]) > 1:
                        potential_name = matches[0].strip()
                        if len(potential_name) > 2 and not potential_name.upper() == "VERIFIED":
                            verified_by_name = potential_name
                            print(f"[PROGRESSIVE] FALLBACK: Extracted name from pattern: '{verified_by_name}'")
                    break
            
            # Additional comprehensive search for VERIFIED text
            if not verification_found:
                # Case-insensitive search for any occurrence of "verified"
                if re.search(r'verified', page_text, re.IGNORECASE):
                    verification_found = True
                    print(f"[PROGRESSIVE] FALLBACK: Found 'verified' text (case-insensitive)")
                
                # Search for common verification phrases
                verification_phrases = [
                    r'verification\s+complete',
                    r'document\s+verified',
                    r'identity\s+verified',
                    r'signature\s+verified',
                    r'verified\s+copy',
                    r'verified\s+true',
                    r'verified\s+correct'
                ]
                
                for phrase in verification_phrases:
                    if re.search(phrase, page_text, re.IGNORECASE):
                        verification_found = True
                        print(f"[PROGRESSIVE] FALLBACK: Found verification phrase: '{phrase}'")
                        break
            
            # Enhanced name extraction - try multiple patterns to get complete names like "BRENDA HALLSTEAT"
            if verification_found and not verified_by_name:
                name_patterns = [
                    r'VERIFIED\s*[-–]\s*([A-Z][A-Z\s]{2,30})',  # VERIFIED - FULL NAME (extended length)
                    r'VERIFIED\s+([A-Z][A-Z\s]{2,30})',        # VERIFIED FULL NAME (no dash) - like "VERIFIED BRENDA HALLSTEAT"
                    r'VERIFIED\s*:\s*([A-Z][A-Z\s]{2,30})',    # VERIFIED: FULL NAME
                    r'VERIFIED\s*BY\s*:?\s*([A-Z][A-Z\s]{2,30})', # VERIFIED BY: FULL NAME
                    r'VERIFIED\s*[-–]\s*([A-Z]+\s+[A-Z]+)',    # VERIFIED - FIRSTNAME LASTNAME
                    r'VERIFIED\s*BY\s*([A-Z]+)',               # VERIFIED BY NAME (single word)
                    r'VERIFIED\s*-\s*([A-Z]+)',                # VERIFIED - NAME (single word)
                ]
                
                for name_pattern in name_patterns:
                    name_match = re.search(name_pattern, page_text, re.IGNORECASE)
                    if name_match:
                        full_name = name_match.group(1).strip()
                        # Clean up the name - remove extra spaces and validate
                        full_name = re.sub(r'\s+', ' ', full_name)  # Replace multiple spaces with single space
                        
                        # Accept names that look valid (1+ words, reasonable length)
                        if len(full_name) >= 2 and len(full_name) <= 30:
                            verified_by_name = full_name
                            print(f"[PROGRESSIVE] FALLBACK: Found complete verified by name: '{verified_by_name}' using pattern '{name_pattern}'")
                            break
                
                # If no name found with patterns, try a broader search around VERIFIED
                if not verified_by_name:
                    # Look for names within 100 characters after VERIFIED (increased range)
                    verified_context = re.search(r'VERIFIED.{0,100}', page_text, re.IGNORECASE | re.DOTALL)
                    if verified_context:
                        context_text = verified_context.group(0)
                        print(f"[PROGRESSIVE] FALLBACK: Searching for names in context: '{context_text[:100]}...'")
                        
                        # Extract potential names (capitalized words)
                        name_candidates = re.findall(r'\b[A-Z][A-Z\s]{1,25}\b', context_text)
                        for candidate in name_candidates:
                            candidate = candidate.strip()
                            # Skip if it's just "VERIFIED" or common words
                            skip_words = ["VERIFIED", "BY", "DATE", "STAMP", "SEAL", "DOCUMENT", "COPY", "TRUE", "CORRECT"]
                            if candidate not in skip_words and len(candidate) >= 2:
                                verified_by_name = candidate
                                print(f"[PROGRESSIVE] FALLBACK: Found verified by name from context: '{verified_by_name}'")
                                break
                    
                    # Also try looking before VERIFIED
                    if not verified_by_name:
                        verified_context_before = re.search(r'.{0,50}VERIFIED', page_text, re.IGNORECASE | re.DOTALL)
                        if verified_context_before:
                            context_text = verified_context_before.group(0)
                            # Look for names right before VERIFIED
                            name_candidates = re.findall(r'\b[A-Z][A-Z\s]{1,25}\b', context_text)
                            if name_candidates:
                                # Take the last name candidate (closest to VERIFIED)
                                candidate = name_candidates[-1].strip()
                                skip_words = ["VERIFIED", "BY", "DATE", "STAMP", "SEAL", "DOCUMENT", "COPY", "TRUE", "CORRECT"]
                                if candidate not in skip_words and len(candidate) >= 2:
                                    verified_by_name = candidate
                                    print(f"[PROGRESSIVE] FALLBACK: Found verified by name before VERIFIED: '{verified_by_name}'")
            
            # CRITICAL: Always add VERIFIED fields if found, even if Claude extracted them
            # This ensures consistency and prevents missing VERIFIED detection
            if verification_found:
                # Always add or update the Verified field
                verified_field_exists = any(key.lower().startswith('verified') and not 'by' in key.lower() for key in extracted_fields.keys())
                
                if not verified_field_exists:
                    print(f"[PROGRESSIVE] FALLBACK: Adding missing VERIFIED field")
                    extracted_fields["Verified"] = {
                        "value": "VERIFIED",
                        "confidence": 95
                    }
                else:
                    print(f"[PROGRESSIVE] FALLBACK: VERIFIED field already exists, ensuring it's marked as found")
                    # Update confidence if Claude found it with lower confidence
                    for key in extracted_fields.keys():
                        if key.lower().startswith('verified') and not 'by' in key.lower():
                            if extracted_fields[key].get("confidence", 0) < 95:
                                extracted_fields[key]["confidence"] = 95
                                print(f"[PROGRESSIVE] FALLBACK: Updated {key} confidence to 95")
                
                # Add verified by name if found
                if verified_by_name:
                    verified_by_exists = any('verified_by' in key.lower() or 'verifiedby' in key.lower() for key in extracted_fields.keys())
                    
                    if not verified_by_exists:
                        print(f"[PROGRESSIVE] FALLBACK: Adding missing Verified_By field: {verified_by_name}")
                        extracted_fields["Verified_By"] = {
                            "value": verified_by_name,
                            "confidence": 85
                        }
                    else:
                        print(f"[PROGRESSIVE] FALLBACK: Verified_By field already exists")
                
                # Log final verification status
                print(f"[PROGRESSIVE] VERIFICATION SUMMARY:")
                print(f"  - Verification found: {verification_found}")
                print(f"  - Verified by name: {verified_by_name}")
                print(f"  - Total VERIFIED fields in result: {len([k for k in extracted_fields.keys() if 'verified' in k.lower()])}")
                
                # Show all verification-related fields
                for key, value in extracted_fields.items():
                    if 'verified' in key.lower():
                        print(f"  - {key}: {value}")
            else:
                print(f"[PROGRESSIVE] VERIFICATION SUMMARY: No VERIFIED text found on this page")
                print(f"[PROGRESSIVE] Page text sample for verification check: {page_text[:300]}...")

            print(f"[PROGRESSIVE] Successfully parsed {len(extracted_fields)} fields")
            
        except json.JSONDecodeError as e:
            print(f"[PROGRESSIVE] JSON parse error: {e}")
            print(f"[PROGRESSIVE] Raw Claude response: '{claude_response}'")
            return jsonify({"success": False, "message": f"Failed to parse extraction result: {str(e)}"}), 500
        
        extraction_time = time.time() - start_time
        
        # Cache the result in the same format as regular /data endpoint
        cache_data = {
            "success": True,
            "page_number": page_index + 1,
            "account_number": account_number,
            "data": extracted_fields,
            "cached": False,
            "prompt_version": "v5_enhanced_verified",  # Updated version to invalidate old cache
            "extraction_method": "progressive",
            "extracted_at": datetime.now().isoformat(),
            "extraction_time_seconds": round(extraction_time, 2),
            "priority": priority,
            "doc_type": doc_type
        }
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            print(f"[PROGRESSIVE] ✓ Cached extraction result: {cache_key}")
        except Exception as s3_error:
            print(f"[PROGRESSIVE] Warning: Failed to cache result: {s3_error}")
        
        fields_count = len(extracted_fields)
        print(f"[PROGRESSIVE] ✅ Extracted {fields_count} fields from account {account_number}, page {page_index} in {extraction_time:.2f}s")
        
        return jsonify({
            "success": True,
            "cached": False,
            "fieldsExtracted": fields_count,
            "extractedAt": datetime.now().isoformat(),
            "accountNumber": account_number,
            "extractionTime": round(extraction_time, 2),
            "extractedFields": extracted_fields
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[PROGRESSIVE] Error extracting page: {str(e)}")
        print(f"[PROGRESSIVE] Traceback: {error_trace}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/page/<int:page_index>/extract-progressive", methods=["POST"])
def extract_regular_page_progressive(doc_id, page_index):
    """Progressive page extraction for regular documents (non-account-based) - extract one page at a time in background"""
    import json
    import time
    from datetime import datetime
    
    print(f"[PROGRESSIVE-REGULAR] Starting regular page extraction for doc {doc_id}, page {page_index}")
    
    try:
        # Get request data
        data = request.get_json() or {}
        priority = data.get('priority', 2)
        
        # Find the document
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get PDF path
        pdf_path = doc.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"success": False, "message": "PDF file not found"}), 404
        
        # Use regular page cache key (no account index)
        cache_key = f"page_data/{doc_id}/page_{page_index}.json"
        try:
            cached_result = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_data = json.loads(cached_result['Body'].read())
            
            # Check prompt version - invalidate old cache
            cached_version = cached_data.get("prompt_version", "v1")
            current_version = "v5_enhanced_verified"
            
            if cached_version != current_version:
                print(f"[PROGRESSIVE-REGULAR] Cache version mismatch ({cached_version} vs {current_version}) - will re-extract")
                raise Exception("Cache version outdated")
            
            # Check if cached data contains only errors or is invalid
            cached_fields = cached_data.get("data", {})
            if isinstance(cached_fields, dict):
                # Skip cache if it only contains error messages
                if len(cached_fields) == 1 and "error" in cached_fields:
                    print(f"[PROGRESSIVE-REGULAR] Cached data contains only error, re-extracting page {page_index}")
                    raise Exception("Cached data is invalid, re-extract")
                
                # Skip cache if error message mentions watermarks
                error_msg = cached_fields.get("error", "")
                if "watermark" in str(error_msg).lower() or "pdf-xchange" in str(error_msg).lower():
                    print(f"[PROGRESSIVE-REGULAR] Cached data contains watermark error, re-extracting page {page_index}")
                    raise Exception("Cached data contains watermark error, re-extract")
            
            # Always re-extract to get fresh data with enhanced VERIFIED detection
            print(f"[PROGRESSIVE-REGULAR] Forcing fresh extraction for page {page_index}")
            raise Exception("Force fresh extraction")
                
        except Exception as e:
            print(f"[PROGRESSIVE-REGULAR] Extracting fresh for page {page_index}: {str(e)}")
        
        # Extract text from the specific page
        import fitz
        pdf_doc = fitz.open(pdf_path)
        
        print(f"[PROGRESSIVE-REGULAR] PDF has {len(pdf_doc)} pages, extracting page {page_index} (0-based)")
        
        if page_index >= len(pdf_doc):
            pdf_doc.close()
            return jsonify({"success": False, "message": f"Page index {page_index} out of range (PDF has {len(pdf_doc)} pages)"}), 400
        
        page = pdf_doc[page_index]
        page_text = page.get_text()
        
        print(f"[PROGRESSIVE-REGULAR] Extracted {len(page_text)} characters from page {page_index}")
        print(f"[PROGRESSIVE-REGULAR] First 200 chars: {page_text[:200]}")
        
        # Check for watermark content and apply OCR if needed
        has_watermark = "PDF-XChange" in page_text or "Click to BUY NOW" in page_text
        has_little_text = len(page_text.strip()) < 100
        
        if has_watermark or has_little_text:
            print(f"[PROGRESSIVE-REGULAR] Page {page_index} needs OCR (watermark: {has_watermark}, little text: {has_little_text})")
            
            try:
                # Convert page to image with higher resolution for better OCR
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution
                
                temp_image_path = os.path.join(OUTPUT_DIR, f"temp_progressive_regular_{doc_id}_{page_index}.png")
                pix.save(temp_image_path)
                
                with open(temp_image_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                
                print(f"[PROGRESSIVE-REGULAR] Running Textract OCR on page {page_index}...")
                
                # Use Textract for OCR
                textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                
                ocr_text = ""
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        ocr_text += block.get('Text', '') + "\n"
                
                # Clean up temp file
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                
                if ocr_text.strip() and len(ocr_text.strip()) > len(page_text.strip()):
                    page_text = ocr_text
                    print(f"[PROGRESSIVE-REGULAR] ✓ OCR extracted {len(page_text)} characters from page {page_index}")
                    print(f"[PROGRESSIVE-REGULAR] OCR first 200 chars: {page_text[:200]}")
                else:
                    print(f"[PROGRESSIVE-REGULAR] OCR didn't improve text for page {page_index}")
                    
            except Exception as ocr_error:
                print(f"[PROGRESSIVE-REGULAR] OCR error on page {page_index}: {str(ocr_error)}")
        
        # Close PDF after text extraction and OCR
        pdf_doc.close()
        
        if not page_text.strip():
            return jsonify({"success": False, "message": "No text found on page"}), 400
        
        # Use Claude AI to extract data from this page
        import boto3
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        # Get document type for appropriate prompt
        doc_type = doc.get("document_type_info", {}).get("type", "unknown")
        
        # Use comprehensive extraction prompt with enhanced VERIFIED detection
        prompt = get_comprehensive_extraction_prompt()
        
        # Call Claude AI
        claude_request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": f"{prompt}\n\nPage text:\n{page_text}"
            }]
        }
        
        start_time = time.time()
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(claude_request)
        )
        
        response_body = json.loads(response['body'].read())
        claude_response = response_body['content'][0]['text']
        
        # Parse extracted data with better error handling
        try:
            print(f"[PROGRESSIVE-REGULAR] Claude response length: {len(claude_response)}")
            print(f"[PROGRESSIVE-REGULAR] Claude response preview: {claude_response[:300]}...")
            
            if not claude_response.strip():
                print(f"[PROGRESSIVE-REGULAR] Empty response from Claude AI")
                return jsonify({"success": False, "message": "Empty response from Claude AI"}), 500
            
            # Clean up Claude response - sometimes it includes extra text
            claude_response_clean = claude_response.strip()
            
            # Try to extract JSON from the response
            json_start = claude_response_clean.find('{')
            json_end = claude_response_clean.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = claude_response_clean[json_start:json_end]
                extracted_fields = json.loads(json_text)
            else:
                # Fallback: try to parse the entire response
                extracted_fields = json.loads(claude_response_clean)
            
            # MANDATORY: Always check for VERIFIED text using regex fallback (same as account-based)
            import re
            
            # ENHANCED VERIFIED DETECTION - Check for VERIFIED text in the page content with comprehensive patterns
            verified_patterns = [
                r'\bVERIFIED\b',
                r'\bVERIFICATION\b', 
                r'\bVERIFY\b',
                r'✓\s*VERIFIED',
                r'VERIFIED\s*[-–]\s*([A-Z\s]+)',  # VERIFIED - NAME pattern
                r'VERIFIED\s*BY\s*:?\s*([A-Z\s]+)',  # VERIFIED BY: NAME pattern
                r'VERIFIED\s*:\s*([A-Z\s]+)',  # VERIFIED: NAME pattern
                r'☑\s*VERIFIED',  # Checkbox with VERIFIED
                r'✓.*VERIFIED',   # Checkmark with VERIFIED
                r'VERIFIED.*✓',   # VERIFIED with checkmark
            ]
            
            verification_found = False
            verified_by_name = None
            
            # Check each pattern and log what we find
            for pattern in verified_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    verification_found = True
                    print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found VERIFIED text with pattern '{pattern}': {matches}")
                    
                    # Try to extract name from the match if it's a capturing group
                    if matches and isinstance(matches[0], str) and len(matches[0]) > 1:
                        potential_name = matches[0].strip()
                        if len(potential_name) > 2 and not potential_name.upper() == "VERIFIED":
                            verified_by_name = potential_name
                            print(f"[PROGRESSIVE-REGULAR] FALLBACK: Extracted name from pattern: '{verified_by_name}'")
                    break
            
            # Additional comprehensive search for VERIFIED text
            if not verification_found:
                # Case-insensitive search for any occurrence of "verified"
                if re.search(r'verified', page_text, re.IGNORECASE):
                    verification_found = True
                    print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found 'verified' text (case-insensitive)")
                
                # Search for common verification phrases
                verification_phrases = [
                    r'verification\s+complete',
                    r'document\s+verified',
                    r'identity\s+verified',
                    r'signature\s+verified',
                    r'verified\s+copy',
                    r'verified\s+true',
                    r'verified\s+correct'
                ]
                
                for phrase in verification_phrases:
                    if re.search(phrase, page_text, re.IGNORECASE):
                        verification_found = True
                        print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found verification phrase: '{phrase}'")
                        break
            
            # Enhanced name extraction - try multiple patterns to get complete names
            if verification_found and not verified_by_name:
                name_patterns = [
                    r'VERIFIED\s*[-–]\s*([A-Z][A-Z\s]{2,30})',  # VERIFIED - FULL NAME (extended length)
                    r'VERIFIED\s+([A-Z][A-Z\s]{2,30})',        # VERIFIED FULL NAME (no dash)
                    r'VERIFIED\s*:\s*([A-Z][A-Z\s]{2,30})',    # VERIFIED: FULL NAME
                    r'VERIFIED\s*BY\s*:?\s*([A-Z][A-Z\s]{2,30})', # VERIFIED BY: FULL NAME
                    r'VERIFIED\s*[-–]\s*([A-Z]+\s+[A-Z]+)',    # VERIFIED - FIRSTNAME LASTNAME
                    r'VERIFIED\s*BY\s*([A-Z]+)',               # VERIFIED BY NAME (single word)
                    r'VERIFIED\s*-\s*([A-Z]+)',                # VERIFIED - NAME (single word)
                ]
                
                for name_pattern in name_patterns:
                    name_match = re.search(name_pattern, page_text, re.IGNORECASE)
                    if name_match:
                        full_name = name_match.group(1).strip()
                        # Clean up the name - remove extra spaces and validate
                        full_name = re.sub(r'\s+', ' ', full_name)  # Replace multiple spaces with single space
                        
                        # Accept names that look valid (1+ words, reasonable length)
                        if len(full_name) >= 2 and len(full_name) <= 30:
                            verified_by_name = full_name
                            print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found complete verified by name: '{verified_by_name}' using pattern '{name_pattern}'")
                            break
                
                # If no name found with patterns, try a broader search around VERIFIED
                if not verified_by_name:
                    # Look for names within 100 characters after VERIFIED (increased range)
                    verified_context = re.search(r'VERIFIED.{0,100}', page_text, re.IGNORECASE | re.DOTALL)
                    if verified_context:
                        context_text = verified_context.group(0)
                        print(f"[PROGRESSIVE-REGULAR] FALLBACK: Searching for names in context: '{context_text[:100]}...'")
                        
                        # Extract potential names (capitalized words)
                        name_candidates = re.findall(r'\b[A-Z][A-Z\s]{1,25}\b', context_text)
                        for candidate in name_candidates:
                            candidate = candidate.strip()
                            # Skip if it's just "VERIFIED" or common words
                            skip_words = ["VERIFIED", "BY", "DATE", "STAMP", "SEAL", "DOCUMENT", "COPY", "TRUE", "CORRECT"]
                            if candidate not in skip_words and len(candidate) >= 2:
                                verified_by_name = candidate
                                print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found verified by name from context: '{verified_by_name}'")
                                break
                    
                    # Also try looking before VERIFIED
                    if not verified_by_name:
                        verified_context_before = re.search(r'.{0,50}VERIFIED', page_text, re.IGNORECASE | re.DOTALL)
                        if verified_context_before:
                            context_text = verified_context_before.group(0)
                            # Look for names right before VERIFIED
                            name_candidates = re.findall(r'\b[A-Z][A-Z\s]{1,25}\b', context_text)
                            if name_candidates:
                                # Take the last name candidate (closest to VERIFIED)
                                candidate = name_candidates[-1].strip()
                                skip_words = ["VERIFIED", "BY", "DATE", "STAMP", "SEAL", "DOCUMENT", "COPY", "TRUE", "CORRECT"]
                                if candidate not in skip_words and len(candidate) >= 2:
                                    verified_by_name = candidate
                                    print(f"[PROGRESSIVE-REGULAR] FALLBACK: Found verified by name before VERIFIED: '{verified_by_name}'")
            
            # CRITICAL: Always add VERIFIED fields if found, even if Claude extracted them
            # This ensures consistency and prevents missing VERIFIED detection
            if verification_found:
                # Always add or update the Verified field
                verified_field_exists = any(key.lower().startswith('verified') and not 'by' in key.lower() for key in extracted_fields.keys())
                
                if not verified_field_exists:
                    print(f"[PROGRESSIVE-REGULAR] FALLBACK: Adding missing VERIFIED field")
                    extracted_fields["Verified"] = {
                        "value": "VERIFIED",
                        "confidence": 95
                    }
                else:
                    print(f"[PROGRESSIVE-REGULAR] FALLBACK: VERIFIED field already exists, ensuring it's marked as found")
                    # Update confidence if Claude found it with lower confidence
                    for key in extracted_fields.keys():
                        if key.lower().startswith('verified') and not 'by' in key.lower():
                            if extracted_fields[key].get("confidence", 0) < 95:
                                extracted_fields[key]["confidence"] = 95
                                print(f"[PROGRESSIVE-REGULAR] FALLBACK: Updated {key} confidence to 95")
                
                # Add verified by name if found
                if verified_by_name:
                    verified_by_exists = any('verified_by' in key.lower() or 'verifiedby' in key.lower() for key in extracted_fields.keys())
                    
                    if not verified_by_exists:
                        print(f"[PROGRESSIVE-REGULAR] FALLBACK: Adding missing Verified_By field: {verified_by_name}")
                        extracted_fields["Verified_By"] = {
                            "value": verified_by_name,
                            "confidence": 85
                        }
                    else:
                        print(f"[PROGRESSIVE-REGULAR] FALLBACK: Verified_By field already exists")
                
                # Log final verification status
                print(f"[PROGRESSIVE-REGULAR] VERIFICATION SUMMARY:")
                print(f"  - Verification found: {verification_found}")
                print(f"  - Verified by name: {verified_by_name}")
                print(f"  - Total VERIFIED fields in result: {len([k for k in extracted_fields.keys() if 'verified' in k.lower()])}")
                
                # Show all verification-related fields
                for key, value in extracted_fields.items():
                    if 'verified' in key.lower():
                        print(f"  - {key}: {value}")
            else:
                print(f"[PROGRESSIVE-REGULAR] VERIFICATION SUMMARY: No VERIFIED text found on this page")
                print(f"[PROGRESSIVE-REGULAR] Page text sample for verification check: {page_text[:300]}...")
            
            print(f"[PROGRESSIVE-REGULAR] Successfully parsed {len(extracted_fields)} fields")
            
        except json.JSONDecodeError as e:
            print(f"[PROGRESSIVE-REGULAR] JSON parse error: {e}")
            print(f"[PROGRESSIVE-REGULAR] Raw Claude response: '{claude_response}'")
            return jsonify({"success": False, "message": f"Failed to parse extraction result: {str(e)}"}), 500
        
        extraction_time = time.time() - start_time
        
        # Cache the result in the same format as regular /data endpoint
        cache_data = {
            "success": True,
            "page_number": page_index + 1,
            "data": extracted_fields,
            "cached": False,
            "prompt_version": "v5_enhanced_verified",  # Updated version to invalidate old cache
            "extraction_method": "progressive_regular",
            "extracted_at": datetime.now().isoformat(),
            "extraction_time_seconds": round(extraction_time, 2),
            "priority": priority,
            "doc_type": doc_type
        }
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            print(f"[PROGRESSIVE-REGULAR] ✓ Cached extraction result: {cache_key}")
        except Exception as s3_error:
            print(f"[PROGRESSIVE-REGULAR] Warning: Failed to cache result: {s3_error}")
        
        fields_count = len(extracted_fields)
        print(f"[PROGRESSIVE-REGULAR] ✅ Extracted {fields_count} fields from page {page_index} in {extraction_time:.2f}s")
        
        return jsonify({
            "success": True,
            "cached": False,
            "fieldsExtracted": fields_count,
            "extractedAt": datetime.now().isoformat(),
            "extractionTime": round(extraction_time, 2),
            "extractedFields": extracted_fields
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[PROGRESSIVE-REGULAR] Error extracting page: {str(e)}")
        print(f"[PROGRESSIVE-REGULAR] Traceback: {error_trace}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/page/<int:page_num>/update", methods=["POST"])
def update_page_data(doc_id, page_num):
    """Update page data and save to S3 cache"""
    import json
    
    try:
        data = request.get_json()
        page_data = data.get("page_data")
        account_index = data.get("account_index")  # Get account index if provided
        
        if not page_data:
            return jsonify({"success": False, "message": "No page data provided"}), 400
        
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Determine cache key based on whether this is an account-based document
        if account_index is not None:
            # Account-based document (loan documents)
            cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
            print(f"[INFO] Updating account-based cache: {cache_key}")
        else:
            # Regular document
            cache_key = f"page_data/{doc_id}/page_{page_num}.json"
            print(f"[INFO] Updating regular cache: {cache_key}")
        
        # Get existing cache to preserve metadata
        try:
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            existing_cache = json.loads(cache_response['Body'].read().decode('utf-8'))
            account_number = existing_cache.get("account_number")
        except:
            account_number = None
        
        cache_data = {
            "data": page_data,
            "extracted_at": datetime.now().isoformat(),
            "edited": True,
            "edited_at": datetime.now().isoformat()
        }
        
        if account_number:
            cache_data["account_number"] = account_number
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            print(f"[INFO] Updated cache: {cache_key}")
            return jsonify({"success": True, "message": "Page data updated successfully"})
        except Exception as s3_error:
            print(f"[ERROR] Failed to update cache: {str(s3_error)}")
            return jsonify({"success": False, "message": f"Failed to update cache: {str(s3_error)}"}), 500
    
    except Exception as e:
        print(f"[ERROR] Failed to update page data: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/delete", methods=["DELETE", "POST"])
def delete_document(doc_id):
    """Delete a processed document"""
    global processed_documents
    
    # Find document
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404
    
    try:
        # Delete OCR file if exists
        if "ocr_file" in doc and doc["ocr_file"] and os.path.exists(doc["ocr_file"]):
            os.remove(doc["ocr_file"])
            print(f"[INFO] Deleted OCR file: {doc['ocr_file']}")
        
        # Delete PDF file if exists
        if "pdf_path" in doc and doc["pdf_path"] and os.path.exists(doc["pdf_path"]):
            os.remove(doc["pdf_path"])
            print(f"[INFO] Deleted PDF file: {doc['pdf_path']}")
        
        # Remove from processed documents
        processed_documents = [d for d in processed_documents if d["id"] != doc_id]
        save_documents_db(processed_documents)
        
        print(f"[INFO] Deleted document: {doc_id}")
        return jsonify({"success": True, "message": "Document deleted successfully"})
    
    except Exception as e:
        print(f"[ERROR] Failed to delete document {doc_id}: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to delete: {str(e)}"}), 500


@app.route("/api/document/<doc_id>/pdf")
def serve_pdf(doc_id):
    """Serve the PDF file for viewing"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    
    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"error": "PDF file not found"}), 404
    
    return send_file(pdf_path, as_attachment=False, mimetype='application/pdf')


@app.route("/api/documents/cleanup", methods=["POST"])
def cleanup_old_documents():
    """Delete all old uploaded documents and OCR results"""
    global processed_documents
    
    try:
        deleted_count = 0
        
        # Delete all OCR result files
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e:
                    print(f"[WARNING] Failed to delete {file_path}: {str(e)}")
        
        # Clear processed documents database
        doc_count = len(processed_documents)
        processed_documents = []
        save_documents_db(processed_documents)
        
        # Clear job status map
        job_status_map.clear()
        
        print(f"[INFO] Cleanup completed: {deleted_count} files deleted, {doc_count} documents cleared")
        
        return jsonify({
            "success": True,
            "message": f"Cleanup completed successfully",
            "files_deleted": deleted_count,
            "documents_cleared": doc_count
        })
    
    except Exception as e:
        print(f"[ERROR] Cleanup failed: {str(e)}")
        return jsonify({"success": False, "message": f"Cleanup failed: {str(e)}"}), 500


@app.route("/upload", methods=["POST"])
@app.route("/process", methods=["POST"])
def upload_file():
    """Handle file upload and start processing"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400
    
    # Get optional document name from form
    document_name = request.form.get("document_name", "").strip()
    
    # Generate unique job ID
    job_id = hashlib.md5(f"{file.filename}{time.time()}".encode()).hexdigest()[:12]
    
    # Read file content
    file_bytes = file.read()
    
    # Start background processing
    thread = threading.Thread(
        target=process_job,
        args=(job_id, file_bytes, file.filename, True, document_name),
        daemon=True
    )
    thread.start()
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "File uploaded successfully. Processing started."
    })


@app.route("/status/<job_id>")
def get_status(job_id):
    """Get processing status for a job"""
    status = job_status_map.get(job_id, {"status": "Unknown job ID", "progress": 0})
    return jsonify(status)


if __name__ == "__main__":
    print(f"[INFO] Starting Universal IDP - region: {AWS_REGION}, model: {MODEL_ID}")
    app.run(debug=True, port=5015)
