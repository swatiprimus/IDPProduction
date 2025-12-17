#!/usr/bin/env python3
"""
Account Splitter Service - Handles splitting loan documents by account numbers
Uses ONLY regex-based account detection - NO LLM calls for account splitting
"""

import re

# Account number regex patterns
ACCOUNT_INLINE_RE = re.compile(r"^ACCOUNT NUMBER[:\s]*([0-9]{6,15})\b")
ACCOUNT_LINE_RE = re.compile(r"^[0-9]{6,15}\b$")
ACCOUNT_HEADER_RE = re.compile(r"^ACCOUNT NUMBER:?\s*$")
ACCOUNT_HOLDER_RE = re.compile(r"^Account Holder Names:?\s*$")


def extract_account_numbers_fast(text: str):
    """
    Fast regex-based account number extraction from OCR text
    Much faster than LLM and works well for standard formats
    """
    print(f"\n{'='*50}")
    print(f"[FAST_EXTRACT] Using regex to extract account numbers...")
    print(f"[FAST_EXTRACT] Text length: {len(text)} characters")
    
    account_numbers = []
    lines = text.splitlines()
    
    # Pattern 1: Account numbers after "ACCOUNT NUMBER" labels
    account_patterns = [
        r'ACCOUNT\s+NUMBER[:\s]*([0-9]{6,15})',
        r'ACCOUNT\s+NO[:\s]*([0-9]{6,15})',
        r'ACCT\s*#[:\s]*([0-9]{6,15})',
        r'I\.D\.[:\s]*([0-9]{6,15})',
        r'ACCOUNT[:\s]*([0-9]{6,15})',
    ]
    
    # Search for labeled account numbers
    for pattern in account_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match) >= 6 and not match.startswith(('19', '20')):  # Exclude dates
                account_numbers.append(match)
                print(f"[FAST_EXTRACT] Found labeled account: {match}")
    
    # Pattern 2: Look for standalone 8-10 digit numbers in account contexts
    for i, line in enumerate(lines):
        line_upper = line.upper()
        
        # Check if this line or nearby lines mention account-related terms
        context_lines = lines[max(0, i-2):min(len(lines), i+3)]  # 2 lines before, 2 after
        context_text = ' '.join(context_lines).upper()
        
        has_account_context = any(term in context_text for term in [
            'ACCOUNT', 'ACCT', 'BANKING', 'SIGNATURE', 'HOLDER', 'OWNER', 'WSFS'
        ])
        
        if has_account_context:
            # Look for 8-10 digit numbers in this line
            numbers = re.findall(r'\b([0-9]{8,10})\b', line)
            for num in numbers:
                # Filter out dates, phone numbers, etc.
                if (not num.startswith(('19', '20')) and  # Not a date
                    not re.match(r'^[0-9]{3}[0-9]{3}[0-9]{4}$', num) and  # Not phone format
                    len(num) >= 8):  # At least 8 digits
                    account_numbers.append(num)
                    print(f"[FAST_EXTRACT] Found contextual account: {num} (line: {line.strip()[:100]})")
    
    # Pattern 3: Look for numbers after specific withdrawal/banking contexts
    withdrawal_patterns = [
        r'([0-9]{8,10})\s+PRESENTED',
        r'FOR\s+([0-9]{8,10})',
        r'ACCOUNT\s+([0-9]{8,10})',
    ]
    
    for pattern in withdrawal_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match) >= 8 and not match.startswith(('19', '20')):
                account_numbers.append(match)
                print(f"[FAST_EXTRACT] Found withdrawal account: {match}")
    
    # Remove duplicates while preserving order
    unique_accounts = []
    seen = set()
    for acc in account_numbers:
        if acc not in seen:
            seen.add(acc)
            unique_accounts.append(acc)
    
    print(f"[FAST_EXTRACT] ✓ Found {len(unique_accounts)} unique account numbers: {unique_accounts}")
    return unique_accounts


def split_accounts_with_regex(text: str):
    """
    REGEX-ONLY account splitter for loan documents:
    - Uses ONLY regex-based account detection (fast, accurate, no LLM costs)
    - Splits document text by identified account numbers
    - Uses the same logic as regex_account_detector.py
    """
    print(f"\n{'='*80}")
    print(f"[SPLIT_ACCOUNTS] Starting REGEX-ONLY account splitting...")
    print(f"[SPLIT_ACCOUNTS] Input text length: {len(text)} characters")
    
    # Step 1: Use regex to extract account numbers (fast and accurate)
    account_numbers = extract_account_numbers_fast(text)
    
    if not account_numbers:
        print(f"[SPLIT_ACCOUNTS] ⚠️ No account numbers found by regex")
        return []
    
    print(f"[SPLIT_ACCOUNTS] Regex found {len(account_numbers)} account numbers: {account_numbers}")
    
    # Step 2: Split text by account numbers
    lines = text.splitlines()
    account_chunks = {}
    
    for account_num in account_numbers:
        print(f"[SPLIT_ACCOUNTS] Processing account: {account_num}")
        
        # Find all lines that contain this account number or are related to it
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Check if this line contains the account number (with or without leading zeros)
            normalized_account = account_num.lstrip('0')
            if (account_num in line_clean or 
                normalized_account in line_clean or
                f"0{normalized_account}" in line_clean):
                
                print(f"[SPLIT_ACCOUNTS] Found account {account_num} on line {i+1}: {line_clean[:100]}...")
                
                # Include context before and after the account number
                start_idx = max(0, i - 5)  # 5 lines before
                end_idx = min(len(lines), i + 50)  # 50 lines after (or until next account)
                
                # Check if there's another account number in the range that would cut this short
                for j in range(i + 1, end_idx):
                    for other_acc in account_numbers:
                        if other_acc != account_num:
                            other_normalized = other_acc.lstrip('0')
                            if (other_acc in lines[j] or 
                                other_normalized in lines[j] or
                                f"0{other_normalized}" in lines[j]):
                                end_idx = j
                                print(f"[SPLIT_ACCOUNTS] Account {account_num} section ends at line {j} (next account: {other_acc})")
                                break
                    if end_idx == j:
                        break
                
                account_text = "\n".join(lines[start_idx:end_idx])
                account_chunks[account_num] = account_text
                print(f"[SPLIT_ACCOUNTS] Account {account_num}: extracted {len(account_text)} characters")
                break
    
    # Step 3: Handle case where accounts weren't found in text (fallback)
    if len(account_chunks) == 0:
        print(f"[SPLIT_ACCOUNTS] ⚠️ Account numbers not found in text, using full document")
        # If regex found account numbers but they're not in the text, 
        # create chunks with the full text for each account
        for account_num in account_numbers:
            account_chunks[account_num] = text
    
    # Convert to structured list
    chunks = [{"accountNumber": acc, "text": txt.strip()} for acc, txt in account_chunks.items()]
    
    print(f"[SPLIT_ACCOUNTS] ✓ Found {len(chunks)} unique accounts")
    for idx, chunk in enumerate(chunks):
        acc_num = chunk.get("accountNumber", "")
        text_len = len(chunk.get("text", ""))
        print(f"[SPLIT_ACCOUNTS]   Account {idx+1}: {acc_num} ({text_len} chars)")
    print(f"{'='*80}\n")
    
    return chunks