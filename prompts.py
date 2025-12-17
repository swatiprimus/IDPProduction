#!/usr/bin/env python3
"""
Prompts Module - Extracted from app_modular.py
Contains all LLM prompts used for document processing
"""



def get_comprehensive_extraction_prompt():
    """Get comprehensive prompt for extracting ALL fields from any page"""
    return """
You are a data extraction expert. Extract ALL fields and their values from this document.

🔴🔴🔴 CRITICAL PRIORITY #1: VERIFICATION DETECTION 🔴🔴🔴
**THIS IS THE MOST IMPORTANT TASK - NEVER SKIP VERIFICATION DETECTION**

**STEP 1: MANDATORY VERIFICATION SCAN (DO THIS FIRST):**
Before extracting any other data, you MUST scan the ENTIRE page for verification indicators:

1. **SEARCH FOR "VERIFIED" TEXT EVERYWHERE:**
   - Look for "VERIFIED" stamps, seals, or text ANYWHERE on the page
   - Look for "VERIFICATION" text or stamps  
   - Look for "VERIFY" or "VERIFIED BY" text
   - Look for checkboxes or boxes marked with "VERIFIED"
   - Look for "✓ VERIFIED" or similar checkmark combinations
   - Search in margins, corners, stamps, seals, form fields, and document body
   - Extract as: Verified: {"value": "VERIFIED", "confidence": 95}

2. **SEARCH FOR NAMES NEAR VERIFICATION:**
   - Look for names immediately after "VERIFIED" (like "VERIFIED - RENDA")
   - Look for "VERIFIED BY: [NAME]" patterns
   - Look for names in verification stamps or seals
   - Extract as: Verified_By: {"value": "Name", "confidence": 85}
   
3. **SEARCH FOR VERIFICATION DATES:**
   - Look for dates on or near verification stamps
   - Look for "VERIFIED ON: [DATE]" patterns
   - Extract as: Verified_Date: {"value": "Date", "confidence": 85}

**OTHER CRITICAL FIELDS:**
4. **PHONE NUMBERS** - Look for "610-485-4979", "610- 485- 4979", "(302) 834-0382" - Extract as Phone_Number
5. **STAMP DATES** - Look for "MAR 21 2016", "DEC 26 2014", "MAR 2 5 2015" - Extract as Stamp_Date  
6. **REFERENCE NUMBERS** - Look for "#652", "#357", "#298" - Extract as Reference_Number
7. **ACCOUNT NUMBERS** - Any 8-10 digit numbers - Extract as Account_Number
8. **HANDWRITTEN TEXT** - Any handwritten numbers or text

🔴🔴🔴 VERIFICATION SEARCH INSTRUCTIONS 🔴🔴🔴
- **ALWAYS** scan the ENTIRE page text for the word "VERIFIED" (case-insensitive)
- **ALWAYS** scan for "VERIFICATION" text
- **ALWAYS** look for verification stamps, seals, or checkmarks
- **NEVER** skip verification detection - it must be checked on every page
- If you find "VERIFIED" anywhere, ALWAYS extract it as a field
- Look in margins, corners, stamps, seals, and form fields

CRITICAL: Extract EVERYTHING you see - printed text, handwritten text, stamps, seals, and marks.

IMPORTANT: Use SIMPLE, SHORT field names. Do NOT copy the entire label text from the document.
- Example: "DATE PRONOUNCED DEAD" → use "Death_Date" (NOT "Date_Pronounced_Dead")
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "Account_Holder_Names")
- Example: If you see "VERIFIED" stamp → use "Verified" with value "Yes" or "VERIFIED"
- Example: If you see handwritten "4630" near "Account" → use "Account_Number" with value "4630"
- Simplify all verbose labels to their core meaning
SPECIAL ATTENTION REQUIRED:
🔴 **HANDWRITTEN TEXT:** Extract ALL handwritten numbers and text - these are CRITICAL data points
   - Handwritten numbers are often account numbers, reference numbers, or IDs
   - **HANDWRITTEN PHONE NUMBERS:** Look for patterns like "610-485-4979", "610- 485- 4979", "(610) 485-4979"
   - Extract them with appropriate field names (Account_Number, Reference_Number, Phone_Number, Contact_Phone, etc.)
   
🔴 **STAMPS & SEALS:** Extract ALL stamps, seals, and verification marks
   - "VERIFIED" stamp → Verified: "Yes" or "VERIFIED"
   - Date stamps → Stamp_Date or Verified_Date (look for formats like "MAR 21 2016", "DEC 26 2014", "JAN 15 2023")
   - Reference numbers with stamps → Reference_Number (look for "#652", "#357", "Ref #123")
   - Names in stamps → Verified_By or Stamped_By
   - Official seals → Official_Seal: "Present" or description
   
🔴 **MULTIPLE NUMBERS:** Documents often have MULTIPLE number types - extract ALL of them
   - **Account_Number** (PRIMARY IDENTIFIER - handwritten or printed account/billing number)
   - Certificate_Number (printed certificate ID - ONLY if clearly labeled as "Certificate Number")
   - File_Number (state file number)
   - Reference_Number (reference or tracking number)

🔴🔴🔴 CRITICAL FOR DEATH CERTIFICATES 🔴🔴🔴
- **ANY LARGE NUMBER (8-10 digits) on a death certificate should be extracted as Account_Number**
- **Examples: 463085233, 468431466 → ALWAYS use Account_Number (NOT Certificate_Number)**
- **Only use Certificate_Number if you see explicit labels like "Certificate Number:" or "Cert #:"**
- **When in doubt on death certificates, use Account_Number for the main identifying number**

PRIORITY ORDER (Extract in this order):
1. **HANDWRITTEN NUMBERS** - These are often the most important (account numbers, IDs)
2. **STAMPS & VERIFICATION MARKS** - Verified stamps, date stamps, official seals
3. **IDENTIFYING NUMBERS** - Certificate numbers, file numbers, license numbers
4. **NAMES** - All person names (full names, witness names, registrar names, stamped names)
5. **DATES** - All dates (issue dates, birth dates, death dates, stamp dates)
6. **LOCATIONS** - Cities, states, counties, countries, addresses
7. **FORM FIELDS** - All labeled fields with values
8. **CHECKBOXES** - Checkbox states (Yes/No, checked/unchecked)
9. **ANY OTHER VISIBLE DATA** - Extract everything else you can see

🔴🔴🔴 CRITICAL PHONE NUMBER EXTRACTION RULES 🔴🔴🔴
- **PHONE NUMBERS ARE CRITICAL** - Look for ALL phone number patterns in the document
- **COMMON PHONE NUMBER FORMATS:**
  * "610-485-4979" (standard format with dashes)
  * "610- 485- 4979" (with spaces around dashes - common in handwritten)
  * "(302) 834-0382" (with parentheses and space)
  * "302.834.0382" (with dots)
  * "3028340382" (no separators)
- **HANDWRITTEN PHONE NUMBERS:** Often have irregular spacing - still extract them
- **WHERE TO FIND:** Can appear anywhere on the document - margins, forms, handwritten notes
- **FIELD NAMES:** Use Phone_Number, Contact_Phone, Mobile_Phone, or Signer1_Phone as appropriate

🔴🔴🔴 CRITICAL STAMP DATE EXTRACTION RULES 🔴🔴🔴
- **STAMP DATES ARE CRITICAL** - Look for standalone dates that appear to be stamped on the document
- **COMMON STAMP DATE FORMATS:**
  * "MAR 21 2016" (month abbreviation, day, year)
  * "DEC 26 2014" (month abbreviation, day, year)  
  * "MAR 2 5 2015" (month abbreviation, day with space, year)
  * "JAN 15 2023" (month abbreviation, day, year)
- **STAMP REFERENCE NUMBERS:** Look for numbers with # symbol like "#652", "#357", "#298"
- **WHERE TO FIND STAMPS:** Usually in margins, corners, or separate sections of certificates
- **EXTRACT BOTH:** If you see a stamp date, also look for an associated reference number nearby
CRITICAL RULES:
- Extract EVERY field you can see - printed, handwritten, stamped, or sealed
- **HANDWRITTEN TEXT IS CRITICAL** - Never skip handwritten numbers or text
- **STAMPS ARE DATA** - Extract stamp text as actual field values, not descriptions
- Include ALL identifying numbers (license #, certificate #, file #, reference #, account #, etc.)
- Extract ALL names, even if they appear multiple times in different contexts
- Extract ALL dates in their original format
- Do NOT extract long legal text, disclaimers, or authorization paragraphs
- Do NOT extract instructions about how to fill the form
- Extract actual DATA, not explanatory text

WHAT TO EXTRACT:
✓ **IDENTIFYING NUMBERS (Extract ALL - Documents can have multiple number types):**
  - **ALWAYS match the field name to the LABEL on the document**
  - **A document can have MULTIPLE number types** (e.g., both Certificate_Number AND Account_Number)
  - **Certificate_Number:** Use when you see "Certificate Number", "Certificate No", "Cert #"
  - **Account_Number:** Use when you see "Account Number", "Account No", "Acct #", "Acct Number" (may be handwritten or printed)
  - **File_Number:** Use when you see "File Number", "File No", "State File Number"
  - **License_Number:** Use when you see "License Number", "License No", "DL #"
  - **Reference_Number:** Use when you see "Reference Number", "Ref #", "Reference No"
  - **Registration_Number:** Use when you see "Registration Number", "Registration No"
  - **IMPORTANT:** Extract ALL numbers you find - don't skip any!
  - **Example:** A death certificate might have BOTH Certificate_Number (for the certificate) AND Account_Number (handwritten for billing)
  - **Rule:** If you see "Account" or "Acct" label → ALWAYS extract as Account_Number (even on certificates)
✓ **ALL OTHER IDENTIFYING NUMBERS:**
  - Document_Number, Reference_Number, Case_Number
  - Any number with a label or identifier
✓ **ALL NAMES:**
  - Full_Name, Spouse_Name, Witness_Names, Registrar_Name
  - Father_Name, Mother_Name, Maiden_Name
  - Any person's name mentioned in the document
✓ **ALL DATES:**
  - Issue_Date, Birth_Date, Marriage_Date, Death_Date
  - Expiration_Date, Filing_Date, Registration_Date
  - Stamp_Date (look for stamps like "DEC 26 2014", "JAN 15 2023", "MAR 21 2016", "MAR 2 5 2015")
  - Reference_Number (look for "#652", "#357", "Ref #123", numbers with # symbol)
✓ **ALL LOCATIONS:**
  - City, State, County, Country
  - Place_of_Birth, Place_of_Marriage, Place_of_Death
  - Address, Residence
✓ **FORM FIELDS:**
  - Business_Name, Account_Number
  - Card_Details, Abbreviations_Needed
  - Branch_Name, Associate_Name
  - ALL other form fields with labels
✓ **SIGNER INFORMATION (if applicable):**
  - If ONE signer: Signer1_Name, Signer1_SSN, Signer1_DateOfBirth, Signer1_Address, Signer1_Phone, Signer1_DriversLicense
  - If TWO signers: Add Signer2_Name, Signer2_SSN, Signer2_DateOfBirth, Signer2_Address, Signer2_Phone, Signer2_DriversLicense
  - If THREE+ signers: Continue with Signer3_, Signer4_, etc.
✓ **VERIFICATION & CERTIFICATION FIELDS:**
  - Verified (Yes/No or checkbox state)
  - Verified_By (name of person who verified)
  - Verified_Date (date of verification)
  - Certification_Date, Certified_By
  - Registrar_Name, Registrar_Signature
  - Official_Seal, Stamp_Date
  - Any verification stamps or certification marks
✓ **CHECKBOXES & STATUS FIELDS:**
  - Extract ALL checkbox states (checked/unchecked, Yes/No, True/False)
  - Status fields (Approved, Pending, Verified, etc.)
  - Any marked or selected options
✓ **PHONE NUMBERS & CONTACT INFO:**
  - Phone_Number, Contact_Phone, Mobile_Phone (look for patterns like "610-485-4979", "610- 485- 4979", "(302) 834-0382")
  - Fax_Number, Email_Address
  - **CRITICAL:** Extract ALL phone numbers, even if handwritten or have unusual spacing
✓ **ALL OTHER VISIBLE FIELDS**

WHAT NOT TO EXTRACT:
✗ Long authorization paragraphs
✗ Legal disclaimers
✗ "NOTE:" sections with instructions
✗ "AUTHORIZATION:" sections with legal text
✗ Form filling instructions
✗ Page numbers
✗ Headers and footers (unless they contain data)
FIELD NAMING:
- Use SIMPLE, SHORT field names (not the full label text)
- Replace spaces with underscores
- **MATCH THE LABEL ON THE DOCUMENT:**
  * If document says "Certificate Number" → use "Certificate_Number"
  * If document says "Account Number" → use "Account_Number"
  * If document says "License Number" → use "License_Number"
  * If document says "File Number" → use "File_Number"
- Example: "License Number" → "License_Number"
- Example: "Date of Birth" → "Date_Of_Birth"
- Example: "DATE PRONOUNCED DEAD" → "Death_Date"
- Example: "ACTUAL OR PRESUMED DATE OF DEATH" → "Death_Date"
- Simplify verbose labels to their core meaning, but keep the field type accurate

EXAMPLES OF MULTIPLE NUMBER TYPES:

Example 1: Death Certificate with handwritten account number
- Document shows: "Certificate Number: 2025-12345" (printed)
- Document shows: "Account No: 987654321" (handwritten)
- Extract BOTH:
{
  "Certificate_Number": {"value": "2025-12345", "confidence": 95},
  "Account_Number": {"value": "987654321", "confidence": 75}
}

Example 2: Bank document with multiple numbers
- Document shows: "Account Number: 1234567890"
- Document shows: "Reference #: 298"
- Extract BOTH:
{
  "Account_Number": {"value": "1234567890", "confidence": 95},
  "Reference_Number": {"value": "298", "confidence": 90}
}

RETURN FORMAT:
Return a JSON object where each field has both a value and a confidence score (0-100):

{
  "Field_Name": {
    "value": "extracted value",
    "confidence": 95
  },
  "Phone_Number": {
    "value": "610-485-4979",
    "confidence": 85
  },
  "Stamp_Date": {
    "value": "MAR 21 2016",
    "confidence": 90
  },
  "Reference_Number": {
    "value": "#357",
    "confidence": 95
  }
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

IMPORTANT:
- Only include fields with actual values (omit empty fields)
- Every field MUST have both "value" and "confidence"
- Be honest about confidence - if text is unclear, use a lower score
- Extract the phone number "610- 485- 4979" as "Phone_Number": {"value": "610-485-4979", "confidence": 75}

EXTRACT EVERYTHING - BE THOROUGH AND COMPLETE!
"""

def get_drivers_license_prompt():
    """Get specialized prompt for extracting driver's license / ID card information"""
    return """
You are a data extraction expert specializing in government-issued identification documents.

Extract ALL information from this Driver's License or ID Card.

CRITICAL FIELDS TO EXTRACT:
1. **PERSONAL INFORMATION:**
   - Full_Name (as shown on license)
   - First_Name, Middle_Name, Last_Name
   - Date_of_Birth (DOB)
   - Sex / Gender
   - Height
   - Weight
   - Eye_Color
   - Hair_Color

2. **LICENSE INFORMATION:**
   - License_Number (DL #, ID #)
   - State / Issuing_State
   - License_Class (Class A, B, C, D, etc.)
   - Issue_Date (ISS)
   - Expiration_Date (EXP)
   - Restrictions (if any)
   - Endorsements (if any)

3. **ADDRESS:**
   - Street_Address
   - City
   - State
   - ZIP_Code
   - Full_Address (complete address as shown)

4. **ADDITIONAL INFORMATION:**
   - Document_Type (Driver License, ID Card, etc.)
   - Card_Number (if different from license number)
   - DD_Number (Document Discriminator)
   - Organ_Donor (Yes/No if indicated)
   - Veteran (if indicated)
   - Any_Barcodes or QR_Codes
   - Any_Other_Numbers or identifiers

EXTRACTION RULES:
- Extract EVERY visible field on the ID card
- Include all numbers, dates, and text
- Preserve exact formatting of license numbers and dates
- Extract address exactly as shown
- Include any stamps, seals, or watermarks mentioned
- If a field is partially visible or unclear, still extract it and note "unclear" or "partially visible"
- Look for information on BOTH front and back of the card if visible

FIELD NAMING:
- Use descriptive names with underscores
- Example: "DL #" → "License_Number"
- Example: "DOB" → "Date_of_Birth"
- Example: "ISS" → "Issue_Date"
- Example: "EXP" → "Expiration_Date"

RETURN FORMAT:
Return ONLY valid JSON in this exact format where EVERY field has both value and confidence:
{
  "documents": [
    {
      "document_id": "dl_001",
      "document_type": "drivers_license",
      "document_type_display": "Driver's License / ID Card",
      "document_icon": "🪪",
      "document_description": "Government-issued identification",
      "extracted_fields": {
        "Document_Type": {
          "value": "Driver License",
          "confidence": 95
        },
        "State": {
          "value": "Delaware",
          "confidence": 100
        },
        "License_Number": {
          "value": "1234567",
          "confidence": 95
        },
        "Full_Name": {
          "value": "John Doe",
          "confidence": 98
        },
        "Date_of_Birth": {
          "value": "01/15/1980",
          "confidence": 100
        },
        "Address": {
          "value": "123 Main St",
          "confidence": 95
        },
        "City": {
          "value": "Wilmington",
          "confidence": 100
        },
        "Issue_Date": {
          "value": "12/03/2012",
          "confidence": 100
        },
        "Expiration_Date": {
          "value": "12/03/2020",
          "confidence": 100
        }
      }
    }
  ]
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL REQUIREMENTS:
- EVERY field MUST have both "value" and "confidence"
- Only include fields that are VISIBLE in the document
- Do not use "N/A" or empty strings
- Extract EVERYTHING you can see on the ID card - be thorough and complete!
"""
def get_loan_document_prompt():
    """Get the specialized prompt for loan/account documents"""
    # PROMPT VERSION: Increment this when prompt changes to invalidate old cache
    # Current version: v7 (enhanced VERIFIED detection for loan documents)
    return """
You are an AI assistant that extracts ALL structured data from loan account documents.

🚨🚨🚨 CRITICAL EXTRACTION RULES - READ FIRST 🚨🚨🚨

**RULE #1: FLAT STRUCTURE ONLY**
- Extract ONLY simple field-value pairs
- DO NOT create nested objects or complex structures
- DO NOT create fields like "ATM_POS_Debit_Card" with nested person data
- Each field should have ONE simple string value

**RULE #2: INDIVIDUAL SIGNER FIELDS**
- Extract each person as separate numbered fields: Signer1_Name, Signer2_Name, etc.
- DO NOT group people into arrays or nested objects
- DO NOT create person names as object keys

**RULE #3: CONFIDENCE SCORES REQUIRED**
- EVERY field MUST be returned in this format:
```json
{
  "Field_Name": {
    "value": "extracted value",
    "confidence": 95
  }
}
```

**CONFIDENCE SCORE GUIDELINES:**
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

🔴🔴🔴 CRITICAL PRIORITY #1: VERIFICATION DETECTION 🔴🔴🔴
**THIS IS THE MOST IMPORTANT TASK - NEVER SKIP VERIFICATION DETECTION**

**STEP 1: MANDATORY VERIFICATION SCAN (DO THIS FIRST):**
Before extracting any other data, you MUST scan the ENTIRE page for verification indicators:

1. **SEARCH FOR "VERIFIED" TEXT EVERYWHERE:**
   - Look for "VERIFIED" stamps, seals, or text ANYWHERE on the page
   - Look for "VERIFICATION" text or stamps  
   - Look for "VERIFY" or "VERIFIED BY" text
   - Look for checkboxes or boxes marked with "VERIFIED"
   - Look for "✓ VERIFIED" or similar checkmark combinations
   - Search in margins, corners, stamps, seals, form fields, and document body
   - Extract as: Verified: {"value": "VERIFIED", "confidence": 95}

2. **SEARCH FOR NAMES NEAR VERIFICATION:**
   - Look for names immediately after "VERIFIED" (like "VERIFIED - RENDA")
   - Look for "VERIFIED BY: [NAME]" patterns
   - Look for names in verification stamps or seals
   - Extract as: Verified_By: {"value": "Name", "confidence": 85}
   
3. **SEARCH FOR VERIFICATION DATES:**
   - Look for dates on or near verification stamps
   - Look for "VERIFIED ON: [DATE]" patterns
   - Extract as: Verified_Date: {"value": "Date", "confidence": 85}

4. **CRITICAL: STAMP DATE DETECTION:**
   - Look for standalone dates that appear to be stamped on the document
   - Common formats: "MAR 21 2016", "DEC 26 2014", "JAN 15 2023", "MAR 2 5 2015"
   - Look for dates in margins, corners, or separate sections of certificates
   - Look for dates near reference numbers like "#652", "#357", "#298"
   - Extract as: Stamp_Date: {"value": "Date", "confidence": 90}

5. **CRITICAL: REFERENCE NUMBER DETECTION:**
   - Look for numbers with # symbol like "#652", "#357", "#298"
   - Look for "Ref #123", "Reference #456" patterns
   - Often appear near stamp dates or verification marks
   - Extract as: Reference_Number: {"value": "#123", "confidence": 90}

🚨 **VERIFICATION DETECTION RULES:**
- **NEVER** skip verification detection - it must be checked on EVERY page
- **ALWAYS** scan the ENTIRE page text for "VERIFIED" (case-insensitive)
- **ALWAYS** extract verification fields if found, even if unclear
- If you find ANY verification indicator, you MUST extract it
- Look in ALL parts of the page: headers, footers, margins, stamps, seals, form fields

🔴🔴🔴 VERIFICATION EXAMPLES - STUDY THESE PATTERNS 🔴🔴🔴

**COMMON VERIFICATION PATTERNS TO LOOK FOR:**
- "VERIFIED" (standalone stamp)
- "VERIFIED - [NAME]" (stamp with name)
- "VERIFIED BY: [NAME]" (formal verification)
- "✓ VERIFIED" (checkmark with verified)
- "VERIFICATION COMPLETE" (process completion)
- "DOCUMENT VERIFIED" (document validation)
- "IDENTITY VERIFIED" (identity confirmation)
- "SIGNATURE VERIFIED" (signature validation)

**EXAMPLE EXTRACTIONS:**
- Text: "VERIFIED" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}
- Text: "VERIFIED - RENDA" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "RENDA", "confidence": 90}
- Text: "VERIFIED BY: MARIA SANTOS" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_By: {"value": "MARIA SANTOS", "confidence": 90}
- Text: "✓ VERIFIED 03/15/2024" → Extract: Verified: {"value": "VERIFIED", "confidence": 95}, Verified_Date: {"value": "03/15/2024", "confidence": 90}
- Text: "VERIFICATION COMPLETE" → Extract: Verified: {"value": "VERIFIED", "confidence": 90}

🚨 **CRITICAL REMINDER:**
- Verification detection is MANDATORY on every page
- Even if the text is unclear, extract it with lower confidence
- Look in ALL areas of the page, not just the main content
- If you're unsure, extract it anyway - better to have false positives than miss verification
🔴🔴🔴 MOST IMPORTANT - EXTRACT ALL ACCOUNT AND SIGNER FIELDS 🔴🔴🔴

**CRITICAL ACCOUNT FIELDS TO EXTRACT:**
1. **Account_Number** - Look for "ACCOUNT NUMBER:", "Account Number:", or similar labels
2. **Account_Holders** - Look for "Account Holder Names:", "ACCOUNT HOLDER NAMES:", or names listed as account owners
3. **Mailing_Address** - Look for "Mailing Address:", complete address with street, city, state, zip
4. **Phone_Number** - Look for "Home Phone:", "Work Phone:", or any phone numbers
5. **Date_Opened** - Look for "DATE OPENED:", "Date Opened:", opening date
6. **CIF_Number** - Look for "CIF Number", "CIF #", customer identification number
7. **Branch** - Look for branch name, location, or office name
8. **Verified_By** - Look for "VERIFIED BY:", "Verified By:", name of verifier
9. **Opened_By** - Look for "OPENED BY:", name of person who opened account
10. **Signatures_Required** - Look for "Number of Signatures Required:", signature requirements

**CRITICAL SIGNER FIELDS TO EXTRACT:**
🚨 **SIGNER EXTRACTION RULES - FOLLOW EXACTLY:**

1. **EXTRACT INDIVIDUAL SIGNER FIELDS ONLY** - Do NOT create nested objects or complex structures
2. **USE FLAT FIELD NAMES** - Signer1_Name, Signer1_SSN, Signer2_Name, etc.
3. **NO NESTED OBJECTS** - Do NOT create fields like "ATM_POS_Debit_Card" or "Account_Holders" with nested data
4. **SIMPLE VALUES ONLY** - Each field should have a simple string value, not an object or array

**CORRECT SIGNER FIELD FORMAT:**
```json
{
  "Signer1_Name": {"value": "LAILA M SOUFI", "confidence": 90},
  "Signer1_SSN": {"value": "861-23-0038", "confidence": 85},
  "Signer1_Phone": {"value": "(302) 482-5887", "confidence": 90},
  "Signer1_Address": {"value": "601 Oakdale Rd Apt L Newark DE 19713", "confidence": 85},
  "Signer2_Name": {"value": "RAHMAH A GOOBA", "confidence": 90},
  "Signer2_SSN": {"value": "732010721", "confidence": 85},
  "Signer2_Phone": {"value": "(302) 257-9213", "confidence": 90}
}
```

**WRONG - DO NOT DO THIS:**
```json
{
  "ATM_POS_Debit_Card": {
    "LAILA M SOUFI": {"Features": [...], "Primary_Account": "..."}
  },
  "Account_Holders": ["ABDULGHAFA M AHMED", "Laila M Soufi"]
}
```

**SIGNER FIELD NAMES TO USE:**
- Signer1_Name, Signer2_Name, Signer3_Name (full names)
- Signer1_SSN, Signer2_SSN, Signer3_SSN (social security numbers)
- Signer1_DOB, Signer2_DOB, Signer3_DOB (dates of birth)
- Signer1_Address, Signer2_Address, Signer3_Address (complete addresses)
- Signer1_Phone, Signer2_Phone, Signer3_Phone (phone numbers)
- Signer1_Email, Signer2_Email, Signer3_Email (email addresses)
- Signer1_DriversLicense, Signer2_DriversLicense (license numbers)
- Signer1_Employer, Signer2_Employer (employer names)
- Signer1_Occupation, Signer2_Occupation (job titles)

**CRITICAL:** Extract each person's information as separate numbered signer fields. Do NOT group them into arrays or nested objects.

**EXAMPLE FIELD MAPPINGS FROM DOCUMENT:**
- "Account Holder Names: DANETTE EBERLY OR R BRUCE EBERLY" → Account_Holders: ["DANETTE EBERLY", "R BRUCE EBERLY"]
- "Mailing Address: 512 PONDEROSA DR, BEAR, DE, 19701-2155" → Mailing_Address: "512 PONDEROSA DR, BEAR, DE, 19701-2155"
- "Home Phone: (302) 834-0382" → Phone_Number: "(302) 834-0382"
- "CIF Number 00000531825" → CIF_Number: "00000531825"
- "VERIFIED BY: Kasie Mears" → Verified_By: "Kasie Mears"
- "468869904" followed by "WSFS Core Savings" → WSFS_Account_Type: "WSFS Core Savings"

🔴🔴🔴 CRITICAL PARSING RULES - READ THESE FIRST 🔴🔴🔴

**RULE 1: WSFS PRODUCT NAME EXTRACTION**
Look for this EXACT pattern in the text:
```
ACCOUNT NUMBER:
Account Holder Names:
468869904
WSFS Core Savings
```
When you see an account number followed by "WSFS Core Savings" (or similar product name), extract it as:
WSFS_Account_Type: "WSFS Core Savings"

**RULE 2: COMBINED OCR TEXT PARSING - CRITICAL SEPARATION REQUIRED**
The OCR often reads form labels and values together without spaces. You MUST parse them correctly:

🚨 ABSOLUTE RULE: NEVER put "Consumer Personal" or "Consumer Business" in Account_Type field! 🚨

IF YOU SEE THIS IN THE TEXT:
- "PurposeConsumer" or "Purpose:Consumer" or "Purpose: Consumer" → Extract as: "Account_Purpose": "Consumer"
- "TypePersonal" or "Type:Personal" or "Type: Personal" → Extract as: "Account_Type": "Personal"
- "Consumer Personal" (anywhere in document) → Extract as TWO fields:
  * "Account_Purpose": "Consumer"
  * "Account_Type": "Personal"
- "Consumer Business" (anywhere in document) → Extract as TWO fields:
  * "Account_Purpose": "Consumer"
  * "Account_Type": "Business"
- "PurposeConsumer Personal" or "Purpose:Consumer Type:Personal" → Extract as TWO fields:
  * "Account_Purpose": "Consumer"
  * "Account_Type": "Personal"

PARSING RULES:
1. Look for the word "Purpose" followed by a value (Consumer, Checking, Savings, etc.) → Extract as Account_Purpose
2. Look for the word "Type" followed by a value (Personal, Business, etc.) → Extract as Account_Type
3. These are ALWAYS separate fields even if they appear together in the text
4. NEVER combine them into one field
5. 🚨 If you see "Consumer Personal" - ALWAYS split: Purpose=Consumer, Type=Personal
6. 🚨 If you see "Consumer Business" - ALWAYS split: Purpose=Consumer, Type=Business

WRONG ❌ - NEVER DO THIS:
{
  "Account_Type": "Consumer Personal"
}
{
  "Account_Type": "Consumer Business"
}

CORRECT ✅ - ALWAYS DO THIS:
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Personal"
}
{
  "Account_Purpose": "Consumer",
  "Account_Type": "Business"
}

IF THE TEXT SAYS "PurposeConsumer Personal", PARSE IT AS:
- Find "Purpose" → Next word is "Consumer" → Account_Purpose: "Consumer"
- Find "Personal" (after Consumer) → This is the Type value → Account_Type: "Personal"

CRITICAL: Use SIMPLE, SHORT field names. Do NOT copy verbose labels from the document.
- Example: "ACCOUNT HOLDER NAMES" → use "Account_Holders" (NOT "AccountHolderNames")
- Example: "DATE OF BIRTH" → use "DOB" or "Birth_Date" (NOT "DateOfBirth")
- Example: "SOCIAL SECURITY NUMBER" → use "SSN" (NOT "SocialSecurityNumber")
- Keep field names concise and readable
**CRITICAL ACCOUNT NUMBER DETECTION RULES (FOR BANK/LOAN DOCUMENTS ONLY):**
- This prompt is for BANK/LOAN documents, so Account_Number is the primary identifier
- Account numbers may be HANDWRITTEN or printed on the document
- Look for labels like: "Account", "Acct", "Account #", "Account No", "Acct Number", "Account Number"
- Account numbers are typically 8-12 digits, may have dashes or spaces
- If you see a handwritten number near an "Account" label, extract it as Account_Number
- DO NOT use Account_Number for:
  * Death/Birth/Marriage certificates (use Certificate_Number instead)
  * Driver's licenses (use License_Number instead)
  * File reference numbers (use File_Number instead)
- ONLY use Account_Number if the document is clearly a bank/loan/account document

Extract EVERY piece of information from the document and return it as valid JSON.

REQUIRED FIELDS (extract if present):

🚨 **CRITICAL OUTPUT FORMAT - FOLLOW EXACTLY:**

**ACCOUNT FIELDS (simple strings only):**
- Account_Number: "468869904"
- Account_Holders: "DANETTE EBERLY, R BRUCE EBERLY" (comma-separated string, NOT array)
- Account_Purpose: "Consumer"
- Account_Type: "Personal"
- WSFS_Account_Type: "WSFS Core Savings"
- Ownership_Type: "Joint Owners"
- Mailing_Address: "512 PONDEROSA DR, BEAR, DE, 19701-2155"
- Phone_Number: "(302) 834-0382"
- Date_Opened: "12/24/2014"
- CIF_Number: "00000531825"
- Branch: "College Square"
- Verified_By: "Kasie Mears"

**SIGNER FIELDS (flat structure only):**
- Signer1_Name: "LAILA M SOUFI"
- Signer1_SSN: "861-23-0038"
- Signer1_DOB: "7/27/1987"
- Signer1_Address: "601 Oakdale Rd Apt L Newark DE 19713"
- Signer1_Phone: "(302) 482-5887"
- Signer1_DriversLicense: "State ID 9464747 DE"
- Signer2_Name: "RAHMAH A GOOBA"
- Signer2_SSN: "732010721"
- Signer2_DOB: "2/20/1954"
- Signer2_Address: "601 Oakdale Rd Apt L Newark DE 19713"
- Signer2_Phone: "(302) 257-9213"
- Signer2_DriversLicense: "State ID 9330424 DE"

🚨 **ABSOLUTELY FORBIDDEN:**
- DO NOT create "ATM_POS_Debit_Card" fields
- DO NOT create nested objects with person names as keys
- DO NOT create arrays of objects
- DO NOT create complex nested structures
- ONLY use simple string values for each field

For documents with MULTIPLE signers, add Signer2_, Signer3_, etc.:
{
  "Account_Number": "string",
  "Signer1_Name": "string",
  "Signer1_SSN": "string",
  "Signer1_DOB": "string",
  "Signer2_Name": "string",
  "Signer2_SSN": "string",
  "Signer2_DOB": "string"
}

FIELD DEFINITIONS - READ CAREFULLY:

🔴 CRITICAL: Account_Purpose and Account_Type are TWO SEPARATE FIELDS - NEVER combine them!

🚨 COMMON MISTAKE TO AVOID: 
- WRONG: "Account_Type": "Consumer Personal" 
- CORRECT: "Account_Purpose": "Consumer", "Account_Type": "Personal"

🚨 IF YOU SEE "Consumer Personal" OR "Consumer Business" - ALWAYS SPLIT INTO TWO FIELDS!

1. Account_Purpose: The CATEGORY or CLASSIFICATION of the account.
   LOOK FOR: The word "Purpose" in the text (may appear as "Purpose:", "PurposeConsumer", "Purpose Consumer", etc.)
   EXTRACT: The value that comes AFTER "Purpose"
   POSSIBLE VALUES:
   - "Consumer" (consumer banking)
   - "Checking" (checking account)
   - "Savings" (savings account)
   - "Money Market" (money market account)
   - "CD" or "Certificate of Deposit"
   - "IRA" or "Retirement"
   - "Loan" (loan account)
   - "Mortgage" (mortgage account)
   
   PARSING EXAMPLES:
   - Text: "Purpose: Consumer" → Account_Purpose: "Consumer"
   - Text: "PurposeConsumer" → Account_Purpose: "Consumer"
   - Text: "Purpose:Consumer Type:Personal" → Account_Purpose: "Consumer" (extract ONLY the Purpose value)
   - Text: "PurposeConsumer Personal" → Account_Purpose: "Consumer" (extract ONLY "Consumer", NOT "Consumer Personal")

2. Account_Type: The USAGE TYPE or WHO uses the account.
   LOOK FOR: The word "Type" in the text (may appear as "Type:", "TypePersonal", "Type Personal", etc.)
   EXTRACT: The value that comes AFTER "Type"
   POSSIBLE VALUES:
   - "Personal" (for individual/family use)
   - "Business" (for business operations)
   - "Commercial" (for commercial purposes)
   - "Corporate" (for corporation)
   - "Trust" (trust account)
   - "Estate" (estate account)
   
   PARSING EXAMPLES:
   - Text: "Type: Personal" → Account_Type: "Personal"
   - Text: "TypePersonal" → Account_Type: "Personal"
   - Text: "Purpose:Consumer Type:Personal" → Account_Type: "Personal" (extract ONLY the Type value)
   - Text: "PurposeConsumer Personal" → Account_Type: "Personal" (extract ONLY "Personal", which comes after "Consumer")
3. WSFS_Account_Type: The SPECIFIC internal bank account type code or classification. Look for:
   - Specific product names like "Premier Checking", "Platinum Savings", "Gold CD", "WSFS Saving Core"
   - Internal codes or account classifications
   - Branded account names unique to the bank
   - **IMPORTANT**: This field often appears WITHOUT a header label - just the value written on the form
   - Look for bank-specific product names like "WSFS Saving Core", "WSFS Checking Plus", etc.
   - These are usually written in a specific area of the form, even without a label
   - If you see "WSFS Saving Core" or similar bank product names, extract as WSFS_Account_Type
   - This is SEPARATE from Account_Type (Personal/Business) and Account_Purpose (Consumer/Checking)

4. Ownership_Type: WHO owns the account legally. Common values:
   - "Individual" or "Single Owner" (single owner)
   - "Joint" or "Joint Owners" (multiple owners with equal rights)
   - "Joint with Rights of Survivorship"
   - "Trust" (held in trust)
   - "Estate" (estate account)
   - "Custodial" (for minor)
   - "Business" or "Corporate"
- DO NOT create a field called "Purpose" with value "Consumer Personal"
- These are ALWAYS separate fields even if they appear together on the form

RETURN FORMAT WITH CONFIDENCE SCORES:
Return JSON where each field has both a value and confidence score (0-100):

{
  "Account_Number": {
    "value": "0210630620",
    "confidence": 95
  },
  "Signer1_Name": {
    "value": "John Doe",
    "confidence": 90
  },
  "Signer1_SSN": {
    "value": "123-45-6789",
    "confidence": 85
  }
}

CONFIDENCE SCORE GUIDELINES:
- 90-100: Text is clear, printed, and easily readable
- 70-89: Text is readable but slightly unclear (handwritten, faded, or small)
- 50-69: Text is partially unclear or ambiguous
- 30-49: Text is difficult to read or uncertain
- 0-29: Very uncertain or guessed

CRITICAL RULES:
1. ONLY extract fields that are VISIBLE in the document
2. DO NOT include fields with "N/A" or empty values
3. For multiple signers, use Signer1_, Signer2_, Signer3_ prefixes
4. Each signer's information should be separate fields, not nested objects
5. Every field MUST have both "value" and "confidence"

🔴 FINAL REMINDER - DO NOT FORGET 🔴
Account_Purpose and Account_Type are ALWAYS TWO SEPARATE FIELDS!

🚨 CRITICAL EXAMPLES:
WRONG: "Account_Type": "Consumer Personal" ❌
WRONG: "Account_Type": "Consumer Business" ❌
WRONG: "Account_Purpose": "Consumer Personal" ❌

CORRECT: "Account_Purpose": "Consumer", "Account_Type": "Personal" ✅
CORRECT: "Account_Purpose": "Consumer", "Account_Type": "Business" ✅

🚨 IF YOU SEE "Consumer Personal" OR "Consumer Business" - ALWAYS SPLIT INTO TWO FIELDS!
"""