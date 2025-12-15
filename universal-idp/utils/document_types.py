"""Document type detection and management utilities."""

import re
import logging
from typing import Dict, List, Optional, Any
from config import SUPPORTED_DOCUMENT_TYPES

logger = logging.getLogger(__name__)

class DocumentTypeDetector:
    """Detects document types based on content analysis."""
    
    def __init__(self):
        self.supported_types = SUPPORTED_DOCUMENT_TYPES
    
    def detect_document_type(self, text: str) -> str:
        """
        Detect document type using hierarchical decision tree.
        Based on specific visual and textual markers.
        """
        logger.info(f"Starting document type detection... Text length: {len(text)} characters")
        
        text_upper = text.upper()
        text_lower = text.lower()
        lines = text.split('\n')
        
        # Helper functions
        def contains_any(patterns):
            return any(p.upper() in text_upper for p in patterns)
        
        def contains_all(patterns):
            return all(p.upper() in text_upper for p in patterns)
        
        # STEP 1: HIGHEST PRIORITY - Check for DEATH CERTIFICATE FIRST (before any other checks)
        # This must be first to prevent false positives from other document types
        
        # Primary death certificate indicators (very specific)
        primary_death_indicators = [
            "CERTIFICATION OF VITAL RECORD",
            "DEATH CERTIFICATION",
            "STATE FILE NUMBER"
        ]
        
        if contains_any(primary_death_indicators):
            logger.info("Primary death certificate indicators found - definitive match")
            return "death_certificate"
        
        # Secondary death certificate indicators
        secondary_death_indicators = [
            "CERTIFICATE OF DEATH", 
            "DECEDENT'S INFORMATION",
            "DECEDENT'S NAME"
        ]
        
        if contains_any(secondary_death_indicators):
            logger.info("Secondary death certificate indicators found")
            return "death_certificate"
        
        # Check for specific death certificate fields (if 4+ found, it's definitely a death cert)
        death_fields = [
            "DATE OF DEATH",
            "CAUSE OF DEATH",
            "MANNER OF DEATH", 
            "FUNERAL DIRECTOR",
            "INFORMANT'S NAME",
            "PLACE OF DEATH",
            "DECEDENT",
            "DECEASED"
        ]
        
        death_field_count = sum(1 for field in death_fields if field in text_upper)
        if death_field_count >= 4:
            logger.info(f"Death certificate detected by field count: {death_field_count}/8 fields found")
            return "death_certificate"
        
        # Additional death certificate patterns
        if (contains_any(["DEATH", "DECEASED", "DECEDENT"]) and 
            contains_any(["CERTIFICATE", "CERTIFICATION", "VITAL RECORD"])):
            logger.info("Death certificate pattern detected")
            return "death_certificate"
        
        # Step 2: Check for BANK LOGO (WSFS Bank)
        if "WSFS BANK" in text_upper or "WSFS" in text_upper:
            logger.info("WSFS Bank detected - checking form type...")
            
            # Business Card Order Form
            if contains_any(["BUSINESS CARD ORDER FORM", "CARD ORDER FORM"]):
                logger.info("Detected: Business Card Order Form")
                return "business_card"
            
            # Account Withdrawal Form
            if contains_any(["ACCOUNT WITHDRAWAL", "WITHDRAWAL FORM"]):
                logger.info("Detected: Account Withdrawal Form")
                return "invoice"
            
            # Name Change Request
            if contains_any(["NAME CHANGE REQUEST", "NAME CHANGE FORM"]):
                logger.info("Detected: Name Change Request")
                return "contract"
            
            # Tax ID Number Change
            if contains_any(["TAX ID NUMBER CHANGE", "TAX ID CHANGE", "TIN CHANGE"]):
                logger.info("Detected: Tax ID Change Form")
                return "tax_form"
            
            # ATM/Debit Card Request
            if contains_any(["ATM/POS/DEBIT CARD REQUEST", "CARD REQUEST", "DEBIT CARD REQUEST"]):
                logger.info("Detected: Card Request Form")
                return "business_card"
            
            # Check for Account Opening Document vs Signature Card
            has_account_number = "ACCOUNT NUMBER" in text_upper
            has_account_holder = "ACCOUNT HOLDER" in text_upper
            has_ownership = "OWNERSHIP TYPE" in text_upper
            
            if has_account_number and has_account_holder and has_ownership:
                logger.info("Found account document indicators - distinguishing type...")
                
                # Count signature lines
                signature_count = text_upper.count("SIGNATURE")
                signature_line_count = text.count("___________")
                
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
                    logger.info("Detected: Joint Account Signature Card (explicit title)")
                    return "loan_document"
                elif has_multiple_signatures and has_tin_withholding:
                    logger.info("Detected: Joint Account Signature Card (multiple signatures + TIN)")
                    return "loan_document"
                elif has_date_opened and has_account_product and has_account_purpose:
                    logger.info("Detected: Account Opening Document (has DATE OPENED + product + purpose)")
                    return "loan_document"
                elif has_date_opened and has_consumer_business:
                    logger.info("Detected: Account Opening Document (has DATE OPENED + consumer/business)")
                    return "loan_document"
                elif has_multiple_signatures:
                    logger.info("Detected: Joint Account Signature Card (multiple signatures)")
                    return "loan_document"
                else:
                    logger.info("Detected: Account Opening Document (default)")
                    return "loan_document"
        

        
        # Step 3: Check for REGISTER OF WILLS / Letters Testamentary
        if contains_any(["REGISTER OF WILLS", "LETTERS TESTAMENTARY", "LETTERS OF ADMINISTRATION"]):
            logger.info("Detected: Letters Testamentary/Administration")
            return "contract"
        
        # Step 4: Check for AFFIDAVIT (Small Estates)
        if "AFFIDAVIT" in text_upper and contains_any(["SMALL ESTATE", "SMALL ESTATES"]):
            logger.info("Detected: Small Estate Affidavit")
            return "contract"
        
        # Step 5: Check for FUNERAL HOME INVOICE
        if contains_any(["FUNERAL HOME", "FUNERAL SERVICES", "STATEMENT OF FUNERAL EXPENSES"]) and \
           contains_any(["INVOICE", "STATEMENT", "BILL", "CHARGES"]):
            logger.info("Detected: Funeral Invoice")
            return "invoice"
        
        # Step 6: Check for Loan/Account Documents (improved detection)
        account_indicators = [
            "ACCOUNT NUMBER",
            "ACCOUNT HOLDER", 
            "ACCOUNT TYPE",
            "OWNERSHIP TYPE",
            "ACCOUNT PURPOSE",
            "SIGNATURE CARD",
            "ACCOUNT OPENING",
            "WSFS ACCOUNT TYPE"
        ]
        
        banking_terms = [
            "CHECKING", "SAVINGS", "MONEY MARKET", "CD", 
            "CERTIFICATE OF DEPOSIT", "CONSUMER", "BUSINESS",
            "JOINT ACCOUNT", "INDIVIDUAL ACCOUNT"
        ]
        
        account_field_count = sum(1 for indicator in account_indicators if indicator in text_upper)
        banking_term_count = sum(1 for term in banking_terms if term in text_upper)
        
        if account_field_count >= 3 or (account_field_count >= 2 and banking_term_count >= 2):
            logger.info(f"Detected: Loan/Account Document (fields: {account_field_count}, banking terms: {banking_term_count})")
            return "loan_document"
        
        # Step 7: Check for ID CARD (Driver's License)
        if contains_any(["DRIVER LICENSE", "DRIVER'S LICENSE", "DRIVERS LICENSE", "IDENTIFICATION CARD", "ID CARD"]):
            logger.info("Detected: Driver's License/ID Card")
            return "drivers_license"
        
        # Fallback: Use keyword-based scoring
        logger.info("No specific pattern matched - using keyword scoring...")
        
        scores = {}
        for doc_type, info in self.supported_types.items():
            score = 0
            for keyword in info['keywords']:
                if keyword.lower() in text_lower:
                    score += 1
            scores[doc_type] = score
        
        logger.info(f"Keyword scores: {scores}")
        
        # Special handling for loan documents
        loan_score = scores.get('loan_document', 0)
        if loan_score >= 5:
            logger.info(f"Detected as loan_document (score: {loan_score})")
            return 'loan_document'
        
        # Check for strong indicators
        priority_types = ['marriage_certificate', 'passport', 'insurance_policy']
        for priority_type in priority_types:
            priority_score = scores.get(priority_type, 0)
            if priority_score >= 2 and priority_score > loan_score:
                logger.info(f"Detected as {priority_type} (score: {priority_score})")
                return priority_type
        
        # Check loan document with lower threshold
        if loan_score >= 2:
            logger.info(f"Detected as loan_document (score: {loan_score})")
            return 'loan_document'
        
        # If we have a clear winner (score >= 2), use it
        max_score = max(scores.values()) if scores else 0
        if max_score >= 2:
            detected_type = max(scores, key=scores.get)
            logger.info(f"Detected as {detected_type} (score: {max_score})")
            return detected_type
        
        logger.warning("Document type unknown")
        return "unknown"
    
    def get_document_info(self, doc_type: str) -> Dict[str, Any]:
        """Get information about a document type."""
        return self.supported_types.get(doc_type, {
            "name": "Unknown Document",
            "icon": "📄",
            "description": "Unidentified document type",
            "expected_fields": []
        })
    
    def get_all_supported_types(self) -> Dict[str, Dict[str, Any]]:
        """Get all supported document types."""
        return self.supported_types

# Global document type detector instance
document_type_detector = DocumentTypeDetector()