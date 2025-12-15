#!/usr/bin/env python3
"""Debug document type detection."""

import sys
import os
sys.path.insert(0, os.getcwd())

from utils.document_types import document_type_detector

# Read the latest OCR text
ocr_files = [f for f in os.listdir('ocr_results') if f.endswith('.txt') and 'BP70C55-K6535_20250805_102701' in f]
if ocr_files:
    latest_ocr = sorted(ocr_files)[-1]
    print(f"Using OCR file: {latest_ocr}")
    
    with open(f'ocr_results/{latest_ocr}', 'r') as f:
        text = f.read()
    
    print(f"Text length: {len(text)} characters")
    print(f"First 200 characters: {text[:200]}")
    print()
    
    # Test detection with debug
    detected_type = document_type_detector.detect_document_type(text)
    print(f"Detected type: {detected_type}")
    
    # Check specific indicators
    text_upper = text.upper()
    
    print("\n=== DEATH CERTIFICATE INDICATORS ===")
    primary_indicators = [
        "CERTIFICATION OF VITAL RECORD",
        "DEATH CERTIFICATION", 
        "STATE FILE NUMBER"
    ]
    
    for indicator in primary_indicators:
        found = indicator in text_upper
        print(f"  {indicator}: {found}")
    
    print("\n=== WSFS BANK CHECK ===")
    wsfs_found = "WSFS BANK" in text_upper or "WSFS" in text_upper
    print(f"  WSFS found: {wsfs_found}")
    if wsfs_found:
        print(f"  WSFS positions: {[i for i, line in enumerate(text.split('\n')) if 'WSFS' in line.upper()]}")
        wsfs_lines = [line for line in text.split('\n') if 'WSFS' in line.upper()]
        print(f"  WSFS lines: {wsfs_lines[:3]}")  # Show first 3 lines with WSFS
    
else:
    print("No OCR files found")