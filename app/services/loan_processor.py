"""
Loan Processor Service - Handles processing of loan/account documents
"""
from .account_splitter import split_accounts_strict

# Global job status map (should be imported from main app)
job_status_map = {}


def detect_loan_document_type(text: str) -> str:
    """
    Detect specific type of loan/account document
    Returns: 'signature_card', 'account_opening', 'cd_rollover', or 'account_document'
    """
    text_upper = text.upper()
    
    # Signature Card Detection (XS forms)
    if any(term in text_upper for term in ["SIGNATURE CARD", "JOINT ACCOUNT SIGNATURE", "AUTHORIZED SIGNATORIES"]):
        return "signature_card"
    
    # CD Rollover Detection
    if any(term in text_upper for term in ["CD ROLLOVER", "CERTIFICATE OF DEPOSIT ROLLOVER", "ROLLOVER INSTRUCTIONS", "MATURITY INSTRUCTIONS"]):
        return "cd_rollover"
    
    # Account Opening Detection
    if any(term in text_upper for term in ["ACCOUNT OPENING", "NEW ACCOUNT", "ACCOUNT APPLICATION", "ACCOUNT AGREEMENT", "ACCOUNT ESTABLISHMENT"]):
        return "account_opening"
    
    # Default to generic account document
    return "account_document"


def extract_loan_document_fields(text: str, doc_type: str) -> dict:
    """
    Extract fields specific to loan document type
    """
    import re
    
    text_upper = text.upper()
    fields = {}
    
    # Common fields for all account documents
    # Account Number
    account_patterns = [
        r'ACCOUNT\s+NUMBER[:\s]*([0-9]{10})',
        r'ACCOUNT\s*#[:\s]*([0-9]{10})',
        r'ACCT\s+NO[:\s]*([0-9]{10})',
    ]
    for pattern in account_patterns:
        match = re.search(pattern, text_upper)
        if match:
            fields['account_number'] = match.group(1)
            break
    
    # Account Holder Names
    name_patterns = [
        r'ACCOUNT\s+HOLDER\s+NAMES?[:\s]*([A-Z\s,&\-\']+?)(?:\n|$)',
        r'SIGNER[S]?[:\s]*([A-Z\s,&\-\']+?)(?:\n|$)',
        r'AUTHORIZED\s+SIGNATORIES?[:\s]*([A-Z\s,&\-\']+?)(?:\n|$)',
    ]
    for pattern in name_patterns:
        matches = re.findall(pattern, text_upper)
        if matches:
            fields['account_holder_names'] = [n.strip() for n in matches[0].split(',') if n.strip()]
            break
    
    # Account Type
    account_type_patterns = [
        r'ACCOUNT\s+TYPE[:\s]*([A-Z\s\-]+?)(?:\n|$)',
        r'(?:CHECKING|SAVINGS|MONEY\s+MARKET|CD|CERTIFICATE\s+OF\s+DEPOSIT)',
    ]
    for pattern in account_type_patterns:
        match = re.search(pattern, text_upper)
        if match:
            fields['account_type'] = match.group(1).strip() if match.lastindex else match.group(0)
            break
    
    # Ownership Type
    ownership_patterns = [
        r'OWNERSHIP\s+TYPE[:\s]*([A-Z\s\-]+?)(?:\n|$)',
        r'(?:INDIVIDUAL|JOINT|BUSINESS|TRUST|ESTATE)',
    ]
    for pattern in ownership_patterns:
        match = re.search(pattern, text_upper)
        if match:
            fields['ownership_type'] = match.group(1).strip() if match.lastindex else match.group(0)
            break
    
    # SSN/Tax ID
    ssn_patterns = [
        r'(?:SSN|SOCIAL\s+SECURITY|TAX\s+ID|TIN)[:\s]*([0-9]{3}[-\s]?[0-9]{2}[-\s]?[0-9]{4})',
    ]
    for pattern in ssn_patterns:
        matches = re.findall(pattern, text_upper)
        if matches:
            fields['ssn'] = [re.sub(r'[-\s]', '', m) for m in matches]
            break
    
    # Document-specific fields
    if doc_type == "signature_card":
        # Signature Card specific fields
        fields['document_subtype'] = 'Signature Card (XS Form)'
        
        # Authorized Signers
        signer_pattern = r'AUTHORIZED\s+SIGNER[S]?[:\s]*([A-Z\s,&\-\']+?)(?:\n|$)'
        match = re.search(signer_pattern, text_upper)
        if match:
            fields['authorized_signers'] = [n.strip() for n in match.group(1).split(',') if n.strip()]
        
        # Backup Withholding
        if "BACKUP WITHHOLDING" in text_upper:
            fields['backup_withholding'] = True
    
    elif doc_type == "cd_rollover":
        # CD Rollover specific fields
        fields['document_subtype'] = 'CD Rollover Form'
        
        # Maturity Date
        date_pattern = r'MATURITY\s+DATE[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})'
        match = re.search(date_pattern, text_upper)
        if match:
            fields['maturity_date'] = match.group(1)
        
        # Rollover Instructions
        if "RENEW" in text_upper or "ROLLOVER" in text_upper:
            fields['rollover_instruction'] = 'Renew/Rollover'
        elif "WITHDRAW" in text_upper:
            fields['rollover_instruction'] = 'Withdraw'
        
        # CD Amount
        amount_pattern = r'(?:AMOUNT|PRINCIPAL)[:\s]*\$?([0-9,]+\.?[0-9]*)'
        match = re.search(amount_pattern, text_upper)
        if match:
            fields['cd_amount'] = match.group(1)
    
    elif doc_type == "account_opening":
        # Account Opening specific fields
        fields['document_subtype'] = 'Account Opening Form'
        
        # Date Opened
        date_pattern = r'DATE\s+(?:OPENED|ESTABLISHED)[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})'
        match = re.search(date_pattern, text_upper)
        if match:
            fields['date_opened'] = match.group(1)
        
        # Account Purpose
        purpose_pattern = r'ACCOUNT\s+PURPOSE[:\s]*([A-Z\s\-]+?)(?:\n|$)'
        match = re.search(purpose_pattern, text_upper)
        if match:
            fields['account_purpose'] = match.group(1).strip()
        
        # Consumer vs Business
        if "CONSUMER" in text_upper:
            fields['account_category'] = 'Consumer'
        elif "BUSINESS" in text_upper:
            fields['account_category'] = 'Business'
    
    return fields


def process_loan_document(text: str, job_id: str = None):
    """
    Special processing for loan/account documents with account splitting
    Handles: Signature Cards (XS forms), CD Rollover forms, Account Opening documents
    Returns same format as loan_pipeline_ui.py
    
    OPTIMIZATION: We no longer call LLM for each account during upload.
    Instead, we just identify accounts and their text chunks.
    Page-level data extraction happens during pre-caching, which is more efficient.
    """
    try:
        print(f"\n{'='*80}")
        print(f"[LOAN_DOCUMENT] Starting loan document processing...")
        print(f"{'='*80}\n")
        
        # Detect specific loan document type
        doc_type = detect_loan_document_type(text)
        print(f"[LOAN_DOCUMENT] Document type: {doc_type}")
        
        # Extract document-specific fields
        doc_fields = extract_loan_document_fields(text, doc_type)
        print(f"[LOAN_DOCUMENT] Extracted fields: {list(doc_fields.keys())}")
        
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
        
        # Build document type display based on detected type
        doc_type_display_map = {
            "signature_card": "Signature Card (XS Form)",
            "cd_rollover": "CD Rollover Form",
            "account_opening": "Account Opening Document",
            "account_document": "Loan/Account Document"
        }
        
        doc_type_description_map = {
            "signature_card": "Joint account signature authorization form",
            "cd_rollover": "Certificate of Deposit rollover/maturity instructions",
            "account_opening": "New account opening and establishment form",
            "account_document": "Banking or loan account information"
        }
        
        # Return in format compatible with universal IDP
        return {
            "documents": [{
                "document_id": "loan_doc_001",
                "document_type": "loan_document",
                "document_type_display": doc_type_display_map.get(doc_type, "Loan/Account Document"),
                "document_subtype": doc_type,
                "document_icon": "🏦",
                "document_description": doc_type_description_map.get(doc_type, "Banking or loan account information"),
                "extracted_fields": {
                    "total_accounts": total,
                    "accounts_processed": len(accounts),
                    "document_subtype": doc_type,
                    **doc_fields  # Include document-specific fields
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