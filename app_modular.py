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
                # SPEED: Use lower resolution (1x) for scanning - faster and cheaper
                pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
                pdf_doc.close()
                
                temp_image_path = os.path.join(OUTPUT_DIR, f"temp_scan_{doc_id}_{page_num}.png")
                pix.save(temp_image_path)
                
                with open(temp_image_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                
                # SPEED: Use detect_document_text (sync) for faster processing
                textract_response = textract.detect_document_text(Document={'Bytes': image_bytes})
                
                page_text = ""
                for block in textract_response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        page_text += block.get('Text', '') + "\n"
                
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    
            except Exception as ocr_err:
                print(f"[ERROR] OCR failed on page {page_num + 1}: {str(ocr_err)}")
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

IMPORTANT: Use SIMPLE, SHORT field names. Do NOT copy the entire label text from the document.
- Example: "DATE PRONOUNCED DEAD" → use "Death_Date" (NOT "Date_Pronounced_Dead")
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "Account_Holder_Names")
- Simplify all verbose labels to their core meaning

PRIORITY ORDER (Extract in this order):
1. **IDENTIFYING NUMBERS** - Match field names to document labels (Certificate_Number, Account_Number, License_Number, File_Number, etc.)
2. **NAMES** - All person names (full names, witness names, registrar names, etc.)
3. **DATES** - All dates (issue dates, birth dates, marriage dates, death dates, expiration dates, stamp dates)
4. **LOCATIONS** - Cities, states, counties, countries, addresses
5. **FORM FIELDS** - All labeled fields with values (Business Name, etc.)
6. **SIGNER INFORMATION** - Extract ALL signers with their complete information
7. **CONTACT INFO** - Phone numbers, emails, addresses
8. **CHECKBOXES** - Checkbox states (Yes/No, checked/unchecked)
9. **SPECIAL FIELDS** - Any other visible data

CRITICAL RULES:
- Extract EVERY field you can see in the document
- Include ALL identifying numbers (license #, certificate #, file #, reference #, account #, etc.)
- **HANDWRITTEN NUMBERS:** Pay special attention to handwritten numbers - they are often account numbers or reference numbers
- **MULTIPLE NUMBERS:** A document can have multiple number types (e.g., Certificate_Number AND Account_Number)
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
  - Stamp_Date (look for stamps like "DEC 26 2014", "JAN 15 2023")
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
  "Another_Field": {
    "value": "another value",
    "confidence": 80
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
    return """
You are an AI assistant that extracts ALL structured data from loan account documents.

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

For documents with ONE signer:
{
  "Account_Number": "string",
  "Account_Holders": ["name1", "name2"],
  "Account_Type": "string",
  "Ownership_Type": "string",
  "WSFS_Account_Type": "string",
  "Account_Purpose": "string",
  "SSN": "string or list of SSNs",
  "Stamp_Date": "string (e.g., DEC 26 2014, JAN 15 2023)",
  "Reference_Number": "string (e.g., #298, Ref #123)",
  "Processed_Date": "string",
  "Received_Date": "string",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DOB": "string",
  "Signer1_Address": "string",
  "Signer1_Phone": "string",
  "Signer1_Email": "string",
  "Supporting_Documents": [
    {
      "Type": "string",
      "Details": "string"
    }
  ]
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

FIELD DEFINITIONS - READ CAREFULLY - THESE ARE SEPARATE FIELDS:

1. Account_Type: The USAGE TYPE or WHO uses the account. Look for these EXACT terms:
   - "Personal" (for individual/family use)
   - "Business" (for business operations)
   - "Commercial" (for commercial purposes)
   - "Corporate" (for corporation)
   - "Trust" (trust account)
   - "Estate" (estate account)
   Extract whether it's for personal or business use.
   EXAMPLE: If you see "Personal" on the form → Account_Type: "Personal"

2. Account_Purpose: The CATEGORY or CLASSIFICATION of the account. Look for these EXACT terms:
   - "Consumer" (consumer banking)
   - "Checking" (checking account)
   - "Savings" (savings account)
   - "Money Market" (money market account)
   - "CD" or "Certificate of Deposit"
   - "IRA" or "Retirement"
   - "Loan" (loan account)
   - "Mortgage" (mortgage account)
   Extract the banking product category or account classification.
   EXAMPLE: If you see "Consumer" on the form → Account_Purpose: "Consumer"

3. WSFS_Account_Type: The SPECIFIC internal bank account type code or classification. Look for:
   - Specific product names like "Premier Checking", "Platinum Savings", "Gold CD"
   - Internal codes or account classifications
   - Branded account names unique to the bank
   - If the document shows "Account Type: Premier Checking", then Account_Type="Personal" (if for personal use) and WSFS_Account_Type="Premier Checking"
   - If only one type is mentioned, use it for WSFS_Account_Type and infer Account_Type from context

4. Ownership_Type: WHO owns the account legally. Common values:
   - "Individual" or "Single Owner" (single owner)
   - "Joint" or "Joint Owners" (multiple owners with equal rights)
   - "Joint with Rights of Survivorship"
   - "Trust" (held in trust)
   - "Estate" (estate account)
   - "Custodial" (for minor)
   - "Business" or "Corporate"

CRITICAL: DO NOT COMBINE Account_Type and Account_Purpose into one field!
- If you see "Consumer" and "Personal" on the form, create TWO separate fields:
  * Account_Purpose: "Consumer"
  * Account_Type: "Personal"
- DO NOT create a field called "Purpose" with value "Consumer Personal"
- These are ALWAYS separate fields even if they appear together on the form

EXTRACTION RULES:
- Extract EVERY field visible in the document, not just the ones listed above
- Include ALL form fields, checkboxes, dates, amounts, addresses, phone numbers, emails
- Extract ALL names, titles, positions, relationships
- Include ALL dates (opened, closed, effective, expiration, birth dates, etc.)
- **IMPORTANT: Extract ALL STAMP DATES** - Look for date stamps like "DEC 26 2014", "JAN 15 2023", etc.
- **IMPORTANT: Extract REFERENCE NUMBERS** - Look for numbers like "#298", "Ref #123", etc.
- Extract ALL identification numbers (SSN, Tax ID, License numbers, etc.)
- Include ALL financial information (balances, limits, rates, fees)
- Extract ALL addresses (mailing, physical, business, home)
- Include ALL contact information (phone, fax, email, website)
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
- **CRITICAL FOR SIGNERS - DO NOT USE NESTED OBJECTS**:
  * WRONG: "Signer1": {"Name": "John", "SSN": "123"}
  * CORRECT: "Signer1_Name": "John", "Signer1_SSN": "123"
  * Use FLAT fields with underscore naming: Signer1_Name, Signer1_SSN, Signer1_DOB, Signer1_Address, Signer1_Phone, Signer1_Drivers_License
  * For second signer: Signer2_Name, Signer2_SSN, Signer2_DOB, Signer2_Address, Signer2_Phone, Signer2_Drivers_License
  * For third signer: Signer3_Name, Signer3_SSN, etc.
  * NEVER nest signer data - always use flat top-level fields
- For Supporting_Documents: Create separate objects for EACH document type found
- Preserve exact account numbers and SSNs as they appear
- If you see multiple account types mentioned, use the most specific one
- Look carefully at the entire document text for ALL fields
- Pay special attention to compliance sections, checkboxes, verification stamps, and date stamps
- **REMEMBER: Only extract what you can SEE in the document. Do not invent or assume fields.**

EXAMPLES:
Example 1: Document says "Premier Checking Account for Business Operations, Consumer Banking"
{
  "Account_Type": "Business",
  "WSFS_Account_Type": "Premier Checking",
  "Account_Purpose": "Consumer"
}

Example 2: Document says "Personal IRA Savings Account"
{
  "Account_Type": "Personal",
  "WSFS_Account_Type": "IRA Savings",
  "Account_Purpose": "Retirement"
}

Example 3: Document says "Personal Checking Account, Consumer"
{
  "Account_Type": "Personal",
  "WSFS_Account_Type": "Personal Checking",
  "Account_Purpose": "Consumer"
}

Example 3b: Document shows checkboxes with "Consumer" checked and "Personal" checked
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal"
}
WRONG: DO NOT combine them like this: {"Purpose": "Consumer Personal"}

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
        "temperature": 0.2,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": f"{prompt}\n\n{text}"}]}
        ],
    }
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(payload))
    return json.loads(resp["body"].read())["content"][0]["text"]


def extract_basic_fields(text: str, num_fields: int = 100):
    """Extract ALL fields from any document (up to 100 fields) - BE THOROUGH"""
    prompt = f"""
YOU ARE A METICULOUS DATA EXTRACTION EXPERT. Extract EVERY SINGLE field from this document.

CRITICAL: Use SIMPLE, SHORT field names. Do NOT copy the entire label text from the document.
- Example: "DATE PRONOUNCED DEAD" → use "Death_Date" (NOT "Date_Pronounced_Dead")
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "Account_Holder_Names")
- Simplify all verbose labels to their core meaning

YOUR MISSION: Find and extract up to {num_fields} fields. Do NOT stop until you've extracted EVERYTHING.

EXTRACTION PRIORITY (Extract ALL of these):
1. ALL IDENTIFYING NUMBERS:
   - Certificate numbers, file numbers, case numbers (K1-0000608, K1-0011267, etc.)
   - License numbers, registration numbers, document numbers
   - Social security numbers, tax IDs, reference numbers
   - ANY number with a label

2. ALL DATES AND TIMES:
   - Issue dates, filing dates, death dates, birth dates, marriage dates
   - Timestamps (22:29, 14:30, etc.)
   - Date stamps (01/09/2016, January 9, 2016, etc.)
   - Extract in ORIGINAL format

3. ALL NAMES:
   - Deceased names, witness names, registrar names, physician names
   - Father names, mother names, spouse names, informant names
   - Funeral director names, certifier names, pronouncer names
   - ANY person's name ANYWHERE

4. ALL LOCATIONS:
   - Cities, counties, states, countries
   - Place of death, place of birth, place of residence
   - Addresses with street numbers, zip codes
   - Hospital names, facility names

5. ALL FORM FIELDS:
   - Look for "FIELD_LABEL: value" patterns
   - Checkbox fields (Yes/No, checked/unchecked)
   - Signature fields and dates
   - License fields, certification fields
   - Cause of death, manner of death
   - Occupation, industry, education
   - Race, ethnicity, marital status

6. ALL ADMINISTRATIVE DATA:
   - Form numbers, version numbers, page numbers
   - Barcode numbers, stamp text
   - "LICENSE NUMBER FOR" values
   - "DATE PRONOUNCED DEAD" values
   - "ACTUAL OR PRESUMED DATE OF DEATH" values
   - ANY labeled field

CRITICAL RULES:
- Extract EVERY field you can see - do NOT skip anything
- Include ALL numbers with labels (even if they seem minor)
- Extract ALL dates in their original format
- Extract ALL names in any context
- Use descriptive field names (e.g., "case_number", "file_number", "license_number_for")
- Only include fields that have actual values (omit empty fields)

FIELD NAMING EXAMPLES:
- "LICENSE NUMBER FOR" → "license_number_for"
- "DATE PRONOUNCED DEAD" → "date_pronounced_dead"
- "K1-0011267" → "case_number" or "file_number"
- "CAUSE OF DEATH" → "cause_of_death"

CRITICAL NAMING FOR DEATH CERTIFICATES:
- The main certificate number (often handwritten, like "468431466" or "K1-0011267") MUST be extracted as "account_number"
- DO NOT use "certificate_number" - use "account_number" instead
- Example: If you see "468431466" or "K1-0011267" as the primary certificate identifier:
  * Extract it as "account_number": "468431466"
  * NOT as "certificate_number"

EXTRACT EVERY SINGLE FIELD - DO NOT MISS ANYTHING:
- Look at EVERY line of text
- Extract EVERY number you see with a label
- Extract EVERY date in any format
- Extract EVERY name mentioned
- Extract EVERY location mentioned
- Extract EVERY checkbox value
- Extract EVERY signature field
- Extract EVERY time stamp
- If you see a field label but can't read the value, still include it as "illegible" or "unclear"

Return ONLY valid JSON where EVERY field has both value and confidence. Extract up to {num_fields} fields - BE THOROUGH AND COMPLETE!

Example format for Death Certificate:
{{
  "account_number": {{
    "value": "468431466",
    "confidence": 95
  }},
  "state_file_number": {{
    "value": "K1-0000608",
    "confidence": 100
  }},
  "date_pronounced_dead": {{
    "value": "01/09/2016",
    "confidence": 100
  }},
  "time_pronounced_dead": {{
    "value": "22:29",
    "confidence": 90
  }},
  "deceased_name": {{
    "value": "John Doe",
    "confidence": 98
  }},
  "place_of_death": {{
    "value": "New Castle, DE",
    "confidence": 100
  }},
  "cause_of_death": {{
    "value": "description",
    "confidence": 85
  }},
  "manner_of_death": {{
    "value": "Natural",
    "confidence": 100
  }}
}}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL: EVERY field MUST have both "value" and "confidence"
"""
    
    try:
        response = call_bedrock(prompt, text[:10000], max_tokens=8192)  # Use maximum tokens for comprehensive extraction
        
        # Find JSON content
        json_start = response.find('{')
        json_end = response.rfind('}')
        
        if json_start == -1 or json_end == -1:
            raise ValueError("No JSON object found in response")
        
        json_str = response[json_start:json_end + 1]
        result = json.loads(json_str)
        
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
                        "pre_cached": True
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
    """Background worker to process documents"""
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
        print(f"[INFO] Starting job {job_id} for file: {filename}")
        print(f"[INFO] File size: {len(file_bytes) / 1024:.2f} KB")
        print(f"[INFO] Use OCR: {use_ocr}")
        print(f"[INFO] Document name: {document_name}")
        if original_file_path:
            print(f"[INFO] Original file path: {original_file_path}")
        
        # Initialize job status
        job_status_map[job_id] = {
            "status": "Starting processing...",
            "progress": 5
        }
        
        # OPTIMIZATION: For PDFs, do a quick check to see if it's a loan document
        # If so, skip expensive full-document OCR and go straight to page-level processing
        is_loan_document = False
        if use_ocr and filename.lower().endswith('.pdf') and saved_pdf_path:
            job_status_map[job_id].update({
                "status": "Quick scan to detect document type...",
                "progress": 10
            })
            
            # Quick scan: extract text from first page only to detect type
            try:
                import fitz
                pdf_doc = fitz.open(saved_pdf_path)
                if len(pdf_doc) > 0:
                    first_page_text = pdf_doc[0].get_text()
                    pdf_doc.close()
                    
                    # Quick detection based on first page
                    # IMPORTANT: Check for business card FIRST before assuming loan document
                    first_page_upper = first_page_text.upper()
                    
                    # Exclude business card order forms and other specific forms
                    is_business_card = "BUSINESS CARD ORDER FORM" in first_page_upper or "CARD ORDER FORM" in first_page_upper
                    is_card_request = "CARD REQUEST" in first_page_upper or "ATM" in first_page_upper or "DEBIT CARD" in first_page_upper
                    is_withdrawal = "WITHDRAWAL FORM" in first_page_upper or "ACCOUNT WITHDRAWAL" in first_page_upper
                    
                    # Only treat as loan document if it has loan-specific indicators AND is not a form
                    has_loan_indicators = (
                        "ACCOUNT NUMBER" in first_page_upper and 
                        "ACCOUNT HOLDER" in first_page_upper and
                        not is_business_card and
                        not is_card_request and
                        not is_withdrawal
                    )
                    
                    if has_loan_indicators:
                        is_loan_document = True
                        print(f"[INFO] OPTIMIZATION: Detected loan document - will skip full OCR and use page-level processing")
                    elif is_business_card or is_card_request:
                        print(f"[INFO] Detected business card/form - will use normal processing")
            except Exception as quick_scan_err:
                print(f"[WARNING] Quick scan failed: {str(quick_scan_err)}, will proceed with normal OCR")
        
        # Step 1: OCR if needed (skip for loan documents - we'll do page-level OCR instead)
        if use_ocr and not is_loan_document:
            # OPTIMIZATION #1: Try PyPDF2 FIRST (FREE) before expensive Textract
            text = None
            ocr_file = None
            
            if filename.lower().endswith('.pdf'):
                job_status_map[job_id].update({
                    "status": "Trying FREE text extraction (PyPDF2)...",
                    "progress": 10
                })
                
                print(f"[OPTIMIZATION] Trying PyPDF2 first (FREE) before Textract...")
                text, ocr_file = try_extract_pdf_with_pypdf(file_bytes, filename)
                
                # Check if text is meaningful (not just watermarks/demo text)
                is_watermark = False
                if text:
                    text_lower = text.lower()
                    # Check for common watermark/demo patterns
                    watermark_indicators = [
                        "pdf-xchange", "click to buy", "demo", "trial version",
                        "unregistered", "evaluation copy", "watermark"
                    ]
                    # If text is mostly watermark content
                    if any(indicator in text_lower for indicator in watermark_indicators):
                        # Count how many lines are watermark vs real content
                        lines = text.split('\n')
                        watermark_lines = sum(1 for line in lines if any(ind in line.lower() for ind in watermark_indicators))
                        if watermark_lines > len(lines) * 0.5:  # More than 50% watermark
                            is_watermark = True
                            print(f"[OPTIMIZATION] ⚠️ PyPDF2 extracted mostly watermark text, falling back to Textract...")
                
                if text and len(text.strip()) > 100 and not is_watermark:
                    # PyPDF2 succeeded! Save money by not using Textract
                    job_status_map[job_id]["ocr_file"] = ocr_file
                    job_status_map[job_id]["ocr_method"] = "PyPDF2 (FREE)"
                    print(f"[OPTIMIZATION] ✅ PyPDF2 succeeded! Saved Textract cost (~$0.04)")
                else:
                    # PyPDF2 failed or extracted too little text, use Textract
                    if not is_watermark:
                        print(f"[OPTIMIZATION] PyPDF2 failed or insufficient text, falling back to Textract...")
                    text = None
                    ocr_file = None
            
            # If PyPDF2 didn't work or not a PDF, use Textract
            if not text:
                job_status_map[job_id].update({
                    "status": "Running OCR with Amazon Textract (this may take 1-2 minutes for scanned PDFs)...",
                    "progress": 15
                })
                
                try:
                    text, ocr_file = extract_text_with_textract(file_bytes, filename)
                    job_status_map[job_id]["ocr_file"] = ocr_file
                    job_status_map[job_id]["ocr_method"] = "Amazon Textract"
                    print(f"[INFO] Textract succeeded")
                except Exception as textract_error:
                    raise Exception(f"Text extraction failed. Error: {str(textract_error)}")
        elif is_loan_document:
            # OPTIMIZATION: For loan documents, extract text quickly with PyMuPDF (no expensive OCR yet)
            print(f"[INFO] OPTIMIZATION: Skipping full document OCR for loan document - will do page-level OCR during pre-caching")
            job_status_map[job_id].update({
                "status": "Extracting text for account detection (no OCR yet)...",
                "progress": 10
            })
            
            import fitz
            pdf_doc = fitz.open(saved_pdf_path)
            text = ""
            for page_num in range(len(pdf_doc)):
                text += pdf_doc[page_num].get_text() + "\n"
            pdf_doc.close()
            
            # Save extracted text
            ocr_file = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
            with open(ocr_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            job_status_map[job_id]["ocr_file"] = ocr_file
            job_status_map[job_id]["ocr_method"] = "PyMuPDF (Fast - OCR deferred to page-level)"
            print(f"[INFO] Extracted {len(text)} characters without OCR - saved significant cost!")
        else:
            print(f"[INFO] Processing as text file (no OCR needed)")
            job_status_map[job_id].update({
                "status": "Reading text file...",
                "progress": 10
            })
            text = file_bytes.decode("utf-8", errors="ignore")
            print(f"[INFO] Text extracted: {len(text)} characters")
            
            # Save text file anyway
            ocr_file = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
            with open(ocr_file, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"[INFO] Saved text to: {ocr_file}")
            
            job_status_map[job_id]["ocr_file"] = ocr_file
            job_status_map[job_id]["ocr_method"] = "Direct Text"
        
        # Step 2: Detect document type (no LLM call, just pattern matching)
        job_status_map[job_id].update({
            "status": "Analyzing document structure...",
            "progress": 40
        })
        
        # Check if this is a loan document - use special processing
        doc_type_preview = detect_document_type(text) if not is_loan_document else "loan_document"
        print(f"[INFO] Document type detected: {doc_type_preview}")
        
        if doc_type_preview == "loan_document":
            # OPTIMIZATION: Skip basic_fields extraction for loan documents
            # We'll get all data from page-level pre-caching
            basic_fields = {}
            
            # Quick check for number of accounts
            account_count = len(split_accounts_strict(text))
            
            if account_count > 20:
                print(f"[WARNING] Large document detected with {account_count} accounts. Processing may take 5-10 minutes.")
                job_status_map[job_id].update({
                    "status": f"Detected loan document with {account_count} accounts - will pre-cache page data...",
                    "progress": 70
                })
            else:
                job_status_map[job_id].update({
                    "status": "Detected loan document - identifying accounts...",
                    "progress": 70
                })
            
            result = process_loan_document(text, job_id, job_status_map)
        else:
            # For non-loan documents, extract basic fields
            job_status_map[job_id].update({
                "status": "Extracting fields from document...",
                "progress": 60
            })
            basic_fields = extract_basic_fields(text, num_fields=20)
            
            job_status_map[job_id].update({
                "status": "Processing document...",
                "progress": 70
            })
            result = detect_and_extract_documents(text)
        
        # Add basic fields to result
        result["basic_fields"] = basic_fields
        result["ocr_file"] = ocr_file
        result["extracted_text_preview"] = text[:500] + "..." if len(text) > 500 else text
        
        # Add document type info
        if result.get("documents") and len(result["documents"]) > 0:
            doc = result["documents"][0]
            doc_type = doc.get("document_type", "unknown")
            
            # Map AI-generated types to supported types
            type_mappings = {
                "account_opening": "loan_document",
                "account_opening_form": "loan_document",
                "signature_card": "loan_document",
                "bank_account": "loan_document",
                "account_form": "loan_document"
            }
            
            # Apply mapping if exists
            if doc_type in type_mappings:
                doc_type = type_mappings[doc_type]
            
            if doc_type in SUPPORTED_DOCUMENT_TYPES:
                doc_info = SUPPORTED_DOCUMENT_TYPES[doc_type]
                result["document_type_info"] = {
                    "type": doc_type,
                    "name": doc_info["name"],
                    "icon": doc_info["icon"],
                    "description": doc_info["description"],
                    "expected_fields": doc_info["expected_fields"],
                    "is_supported": True
                }
            else:
                result["document_type_info"] = {
                    "type": "unknown",
                    "name": "Unknown Document",
                    "icon": "📄",
                    "description": "Document type not recognized",
                    "expected_fields": [],
                    "is_supported": False
                }
        
        # Step 4: Use filename as document name (don't auto-generate)
        # The filename is what the user chose, so we should respect it
        if not document_name:
            # Remove file extension from filename for cleaner display
            document_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        # Step 5: Check for existing account and merge if found
        document_record = {
            "id": job_id,
            "filename": filename,
            "document_name": document_name,  # User-provided or auto-generated name
            "timestamp": timestamp,
            "processed_date": datetime.now().isoformat(),
            "ocr_file": ocr_file,
            "ocr_method": job_status_map[job_id].get("ocr_method", "Unknown"),
            "basic_fields": basic_fields,
            "documents": result.get("documents", []),
            "document_type_info": result.get("document_type_info", {}),
            "use_ocr": use_ocr,
            "pdf_path": saved_pdf_path  # Store saved PDF path for viewing
        }
        
        if "textract_error" in job_status_map[job_id]:
            document_record["textract_error"] = job_status_map[job_id]["textract_error"]
        
        # Check if account number exists in the new document
        account_number = None
        if basic_fields.get("account_number"):
            account_number = basic_fields["account_number"]
        elif result.get("documents"):
            for doc in result["documents"]:
                if doc.get("extracted_fields", {}).get("account_number"):
                    account_number = doc["extracted_fields"]["account_number"]
                    break
                if doc.get("accounts") and len(doc["accounts"]) > 0:
                    account_number = doc["accounts"][0].get("accountNumber")
                    break
        
        # Check if this account already exists
        existing_doc = find_existing_document_by_account(account_number) if account_number else None
        
        if existing_doc:
            # Account exists - merge the changes
            print(f"[INFO] Account {account_number} already exists in document {existing_doc['id']} - merging changes")
            merged_doc, changes = merge_document_fields(existing_doc, document_record)
            
            # Update the existing document in the list
            for i, doc in enumerate(processed_documents):
                if doc["id"] == existing_doc["id"]:
                    processed_documents[i] = merged_doc
                    break
            
            # Update job status to indicate merge
            job_status_map[job_id]["merge_info"] = {
                "merged_with_doc_id": existing_doc["id"],
                "merged_with_doc_name": existing_doc.get("document_name", "Unknown"),
                "account_number": account_number,
                "changes_count": len(changes),
                "changes": changes
            }
            
            print(f"[INFO] ✅ Merged {len(changes)} changes into existing document")
        else:
            # New account - add as new document
            processed_documents.append(document_record)
            print(f"[INFO] ✅ Added new document with account {account_number if account_number else 'N/A'}")
        
        save_documents_db(processed_documents)
        
        # Step 6: Mark job as complete FIRST
        job_status_map[job_id] = {
            "status": "✅ Processing completed",
            "progress": 100,
            "result": result,
            "ocr_file": ocr_file
        }
        
        # OPTIMIZATION: Skip pre-caching entirely for now
        # Pre-caching is expensive (OCR + AI extraction for every page)
        # Instead, we'll extract data on-demand when user views a page
        # This makes upload MUCH faster and only processes pages that are actually viewed
        
        # Pre-cache all page data for loan documents in BACKGROUND (non-blocking)
        # DISABLED FOR PERFORMANCE - uncomment if you want to pre-cache all pages
        # if doc_type_preview == "loan_document" and saved_pdf_path and result.get("documents"):
        #     doc_data = result["documents"][0]
        #     accounts = doc_data.get("accounts", [])
        #     
        #     if accounts and len(accounts) > 0:
        #         print(f"[INFO] Starting BACKGROUND pre-cache for {len(accounts)} accounts")
        #         
        #         # Run pre-caching in a separate thread (non-blocking)
        #         def background_precache():
        #             try:
        #                 pre_cache_all_pages(job_id, saved_pdf_path, accounts)
        #                 print(f"[INFO] ✅ Background pre-caching completed for job {job_id}")
        #             except Exception as cache_err:
        #                 print(f"[WARNING] Background pre-caching failed for job {job_id}: {str(cache_err)}")
        #         
        #         cache_thread = threading.Thread(target=background_precache, daemon=True)
        #         cache_thread.start()
        
        print(f"[INFO] ✅ Document processing completed - data will be extracted on-demand when pages are viewed")
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
    return jsonify({"documents": processed_documents, "total": len(processed_documents)})


@app.route("/api/document/<doc_id>")
def get_document_detail(doc_id):
    """Get details of a specific document"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return jsonify({"success": True, "document": doc})
    return jsonify({"success": False, "message": "Document not found"}), 404


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
        
        # Assign pages to the target account
        # Strategy: Find where this account starts, then include pages until the next account starts
        account_pages = []
        marked_pages = [p for p in range(total_pages) if page_to_account.get(p) == target_account_number]
        
        if marked_pages:
            # Start from the first page marked with this account
            first_page = marked_pages[0]
            
            # Find where the next account starts (or end of document)
            next_account_page = total_pages  # Default to end of document
            for page_num in range(first_page + 1, total_pages):
                if page_num in page_to_account and page_to_account[page_num] != target_account_number:
                    next_account_page = page_num
                    print(f"[DEBUG] Next account starts at page {page_num}")
                    break
            
            # Include all pages from first_page to next_account_page (exclusive)
            account_pages = list(range(first_page, next_account_page))
            
            print(f"[DEBUG] Account {target_account_number} marked on page: {first_page + 1}")
            print(f"[DEBUG] Assigned pages {first_page + 1} to {next_account_page} (total: {len(account_pages)} pages)")
        
        # Display page numbers as 1-based for clarity
        display_pages = [p + 1 for p in account_pages]
        print(f"[INFO] Account {target_account_number} has {len(account_pages)} page(s): {display_pages}")
        
        # If no pages found, fall back to even distribution
        if not account_pages:
            print(f"[WARNING] No pages found for account {target_account_number}, using even distribution")
            pages_per_account = max(1, total_pages // len(accounts))
            start_page = account_index * pages_per_account
            end_page = start_page + pages_per_account if account_index < len(accounts) - 1 else total_pages
            account_pages = list(range(start_page, end_page))
        
        # Display page numbers as 1-based for clarity
        display_pages = [p + 1 for p in account_pages]
        print(f"[INFO] Account {target_account_number} has {len(account_pages)} page(s): {display_pages}")
        
        response_data = {
            "success": True,
            "total_pages": len(account_pages),
            "pages": account_pages,
            "account_number": target_account_number
        }
        print(f"[INFO] Returning response: {response_data}")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[ERROR] Failed to get account pages: {str(e)}")
        import traceback
        traceback.print_exc()
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
            print(f"[DEBUG] Found cached data in S3")
            
            # CRITICAL: Apply flattening to cached data too!
            cached_fields = cached_data.get("data", {})
            cached_fields = flatten_nested_objects(cached_fields)
            print(f"[DEBUG] Applied flattening to cached data")
            
            return jsonify({
                "success": True,
                "page_number": page_num + 1,
                "account_number": cached_data.get("account_number"),
                "data": cached_fields,
                "cached": True
            })
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
            
            return jsonify({
                "success": True,
                "page_number": page_num + 1,
                "account_number": account_number,
                "data": parsed,
                "cached": False
            })
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
            
            return jsonify({
                "success": True,
                "page_number": page_num + 1,
                "data": parsed,
                "cached": False
            })
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
            print(f"[INFO] Updated S3 cache with edited data: {cache_key}")
            print(f"[INFO] Updated fields: {list(page_data.keys())}")
            
            return jsonify({
                "success": True,
                "message": "Page data updated successfully",
                "cache_key": cache_key
            })
        except Exception as s3_error:
            print(f"[ERROR] Failed to update S3 cache: {str(s3_error)}")
            return jsonify({"success": False, "message": f"Failed to save: {str(s3_error)}"}), 500
            
    except Exception as e:
        print(f"[ERROR] Failed to update page data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>/update", methods=["POST"])
def update_account_page_data(doc_id, account_index, page_num):
    """Update page data for account-based documents and save to S3 cache"""
    import json
    
    try:
        data = request.get_json()
        page_data = data.get("page_data")
        
        if not page_data:
            return jsonify({"success": False, "message": "No page data provided"}), 400
        
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get account info
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if account_index >= len(accounts):
            return jsonify({"success": False, "message": "Account index out of range"}), 400
        
        account = accounts[account_index]
        account_number = account.get("accountNumber", "Unknown")
        
        # Cache key for account-based page
        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
        print(f"[INFO] Updating account page cache: {cache_key}")
        
        cache_data = {
            "account_number": account_number,
            "data": page_data,
            "extracted_at": datetime.now().isoformat(),
            "edited": True,
            "edited_at": datetime.now().isoformat()
        }
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            print(f"[INFO] Updated S3 cache for account {account_number}: {cache_key}")
            print(f"[INFO] Updated fields: {list(page_data.keys())}")
            
            return jsonify({
                "success": True,
                "message": "Page data updated successfully",
                "cache_key": cache_key
            })
        except Exception as s3_error:
            print(f"[ERROR] Failed to update S3 cache: {str(s3_error)}")
            return jsonify({"success": False, "message": f"Failed to save: {str(s3_error)}"}), 500
            
    except Exception as e:
        print(f"[ERROR] Failed to update account page data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/update", methods=["POST"])
def update_document_field(doc_id):
    """Update a specific field in the document and S3 cache"""
    try:
        data = request.get_json()
        field_name = data.get("field_name")
        field_value = data.get("field_value")
        account_index = data.get("account_index")
        page_num = data.get("page_num")  # Get current page number
        
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Update the field in the document structure
        doc_data = doc.get("documents", [{}])[0]
        
        if account_index is not None:
            # Update account-level data
            accounts = doc_data.get("accounts", [])
            if account_index < len(accounts):
                account = accounts[account_index]
                if "result" not in account:
                    account["result"] = {}
                account["result"][field_name] = field_value
                
                # Save to database
                save_documents_db(processed_documents)
                
                # IMPORTANT: Update S3 cache if page_num is provided
                if page_num is not None:
                    try:
                        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
                        
                        # Get existing cache
                        try:
                            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
                            cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
                        except:
                            cached_data = {
                                "account_number": account.get("accountNumber"),
                                "data": {},
                                "extracted_at": datetime.now().isoformat()
                            }
                        
                        # Update the field in cache
                        if "data" not in cached_data:
                            cached_data["data"] = {}
                        cached_data["data"][field_name] = field_value
                        cached_data["updated_at"] = datetime.now().isoformat()
                        
                        # Save updated cache to S3
                        s3_client.put_object(
                            Bucket=S3_BUCKET,
                            Key=cache_key,
                            Body=json.dumps(cached_data),
                            ContentType='application/json'
                        )
                        print(f"[INFO] Updated S3 cache: {cache_key}")
                    except Exception as cache_error:
                        print(f"[WARNING] Failed to update S3 cache: {str(cache_error)}")
                
                return jsonify({"success": True, "message": "Field updated successfully"})
            else:
                return jsonify({"success": False, "message": "Account index out of range"}), 400
        else:
            # Update document-level data
            if "extracted_fields" not in doc_data:
                doc_data["extracted_fields"] = {}
            doc_data["extracted_fields"][field_name] = field_value
            
            # Save to database
            save_documents_db(processed_documents)
            
            return jsonify({"success": True, "message": "Field updated successfully"})
            
    except Exception as e:
        print(f"[ERROR] Failed to update field: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


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


@app.route("/api/document/<doc_id>/debug-cache/<int:account_index>/<int:page_num>", methods=["GET"])
def debug_cache_data(doc_id, account_index, page_num):
    """Debug endpoint to see what's actually in the cache"""
    try:
        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
        
        try:
            cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
            cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
            
            data = cached_data.get("data", {})
            
            # Analyze the data
            all_keys = list(data.keys())
            signer_keys = [k for k in all_keys if 'signer' in k.lower()]
            
            return jsonify({
                "success": True,
                "cache_key": cache_key,
                "total_fields": len(all_keys),
                "all_keys": all_keys,
                "signer_keys": signer_keys,
                "sample_data": {k: data[k] for k in list(data.keys())[:10]},
                "full_data": data
            })
        except s3_client.exceptions.NoSuchKey:
            return jsonify({"success": False, "message": "No cache found"}), 404
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/document/<doc_id>/migrate-cache", methods=["POST"])
def migrate_document_cache(doc_id):
    """Migrate existing S3 cache to flatten nested objects (Signer1: {} -> Signer1_Name, etc.)"""
    try:
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get all accounts
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        migrated_count = 0
        
        # Migrate cache for all accounts and pages
        for account_index in range(len(accounts)):
            # Migrate page data cache (try up to 100 pages)
            for page_num in range(100):
                try:
                    cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
                    
                    # Try to load existing cache
                    cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
                    cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
                    
                    # Apply flattening
                    original_data = cached_data.get("data", {})
                    flattened_data = flatten_nested_objects(original_data)
                    
                    # Check if anything changed
                    if flattened_data != original_data:
                        cached_data["data"] = flattened_data
                        cached_data["migrated"] = True
                        cached_data["migrated_at"] = datetime.now().isoformat()
                        
                        # Save back to S3
                        s3_client.put_object(
                            Bucket=S3_BUCKET,
                            Key=cache_key,
                            Body=json.dumps(cached_data),
                            ContentType='application/json'
                        )
                        migrated_count += 1
                        print(f"[INFO] Migrated cache: {cache_key}")
                except s3_client.exceptions.NoSuchKey:
                    pass  # No cache for this page
                except Exception as e:
                    print(f"[WARNING] Failed to migrate {cache_key}: {str(e)}")
        
        # Also migrate non-account page cache
        for page_num in range(100):
            try:
                cache_key = f"page_data/{doc_id}/page_{page_num}.json"
                
                cache_response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
                cached_data = json.loads(cache_response['Body'].read().decode('utf-8'))
                
                original_data = cached_data.get("data", {})
                flattened_data = flatten_nested_objects(original_data)
                
                if flattened_data != original_data:
                    cached_data["data"] = flattened_data
                    cached_data["migrated"] = True
                    cached_data["migrated_at"] = datetime.now().isoformat()
                    
                    s3_client.put_object(
                        Bucket=S3_BUCKET,
                        Key=cache_key,
                        Body=json.dumps(cached_data),
                        ContentType='application/json'
                    )
                    migrated_count += 1
                    print(f"[INFO] Migrated cache: {cache_key}")
            except s3_client.exceptions.NoSuchKey:
                pass
            except Exception as e:
                print(f"[WARNING] Failed to migrate {cache_key}: {str(e)}")
        
        print(f"[INFO] Migrated {migrated_count} cache entries for document {doc_id}")
        
        return jsonify({
            "success": True,
            "message": f"Cache migrated successfully. Updated {migrated_count} cache entries.",
            "note": "Refresh the page to see updated data with flattened signers"
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to migrate cache: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to migrate cache: {str(e)}"}), 500


@app.route("/api/document/<doc_id>/clear-cache", methods=["POST"])
def clear_document_cache(doc_id):
    """Clear S3 cache for a specific document to force re-extraction with updated prompts"""
    try:
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get all accounts
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        deleted_count = 0
        
        # Delete cache for all accounts and pages
        for account_index in range(len(accounts)):
            # Try to delete page mapping cache
            try:
                cache_key = f"page_mapping/{doc_id}/mapping.json"
                s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
                deleted_count += 1
                print(f"[INFO] Deleted cache: {cache_key}")
            except:
                pass
            
            # Delete page data cache (try up to 100 pages)
            for page_num in range(100):
                try:
                    cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
                    s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
                    deleted_count += 1
                    print(f"[INFO] Deleted cache: {cache_key}")
                except:
                    pass
        
        # Also delete non-account page cache
        for page_num in range(100):
            try:
                cache_key = f"page_data/{doc_id}/page_{page_num}.json"
                s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
                deleted_count += 1
                print(f"[INFO] Deleted cache: {cache_key}")
            except:
                pass
        
        print(f"[INFO] Cleared {deleted_count} cache entries for document {doc_id}")
        
        # Also mark the document to force re-extraction on next page load
        # This ensures page 0 will re-extract instead of using cached extracted_fields
        doc["cache_cleared"] = True
        doc["cache_cleared_at"] = datetime.now().isoformat()
        
        # Save to database
        save_documents_db(processed_documents)
        
        return jsonify({
            "success": True,
            "message": f"Cache cleared successfully. Deleted {deleted_count} cache entries.",
            "note": "Click on pages again to re-extract with updated prompts"
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to clear cache: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to clear cache: {str(e)}"}), 500


@app.route("/process", methods=["POST"])
def process_document():
    """Upload and process document"""
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "message": "No file uploaded"}), 400
    
    # Read file content
    file_bytes = f.read()
    filename = f.filename
    
    # Get document name from form (optional, defaults to filename)
    document_name = request.form.get("document_name", filename)
    
    # Determine if OCR is needed (PDF, images)
    # Textract supports: PDF, PNG, JPG, JPEG
    use_ocr = filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg'))
    
    # Generate job ID
    job_id = hashlib.md5(f"{time.time()}".encode()).hexdigest()[:10]
    
    # Start background processing
    thread = threading.Thread(target=process_job, args=(job_id, file_bytes, filename, use_ocr, document_name, None))
    thread.start()
    
    return jsonify({"success": True, "job_id": job_id, "use_ocr": use_ocr})


@app.route("/status/<job_id>")
def get_status(job_id):
    """Get processing status"""
    status = job_status_map.get(job_id, {"status": "Unknown job", "progress": 0})
    
    # Add merge information if available
    if "merge_info" in status:
        merge_info = status["merge_info"]
        status["status"] = f"✅ Document merged with existing account {merge_info['account_number']} - {merge_info['changes_count']} changes detected"
        status["is_merged"] = True
    
    return jsonify(status)


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
        if "ocr_file" in doc and os.path.exists(doc["ocr_file"]):
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
        return "Document not found", 404
    
    # Get saved PDF path
    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF file not found", 404
    
    # Serve the PDF file
    from flask import send_file
    return send_file(pdf_path, mimetype='application/pdf')


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


if __name__ == "__main__":
    print(f"[INFO] Starting Universal IDP - region: {AWS_REGION}, model: {MODEL_ID}")
    app.run(debug=True, port=5015)
