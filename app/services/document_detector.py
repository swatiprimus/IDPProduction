"""
Document Type Detector - Identifies document types using pattern matching
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
    # STEP 1: Check for LOAN/ACCOUNT DOCUMENT FIRST (highest priority)
    # ============================================================
    has_account_number = "ACCOUNT NUMBER" in text_upper
    has_account_holder = "ACCOUNT HOLDER" in text_upper
    has_account_purpose = "ACCOUNT PURPOSE" in text_upper
    has_account_type = "ACCOUNT TYPE" in text_upper
    has_ownership_type = "OWNERSHIP TYPE" in text_upper
    has_signature_card = "SIGNATURE CARD" in text_upper
    
    # Count how many required fields are present
    required_fields_count = sum([
        has_account_number,
        has_account_holder,
        has_account_purpose,
        has_account_type,
        has_ownership_type,
        has_signature_card
    ])
    
    # If 3 or more required fields present, it's likely a loan/account document
    if required_fields_count >= 3:
        print(f"[DETECT_TYPE] Found {required_fields_count}/6 account document fields")
        print(f"[DETECT_TYPE] ✓ Detected: Loan/Account Document")
        print(f"{'='*80}\n")
        return "loan_document"
    
    # ============================================================
    # STEP 2: Check for SPECIFIC FORM TYPES
    # ============================================================
    
    # Business Card Order Form (must be specific - not just "CARD")
    if contains_any(["BUSINESS CARD ORDER FORM", "BUSINESS CARD ORDER"]) and not has_signature_card:
        print(f"[DETECT_TYPE] ✓ Detected: Business Card Order Form")
        print(f"{'='*80}\n")
        return "business_card"
    
    # ATM/Debit Card Request (must be specific)
    if contains_any(["ATM/POS/DEBIT CARD REQUEST", "DEBIT CARD REQUEST", "ATM CARD REQUEST"]) and not has_signature_card:
        print(f"[DETECT_TYPE] ✓ Detected: Card Request Form")
        print(f"{'='*80}\n")
        return "business_card"
    
    # Account Withdrawal Form
    if contains_any(["ACCOUNT WITHDRAWAL", "WITHDRAWAL FORM"]):
        print(f"[DETECT_TYPE] ✓ Detected: Account Withdrawal Form")
        print(f"{'='*80}\n")
        return "invoice"
    
    # Name Change Request
    if contains_any(["NAME CHANGE REQUEST", "NAME CHANGE FORM"]):
        print(f"[DETECT_TYPE] ✓ Detected: Name Change Request")
        print(f"{'='*80}\n")
        return "contract"
    
    # Tax ID Number Change
    if contains_any(["TAX ID NUMBER CHANGE", "TAX ID CHANGE", "TIN CHANGE"]):
        print(f"[DETECT_TYPE] ✓ Detected: Tax ID Change Form")
        print(f"{'='*80}\n")
        return "tax_form"
    

    
    # ============================================================
    # STEP 3: Check for ID CARD (Driver's License)
    # ============================================================
    if contains_any(["DRIVER LICENSE", "DRIVER'S LICENSE", "DRIVERS LICENSE", "IDENTIFICATION CARD", "ID CARD"]):
        print(f"[DETECT_TYPE] ✓ Detected: Driver's License/ID Card")
        print(f"{'='*80}\n")
        return "drivers_license"
    
    # ============================================================
    # FALLBACK: Use keyword-based scoring
    # ============================================================
    print(f"[DETECT_TYPE] No specific pattern matched - using keyword scoring...")
    
    scores = {}
    for doc_type, info in SUPPORTED_DOCUMENT_TYPES.items():
        score = 0
        for keyword in info['keywords']:
            if keyword.lower() in text_lower:
                score += 1
        scores[doc_type] = score
    
    # Check for strong indicators
    loan_score = scores.get('loan_document', 0)
    if loan_score >= 5:
        print(f"[DETECT_TYPE] ✓ Detected: loan_document (score: {loan_score})")
        print(f"{'='*80}\n")
        return 'loan_document'
    
    # If we have a clear winner (score >= 2), use it
    max_score = max(scores.values()) if scores else 0
    if max_score >= 2:
        detected_type = max(scores, key=scores.get)
        print(f"[DETECT_TYPE] ✓ Detected: {detected_type} (score: {max_score})")
        print(f"{'='*80}\n")
        return detected_type
    
    print(f"[DETECT_TYPE] ⚠️ Document type unknown")
    print(f"{'='*80}\n")
    return "unknown"
