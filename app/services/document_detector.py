"""
Document Detector Service - Detects document types using hierarchical decision tree
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