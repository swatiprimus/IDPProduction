#!/usr/bin/env python3
"""
Universal IDP - Handles any document type dynamically
AI determines document type and extracts relevant fields
"""

from flask import Flask, render_template, request, jsonify
import boto3, json, time, threading, hashlib, os, re
from datetime import datetime
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

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

# ----------------------------------------------------------
# Loan Document Account Splitting Logic (from loan_pipeline_ui.py)
# ----------------------------------------------------------
ACCOUNT_INLINE_RE = re.compile(r"^ACCOUNT NUMBER[:\s]*([0-9]{6,15})\b")
ACCOUNT_LINE_RE = re.compile(r"^[0-9]{6,15}\b$")
ACCOUNT_HEADER_RE = re.compile(r"^ACCOUNT NUMBER:?\s*$")
ACCOUNT_HOLDER_RE = re.compile(r"^Account Holder Names:?\s*$")


def split_accounts_strict(text: str):
    """
    Smart splitter for loan documents:
    - Handles both inline and multi-line 'ACCOUNT NUMBER' formats.
    - Accumulates text for the same account number if repeated.
    """
    print(f"\n{'='*80}")
    print(f"[SPLIT_ACCOUNTS] Starting account splitting...")
    print(f"[SPLIT_ACCOUNTS] Input text length: {len(text)} characters")
    
    lines = text.splitlines()
    print(f"[SPLIT_ACCOUNTS] Total lines: {len(lines)}")
    
    account_chunks = {}
    current_account = None
    buffer = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()

        # --- Case 1: Inline account number ---
        inline_match = ACCOUNT_INLINE_RE.match(line)
        if inline_match:
            acc = inline_match.group(1)
            print(f"[SPLIT_ACCOUNTS] Line {i+1}: Found inline account number: {acc}")
            # Save previous buffer if moving to a new account
            if current_account and buffer:
                account_chunks[current_account] = (
                    account_chunks.get(current_account, "") + "\n" + "\n".join(buffer)
                )
                buffer = []
            current_account = acc
            i += 1
            continue

        # --- Case 2: Multi-line header format ---
        if ACCOUNT_HEADER_RE.match(line):
            # Look ahead for "Account Holder Names:" then a number
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and ACCOUNT_HOLDER_RE.match(lines[j].strip()):
                k = j + 1
                while k < n and lines[k].strip() == "":
                    k += 1
                if k < n and ACCOUNT_LINE_RE.match(lines[k].strip()):
                    acc = lines[k].strip()
                    print(f"[SPLIT_ACCOUNTS] Line {i+1}: Found multi-line account number: {acc}")
                    if current_account and buffer:
                        account_chunks[current_account] = (
                            account_chunks.get(current_account, "") + "\n" + "\n".join(buffer)
                        )
                        buffer = []
                    current_account = acc
                    i = k + 1
                    continue

        # --- Default: add to current account buffer ---
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
    
    print(f"[SPLIT_ACCOUNTS] ✓ Found {len(chunks)} unique accounts")
    for idx, chunk in enumerate(chunks):
        acc_num = chunk.get("accountNumber", "")
        text_len = len(chunk.get("text", ""))
        print(f"[SPLIT_ACCOUNTS]   Account {idx+1}: {acc_num} ({text_len} chars)")
    print(f"{'='*80}\n")
    
    return chunks


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

CRITICAL: Extract EVERYTHING you see - printed text, handwritten text, stamps, seals, and marks.

IMPORTANT: Use SIMPLE, SHORT field names.
- Example: If you see "VERIFIED" stamp → use "Verified" with value "Yes" or "VERIFIED"
- Example: If you see handwritten "4630" near "Account" → use "Account_Number" with value "4630"
- Simplify all verbose labels to their core meaning

SPECIAL ATTENTION REQUIRED:
🔴 **HANDWRITTEN TEXT:** Extract ALL handwritten numbers and text - these are CRITICAL data points
   - Handwritten numbers are often account numbers, reference numbers, or IDs
   - Extract them with appropriate field names (Account_Number, Reference_Number, etc.)
   
🔴 **STAMPS & SEALS:** Extract ALL stamps, seals, and verification marks
   - "VERIFIED" stamp → Verified: "Yes" or "VERIFIED"
   - Date stamps → Stamp_Date or Verified_Date
   - Names in stamps → Verified_By or Stamped_By
   - Official seals → Official_Seal: "Present" or description
   
🔴 **MULTIPLE NUMBERS:** Documents often have MULTIPLE number types - extract ALL of them
   - Certificate_Number (printed certificate ID)
   - Account_Number (handwritten or printed account/billing number)
   - File_Number (state file number)
   - Reference_Number (reference or tracking number)

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
✓ **ALL IDENTIFYING NUMBERS:**
  - Certificate_Number, License_Number, File_Number, Document_Number
  - Reference_Number, Registration_Number, Case_Number
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
  - **CRITICAL FOR ACCOUNT NUMBER**: 
    * Extract ONLY the PRIMARY account number from the main form/header (usually labeled "ACCOUNT NUMBER:" at the top)
    * DO NOT extract account numbers from summary lists, sidebars, or reference sections
    * If you see a list of multiple account numbers (like "Account Numbers: 123, 456, 789"), IGNORE IT
    * Only extract the single account number that this specific page is about
    * **HANDWRITTEN ACCOUNT NUMBERS**: If you find a 6 to 9 -digit number that appears to be handwritten and has NO clear field label, treat it as "Account_Number"
    * This is especially common in death certificates where account numbers may be written by hand
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
- Use descriptive names based on the field label
- Replace spaces with underscores
- Example: "License Number" → "License_Number"
- Example: "Date of Birth" → "Date_of_Birth"

RETURN FORMAT:
- Valid JSON only
- One field per label-value pair
- Only include fields with actual values (omit empty fields)

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
Return ONLY valid JSON in this exact format:
{
  "documents": [
    {
      "document_id": "dl_001",
      "document_type": "drivers_license",
      "document_type_display": "Driver's License / ID Card",
      "document_icon": "🪪",
      "document_description": "Government-issued identification",
      "extracted_fields": {
        "Document_Type": "Driver License",
        "State": "Delaware",
        "License_Number": "1234567",
        "Full_Name": "John Doe",
        "First_Name": "John",
        "Last_Name": "Doe",
        "Date_of_Birth": "01/15/1980",
        "Sex": "M",
        "Height": "5-10",
        "Weight": "180",
        "Eye_Color": "BRN",
        "Hair_Color": "BRN",
        "Address": "123 Main St",
        "City": "Wilmington",
        "State_Address": "DE",
        "ZIP_Code": "19801",
        "Issue_Date": "12/03/2012",
        "Expiration_Date": "12/03/2020",
        "License_Class": "D",
        "DD_Number": "1234567890123",
        "Organ_Donor": "Yes"
      }
    }
  ]
}

CRITICAL: Only include fields that are VISIBLE in the document. Do not use "N/A" or empty strings.
Extract EVERYTHING you can see on the ID card - be thorough and complete!
"""

def get_loan_document_prompt():
    """Get the specialized prompt for loan/account documents"""
    return """
You are an AI assistant that extracts ALL structured data from loan account documents.

Extract EVERY piece of information from the document and return it as valid JSON.

🔴🔴🔴 CRITICAL PARSING RULE - READ THIS FIRST 🔴🔴🔴

The OCR often reads form labels and values together without spaces. You MUST parse them correctly:

IF YOU SEE THIS IN THE TEXT:
- "PurposeConsumer" or "Purpose:Consumer" or "Purpose: Consumer" → Extract as: "AccountPurpose": "Consumer"
- "TypePersonal" or "Type:Personal" or "Type: Personal" → Extract as: "AccountType": "Personal"
- "PurposeConsumer Personal" or "Purpose:Consumer Type:Personal" → Extract as TWO fields:
  * "AccountPurpose": "Consumer"
  * "AccountType": "Personal"

PARSING RULES:
1. Look for the word "Purpose" followed by a value (Consumer, Checking, Savings, etc.) → Extract as AccountPurpose
2. Look for the word "Type" followed by a value (Personal, Business, etc.) → Extract as AccountType
3. These are ALWAYS separate fields even if they appear together in the text
4. NEVER combine them into one field

WRONG ❌:
{
  "AccountPurpose": "Consumer Personal"
}

CORRECT ✅:
{
  "AccountPurpose": "Consumer",
  "AccountType": "Personal"
}

IF THE TEXT SAYS "PurposeConsumer Personal", PARSE IT AS:
- Find "Purpose" → Next word is "Consumer" → AccountPurpose: "Consumer"
- Find "Personal" (after Consumer) → This is the Type value → AccountType: "Personal"

REQUIRED FIELDS (extract if present):

For documents with ONE signer:
{
  "AccountNumber": "string",
  "AccountHolderNames": ["name1", "name2"],
  "AccountType": "string",
  "OwnershipType": "string",
  "WSFSAccountType": "string",
  "AccountPurpose": "string",
  "SSN": "string or list of SSNs",
  "StampDate": "string (e.g., DEC 26 2014, JAN 15 2023)",
  "ReferenceNumber": "string (e.g., #298, Ref #123)",
  "ProcessedDate": "string",
  "ReceivedDate": "string",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DateOfBirth": "string",
  "Signer1_Address": "string",
  "Signer1_Phone": "string",
  "Signer1_Email": "string",
  "SupportingDocuments": [
    {
      "DocumentType": "string",
      "Details": "string"
    }
  ]
}

For documents with MULTIPLE signers, add Signer2_, Signer3_, etc.:
{
  "AccountNumber": "string",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DateOfBirth": "string",
  "Signer2_Name": "string",
  "Signer2_SSN": "string",
  "Signer2_DateOfBirth": "string"
}

FIELD DEFINITIONS - READ CAREFULLY:

🔴 CRITICAL: AccountPurpose and AccountType are TWO SEPARATE FIELDS - NEVER combine them!

1. AccountPurpose: The CATEGORY or CLASSIFICATION of the account.
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
   - Text: "Purpose: Consumer" → AccountPurpose: "Consumer"
   - Text: "PurposeConsumer" → AccountPurpose: "Consumer"
   - Text: "Purpose:Consumer Type:Personal" → AccountPurpose: "Consumer" (extract ONLY the Purpose value)
   - Text: "PurposeConsumer Personal" → AccountPurpose: "Consumer" (extract ONLY "Consumer", NOT "Consumer Personal")

2. AccountType: The USAGE TYPE or WHO uses the account.
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
   - Text: "Type: Personal" → AccountType: "Personal"
   - Text: "TypePersonal" → AccountType: "Personal"
   - Text: "Purpose:Consumer Type:Personal" → AccountType: "Personal" (extract ONLY the Type value)
   - Text: "PurposeConsumer Personal" → AccountType: "Personal" (extract ONLY "Personal", which comes after "Consumer")

3. WSFSAccountType: The SPECIFIC internal bank account type code or classification. Look for:
   - Specific product names like "Premier Checking", "Platinum Savings", "Gold CD", "WSFS Saving Core"
   - Internal codes or account classifications
   - Branded account names unique to the bank
   - **IMPORTANT**: This field often appears WITHOUT a header label - just the value written on the form
   - Look for bank-specific product names like "WSFS Saving Core", "WSFS Checking Plus", etc.
   - These are usually written in a specific area of the form, even without a label
   - If you see "WSFS Saving Core" or similar bank product names, extract as WSFSAccountType
   - This is SEPARATE from AccountType (Personal/Business) and AccountPurpose (Consumer/Checking)

4. OwnershipType: WHO owns the account legally. Common values:
   - "Individual" or "Single Owner" (single owner)
   - "Joint" or "Joint Owners" (multiple owners with equal rights)
   - "Joint with Rights of Survivorship"
   - "Trust" (held in trust)
   - "Estate" (estate account)
   - "Custodial" (for minor)
   - "Business" or "Corporate"

EXTRACTION RULES - EXTRACT EVERYTHING COMPLETELY:
- 🔴 CRITICAL: Extract EVERY field visible in the document with COMPLETE information
- 🔴 DO NOT skip any fields or partial information - extract EVERYTHING you see
- Include ALL form fields, checkboxes, dates, amounts, addresses, phone numbers, emails
- Extract ALL names, titles, positions, relationships with FULL details
- Include ALL dates (opened, closed, effective, expiration, birth dates, etc.)
- Extract COMPLETE addresses (street, city, state, zip) - not just partial
- Extract COMPLETE phone numbers with area codes
- Extract COMPLETE SSNs, license numbers, account numbers
- **IMPORTANT: Extract ALL STAMP DATES** - Look for date stamps like "DEC 26 2014", "JAN 15 2023", etc.
- **IMPORTANT: Extract REFERENCE NUMBERS** - Look for numbers like "#298", "Ref #123", etc.
- Extract ALL identification numbers (SSN, Tax ID, License numbers, etc.)
- **CRITICAL: PARSE AND SEPARATE COMBINED VALUES** - OCR often reads form labels and values together without spaces:
  * If you see "PurposeConsumer Personal" → Parse as: AccountPurpose: "Consumer", AccountType: "Personal"
  * If you see "TypeBusiness" → Parse as: AccountType: "Business"
  * If you see "OwnershipJoint" → Parse as: OwnershipType: "Joint"
  * RULE: Look for field labels (Purpose, Type, Ownership) followed immediately by values
  * RULE: Capital letters in the middle of text indicate separate words/fields
  * RULE: Match the pattern against field definitions above to extract correct values
  * DO NOT create a field with combined text - ALWAYS separate into proper fields
  * Example: NEVER output "AccountPurpose": "PurposeConsumer Personal" - ALWAYS split it
- **CRITICAL: EXTRACT WSFS PRODUCT NAMES WITHOUT HEADERS** - Look for bank product names that appear without field labels:
  * "WSFS Saving Core" (no header) → WSFSAccountType: "WSFS Saving Core"
  * "WSFS Checking Plus" (no header) → WSFSAccountType: "WSFS Checking Plus"
  * "WSFS Money Market" (no header) → WSFSAccountType: "WSFS Money Market"
  * These product names are usually written in a specific section of the form
  * Extract them even if they don't have a field label like "Account Type:" or "Product:"
  * This is SEPARATE from AccountType (Personal/Business) and AccountPurpose (Consumer/Checking)
- **CRITICAL FOR ACCOUNT NUMBER**: 
  * Extract ONLY the PRIMARY account number from the main form/header (usually labeled "ACCOUNT NUMBER:" at the top)
  * DO NOT extract account numbers from summary lists, sidebars, or reference sections
  * If you see a list of multiple account numbers (like "Account Numbers: 123, 456, 789"), IGNORE IT
  * Only extract the single account number that this specific page is about
  * The primary account number is typically at the top of the form in a field labeled "ACCOUNT NUMBER"
  * **HANDWRITTEN ACCOUNT NUMBERS**: If you find a 9-digit number that appears to be handwritten and has NO clear field label, treat it as "AccountNumber"
  * This is especially common in death certificates where account numbers may be written by hand
  * Look for standalone 6-digit numbers without labels - these are likely handwritten account numbers
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
- For AccountHolderNames: Return as array even if single name, e.g., ["John Doe"]
- 🔴🔴🔴 CRITICAL FOR SIGNERS - EXTRACT COMPLETE INFORMATION - DO NOT SKIP ANYTHING 🔴🔴🔴
  * SIGNERS ARE THE MOST IMPORTANT PART - Extract EVERY SINGLE piece of information for EACH signer
  * DO NOT skip any signer fields - extract EVERYTHING you see
  * For EACH signer, you MUST extract ALL of these fields if they are visible:
    
    SIGNER 1 - EXTRACT ALL OF THESE:
    - Signer1_Name (full name - first, middle, last)
    - Signer1_SSN (social security number - complete 9 digits)
    - Signer1_DateOfBirth (date of birth in any format)
    - Signer1_Address (COMPLETE address: street number, street name, apartment/unit, city, state, zip code)
    - Signer1_Phone (phone number with area code)
    - Signer1_Email (email address)
    - Signer1_DriversLicense (driver's license number AND state)
    - Signer1_DriversLicenseExpiration (expiration date if shown)
    - Signer1_Citizenship (citizenship status: US Citizen, Permanent Resident, etc.)
    - Signer1_Occupation (job title or occupation)
    - Signer1_Employer (employer name and address if shown)
    - Signer1_EmployerPhone (employer phone if shown)
    - Signer1_MothersMaidenName (if shown)
    - Signer1_Relationship (relationship to account: Owner, Joint Owner, etc.)
    - Signer1_Signature (if signature is present, note "Signed" or "Signature present")
    - Signer1_SignatureDate (date of signature if shown)
    - ANY other signer-specific information you see
    
    SIGNER 2 - EXTRACT ALL OF THESE (if second signer exists):
    - Signer2_Name, Signer2_SSN, Signer2_DateOfBirth, Signer2_Address, Signer2_Phone, Signer2_Email
    - Signer2_DriversLicense, Signer2_DriversLicenseExpiration, Signer2_Citizenship
    - Signer2_Occupation, Signer2_Employer, Signer2_EmployerPhone
    - Signer2_MothersMaidenName, Signer2_Relationship, Signer2_Signature, Signer2_SignatureDate
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
- For SupportingDocuments: Create separate objects for EACH document type found
- Preserve exact account numbers and SSNs as they appear
- If you see multiple account types mentioned, use the most specific one
- Look carefully at the entire document text for ALL fields
- Pay special attention to compliance sections, checkboxes, verification stamps, and date stamps
- **REMEMBER: Only extract what you can SEE in the document. Do not invent or assume fields.**

EXAMPLES OF CORRECT FIELD SEPARATION:

Example 1: Document shows "Purpose: Consumer" and "Type: Personal"
{
  "AccountPurpose": "Consumer",
  "AccountType": "Personal"
}

Example 2: Document shows "Purpose: Consumer", "Type: Personal", and "WSFS Saving Core" (no header for WSFS)
{
  "AccountPurpose": "Consumer",
  "AccountType": "Personal",
  "WSFSAccountType": "WSFS Saving Core"
}

Example 3: Document shows combined text "PurposeConsumer Personal" (NO SPACES)
{
  "AccountPurpose": "Consumer",
  "AccountType": "Personal"
}

Example 4: Document shows "Purpose: Consumer Type: Business" and also has "WSFS Checking Plus" written somewhere
{
  "AccountPurpose": "Consumer",
  "AccountType": "Business",
  "WSFSAccountType": "WSFS Checking Plus"
}

Example 5: Document says "Premier Checking Account for Business Operations, Consumer Banking"
{
  "AccountType": "Business",
  "WSFSAccountType": "Premier Checking",
  "AccountPurpose": "Consumer"
}

Example 6: Document says "Personal IRA Savings Account"
{
  "AccountType": "Personal",
  "WSFSAccountType": "IRA Savings",
  "AccountPurpose": "Retirement"
}

Example 4: SupportingDocuments with OFAC check and verification
{
  "SupportingDocuments": [
    {
      "DocumentType": "Driver's License",
      "Details": "DE #1234567, Expires: 12/03/2020"
    },
    {
      "DocumentType": "OFAC Check",
      "Details": "Completed on 3/18/2016 - No match found"
    },
    {
      "DocumentType": "Background Check",
      "Details": "Verified by Sara Halttunen on 12/24/2014"
    },
    {
      "DocumentType": "ID Verification",
      "Details": "Drivers License #9243231 verified"
    }
  ]
}

Example 5: Multiple supporting documents
{
  "SupportingDocuments": [
    {
      "DocumentType": "Driver's License",
      "Details": "State: DE, Number: 719077, Issued: 12-03-2012, Expires: 12-03-2020"
    },
    {
      "DocumentType": "OFAC Screening",
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

CRITICAL RULES:
1. ONLY extract fields that are VISIBLE in the document
2. DO NOT include fields with "N/A" or empty values
3. For multiple signers, use Signer1_, Signer2_, Signer3_ prefixes
4. Each signer's information should be separate fields, not nested objects

🔴 FINAL REMINDER - DO NOT FORGET 🔴
AccountPurpose and AccountType are ALWAYS TWO SEPARATE FIELDS!
NEVER combine them like "AccountPurpose": "Consumer Personal"
ALWAYS separate: "AccountPurpose": "Consumer", "AccountType": "Personal"
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


def flatten_nested_objects(data):
    """
    Flatten nested objects like Signer1: {Name: "John"} to Signer1_Name: "John"
    Also handles SupportingDocuments and other nested structures
    """
    if not isinstance(data, dict):
        return data
    
    flattened = {}
    
    for key, value in data.items():
        # Check if this is a signer object (Signer1, Signer2, etc.)
        # Match: Signer1, Signer2, Signer_1, Signer_2, etc.
        if (key.startswith("Signer") and isinstance(value, dict) and 
            any(char.isdigit() for char in key)):
            # Flatten the signer object
            print(f"[DEBUG] Flattening signer object: {key} with {len(value)} fields")
            for sub_key, sub_value in value.items():
                flat_key = f"{key}_{sub_key}"
                flattened[flat_key] = sub_value
                print(f"[DEBUG] Created flat field: {flat_key} = {sub_value}")
        # Keep arrays and other structures as-is
        elif isinstance(value, (list, str, int, float, bool)) or value is None:
            flattened[key] = value
        # Recursively flatten other nested dicts (but not arrays of dicts)
        elif isinstance(value, dict):
            # Check if it's a special structure like SupportingDocuments
            if key in ["SupportingDocuments", "AccountHolderNames"]:
                flattened[key] = value
            else:
                # Flatten other nested objects
                for sub_key, sub_value in value.items():
                    flattened[f"{key}_{sub_key}"] = sub_value
        else:
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


def extract_text_with_textract_async(s3_bucket: str, s3_key: str):
    """Extract text from PDF using Textract async API (for scanned/multi-page PDFs)"""
    try:
        # Start async job
        response = textract.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': s3_bucket, 'Name': s3_key}}
        )
        
        job_id = response['JobId']
        
        # Poll for completion (max 5 minutes)
        max_attempts = 60
        attempt = 0
        
        while attempt < max_attempts:
            time.sleep(5)  # Wait 5 seconds between checks
            
            result = textract.get_document_text_detection(JobId=job_id)
            status = result['JobStatus']
            
            if status == 'SUCCEEDED':
                # Extract text from all pages
                extracted_text = ""
                for block in result.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        extracted_text += block['Text'] + "\n"
                
                # Handle pagination if there are more results
                next_token = result.get('NextToken')
                while next_token:
                    result = textract.get_document_text_detection(
                        JobId=job_id,
                        NextToken=next_token
                    )
                    for block in result.get('Blocks', []):
                        if block['BlockType'] == 'LINE':
                            extracted_text += block['Text'] + "\n"
                    next_token = result.get('NextToken')
                
                return extracted_text
            
            elif status == 'FAILED':
                raise Exception(f"Textract async job failed: {result.get('StatusMessage', 'Unknown error')}")
            
            attempt += 1
        
        raise Exception("Textract async job timed out after 5 minutes")
        
    except Exception as e:
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


def extract_basic_fields(text: str, num_fields: int = 100):
    """Extract ALL fields from any document (up to 100 fields) - BE THOROUGH"""
    prompt = f"""
YOU ARE A METICULOUS DATA EXTRACTION EXPERT. Extract EVERY SINGLE field from this document.

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

CRITICAL NAMING FOR DEATH CERTIFICATES AND VITAL RECORDS:
- ANY handwritten number on the certificate MUST be extracted as "account_number"
- DO NOT use "reference_number", "certificate_number", or any other name
- ALWAYS use "account_number" for handwritten numbers
- Examples:
  * Handwritten "468431466" → account_number: "468431466"
  * Handwritten "4630" → account_number: "4630"
  * Handwritten "85333" → account_number: "85333"
  * Handwritten "K1-0011267" → account_number: "K1-0011267"
- If there are MULTIPLE handwritten numbers, use account_number, account_number_2, account_number_3, etc.
- NEVER use "reference_number" for handwritten numbers on certificates

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

Return ONLY valid JSON. Extract up to {num_fields} fields - BE THOROUGH AND COMPLETE!

Example format for Death Certificate:
{{
  "account_number": "468431466",
  "state_file_number": "K1-0000608",
  "date_pronounced_dead": "01/09/2016",
  "time_pronounced_dead": "22:29",
  "actual_date_of_death": "January 9, 2016",
  "time_of_death": "22:29",
  "deceased_name": "John Doe",
  "place_of_death": "New Castle, DE",
  "license_number_for": "funeral_director_name",
  "signature_of_person_pronouncing_death": "signature_present",
  "date_signed": "01/09/2016",
  "cause_of_death": "description",
  "manner_of_death": "Natural",
  "was_medical_examiner_contacted": "Yes",
  ...
}}
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


def detect_document_type(text: str):
    """
    Detect document type using hierarchical decision tree
    Based on specific visual and textual markers
    """
    print(f"\n{'='*80}")
    print(f"[DETECT_TYPE] Starting document type detection...")
    print(f"[DETECT_TYPE] Text length: {len(text)} characters")
    
    text_upper = text.upper()
    text_lower = text.lower()
    lines = text.split('\n')
    
    # Helper function to check for patterns
    def contains_any(patterns):
        return any(p.upper() in text_upper for p in patterns)
    
    def contains_all(patterns):
        return all(p.upper() in text_upper for p in patterns)
    
    # ============================================================
    # STEP 1: Check for BANK LOGO (WSFS Bank)
    # ============================================================
    if "WSFS BANK" in text_upper or "WSFS" in text_upper:
        print(f"[DETECT_TYPE] WSFS Bank detected - checking form type...")
        
        # Business Card Order Form
        if contains_any(["BUSINESS CARD ORDER FORM", "CARD ORDER FORM"]):
            print(f"[DETECT_TYPE] ✓ Detected: Business Card Order Form")
            print(f"{'='*80}\n")
            return "business_card"
        
        # Account Withdrawal Form
        if contains_any(["ACCOUNT WITHDRAWAL", "WITHDRAWAL FORM"]):
            print(f"[DETECT_TYPE] ✓ Detected: Account Withdrawal Form")
            print(f"{'='*80}\n")
            return "invoice"  # Using invoice as withdrawal form
        
        # Name Change Request
        if contains_any(["NAME CHANGE REQUEST", "NAME CHANGE FORM"]):
            print(f"[DETECT_TYPE] ✓ Detected: Name Change Request")
            print(f"{'='*80}\n")
            return "contract"  # Using contract for name change
        
        # Tax ID Number Change
        if contains_any(["TAX ID NUMBER CHANGE", "TAX ID CHANGE", "TIN CHANGE"]):
            print(f"[DETECT_TYPE] ✓ Detected: Tax ID Change Form")
            print(f"{'='*80}\n")
            return "tax_form"
        
        # ATM/Debit Card Request
        if contains_any(["ATM/POS/DEBIT CARD REQUEST", "CARD REQUEST", "DEBIT CARD REQUEST"]):
            print(f"[DETECT_TYPE] ✓ Detected: Card Request Form")
            print(f"{'='*80}\n")
            return "business_card"
        
        # Check for Account Opening Document vs Signature Card
        # Both have: ACCOUNT NUMBER, ACCOUNT HOLDER NAMES, OWNERSHIP TYPE
        has_account_number = "ACCOUNT NUMBER" in text_upper
        has_account_holder = "ACCOUNT HOLDER" in text_upper
        has_ownership = "OWNERSHIP TYPE" in text_upper
        
        if has_account_number and has_account_holder and has_ownership:
            print(f"[DEBUG] Found account document indicators - distinguishing type...")
            
            # Count signature lines (indicators of signature card)
            signature_count = text_upper.count("SIGNATURE")
            signature_line_count = text.count("___________")  # Signature lines
            
            # Check for signature card indicators
            has_tin_withholding = "TIN" in text_upper and "BACKUP WITHHOLDING" in text_upper
            has_multiple_signatures = signature_count >= 3 or signature_line_count >= 4
            has_signature_card_title = "SIGNATURE CARD" in text_upper
            
            # Check for account opening indicators
            has_date_opened = "DATE OPENED" in text_upper
            has_account_product = any(prod in text_upper for prod in [
                "CORE CHECKING", "RELATIONSHIP CHECKING", "MONEY MARKET", 
                "SAVINGS", "PREMIER CHECKING", "PLATINUM"
            ])
            has_account_purpose = "ACCOUNT PURPOSE" in text_upper
            has_consumer_business = "CONSUMER" in text_upper or "BUSINESS" in text_upper
            
            # Decision logic
            if has_signature_card_title:
                print(f"[INFO] Detected: Joint Account Signature Card (explicit title)")
                return "loan_document"
            
            elif has_multiple_signatures and has_tin_withholding:
                print(f"[INFO] Detected: Joint Account Signature Card (multiple signatures + TIN)")
                return "loan_document"
            
            elif has_date_opened and has_account_product and has_account_purpose:
                print(f"[INFO] Detected: Account Opening Document (has DATE OPENED + product + purpose)")
                return "loan_document"
            
            elif has_date_opened and has_consumer_business:
                print(f"[INFO] Detected: Account Opening Document (has DATE OPENED + consumer/business)")
                return "loan_document"
            
            elif has_multiple_signatures:
                print(f"[INFO] Detected: Joint Account Signature Card (multiple signatures)")
                return "loan_document"
            
            else:
                # Default to account opening document if unclear
                print(f"[INFO] Detected: Account Opening Document (default)")
                return "loan_document"
    
    # ============================================================
    # STEP 2: Check for DEATH CERTIFICATE
    # ============================================================
    if contains_any(["CERTIFICATION OF VITAL RECORD", "CERTIFICATE OF DEATH"]) or \
       (contains_any(["DEATH", "DECEASED", "DECEDENT"]) and contains_any(["CERTIFICATE", "CERTIFICATION"])):
        print(f"[DEBUG] Death certificate detected - checking state...")
        
        # Delaware Death Certificate
        if "DELAWARE" in text_upper or "STATE OF DELAWARE" in text_upper:
            print(f"[INFO] Detected: Delaware Death Certificate")
            return "death_certificate"
        
        # Pennsylvania Death Certificate
        if "PENNSYLVANIA" in text_upper or "COMMONWEALTH OF PENNSYLVANIA" in text_upper or \
           "LOCAL REGISTRAR" in text_upper:
            print(f"[INFO] Detected: Pennsylvania Death Certificate")
            return "death_certificate"
        
        # Generic death certificate
        print(f"[INFO] Detected: Death Certificate (Generic)")
        return "death_certificate"
    
    # ============================================================
    # STEP 3: Check for REGISTER OF WILLS / Letters Testamentary
    # ============================================================
    if contains_any(["REGISTER OF WILLS", "LETTERS TESTAMENTARY", "LETTERS OF ADMINISTRATION"]):
        print(f"[INFO] Detected: Letters Testamentary/Administration")
        return "contract"  # Using contract for legal documents
    
    # ============================================================
    # STEP 4: Check for AFFIDAVIT (Small Estates)
    # ============================================================
    if "AFFIDAVIT" in text_upper and contains_any(["SMALL ESTATE", "SMALL ESTATES"]):
        print(f"[INFO] Detected: Small Estate Affidavit")
        return "contract"
    
    # ============================================================
    # STEP 5: Check for FUNERAL HOME INVOICE
    # ============================================================
    if contains_any(["FUNERAL HOME", "FUNERAL SERVICES", "STATEMENT OF FUNERAL EXPENSES"]) and \
       contains_any(["INVOICE", "STATEMENT", "BILL", "CHARGES"]):
        print(f"[INFO] Detected: Funeral Invoice")
        return "invoice"
    
    # ============================================================
    # STEP 6: Check for Loan/Account Documents FIRST (before ID cards)
    # ============================================================
    # Check for required account document fields
    has_account_number = "ACCOUNT NUMBER" in text_upper
    has_account_holder = "ACCOUNT HOLDER" in text_upper
    has_account_purpose = "ACCOUNT PURPOSE" in text_upper
    has_account_type = "ACCOUNT TYPE" in text_upper
    has_ownership_type = "OWNERSHIP TYPE" in text_upper
    
    # Count how many required fields are present
    required_fields_count = sum([
        has_account_number,
        has_account_holder,
        has_account_purpose,
        has_account_type,
        has_ownership_type
    ])
    
    # If 3 or more required fields present, it's likely a loan/account document
    # This check happens BEFORE ID card check because loan docs often contain attached IDs
    if required_fields_count >= 3:
        print(f"[DEBUG] Found {required_fields_count}/5 account document fields")
        
        # Additional checks for account products
        has_checking_savings = any(prod in text_upper for prod in [
            "CHECKING", "SAVINGS", "MONEY MARKET", "CD", "CERTIFICATE OF DEPOSIT"
        ])
        
        has_consumer_business = "CONSUMER" in text_upper or "BUSINESS" in text_upper
        
        if has_checking_savings or has_consumer_business:
            print(f"[INFO] Detected: Loan/Account Document (field-based detection)")
            return "loan_document"
    
    # ============================================================
    # STEP 7: Check for ID CARD (Driver's License) - AFTER loan document check
    # ============================================================
    if contains_any(["DRIVER LICENSE", "DRIVER'S LICENSE", "DRIVERS LICENSE", "IDENTIFICATION CARD", "ID CARD"]):
        print(f"[INFO] Detected: Driver's License/ID Card")
        return "drivers_license"
    
    # ============================================================
    # FALLBACK: Use keyword-based scoring for other document types
    # ============================================================
    print(f"[DEBUG] No specific pattern matched - using keyword scoring...")
    
    scores = {}
    matched_keywords = {}
    for doc_type, info in SUPPORTED_DOCUMENT_TYPES.items():
        score = 0
        matches = []
        for keyword in info['keywords']:
            if keyword.lower() in text_lower:
                score += 1
                matches.append(keyword)
        scores[doc_type] = score
        if matches:
            matched_keywords[doc_type] = matches
    
    print(f"[DEBUG] Keyword scores: {scores}")
    
    # Special handling for loan documents
    loan_score = scores.get('loan_document', 0)
    if loan_score >= 5:
        print(f"[INFO] Detected as loan_document (score: {loan_score})")
        return 'loan_document'
    
    # Check for strong indicators
    priority_types = ['marriage_certificate', 'passport', 'insurance_policy']
    for priority_type in priority_types:
        priority_score = scores.get(priority_type, 0)
        if priority_score >= 2 and priority_score > loan_score:
            print(f"[INFO] Detected as {priority_type} (score: {priority_score})")
            return priority_type
    
    # Check loan document with lower threshold
    if loan_score >= 2:
        print(f"[INFO] Detected as loan_document (score: {loan_score})")
        return 'loan_document'
    
    # If we have a clear winner (score >= 2), use it
    max_score = max(scores.values()) if scores else 0
    if max_score >= 2:
        detected_type = max(scores, key=scores.get)
        print(f"[INFO] Detected as {detected_type} (score: {max_score})")
        return detected_type
    
    print(f"[DETECT_TYPE] ⚠️ Document type unknown")
    print(f"{'='*80}\n")
    return "unknown"


def process_loan_document(text: str, job_id: str = None):
    """
    Special processing for loan/account documents with account splitting
    Returns same format as loan_pipeline_ui.py
    
    OPTIMIZATION: We no longer call LLM for each account during upload.
    Instead, we just identify accounts and their text chunks.
    Page-level data extraction happens during pre-caching, which is more efficient.
    """
    try:
        print(f"\n{'='*80}")
        print(f"[LOAN_DOCUMENT] Starting loan document processing...")
        print(f"{'='*80}\n")
        
        # Split into individual accounts
        chunks = split_accounts_strict(text)
        
        if not chunks:
            print(f"[LOAN_DOCUMENT] ⚠️ No accounts found, treating as single document")
            # No accounts found, treat as single document
            chunks = [{"accountNumber": "N/A", "text": text}]
        
        total = len(chunks)
        accounts = []
        
        # Log processing start
        print(f"[LOAN_DOCUMENT] Found {total} accounts to process")
        print(f"[LOAN_DOCUMENT] OPTIMIZATION: Skipping account-level LLM calls")
        print(f"[LOAN_DOCUMENT] Page-level data will be extracted during pre-caching\n")
        
        for idx, chunk in enumerate(chunks, start=1):
            acc = chunk["accountNumber"] or f"Unknown_{idx}"
            
            # Update progress for each account
            # Progress: 40% (basic fields) + 30% (account processing) = 40 + (30 * idx/total)
            progress = 40 + int((30 * idx) / total)
            
            if job_id and job_id in job_status_map:
                job_status_map[job_id].update({
                    "status": f"Identifying account {idx}/{total}: {acc}",
                    "progress": progress
                })
            
            print(f"[LOAN_DOCUMENT] Account {idx}/{total}: {acc}")
            
            try:
                # OPTIMIZATION: Skip LLM call here - we'll extract page-level data during pre-caching
                # This saves significant processing time and LLM costs
                
                # Just create a placeholder with account info
                parsed = {
                    "AccountNumber": acc,
                    "AccountHolderNames": [],
                    "note": "Data will be extracted from individual pages during pre-caching"
                }
                    
                # OPTIMIZATION: Set placeholder values - accuracy will be calculated from actual extracted data
                accounts.append({
                    "accountNumber": acc,
                    "result": parsed,
                    "accuracy_score": None,  # Will be calculated automatically from extracted data
                    "filled_fields": 0,
                    "total_fields": 0,
                    "fields_needing_review": [],
                    "needs_human_review": False,
                    "optimized": True  # Flag to indicate this used optimized processing
                })
                    
            except Exception as e:
                print(f"[LOAN_DOCUMENT ERROR] Account {acc}: {str(e)}")
                accounts.append({
                    "accountNumber": acc,
                    "error": str(e),
                    "accuracy_score": 0
                })
        
        print(f"\n[LOAN_DOCUMENT] ✓ Completed processing {len(accounts)} accounts")
        print(f"{'='*80}\n")
        
        # Calculate overall status from actual account data
        # Accuracy will be calculated automatically based on OCR and LLM extraction quality
        overall_accuracy = None  # Let the system calculate this naturally
        needs_review = False
        all_fields_needing_review = []
        
        # Return in format compatible with universal IDP
        return {
            "documents": [{
                "document_id": "loan_doc_001",
                "document_type": "loan_document",
                "document_type_display": "Loan/Account Document",
                "document_icon": "🏦",
                "document_description": "Banking or loan account information",
                "extracted_fields": {
                    "total_accounts": total,
                    "accounts_processed": len(accounts)
                },
                "accounts": accounts,  # Special field for loan documents
                "accuracy_score": overall_accuracy,
                "total_fields": sum(a.get("total_fields", 0) for a in accounts),  # Sum of all fields across all accounts
                "filled_fields": sum(a.get("filled_fields", 0) for a in accounts),
                "needs_human_review": needs_review,
                "fields_needing_review": all_fields_needing_review
            }]
        }
        
    except Exception as e:
        return {
            "documents": [{
                "document_id": "loan_error_001",
                "document_type": "loan_document",
                "document_type_display": "Loan/Account Document (Error)",
                "error": str(e),
                "extracted_fields": {},
                "accuracy_score": 0
            }]
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
- Use descriptive names based on the exact label in the document
- Replace spaces with underscores
- Examples:
  * "LICENSE NUMBER FOR" → "License_Number_For"
  * "DATE PRONOUNCED DEAD" → "Date_Pronounced_Dead"
  * "ACTUAL OR PRESUMED DATE OF DEATH" → "Actual_Or_Presumed_Date_Of_Death"
  * "CAUSE OF DEATH" → "Cause_Of_Death"
  * "K1-0011267" → "Case_Number" or "File_Number"

CRITICAL NAMING FOR DEATH CERTIFICATES AND VITAL RECORDS:
- ANY handwritten number on the certificate MUST be extracted as "Account_Number"
- DO NOT use "Reference_Number", "Certificate_Number", or any other name
- ALWAYS use "Account_Number" for handwritten numbers
- IMPORTANT: Only extract Account_Number if there is a SEPARATE handwritten number that is DIFFERENT from the Certificate_Number
- DO NOT extract partial numbers or substrings of the Certificate_Number as Account_Number
- Examples:
  * Handwritten "468431466" (separate from cert number) → Account_Number: "468431466"
  * Handwritten "4630" (separate from cert number) → Account_Number: "4630"
  * Handwritten "85333" (separate from cert number) → Account_Number: "85333"
  * Handwritten "K1-0011267" (separate from cert number) → Account_Number: "K1-0011267"
- If Certificate_Number is "463085233" and you see "4630" which is just the first 4 digits, DO NOT extract it as Account_Number
- If there are MULTIPLE handwritten numbers, use Account_Number, Account_Number_2, Account_Number_3, etc.
- NEVER use "Reference_Number" for handwritten numbers on certificates
- If no separate handwritten account number exists, DO NOT include Account_Number field at all

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

Return ONLY valid JSON in this exact format:
{{
  "documents": [
    {{
      "document_id": "doc_001",
      "document_type": "{doc_type}",
      "document_type_display": "{doc_info['name']}",
      "document_icon": "{doc_info['icon']}",
      "document_description": "{doc_info['description']}",
      "extracted_fields": {{
        "field_name": "exact_value_from_document",
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
                    
                    parsed["AccountNumber"] = account_number
                    
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
        total_pages = len(page_infos)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_extract_page_data, page_info) for page_info in page_infos]
            
            for future in as_completed(futures):
                try:
                    if future.result():
                        success_count += 1
                    
                    # Update progress as pages complete
                    if job_id and job_id in job_status_map:
                        # Progress from 85% to 95% during page scanning
                        page_progress = 85 + int((10 * success_count) / total_pages)
                        job_status_map[job_id].update({
                            "status": f"Scanning pages: {success_count}/{total_pages} completed",
                            "progress": page_progress
                        })
                        
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
        
        # OPTIMIZATION: For PDFs, do a quick check to see if we should skip upfront OCR
        # Skip OCR for: loan documents, certificates, IDs (do page-level OCR instead)
        skip_upfront_ocr = False
        actual_doc_type = None  # Track what type of document this actually is
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
                    first_page_upper = first_page_text.upper()
                    
                    # Exclude business card order forms and other specific forms
                    is_business_card = "BUSINESS CARD ORDER FORM" in first_page_upper or "CARD ORDER FORM" in first_page_upper
                    is_card_request = "CARD REQUEST" in first_page_upper or "ATM" in first_page_upper or "DEBIT CARD" in first_page_upper
                    is_withdrawal = "WITHDRAWAL FORM" in first_page_upper or "ACCOUNT WITHDRAWAL" in first_page_upper
                    
                    # Detect certificates (death, birth, marriage, etc.) - these should skip upfront OCR
                    # Be more aggressive with detection - check for any vital record indicators
                    is_certificate = (
                        # Standard certificate indicators
                        (("CERTIFICATE" in first_page_upper or "CERTIFICATION" in first_page_upper) and
                         ("DEATH" in first_page_upper or "BIRTH" in first_page_upper or 
                          "MARRIAGE" in first_page_upper or "VITAL RECORD" in first_page_upper)) or
                        # Death-specific indicators
                        ("DECEASED" in first_page_upper or "DECEDENT" in first_page_upper) or
                        ("CAUSE OF DEATH" in first_page_upper) or
                        ("DATE OF DEATH" in first_page_upper) or
                        ("PLACE OF DEATH" in first_page_upper) or
                        ("REGISTRAR" in first_page_upper and "DEATH" in first_page_upper) or
                        # Birth-specific indicators
                        ("DATE OF BIRTH" in first_page_upper and "PLACE OF BIRTH" in first_page_upper) or
                        # Marriage-specific indicators
                        ("BRIDE" in first_page_upper and "GROOM" in first_page_upper) or
                        # Generic vital record indicators
                        ("VITAL STATISTICS" in first_page_upper) or
                        ("STATE FILE NUMBER" in first_page_upper and ("DELAWARE" in first_page_upper or "PENNSYLVANIA" in first_page_upper))
                    )
                    
                    # Detect driver's license / ID cards
                    is_drivers_license = (
                        "DRIVER" in first_page_upper or "LICENSE" in first_page_upper or
                        "IDENTIFICATION CARD" in first_page_upper or "STATE ID" in first_page_upper
                    )
                    
                    # Only treat as loan document if it has loan-specific indicators AND is not a form
                    has_loan_indicators = (
                        "ACCOUNT NUMBER" in first_page_upper and 
                        "ACCOUNT HOLDER" in first_page_upper and
                        not is_business_card and
                        not is_card_request and
                        not is_withdrawal
                    )
                    
                    # Skip upfront OCR for loan documents, certificates, and IDs
                    if has_loan_indicators or is_certificate or is_drivers_license:
                        skip_upfront_ocr = True
                        if has_loan_indicators:
                            actual_doc_type = "loan_document"
                            print(f"[INFO] OPTIMIZATION: Detected loan document - will skip full OCR and use page-level processing")
                        elif is_certificate:
                            actual_doc_type = "certificate"
                            print(f"[INFO] OPTIMIZATION: Detected certificate - will skip full OCR and use page-level processing")
                        elif is_drivers_license:
                            actual_doc_type = "drivers_license"
                            print(f"[INFO] OPTIMIZATION: Detected driver's license/ID - will skip full OCR and use page-level processing")
                    elif is_business_card or is_card_request:
                        print(f"[INFO] Detected business card/form - will use normal processing")
            except Exception as quick_scan_err:
                print(f"[WARNING] Quick scan failed: {str(quick_scan_err)}, will proceed with normal OCR")
        
        # Step 1: OCR if needed (skip if we detected a document type that should defer OCR)
        if use_ocr and not skip_upfront_ocr:
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
        elif skip_upfront_ocr:
            # OPTIMIZATION: For detected documents, extract text quickly with PyMuPDF (no expensive OCR yet)
            print(f"[INFO] OPTIMIZATION: Skipping full document OCR for {actual_doc_type} - will do page-level OCR when viewing")
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
        
        # Detect document type - use actual_doc_type if we detected it during quick scan
        if actual_doc_type == "loan_document":
            doc_type_preview = "loan_document"
        elif actual_doc_type == "certificate":
            # For certificates, run full detection to get specific type (death, birth, marriage)
            doc_type_preview = detect_document_type(text)
            print(f"[INFO] Certificate detected during quick scan, running full detection: {doc_type_preview}")
            
            # If detection fails, default to death_certificate (most common)
            if doc_type_preview == "unknown" or doc_type_preview == "invoice":
                print(f"[WARNING] Full detection failed, defaulting to death_certificate based on quick scan")
                doc_type_preview = "death_certificate"
        elif actual_doc_type == "drivers_license":
            doc_type_preview = "drivers_license"
        else:
            doc_type_preview = detect_document_type(text)
        
        print(f"[INFO] Final document type: {doc_type_preview}")
        
        job_status_map[job_id].update({
            "status": f"Document type identified: {doc_type_preview}",
            "progress": 45
        })
        
        if doc_type_preview == "loan_document":
            # OPTIMIZATION: Skip basic_fields extraction for loan documents
            # We'll get all data from page-level pre-caching
            basic_fields = {}
            
            job_status_map[job_id].update({
                "status": "Splitting document into accounts...",
                "progress": 50
            })
            
            # Quick check for number of accounts
            account_count = len(split_accounts_strict(text))
            
            if account_count > 20:
                print(f"[WARNING] Large document detected with {account_count} accounts. Processing may take 5-10 minutes.")
                job_status_map[job_id].update({
                    "status": f"Found {account_count} accounts - processing...",
                    "progress": 55
                })
            else:
                job_status_map[job_id].update({
                    "status": f"Found {account_count} accounts - processing...",
                    "progress": 55
                })
            
            job_status_map[job_id].update({
                "status": "Extracting account information...",
                "progress": 60
            })
            
            result = process_loan_document(text, job_id)
            
            job_status_map[job_id].update({
                "status": "Account processing completed",
                "progress": 70
            })
        else:
            # For non-loan documents, just detect document type - don't extract fields yet
            # Fields will be extracted page-by-page when user views them
            print(f"[INFO] Document type identified: {doc_type_preview} - fields will extract on page view")
            job_status_map[job_id].update({
                "status": f"Document type identified: {doc_type_preview}",
                "progress": 70
            })
            
            # Create result with document type but no extracted fields
            basic_fields = {}
            result = {
                "documents": [{
                    "document_type": doc_type_preview,
                    "extracted_fields": {},
                    "total_fields": 0,
                    "filled_fields": 0
                }]
            }

        
        # Add basic fields to result
        result["basic_fields"] = basic_fields
        result["ocr_file"] = ocr_file
        result["extracted_text_preview"] = text[:500] + "..." if len(text) > 500 else text
        
        # Add document type info
        if result.get("documents") and len(result["documents"]) > 0:
            doc = result["documents"][0]
            doc_type = doc.get("document_type", "unknown")
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
        
        # Step 4: Keep original filename as document name
        # DO NOT auto-generate - user wants to keep the original filename
        if not document_name:
            document_name = filename
        
        job_status_map[job_id].update({
            "status": "Preparing document record...",
            "progress": 75
        })
        
        # Step 5: Save to persistent storage
        job_status_map[job_id].update({
            "status": "Saving document to database...",
            "progress": 80
        })
        
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
        
        processed_documents.append(document_record)
        save_documents_db(processed_documents)
        
        # Step 6: Pre-cache all page data for loan documents (to avoid re-running OCR on every click)
        if doc_type_preview == "loan_document" and saved_pdf_path and result.get("documents"):
            doc_data = result["documents"][0]
            accounts = doc_data.get("accounts", [])
            
            if accounts and len(accounts) > 0:
                job_status_map[job_id].update({
                    "status": f"Scanning {len(accounts)} accounts across pages...",
                    "progress": 85
                })
                
                print(f"[INFO] Starting pre-cache for {len(accounts)} accounts")
                pre_cache_all_pages(job_id, saved_pdf_path, accounts)
                
                job_status_map[job_id].update({
                    "status": "Page scanning completed",
                    "progress": 95
                })
        
        job_status_map[job_id] = {
            "status": "✅ Processing completed",
            "progress": 100,
            "result": result,
            "ocr_file": ocr_file
        }
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
            
            # CRITICAL: Detect handwritten account numbers (6-9 digits without clear labels)
            # If AccountNumber is missing but we have a 6-9 digit number labeled as something else, reclassify it
            print(f"[DEBUG] Checking for account number in parsed data...")
            print(f"[DEBUG] Current AccountNumber value: {parsed.get('AccountNumber', 'NOT FOUND')}")
            
            if "AccountNumber" not in parsed or not parsed["AccountNumber"] or parsed["AccountNumber"] == "Unknown":
                print(f"[ACCOUNT_DETECT] AccountNumber missing or unknown, checking for 6-9 digit numbers...")
                
                # Look for fields that might be misclassified account numbers
                potential_account_fields = [
                    "Document_Number", "DocumentNumber", "Reference_Number", "ReferenceNumber",
                    "File_Number", "FileNumber", "Certificate_Number", "CertificateNumber",
                    "License_Number", "LicenseNumber", "ID_Number", "IDNumber",
                    "Registration_Number", "RegistrationNumber", "Case_Number", "CaseNumber"
                ]
                
                found_account = False
                for field_name in potential_account_fields:
                    if field_name in parsed:
                        value = str(parsed[field_name]).strip()
                        # Check if it's a 6-9 digit number (possibly with spaces or dashes)
                        clean_value = value.replace(" ", "").replace("-", "").replace(".", "")
                        if clean_value.isdigit() and 6 <= len(clean_value) <= 9:
                            print(f"[ACCOUNT_DETECT] ✓ Found potential account number in {field_name}: {value} (cleaned: {clean_value})")
                            parsed["AccountNumber"] = clean_value
                            account_number = clean_value
                            # Keep the original field too, don't delete it
                            print(f"[ACCOUNT_DETECT] ✓ Reclassified {field_name} as AccountNumber: {clean_value}")
                            found_account = True
                            break
                
                # If still no account number found, look for ANY 6-9 digit number in the data
                if not found_account:
                    print(f"[ACCOUNT_DETECT] Still no account number, scanning ALL fields for 6-9 digit numbers...")
                    for field_name, field_value in parsed.items():
                        if isinstance(field_value, (str, int)):
                            value = str(field_value).strip()
                            clean_value = value.replace(" ", "").replace("-", "").replace(".", "")
                            if clean_value.isdigit() and 6 <= len(clean_value) <= 9:
                                print(f"[ACCOUNT_DETECT] ✓ Found 6-9 digit number in {field_name}: {value} (cleaned: {clean_value})")
                                parsed["AccountNumber"] = clean_value
                                account_number = clean_value
                                print(f"[ACCOUNT_DETECT] ✓ Using {field_name} as AccountNumber: {clean_value}")
                                found_account = True
                                break
                
                if not found_account:
                    print(f"[ACCOUNT_DETECT] ⚠️ No 6-9 digit account number found in any field")
            else:
                print(f"[ACCOUNT_DETECT] ✓ AccountNumber already present: {parsed['AccountNumber']}")
            
            # Add account number to the result
            if "AccountNumber" not in parsed:
                parsed["AccountNumber"] = account_number
                print(f"[ACCOUNT_DETECT] Set AccountNumber to default: {account_number}")
            
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
    """Update page data for a specific account and save to S3 cache"""
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
            return jsonify({"success": False, "message": "Account not found"}), 404
        
        account = accounts[account_index]
        account_number = account.get("accountNumber", "Unknown")
        
        # Account-based cache key
        cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
        print(f"[INFO] Updating account page cache: {cache_key}")
        print(f"[INFO] Account: {account_number}, Page: {page_num}")
        
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
            print(f"[INFO] Updated S3 cache with edited data")
            print(f"[INFO] Updated fields: {list(page_data.keys())}")
            
            return jsonify({
                "success": True,
                "message": f"Page data updated for Account {account_number}",
                "cache_key": cache_key,
                "account_number": account_number
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


@app.route("/api/document/<doc_id>/account/<int:account_index>/clear-cache", methods=["POST"])
def clear_account_cache(doc_id, account_index):
    """Clear S3 cache for a specific account only"""
    try:
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Get the account
        doc_data = doc.get("documents", [{}])[0]
        accounts = doc_data.get("accounts", [])
        
        if account_index >= len(accounts):
            return jsonify({"success": False, "message": "Account not found"}), 404
        
        account = accounts[account_index]
        account_number = account.get("accountNumber", "Unknown")
        
        deleted_count = 0
        
        # Delete page data cache for this account only (try up to 100 pages)
        for page_num in range(100):
            try:
                cache_key = f"page_data/{doc_id}/account_{account_index}/page_{page_num}.json"
                s3_client.delete_object(Bucket=S3_BUCKET, Key=cache_key)
                deleted_count += 1
                print(f"[INFO] Deleted cache for account {account_number}: {cache_key}")
            except s3_client.exceptions.NoSuchKey:
                # No more pages for this account
                break
            except Exception as e:
                print(f"[WARNING] Failed to delete {cache_key}: {str(e)}")
                pass
        
        print(f"[INFO] Cleared {deleted_count} cache entries for account {account_number} (index {account_index})")
        
        return jsonify({
            "success": True,
            "message": f"Cache cleared for Account {account_number}",
            "pages_cleared": deleted_count,
            "account_number": account_number,
            "note": "Click on pages again to re-extract with updated prompts"
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to clear account cache: {str(e)}")
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
