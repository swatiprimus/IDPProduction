#!/usr/bin/env python3
"""
OCR Cache Manager - Prevents duplicate OCR calls for the same document
Tracks which documents have already been OCR'd and caches the results
"""

import json
import boto3
import hashlib
import os
from typing import Optional, Dict, Tuple

class OCRCacheManager:
    """Manages OCR caching to prevent duplicate OCR calls"""
    
    def __init__(self, s3_client, bucket_name: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.cache_prefix = "ocr_status"
    
    def get_ocr_cache_key(self, doc_id: str) -> str:
        """Get the S3 cache key for OCR status"""
        return f"{self.cache_prefix}/{doc_id}/ocr_status.json"
    
    def has_ocr_been_done(self, doc_id: str) -> bool:
        """Check if OCR has already been done for this document"""
        try:
            cache_key = self.get_ocr_cache_key(doc_id)
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=cache_key)
            cache_data = json.loads(response['Body'].read())
            
            if cache_data.get("ocr_completed"):
                print(f"[OCR_CACHE] ✅ OCR already completed for {doc_id}")
                return True
            else:
                print(f"[OCR_CACHE] ⏳ OCR in progress for {doc_id}")
                return False
                
        except self.s3_client.exceptions.NoSuchKey:
            print(f"[OCR_CACHE] ℹ️ No OCR cache found for {doc_id}")
            return False
        except Exception as e:
            print(f"[OCR_CACHE] ⚠️ Error checking OCR cache: {e}")
            return False
    
    def mark_ocr_in_progress(self, doc_id: str) -> bool:
        """Mark OCR as in progress for this document"""
        try:
            cache_key = self.get_ocr_cache_key(doc_id)
            cache_data = {
                "doc_id": doc_id,
                "ocr_completed": False,
                "ocr_in_progress": True,
                "timestamp": str(__import__('datetime').datetime.now().isoformat())
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            
            print(f"[OCR_CACHE] 🔄 Marked OCR as in progress for {doc_id}")
            return True
            
        except Exception as e:
            print(f"[OCR_CACHE] ❌ Error marking OCR in progress: {e}")
            return False
    
    def mark_ocr_completed(self, doc_id: str, ocr_text: str = None, metadata: Dict = None) -> bool:
        """Mark OCR as completed for this document"""
        try:
            cache_key = self.get_ocr_cache_key(doc_id)
            cache_data = {
                "doc_id": doc_id,
                "ocr_completed": True,
                "ocr_in_progress": False,
                "timestamp": str(__import__('datetime').datetime.now().isoformat()),
                "text_length": len(ocr_text) if ocr_text else 0,
                "metadata": metadata or {}
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=cache_key,
                Body=json.dumps(cache_data),
                ContentType='application/json'
            )
            
            print(f"[OCR_CACHE] ✅ Marked OCR as completed for {doc_id}")
            return True
            
        except Exception as e:
            print(f"[OCR_CACHE] ❌ Error marking OCR completed: {e}")
            return False
    
    def get_ocr_status(self, doc_id: str) -> Optional[Dict]:
        """Get the OCR status for a document"""
        try:
            cache_key = self.get_ocr_cache_key(doc_id)
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=cache_key)
            cache_data = json.loads(response['Body'].read())
            return cache_data
            
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            print(f"[OCR_CACHE] ⚠️ Error getting OCR status: {e}")
            return None
    
    def clear_ocr_cache(self, doc_id: str) -> bool:
        """Clear OCR cache for a document"""
        try:
            cache_key = self.get_ocr_cache_key(doc_id)
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=cache_key)
            print(f"[OCR_CACHE] 🗑️ Cleared OCR cache for {doc_id}")
            return True
            
        except Exception as e:
            print(f"[OCR_CACHE] ⚠️ Error clearing OCR cache: {e}")
            return False
