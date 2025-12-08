"""
Loan Document Processor - Handles processing of loan/account documents
"""
from .account_splitter import split_accounts_strict


def process_loan_document(text: str, job_id: str = None, job_status_map: dict = None):
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
            
            if job_id and job_status_map and job_id in job_status_map:
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
                    "account_numbers": [acc["accountNumber"] for acc in accounts]
                },
                "accounts": accounts,
                "accuracy_score": overall_accuracy,
                "needs_human_review": needs_review,
                "fields_needing_review": all_fields_needing_review
            }]
        }
        
    except Exception as e:
        print(f"[LOAN_DOCUMENT ERROR] ❌ Processing failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
