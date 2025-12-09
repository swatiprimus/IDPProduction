"""
Document Type Detector - Identifies document types using LLM
"""
import boto3
import json

# AWS Configuration
AWS_REGION = "us-east-1"
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

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
    Detect document type using LLM (Claude) for accurate classification
    """
    print(f"\n{'='*80}")
    print(f"[DETECT_TYPE] Starting LLM-based document type detection...")
    print(f"[DETECT_TYPE] Text length: {len(text)} characters")
    
    # Truncate text if too long (use first 3000 chars for detection)
    text_sample = text[:3000] if len(text) > 3000 else text
    
    # Build list of supported document types for the prompt
    doc_types_list = []
    for doc_type, info in SUPPORTED_DOCUMENT_TYPES.items():
        doc_types_list.append(f"- {doc_type}: {info['description']}")
    
    doc_types_str = "\n".join(doc_types_list)
    
    prompt = f"""You are a document classification expert. Analyze the following document text and identify its type.

SUPPORTED DOCUMENT TYPES:
{doc_types_str}

DOCUMENT TEXT:
{text_sample}

INSTRUCTIONS:
1. Carefully read the document text
2. Identify the document type from the supported types above
3. Return ONLY the document type key (e.g., "death_certificate", "loan_document", "invoice")
4. If the document doesn't match any type, return "unknown"

IMPORTANT DISTINCTIONS:
- "loan_document" = Bank account forms, signature cards, account opening documents
- "invoice" = Invoices, bills, withdrawal forms, funeral statements
- "death_certificate" = Official death certificates from vital records
- "business_card" = Business cards or card order forms (ATM/debit card requests)
- "contract" = Legal documents, estate documents, name change forms

Return ONLY the document type key, nothing else."""

    try:
        # Call Claude API
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 50,
                "temperature": 0,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            })
        )
        
        result = json.loads(response['body'].read())
        detected_type = result['content'][0]['text'].strip().lower()
        
        # Validate the detected type
        if detected_type in SUPPORTED_DOCUMENT_TYPES:
            print(f"[DETECT_TYPE] ✓ LLM Detected: {detected_type}")
            print(f"{'='*80}\n")
            return detected_type
        else:
            print(f"[DETECT_TYPE] ⚠️ LLM returned invalid type: {detected_type}")
            print(f"[DETECT_TYPE] Falling back to 'unknown'")
            print(f"{'='*80}\n")
            return "unknown"
            
    except Exception as e:
        print(f"[DETECT_TYPE] ❌ LLM detection failed: {str(e)}")
        print(f"[DETECT_TYPE] Falling back to keyword-based detection")
        
        # Fallback to simple keyword matching
        text_upper = text.upper()
        
        if "SIGNATURE CARD" in text_upper and "ACCOUNT" in text_upper:
            print(f"[DETECT_TYPE] ✓ Fallback: loan_document")
            print(f"{'='*80}\n")
            return "loan_document"
        elif "DEATH" in text_upper and "CERTIFICATE" in text_upper:
            print(f"[DETECT_TYPE] ✓ Fallback: death_certificate")
            print(f"{'='*80}\n")
            return "death_certificate"
        elif "MARRIAGE" in text_upper and "CERTIFICATE" in text_upper:
            print(f"[DETECT_TYPE] ✓ Fallback: marriage_certificate")
            print(f"{'='*80}\n")
            return "marriage_certificate"
        elif "WITHDRAWAL" in text_upper:
            print(f"[DETECT_TYPE] ✓ Fallback: invoice")
            print(f"{'='*80}\n")
            return "invoice"
        else:
            print(f"[DETECT_TYPE] ⚠️ Fallback: unknown")
            print(f"{'='*80}\n")
            return "unknown"
