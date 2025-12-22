#!/usr/bin/env python3
"""
Cost Tracking System for Document Processing

Tracks costs for:
- AWS Textract (OCR)
- AWS Bedrock (LLM)
- AWS S3 (Storage)
- Total processing cost per document
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

# AWS Pricing (as of 2025)
# Prices in USD per unit
PRICING = {
    "textract": {
        "detect_document_text": 0.0015,  # Per page (sync API)
        "start_document_text_detection": 0.0001,  # Per page (async API)
        "unit": "page"
    },
    "bedrock": {
        "claude_3_5_sonnet": {
            "input": 0.003,  # Per 1K input tokens
            "output": 0.015,  # Per 1K output tokens
            "unit": "1K tokens"
        }
    },
    "s3": {
        "put_object": 0.000005,  # Per request
        "get_object": 0.0000004,  # Per request
        "storage": 0.023,  # Per GB per month (daily rate: 0.023/30)
        "unit": "request/GB"
    }
}

class CostTracker:
    """Track costs for document processing operations"""
    
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.costs = {
            "textract": {
                "sync_pages": 0,
                "async_pages": 0,
                "cost": 0.0
            },
            "bedrock": {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0
            },
            "s3": {
                "put_requests": 0,
                "get_requests": 0,
                "storage_gb": 0,
                "cost": 0.0
            },
            "total": 0.0,
            "timestamp": datetime.now().isoformat(),
            "breakdown": {}
        }
    
    def track_textract_sync(self, pages: int = 1):
        """Track Textract sync API call (detect_document_text)"""
        self.costs["textract"]["sync_pages"] += pages
        cost = pages * PRICING["textract"]["detect_document_text"]
        self.costs["textract"]["cost"] += cost
        self.costs["total"] += cost
        
        print(f"[COST] Textract Sync: {pages} pages × ${PRICING['textract']['detect_document_text']:.6f} = ${cost:.6f}")
        return cost
    
    def track_textract_async(self, pages: int = 1):
        """Track Textract async API call (start_document_text_detection)"""
        self.costs["textract"]["async_pages"] += pages
        cost = pages * PRICING["textract"]["start_document_text_detection"]
        self.costs["textract"]["cost"] += cost
        self.costs["total"] += cost
        
        print(f"[COST] Textract Async: {pages} pages × ${PRICING['textract']['start_document_text_detection']:.6f} = ${cost:.6f}")
        return cost
    
    def track_bedrock_call(self, input_tokens: int, output_tokens: int, model: str = "claude_3_5_sonnet"):
        """Track Bedrock LLM API call"""
        self.costs["bedrock"]["calls"] += 1
        self.costs["bedrock"]["input_tokens"] += input_tokens
        self.costs["bedrock"]["output_tokens"] += output_tokens
        
        # Calculate cost (pricing is per 1K tokens)
        input_cost = (input_tokens / 1000) * PRICING["bedrock"][model]["input"]
        output_cost = (output_tokens / 1000) * PRICING["bedrock"][model]["output"]
        total_cost = input_cost + output_cost
        
        self.costs["bedrock"]["cost"] += total_cost
        self.costs["total"] += total_cost
        
        print(f"[COST] Bedrock: {input_tokens} input + {output_tokens} output tokens = ${total_cost:.6f}")
        return total_cost
    
    def track_s3_put(self, count: int = 1, size_bytes: int = 0):
        """Track S3 PUT requests"""
        self.costs["s3"]["put_requests"] += count
        request_cost = count * PRICING["s3"]["put_object"]
        
        # Add storage cost (rough estimate: 1 day of storage)
        # Note: For small files, storage cost is negligible but we track it anyway
        storage_cost = 0.0
        if size_bytes > 0:
            size_gb = size_bytes / (1024 ** 3)
            storage_cost = (size_gb / 30) * PRICING["s3"]["storage"]  # Daily rate
            self.costs["s3"]["storage_gb"] += size_gb
        
        total_cost = request_cost + storage_cost
        self.costs["s3"]["cost"] += total_cost
        self.costs["total"] += total_cost
        
        print(f"[COST] S3 PUT: {count} requests × ${PRICING['s3']['put_object']:.8f} + storage ${storage_cost:.8f} = ${total_cost:.8f}")
        return total_cost
    
    def track_s3_get(self, count: int = 1):
        """Track S3 GET requests"""
        self.costs["s3"]["get_requests"] += count
        cost = count * PRICING["s3"]["get_object"]
        self.costs["s3"]["cost"] += cost
        self.costs["total"] += cost
        
        print(f"[COST] S3 GET: {count} requests × ${PRICING['s3']['get_object']:.8f} = ${cost:.6f}")
        return cost
    
    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary for this document"""
        return {
            "document_id": self.doc_id,
            "textract": {
                "sync_pages": self.costs["textract"]["sync_pages"],
                "async_pages": self.costs["textract"]["async_pages"],
                "total_pages": self.costs["textract"]["sync_pages"] + self.costs["textract"]["async_pages"],
                "cost": round(self.costs["textract"]["cost"], 6)
            },
            "bedrock": {
                "calls": self.costs["bedrock"]["calls"],
                "input_tokens": self.costs["bedrock"]["input_tokens"],
                "output_tokens": self.costs["bedrock"]["output_tokens"],
                "total_tokens": self.costs["bedrock"]["input_tokens"] + self.costs["bedrock"]["output_tokens"],
                "cost": round(self.costs["bedrock"]["cost"], 6)
            },
            "s3": {
                "put_requests": self.costs["s3"]["put_requests"],
                "get_requests": self.costs["s3"]["get_requests"],
                "total_requests": self.costs["s3"]["put_requests"] + self.costs["s3"]["get_requests"],
                "storage_gb": round(self.costs["s3"]["storage_gb"], 6),
                "cost": round(self.costs["s3"]["cost"], 6)
            },
            "total_cost": round(self.costs["total"], 6),
            "timestamp": self.costs["timestamp"],
            "breakdown": {
                "textract_percentage": round((self.costs["textract"]["cost"] / max(self.costs["total"], 0.000001)) * 100, 2),
                "bedrock_percentage": round((self.costs["bedrock"]["cost"] / max(self.costs["total"], 0.000001)) * 100, 2),
                "s3_percentage": round((self.costs["s3"]["cost"] / max(self.costs["total"], 0.000001)) * 100, 2)
            }
        }
    
    def get_formatted_summary(self) -> str:
        """Get formatted cost summary for logging"""
        summary = self.get_summary()
        
        output = f"""
╔════════════════════════════════════════════════════════════════╗
║                    DOCUMENT PROCESSING COST                    ║
╠════════════════════════════════════════════════════════════════╣
║ Document ID: {summary['document_id']:<50} ║
╠════════════════════════════════════════════════════════════════╣
║ TEXTRACT (OCR):                                                ║
║   • Sync Pages: {summary['textract']['sync_pages']:<45} ║
║   • Async Pages: {summary['textract']['async_pages']:<44} ║
║   • Total Pages: {summary['textract']['total_pages']:<44} ║
║   • Cost: ${summary['textract']['cost']:<51.6f} ║
╠════════════════════════════════════════════════════════════════╣
║ BEDROCK (LLM):                                                 ║
║   • API Calls: {summary['bedrock']['calls']:<46} ║
║   • Input Tokens: {summary['bedrock']['input_tokens']:<42} ║
║   • Output Tokens: {summary['bedrock']['output_tokens']:<41} ║
║   • Total Tokens: {summary['bedrock']['total_tokens']:<42} ║
║   • Cost: ${summary['bedrock']['cost']:<51.6f} ║
╠════════════════════════════════════════════════════════════════╣
║ S3 (STORAGE):                                                  ║
║   • PUT Requests: {summary['s3']['put_requests']:<42} ║
║   • GET Requests: {summary['s3']['get_requests']:<42} ║
║   • Total Requests: {summary['s3']['total_requests']:<40} ║
║   • Storage (GB): {summary['s3']['storage_gb']:<42.6f} ║
║   • Cost: ${summary['s3']['cost']:<51.6f} ║
╠════════════════════════════════════════════════════════════════╣
║ COST BREAKDOWN:                                                ║
║   • Textract: {summary['breakdown']['textract_percentage']:.2f}%                                      ║
║   • Bedrock: {summary['breakdown']['bedrock_percentage']:.2f}%                                       ║
║   • S3: {summary['breakdown']['s3_percentage']:.2f}%                                          ║
╠════════════════════════════════════════════════════════════════╣
║ TOTAL COST: ${summary['total_cost']:<50.6f} ║
╚════════════════════════════════════════════════════════════════╝
"""
        return output


class CostTrackerManager:
    """Manage cost trackers for multiple documents"""
    
    def __init__(self):
        self.trackers: Dict[str, CostTracker] = {}
    
    def get_tracker(self, doc_id: str) -> CostTracker:
        """Get or create tracker for document"""
        if doc_id not in self.trackers:
            self.trackers[doc_id] = CostTracker(doc_id)
        return self.trackers[doc_id]
    
    def get_all_costs(self) -> Dict[str, Dict]:
        """Get costs for all documents"""
        return {
            doc_id: tracker.get_summary()
            for doc_id, tracker in self.trackers.items()
        }
    
    def get_total_costs(self) -> Dict[str, Any]:
        """Get total costs across all documents"""
        total = {
            "total_cost": 0.0,
            "textract_cost": 0.0,
            "bedrock_cost": 0.0,
            "s3_cost": 0.0,
            "documents_processed": len(self.trackers),
            "details": {}
        }
        
        for doc_id, tracker in self.trackers.items():
            summary = tracker.get_summary()
            total["total_cost"] += summary["total_cost"]
            total["textract_cost"] += summary["textract"]["cost"]
            total["bedrock_cost"] += summary["bedrock"]["cost"]
            total["s3_cost"] += summary["s3"]["cost"]
            total["details"][doc_id] = summary
        
        return total


# Global cost tracker manager
cost_tracker_manager = CostTrackerManager()


def get_cost_tracker(doc_id: str) -> CostTracker:
    """Get cost tracker for a document"""
    return cost_tracker_manager.get_tracker(doc_id)


def get_all_costs() -> Dict[str, Dict]:
    """Get costs for all documents"""
    return cost_tracker_manager.get_all_costs()


def get_total_costs() -> Dict[str, Any]:
    """Get total costs across all documents"""
    return cost_tracker_manager.get_total_costs()
