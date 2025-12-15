"""Data models for the Universal IDP application."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class DocumentField:
    """Represents a single extracted field from a document."""
    name: str
    value: Any
    confidence: Optional[float] = None
    needs_review: bool = False


@dataclass
class ExtractedDocument:
    """Represents a processed document with extracted fields."""
    document_id: str
    document_type: str
    document_type_display: str
    document_icon: str
    document_description: str
    extracted_fields: Dict[str, Any]
    accuracy_score: Optional[float] = None
    total_fields: int = 0
    filled_fields: int = 0
    needs_human_review: bool = False
    fields_needing_review: List[Dict[str, Any]] = None
    accounts: List[Dict[str, Any]] = None  # For loan documents
    
    def __post_init__(self):
        if self.fields_needing_review is None:
            self.fields_needing_review = []


@dataclass
class ProcessingJob:
    """Represents a document processing job."""
    job_id: str
    filename: str
    document_name: str
    status: str
    progress: int
    timestamp: str
    use_ocr: bool
    ocr_method: Optional[str] = None
    ocr_file: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_details: Optional[str] = None


@dataclass
class DocumentRecord:
    """Represents a complete processed document record."""
    id: str
    filename: str
    document_name: str
    timestamp: str
    processed_date: str
    ocr_file: str
    ocr_method: str
    basic_fields: Dict[str, Any]
    documents: List[ExtractedDocument]
    document_type_info: Dict[str, Any]
    use_ocr: bool
    pdf_path: Optional[str] = None