#!/usr/bin/env python3
"""
Script to create app.py from universal_idp.py using modular services
"""

# Read universal_idp.py
with open('universal_idp.py', 'r', encoding='utf-8') as f:
    original_lines = f.readlines()

# Start building the new app.py
new_app = []

# Add header
new_app.append('#!/usr/bin/env python3\n')
new_app.append('"""\n')
new_app.append('Universal IDP - Modular Version\n')
new_app.append('Uses clean modular services instead of monolithic code\n')
new_app.append('"""\n\n')

# Add imports
new_app.append('from flask import Flask, render_template, request, jsonify, send_file\n')
new_app.append('import boto3\n')
new_app.append('import json\n')
new_app.append('import time\n')
new_app.append('import threading\n')
new_app.append('import hashlib\n')
new_app.append('import os\n')
new_app.append('import re\n')
new_app.append('from datetime import datetime\n')
new_app.append('import io\n')
new_app.append('from concurrent.futures import ThreadPoolExecutor, as_completed\n\n')

# Add modular service imports
new_app.append('# Import modular services\n')
new_app.append('from app.services.textract_service import extract_text_with_textract, try_extract_pdf_with_pypdf\n')
new_app.append('from app.services.account_splitter import split_accounts_strict\n')
new_app.append('from app.services.document_detector import detect_document_type, SUPPORTED_DOCUMENT_TYPES\n')
new_app.append('from app.services.loan_processor import process_loan_document\n\n')

# Add Flask app initialization and config
new_app.append('app = Flask(__name__)\n\n')
new_app.append('# AWS & Model Configuration\n')
new_app.append('AWS_REGION = "us-east-1"\n')
new_app.append('bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)\n')
new_app.append('textract = boto3.client("textract", region_name=AWS_REGION)\n')
new_app.append('s3_client = boto3.client("s3", region_name=AWS_REGION)\n')
new_app.append('MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"\n')
new_app.append('S3_BUCKET = "awsidpdocs"\n\n')
new_app.append('# In-memory Job Tracker\n')
new_app.append('job_status_map = {}\n\n')
new_app.append('# Create output directory for OCR results\n')
new_app.append('OUTPUT_DIR = "ocr_results"\n')
new_app.append('os.makedirs(OUTPUT_DIR, exist_ok=True)\n\n')
new_app.append('# Persistent storage for processed documents\n')
new_app.append('DOCUMENTS_DB_FILE = "processed_documents.json"\n\n')

# Add database functions
new_app.append('def load_documents_db():\n')
new_app.append('    """Load processed documents from file"""\n')
new_app.append('    if os.path.exists(DOCUMENTS_DB_FILE):\n')
new_app.append('        with open(DOCUMENTS_DB_FILE, \'r\', encoding=\'utf-8\') as f:\n')
new_app.append('            return json.load(f)\n')
new_app.append('    return []\n\n')
new_app.append('def save_documents_db(documents):\n')
new_app.append('    """Save processed documents to file"""\n')
new_app.append('    with open(DOCUMENTS_DB_FILE, \'w\', encoding=\'utf-8\') as f:\n')
new_app.append('        json.dump(documents, indent=2, fp=f)\n\n')
new_app.append('# Load existing documents on startup\n')
new_app.append('processed_documents = load_documents_db()\n\n')

# Now copy specific functions from universal_idp.py
# We need: flatten_nested_objects, call_bedrock, extract_basic_fields, prompts, and all routes

# Find and copy functions (skip the ones we already have in modules)
skip_functions = [
    'split_accounts_strict',
    'detect_document_type',
    'process_loan_document',
    'extract_text_with_textract',
    'extract_text_with_textract_async',
    'try_extract_pdf_with_pypdf'
]

in_function = False
function_name = None
function_lines = []

for i, line in enumerate(original_lines):
    # Check if this is a function we should skip
    if line.startswith('def '):
        func_name = line.split('(')[0].replace('def ', '').strip()
        if func_name in skip_functions:
            in_function = True
            function_name = func_name
            continue
    
    # If we're in a skipped function, skip until we hit the next function or route
    if in_function:
        if line.startswith('def ') or line.startswith('@app.route'):
            in_function = False
            function_name = None
        else:
            continue
    
    # Copy everything else after line 50 (skip initial imports/config)
    if i >= 50:
        new_app.append(line)

# Write the new app.py
with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_app)

print("✅ Created app.py successfully!")
print(f"✅ Original file: {len(original_lines)} lines")
print(f"✅ New file: {len(new_app)} lines")
print(f"✅ Skipped functions: {', '.join(skip_functions)}")
