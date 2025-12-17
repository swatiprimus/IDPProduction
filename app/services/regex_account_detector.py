#!/usr/bin/env python3
"""
Regex-based Account Number Detector Service
Fast, reliable, and accurate account number detection without LLM
"""

import re
from typing import List, Set, Dict

class RegexAccountDetector:
    """
    Fast regex-based account number detector
    Designed to be more accurate and faster than LLM approach
    """
    
    def __init__(self):
        # STRICT account number patterns - LABELED ONLY (highest confidencnfidence)
        # STRICT account-number patterns – LABELED ONLY
        # Every pattern ends with a CAPTURE GROUP that must start
        # on the same line or the very next line, and must be the
        # *first* 8-12-digit sequence after the label.
        self.labeled_patterns = [
            # Same line, colon/space optional, then digits
            r'ACCOUNT\s+NUMBER\s*[:]*\s*\b([0-9]{8,12})\b',
            r'ACCOUNT\s+NO\s*[:\.]*\s*\b([0-9]{8,12})\b',
            r'ACCOUNT\s*#\s*[:]*\s*\b([0-9]{8,12})\b',


            # Next line: label ends with colon, then optional spaces on next line, then digits
            r'ACCOUNT\s+NUMBER\s*:\s*\n\s*\b([0-9]{8,12})\b',
            r'ACCOUNT\s+NO\s*:\s*\n\s*\b([0-9]{8,12})\b',

            # # “Account Holder Names” edge case – digits must appear *right* after that phrase
            # r'ACCOUNT\s+HOLDER\s+NAMES?\s*[:]\s*\b([0-9]{8,12})\b',
            # r'ACCOUNT\s+HOLDER\s+NAMES?\s*:\s*\n\s*\b([0-9]{8,12})\b',

            # Two-line combo: ACCOUNT NUMBER:<newline>Account Holder Names:<newline>digits
            r'ACCOUNT\s+NUMBER\s*:\s*\n\s*ACCOUNT\s+HOLDER\s+NAMES?\s*[:]\s*\n\s*\b([0-9]{8,12})\b',

            # “Account #s:”  – digits must be the very next non-blank token
            r'ACCOUNT\s*#S?\s*[:]\s*\b([0-9]{8,12})\b',

            # Prefixed variants (CD, Savings, etc.) – same tight anchoring
            r'\b\w+\s+ACCOUNT\s+NUMBER\s*[:]\s*\b([0-9]{8,12})\b',
            r'\b\w+\s+ACCOUNT\s+NO\s*[:\.]\s*\b([0-9]{8,12})\b',
            r'\b\w+\s+ACCOUNT\s*#\s*[:]\s*\b([0-9]{8,12})\b',
            r'\b\w+\s+ACCT\s+NUMBER\s*[:]\s*\b([0-9]{8,12})\b',
            r'\b\w+\s+ACCT\s*#?\s*[:]\s*\b([0-9]{8,12})\b',
        ]
        

    
    def normalize_account_number(self, account: str) -> str:
        """Normalize account number by removing leading zeros"""
        return account.lstrip('0') or '0'  # Keep at least one zero if all zeros
    
    def extract_accounts_from_text(self, text: str) -> List[str]:
        """Extract account numbers from text using LABELED PATTERNS ONLY"""
        found_accounts = set()
        
        # ONLY search for labeled patterns (highest confidence)
        # This avoids false positives from SSN, ZIP codes, Inquiry IDs, etc.
        for pattern in self.labeled_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                # No validation - trust the labeled patterns
                normalized = self.normalize_account_number(match)
                found_accounts.add(normalized)
        
        # Convert to sorted list
        return sorted(list(found_accounts))

# Convenience function for easy integration
def extract_account_numbers_fast(text: str) -> List[str]:
    """
    Fast regex-based account number extraction
    
    Args:
        text: OCR text to search for account numbers
    
    Returns:
        List of account numbers found
    """
    detector = RegexAccountDetector()
    return detector.extract_accounts_from_text(text)
