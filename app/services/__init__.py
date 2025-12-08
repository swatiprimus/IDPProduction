"""
Services Package - Modular services for Universal IDP

This package contains all the core processing services:
- textract_service: AWS Textract OCR operations
- account_splitter: Account number detection and splitting
- document_detector: Document type detection
- loan_processor: Loan document processing
"""

from .textract_service import (
    extract_text_with_textract,
    extract_text_with_textract_async,
    try_extract_pdf_with_pypdf
)
from .account_splitter import split_accounts_strict
from .document_detector import detect_document_type, SUPPORTED_DOCUMENT_TYPES
from .loan_processor import process_loan_document

__all__ = [
    'extract_text_with_textract',
    'extract_text_with_textract_async',
    'try_extract_pdf_with_pypdf',
    'split_accounts_strict',
    'detect_document_type',
    'SUPPORTED_DOCUMENT_TYPES',
    'process_loan_document',
]
