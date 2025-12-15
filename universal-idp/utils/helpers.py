"""Utility functions for the Universal IDP application."""

import json
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

def flatten_nested_objects(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested objects like Signer1: {Name: "John"} to Signer1_Name: "John"
    Also handles SupportingDocuments and other nested structures
    """
    if not isinstance(data, dict):
        return data
    
    flattened = {}
    
    for key, value in data.items():
        # Check if this is a signer object (Signer1, Signer2, etc.)
        # Match: Signer1, Signer2, Signer_1, Signer_2, etc.
        if (key.startswith("Signer") and isinstance(value, dict) and 
            any(char.isdigit() for char in key)):
            # Flatten the signer object
            logger.debug(f"Flattening signer object: {key} with {len(value)} fields")
            for sub_key, sub_value in value.items():
                flat_key = f"{key}_{sub_key}"
                flattened[flat_key] = sub_value
                logger.debug(f"Created flat field: {flat_key} = {sub_value}")
        # Keep arrays and other structures as-is
        elif isinstance(value, (list, str, int, float, bool)) or value is None:
            flattened[key] = value
        # Recursively flatten other nested dicts (but not arrays of dicts)
        elif isinstance(value, dict):
            # Check if it's a special structure like SupportingDocuments
            if key in ["SupportingDocuments", "AccountHolderNames"]:
                flattened[key] = value
            else:
                # Flatten other nested objects
                for sub_key, sub_value in value.items():
                    flattened[f"{key}_{sub_key}"] = sub_value
        else:
            flattened[key] = value
    
    logger.debug(f"Flattening complete: {len(data)} input fields -> {len(flattened)} output fields")
    return flattened

def save_documents_db(documents: List[Dict[str, Any]]) -> bool:
    """Save processed documents to file."""
    try:
        with open('processed_documents.json', 'w', encoding='utf-8') as f:
            json.dump(documents, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(documents)} documents to database")
        return True
    except Exception as e:
        logger.error(f"Failed to save documents database: {str(e)}")
        return False

def load_documents_db() -> List[Dict[str, Any]]:
    """Load processed documents from file."""
    try:
        if os.path.exists('processed_documents.json'):
            with open('processed_documents.json', 'r', encoding='utf-8') as f:
                documents = json.load(f)
            logger.info(f"Loaded {len(documents)} documents from database")
            return documents
        return []
    except Exception as e:
        logger.error(f"Failed to load documents database: {str(e)}")
        return []

def calculate_accuracy_score(extracted_fields: Dict[str, Any]) -> float:
    """Calculate accuracy score based on filled vs total fields."""
    if not extracted_fields:
        return 0.0
    
    total_fields = len(extracted_fields)
    filled_fields = sum(1 for v in extracted_fields.values() 
                       if v and v != "N/A" and v != "")
    
    return round((filled_fields / total_fields) * 100, 1) if total_fields > 0 else 0.0

def identify_fields_needing_review(extracted_fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Identify fields that need human review."""
    fields_needing_review = []
    
    for field_name, value in extracted_fields.items():
        if not value or value == "N/A" or value == "" or (isinstance(value, list) and len(value) == 0):
            fields_needing_review.append({
                "field_name": field_name,
                "reason": "Missing or not found in document",
                "current_value": value if value else "Not extracted"
            })
    
    return fields_needing_review

def format_document_summary(doc: Dict[str, Any]) -> str:
    """Format a document summary for display."""
    summary_parts = []
    
    # Basic info
    summary_parts.append(f"Document: {doc.get('document_name', 'Unknown')}")
    summary_parts.append(f"Type: {doc.get('document_type_info', {}).get('name', 'Unknown')}")
    summary_parts.append(f"Processed: {doc.get('processed_date', 'Unknown')}")
    
    # Document-specific info
    documents = doc.get("documents", [])
    if documents:
        first_doc = documents[0]
        accuracy = first_doc.get("accuracy_score")
        if accuracy is not None:
            summary_parts.append(f"Accuracy: {accuracy}%")
        
        total_fields = first_doc.get("total_fields", 0)
        filled_fields = first_doc.get("filled_fields", 0)
        if total_fields > 0:
            summary_parts.append(f"Fields: {filled_fields}/{total_fields}")
    
    return " | ".join(summary_parts)

def validate_json_response(response_text: str) -> Optional[Dict[str, Any]]:
    """Validate and extract JSON from AI response."""
    try:
        # Find JSON content - look for the first { and last }
        json_start = response_text.find('{')
        json_end = response_text.rfind('}')
        
        if json_start == -1 or json_end == -1:
            logger.error("No JSON object found in response")
            return None
        
        json_str = response_text[json_start:json_end + 1]
        result = json.loads(json_str)
        
        # Ensure documents array exists
        if "documents" not in result:
            result = {"documents": [result]}
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {str(e)}")
        logger.error(f"Response text: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Failed to validate JSON response: {str(e)}")
        return None

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations."""
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Ensure filename is not empty
    if not filename:
        filename = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return filename

def get_file_extension(filename: str) -> str:
    """Get file extension in lowercase."""
    return filename.lower().split('.')[-1] if '.' in filename else ''

def is_supported_file_type(filename: str) -> bool:
    """Check if file type is supported for OCR."""
    supported_extensions = ['pdf', 'png', 'jpg', 'jpeg', 'txt']
    return get_file_extension(filename) in supported_extensions

