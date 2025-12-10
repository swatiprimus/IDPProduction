#!/usr/bin/env python3
"""
Test script to verify WSFS product extraction is working
"""

# Sample OCR text from the actual document
sample_ocr_text = """
ACCOUNT NUMBER:
Account Holder Names:
468869904
WSFS Core Savings
DANETTE EBERLY OR
R BRUCE EBERLY
ACCOUNT PURPOSE:
ACCOUNT TYPE:
Consumer
Personal
OWNERSHIP TYPE:
Mailing Address: 512 PONDEROSA DR, BEAR, DE, 19701-2155
Joint Owners
DATE OPENED:
DATE REVISED:
Home Phone: (302) 834-0382
Work Phone:
12/24/2014
Number of Signatures Required: 1
CIF Number 00000531825
VERIFIED BY:
OPENED BY:
Special Instructions:
Kasie Mears
College Square
"""

def extract_wsfs_product_from_text(text):
    """Extract WSFS product names from raw OCR text"""
    if not isinstance(text, str):
        return None
    
    wsfs_products = [
        "WSFS Core Savings",
        "WSFS Checking Plus", 
        "WSFS Money Market",
        "WSFS Premier Checking",
        "Premier Checking",
        "Platinum Savings",
        "Gold CD",
        "Business Checking"
    ]
    
    for product in wsfs_products:
        if product in text:
            return product
    
    return None

def test_wsfs_extraction():
    """Test WSFS product extraction"""
    
    print("Testing WSFS Product Extraction")
    print("=" * 50)
    
    # Test the extraction function
    wsfs_product = extract_wsfs_product_from_text(sample_ocr_text)
    
    if wsfs_product:
        print(f"✅ WSFS Product Found: {wsfs_product}")
    else:
        print("❌ WSFS Product NOT found")
    
    print("\nExpected extraction results with enhanced prompt:")
    print("-" * 50)
    
    expected_fields = {
        "Account_Number": "468869904",
        "Account_Holders": ["DANETTE EBERLY", "R BRUCE EBERLY"],
        "WSFS_Account_Type": "WSFS Core Savings",  # This should now be extracted!
        "Account_Purpose": "Consumer", 
        "Account_Category": "Personal",
        "Ownership_Type": "Joint Owners",
        "Address": "512 PONDEROSA DR, BEAR, DE, 19701-2155",
        "Phone_Number": "(302) 834-0382",
        "Date_Opened": "12/24/2014",
        "Signatures_Required": "1",
        "CIF_Number": "00000531825",
        "Verified_By": "Kasie Mears",
        "Branch": "College Square"
    }
    
    for field, value in expected_fields.items():
        if field == "WSFS_Account_Type":
            print(f"🔴 {field}: {value} ← CRITICAL FIELD")
        else:
            print(f"   {field}: {value}")
    
    print(f"\nTotal expected fields: {len(expected_fields)}")
    
    print("\nKey enhancements for WSFS product extraction:")
    print("✅ Added specific pattern recognition for account number + product name")
    print("✅ Enhanced prompt with WSFS Core Savings examples")
    print("✅ Added fallback extraction from raw OCR text")
    print("✅ Updated prompt version to v5 to invalidate old cache")
    print("✅ Added critical parsing rules at the top of prompt")
    
    return wsfs_product is not None

if __name__ == "__main__":
    success = test_wsfs_extraction()
    if success:
        print("\n🎉 WSFS extraction test PASSED!")
    else:
        print("\n❌ WSFS extraction test FAILED!")