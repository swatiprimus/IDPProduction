#!/usr/bin/env python3
"""
Account Splitter Service - Handles splitting loan documents by account numbers
"""

import re

# Account number regex patterns
ACCOUNT_INLINE_RE = re.compile(r"^ACCOUNT NUMBER[:\s]*([0-9]{6,15})\b")
ACCOUNT_LINE_RE = re.compile(r"^[0-9]{6,15}\b$")
ACCOUNT_HEADER_RE = re.compile(r"^ACCOUNT NUMBER:?\s*$")
ACCOUNT_HOLDER_RE = re.compile(r"^Account Holder Names:?\s*$")


def extract_account_numbers_with_llm(text: str):
    """
    Use LLM to intelligently extract account numbers from document text
    More accurate than regex for distinguishing account numbers from SSNs, etc.
    """
    import boto3
    import json
    
    print(f"\n{'='*50}")
    print(f"[LLM_EXTRACT] Using LLM to extract account numbers...")
    print(f"[LLM_EXTRACT] Text length: {len(text)} characters")
    
    try:
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
        
        prompt = f"""
You are an expert at analyzing banking and loan documents to extract account numbers.

Your task: Find ALL account numbers in this document text.

IMPORTANT RULES:
1. Look for account numbers that are typically 8-10 digits long
2. Account numbers may appear after labels like:
   - "ACCOUNT NUMBER"
   - "ACCOUNT NO" 
   - "ACCT #"
   - "I.D." (in banking context)
   - Or standalone in account forms
3. EXCLUDE the following (these are NOT account numbers):
   - SSNs/Tax IDs (usually 9 digits, often in format XXX-XX-XXXX)
   - Dates (like 20151201, 12/24/2014)
   - Phone numbers
   - Reference numbers or transaction IDs
   - Certificate numbers
4. Focus on numbers that appear in account opening or banking contexts
5. Look for numbers associated with account holder names or signatures

Document text:
{text}

Return ONLY a JSON array of account numbers found, like:
["123456789", "987654321"]

If no account numbers found, return: []
"""

        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        result = json.loads(response['body'].read())
        llm_response = result['content'][0]['text'].strip()
        
        print(f"[LLM_EXTRACT] LLM response: {llm_response}")
        
        # Parse the JSON response
        try:
            # Clean up the response - remove any markdown formatting
            clean_response = llm_response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response.replace('```json', '').replace('```', '').strip()
            elif clean_response.startswith('```'):
                clean_response = clean_response.replace('```', '').strip()
            
            account_numbers = json.loads(clean_response)
            
            if isinstance(account_numbers, list):
                print(f"[LLM_EXTRACT] ✓ Found {len(account_numbers)} account numbers: {account_numbers}")
                return account_numbers
            else:
                print(f"[LLM_EXTRACT] ⚠️ Unexpected response format: {account_numbers}")
                return []
                
        except json.JSONDecodeError as e:
            print(f"[LLM_EXTRACT] ❌ JSON parsing error: {str(e)}")
            print(f"[LLM_EXTRACT] Raw response: {llm_response}")
            return []
            
    except Exception as e:
        print(f"[LLM_EXTRACT] ❌ LLM extraction failed: {str(e)}")
        return []


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


def split_accounts_strict(text: str):
    """
    LLM-powered account splitter for loan documents:
    - Uses OCR + LLM to intelligently extract account numbers
    - Splits document text by identified account numbers
    """
    print(f"\n{'='*80}")
    print(f"[SPLIT_ACCOUNTS] Starting LLM-powered account splitting...")
    print(f"[SPLIT_ACCOUNTS] Input text length: {len(text)} characters")
    
    # Step 1: Use LLM to extract account numbers (more accurate than regex)
    account_numbers = extract_account_numbers_with_llm(text)
    
    if not account_numbers:
        print(f"[SPLIT_ACCOUNTS] ⚠️ No account numbers found by LLM")
        return []
    
    print(f"[SPLIT_ACCOUNTS] LLM found {len(account_numbers)} account numbers: {account_numbers}")
    
    # Step 2: Split text by account numbers
    lines = text.splitlines()
    account_chunks = {}
    
    for account_num in account_numbers:
        print(f"[SPLIT_ACCOUNTS] Processing account: {account_num}")
        
        # Find all lines that contain this account number or are related to it
        account_lines = []
        account_context_started = False
        
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Check if this line contains the account number
            if account_num in line_clean:
                print(f"[SPLIT_ACCOUNTS] Found account {account_num} on line {i+1}: {line_clean[:100]}...")
                account_context_started = True
                
                # Include context before and after the account number
                start_idx = max(0, i - 5)  # 5 lines before
                end_idx = min(len(lines), i + 50)  # 50 lines after (or until next account)
                
                # Check if there's another account number in the range that would cut this short
                for j in range(i + 1, end_idx):
                    for other_acc in account_numbers:
                        if other_acc != account_num and other_acc in lines[j]:
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
        # If LLM found account numbers but they're not in the text, 
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