#!/usr/bin/env python3
"""
Universal IDP - Handles any document type dynamically
AI determines document type and extracts relevant fields
"""

from flask import Flask, render_template, request, jsonify
import boto3, json, time, threading, hashlib, os, re
from datetime import datetime
import io

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
    lines = text.splitlines()
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
    return chunks


def get_loan_document_prompt():
    """Get the specialized prompt for loan/account documents"""
    return """
You are an AI assistant that extracts structured data from loan account documents.

Extract the following information and return it as valid JSON:

{
  "AccountNumber": "string",
  "AccountHolderNames": ["name1", "name2"],
  "AccountType": "string",
  "OwnershipType": "string",
  "WSFSAccountType": "string",
  "AccountPurpose": "string",
  "SSN": "string or list of SSNs",
  "Signers": [
    {
      "Name": "string",
      "SSN": "string",
      "DateOfBirth": "string",
      "Address": "string",
      "Phone": "string",
      "Email": "string"
    }
  ],
  "SupportingDocuments": [
    {
      "DocumentType": "string",
      "Details": "string"
    }
  ]
}

FIELD DEFINITIONS - READ CAREFULLY:

1. AccountType: The USAGE TYPE or WHO uses the account. Look for these terms:
   - "Personal" (for individual/family use)
   - "Business" (for business operations)
   - "Commercial" (for commercial purposes)
   - "Corporate" (for corporation)
   - "Trust" (trust account)
   - "Estate" (estate account)
   Extract whether it's for personal or business use.

2. WSFSAccountType: The SPECIFIC internal bank account type code or classification. Look for:
   - Specific product names like "Premier Checking", "Platinum Savings", "Gold CD"
   - Internal codes or account classifications
   - Branded account names unique to the bank
   - If the document shows "Account Type: Premier Checking", then AccountType="Personal" (if for personal use) and WSFSAccountType="Premier Checking"
   - If only one type is mentioned, use it for WSFSAccountType and infer AccountType from context

3. AccountPurpose: The CATEGORY or CLASSIFICATION of the account. Look for:
   - "Consumer" (consumer banking)
   - "Checking" (checking account)
   - "Savings" (savings account)
   - "Money Market" (money market account)
   - "CD" or "Certificate of Deposit"
   - "IRA" or "Retirement"
   - "Loan" (loan account)
   - "Mortgage" (mortgage account)
   Extract the banking product category or account classification.

4. OwnershipType: WHO owns the account legally. Common values:
   - "Individual" or "Single Owner" (single owner)
   - "Joint" or "Joint Owners" (multiple owners with equal rights)
   - "Joint with Rights of Survivorship"
   - "Trust" (held in trust)
   - "Estate" (estate account)
   - "Custodial" (for minor)
   - "Business" or "Corporate"

EXTRACTION RULES:
- Return ONLY valid JSON, no additional text before or after
- Use "N/A" ONLY if the field is truly not mentioned anywhere in the document
- For AccountHolderNames: Return as array even if single name, e.g., ["John Doe"]
- For Signers: Extract ALL available information for each signer, create separate objects for each person
- For SupportingDocuments: List every document mentioned (Driver's License, Death Certificate, etc.)
- Preserve exact account numbers and SSNs as they appear
- If you see multiple account types mentioned, use the most specific one
- Look carefully at the entire document text for these fields

EXAMPLES:
Example 1: Document says "Premier Checking Account for Business Operations, Consumer Banking"
{
  "AccountType": "Business",
  "WSFSAccountType": "Premier Checking",
  "AccountPurpose": "Consumer"
}

Example 2: Document says "Personal IRA Savings Account"
{
  "AccountType": "Personal",
  "WSFSAccountType": "IRA Savings",
  "AccountPurpose": "Retirement"
}

Example 3: Document says "Personal Checking Account, Consumer"
{
  "AccountType": "Personal",
  "WSFSAccountType": "Personal Checking",
  "AccountPurpose": "Consumer"
}
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
        "expected_fields": ["deceased_name", "date_of_death", "place_of_death", "cause_of_death", "certificate_number", "age", "date_of_birth", "social_security_number", "state_file_number", "registrar"],
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


def call_bedrock(prompt: str, text: str, max_tokens: int = 4000):
    """Call AWS Bedrock with Claude"""
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = filename.lower().split('.')[-1]
        
        # Validate file size (Textract limits: 5MB for sync, 500MB for async via S3)
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        # For images (PNG, JPG, JPEG), use bytes directly
        if file_ext in ['png', 'jpg', 'jpeg']:
            if file_size_mb > 5:
                # If larger than 5MB, upload to S3
                s3_key = f"uploads/{timestamp}_{filename}"
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=f'image/{file_ext}'
                )
                response = textract.detect_document_text(
                    Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}}
                )
            else:
                # Process directly from bytes
                response = textract.detect_document_text(
                    Document={'Bytes': file_bytes}
                )
            
            # Extract text from blocks
            extracted_text = ""
            for block in response.get('Blocks', []):
                if block['BlockType'] == 'LINE':
                    extracted_text += block['Text'] + "\n"
        
        # For PDF, must use S3
        elif file_ext == 'pdf':
            # Validate PDF is not corrupted
            if file_bytes[:4] != b'%PDF':
                raise Exception("Invalid PDF file format. File may be corrupted.")
            
            if file_size_mb > 500:
                raise Exception(f"PDF file too large ({file_size_mb:.1f}MB). Maximum size is 500MB.")
            
            s3_key = f"uploads/{timestamp}_{filename}"
            
            # Upload to S3 with proper content type
            try:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType='application/pdf'
                )
            except Exception as s3_error:
                raise Exception(f"S3 upload failed: {str(s3_error)}")
            
            # Try sync API first (faster for simple PDFs)
            try:
                response = textract.detect_document_text(
                    Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}}
                )
                
                # Extract text from blocks
                extracted_text = ""
                for block in response.get('Blocks', []):
                    if block['BlockType'] == 'LINE':
                        extracted_text += block['Text'] + "\n"
                        
            except Exception as sync_error:
                error_msg = str(sync_error)
                if "UnsupportedDocumentException" in error_msg or "InvalidParameterException" in error_msg:
                    # PDF is scanned or multi-page, use async API
                    extracted_text = extract_text_with_textract_async(S3_BUCKET, s3_key)
                else:
                    raise Exception(f"Textract processing failed: {error_msg}")
        
        else:
            raise Exception(f"Unsupported file format: {file_ext}. Supported: PDF, PNG, JPG, JPEG")
        
        if not extracted_text.strip():
            extracted_text = "[No text detected in document. Document may be blank or image quality too low.]"
        
        # Save extracted text to file
        output_filename = f"{OUTPUT_DIR}/{timestamp}_{filename}.txt"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        
        return extracted_text, output_filename
        
    except Exception as e:
        # Save error info
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_file = f"{OUTPUT_DIR}/{timestamp}_{filename}_ERROR.txt"
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"OCR Error: {str(e)}\n")
            f.write(f"File: {filename}\n")
            f.write(f"Size: {len(file_bytes) / 1024:.2f} KB\n")
        
        raise Exception(f"Textract OCR failed: {str(e)}")


def extract_basic_fields(text: str, num_fields: int = 20):
    """Extract up to 20 most important basic fields from any document"""
    prompt = f"""
Extract the {num_fields} MOST IMPORTANT fields from this document. Prioritize:
1. Identifying information (names, IDs, numbers)
2. Dates (issue date, expiration, birth date, etc.)
3. Amounts or values (if applicable)
4. Contact information (address, phone, email)
5. Document-specific critical fields

Return ONLY valid JSON with descriptive field names. Example format:
{{
  "document_type": "value",
  "full_name": "value",
  "document_number": "value",
  "issue_date": "value",
  ...
}}

Use clear, descriptive field names (e.g., "full_name" not "field_1").
Extract up to {num_fields} fields, but only include fields that have actual values.
If a field is not available, omit it rather than using "N/A".
"""
    
    try:
        response = call_bedrock(prompt, text[:3000])  # Use more text for better extraction
        
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
    text_upper = text.upper()
    text_lower = text.lower()
    lines = text.split('\n')
    
    # Helper function to check for patterns
    def contains_any(patterns):
        return any(p.upper() in text_upper for p in patterns)
    
    def contains_all(patterns):
        return all(p.upper() in text_upper for p in patterns)
    
    print(f"[DEBUG] Starting document classification...")
    
    # ============================================================
    # STEP 1: Check for BANK LOGO (WSFS Bank)
    # ============================================================
    if "WSFS BANK" in text_upper or "WSFS" in text_upper:
        print(f"[DEBUG] WSFS Bank detected - checking form type...")
        
        # Business Card Order Form
        if contains_any(["BUSINESS CARD ORDER FORM", "CARD ORDER FORM"]):
            print(f"[INFO] Detected: Business Card Order Form")
            return "business_card"
        
        # Account Withdrawal Form
        if contains_any(["ACCOUNT WITHDRAWAL", "WITHDRAWAL FORM"]):
            print(f"[INFO] Detected: Account Withdrawal Form")
            return "invoice"  # Using invoice as withdrawal form
        
        # Name Change Request
        if contains_any(["NAME CHANGE REQUEST", "NAME CHANGE FORM"]):
            print(f"[INFO] Detected: Name Change Request")
            return "contract"  # Using contract for name change
        
        # Tax ID Number Change
        if contains_any(["TAX ID NUMBER CHANGE", "TAX ID CHANGE", "TIN CHANGE"]):
            print(f"[INFO] Detected: Tax ID Change Form")
            return "tax_form"
        
        # ATM/Debit Card Request
        if contains_any(["ATM/POS/DEBIT CARD REQUEST", "CARD REQUEST", "DEBIT CARD REQUEST"]):
            print(f"[INFO] Detected: Card Request Form")
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
    
    print(f"[INFO] Document type unknown")
    return "unknown"


def process_loan_document(text: str, job_id: str = None):
    """
    Special processing for loan/account documents with account splitting
    Returns same format as loan_pipeline_ui.py
    """
    try:
        # Split into individual accounts
        chunks = split_accounts_strict(text)
        
        if not chunks:
            # No accounts found, treat as single document
            chunks = [{"accountNumber": "N/A", "text": text}]
        
        total = len(chunks)
        accounts = []
        loan_prompt = get_loan_document_prompt()
        
        # Log processing start
        print(f"[INFO] Processing loan document with {total} accounts")
        
        for idx, chunk in enumerate(chunks, start=1):
            acc = chunk["accountNumber"] or f"Unknown_{idx}"
            
            # Update progress for each account
            # Progress: 40% (basic fields) + 30% (account processing) = 40 + (30 * idx/total)
            progress = 40 + int((30 * idx) / total)
            
            if job_id and job_id in job_status_map:
                job_status_map[job_id].update({
                    "status": f"Processing account {idx}/{total}: {acc} (this may take a few minutes for large documents)",
                    "progress": progress
                })
            
            print(f"[INFO] Processing account {idx}/{total}: {acc}")
            
            try:
                # Call AI with loan-specific prompt - increase max_tokens for complex accounts
                response = call_bedrock(loan_prompt, chunk["text"], max_tokens=6000)
                
                # Clean and parse JSON
                json_start = response.find('{')
                json_end = response.rfind('}')
                
                if json_start != -1 and json_end != -1:
                    json_str = response[json_start:json_end + 1]
                    parsed = json.loads(json_str)
                    
                    # Calculate accuracy score and identify fields needing review
                    # Note: AccountNumber is excluded because it's already displayed in the account header
                    required_fields = ["AccountHolderNames", "AccountType", 
                                     "OwnershipType", "WSFSAccountType", "AccountPurpose", "SSN", "Signers"]
                    filled_fields = sum(1 for field in required_fields 
                                      if parsed.get(field) and parsed.get(field) != "N/A" and parsed.get(field) != [])
                    accuracy_score = round((filled_fields / len(required_fields)) * 100, 1)
                    
                    # Identify fields that need manual review (excluding AccountNumber)
                    fields_needing_review = []
                    for field in required_fields:
                        value = parsed.get(field)
                        if not value or value == "N/A" or value == [] or value == "":
                            fields_needing_review.append({
                                "field_name": field,
                                "reason": "Missing or not found in document",
                                "current_value": value if value else "Not extracted"
                            })
                    
                    accounts.append({
                        "accountNumber": acc,
                        "result": parsed,
                        "accuracy_score": accuracy_score,
                        "filled_fields": filled_fields,
                        "total_fields": len(required_fields),
                        "fields_needing_review": fields_needing_review,
                        "needs_human_review": accuracy_score < 100
                    })
                else:
                    print(f"[ERROR] Failed to parse JSON for account {acc}")
                    accounts.append({
                        "accountNumber": acc,
                        "error": "Failed to parse JSON from AI response",
                        "raw_response": response[:500],
                        "accuracy_score": 0
                    })
                    
            except Exception as e:
                print(f"[ERROR] Error processing account {acc}: {str(e)}")
                accounts.append({
                    "accountNumber": acc,
                    "error": str(e),
                    "accuracy_score": 0
                })
        
        print(f"[INFO] Completed processing {len(accounts)} accounts")
        
        # Calculate overall review status
        overall_accuracy = round(sum(a.get("accuracy_score", 0) for a in accounts) / len(accounts), 1) if accounts else 0
        needs_review = overall_accuracy < 100
        all_fields_needing_review = []
        for account in accounts:
            if account.get("fields_needing_review"):
                all_fields_needing_review.extend([
                    {**field, "account_number": account.get("accountNumber")} 
                    for field in account["fields_needing_review"]
                ])
        
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
                "total_fields": len(accounts) * 7,  # 7 required fields per account (excluding AccountNumber)
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

IMPORTANT: 
- Extract EVERY piece of information you can find
- Use exact values from the document
- For dates, preserve the original format
- For names, include full names as they appear
- Include all numbers, IDs, and reference codes
- ALWAYS include a "SupportingDocuments" field listing any related documents, attachments, or references mentioned

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

For SupportingDocuments, include any:
- Attached documents mentioned
- Referenced certificates or IDs
- Related forms or paperwork
- Witness documents
- Verification documents

Do NOT use "N/A" - only include fields that have actual values in the document.
"""
    
    try:
        response = call_bedrock(prompt, text)
        
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
            
            fields = doc.get("extracted_fields", {})
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
        
        # Step 1: OCR if needed
        if use_ocr:
            job_status_map[job_id].update({
                "status": "Running OCR with Amazon Textract (this may take 1-2 minutes for scanned PDFs)...",
                "progress": 10
            })
            
            try:
                text, ocr_file = extract_text_with_textract(file_bytes, filename)
                job_status_map[job_id]["ocr_file"] = ocr_file
                job_status_map[job_id]["ocr_method"] = "Amazon Textract"
            except Exception as textract_error:
                # If Textract fails for PDF, try PyPDF2 as fallback
                if filename.lower().endswith('.pdf'):
                    job_status_map[job_id].update({
                        "status": "Textract failed, trying PyPDF2 fallback...",
                        "progress": 15
                    })
                    text, ocr_file = try_extract_pdf_with_pypdf(file_bytes, filename)
                    
                    if text and ocr_file:
                        job_status_map[job_id]["ocr_file"] = ocr_file
                        job_status_map[job_id]["ocr_method"] = "PyPDF2 (Fallback)"
                        job_status_map[job_id]["textract_error"] = str(textract_error)
                    else:
                        raise Exception(f"Both Textract and PyPDF2 failed. Textract error: {str(textract_error)}")
                else:
                    raise textract_error
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
        
        # Step 2: Extract up to 20 basic fields
        job_status_map[job_id].update({
            "status": "Extracting key fields (up to 20 important fields)...",
            "progress": 40
        })
        basic_fields = extract_basic_fields(text, num_fields=20)
        
        # Step 3: Full document analysis
        job_status_map[job_id].update({
            "status": "Analyzing document structure...",
            "progress": 70,
            "basic_fields": basic_fields
        })
        
        # Check if this is a loan document - use special processing
        doc_type_preview = detect_document_type(text)
        print(f"[INFO] Document type detected: {doc_type_preview}")
        
        if doc_type_preview == "loan_document":
            # Quick check for number of accounts
            account_count = len(split_accounts_strict(text))
            
            if account_count > 20:
                print(f"[WARNING] Large document detected with {account_count} accounts. Processing may take 5-10 minutes.")
                job_status_map[job_id].update({
                    "status": f"Detected loan document with {account_count} accounts - this will take several minutes...",
                    "progress": 75
                })
            else:
                job_status_map[job_id].update({
                    "status": "Detected loan document - splitting accounts...",
                    "progress": 75
                })
            
            result = process_loan_document(text, job_id)
        else:
            result = detect_and_extract_documents(text)
        
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
        
        # Step 4: Generate auto document name if not provided
        if not document_name or document_name == filename:
            # Auto-generate a meaningful name based on extracted data
            doc_type_info = result.get("document_type_info", {})
            doc_type_name = doc_type_info.get("name", "Document")
            
            # Try to get a meaningful identifier from basic fields
            identifier = None
            if basic_fields:
                # Try common identifying fields
                identifier = (basic_fields.get("account_holder_name") or 
                            basic_fields.get("full_name") or
                            basic_fields.get("account_number") or
                            basic_fields.get("document_number") or
                            basic_fields.get("certificate_number") or
                            basic_fields.get("invoice_number"))
            
            # Generate name
            if identifier:
                auto_name = f"{doc_type_name} - {identifier}"
            else:
                # Use date if no identifier
                date_str = datetime.now().strftime("%Y-%m-%d")
                auto_name = f"{doc_type_name} - {date_str}"
            
            document_name = auto_name
        
        # Step 5: Save to persistent storage
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


@app.route("/document/<doc_id>")
def view_document(doc_id):
    """View document details in a new page"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("document_detail.html", document=doc)
    return "Document not found", 404


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
