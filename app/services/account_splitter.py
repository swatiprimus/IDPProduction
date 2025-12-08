"""
Account Splitter Service - Handles splitting loan documents by account numbers
"""
import re

# Account number patterns
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
    print(f"\n{'='*80}")
    print(f"[SPLIT_ACCOUNTS] Starting account splitting...")
    print(f"[SPLIT_ACCOUNTS] Input text length: {len(text)} characters")
    
    lines = text.splitlines()
    print(f"[SPLIT_ACCOUNTS] Total lines: {len(lines)}")
    
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
            print(f"[SPLIT_ACCOUNTS] Line {i+1}: Found inline account number: {acc}")
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
                    print(f"[SPLIT_ACCOUNTS] Line {i+1}: Found multi-line account number: {acc}")
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
    
    print(f"[SPLIT_ACCOUNTS] ✓ Found {len(chunks)} unique accounts")
    for idx, chunk in enumerate(chunks):
        acc_num = chunk.get("accountNumber", "")
        text_len = len(chunk.get("text", ""))
        print(f"[SPLIT_ACCOUNTS]   Account {idx+1}: {acc_num} ({text_len} chars)")
    print(f"{'='*80}\n")
    
    return chunks
