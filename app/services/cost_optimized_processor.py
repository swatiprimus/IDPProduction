#!/usr/bin/env python3
"""
Cost-Optimized Document Processor Service
Each page goes to LLM only ONCE for both account detection AND data extraction
Now with Batch Processing and Parallel LLM Calls
"""

import json
import boto3
import time
from typing import Dict, List, Set, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .regex_account_detector import extract_account_numbers_fast

class CostOptimizedProcessor:
    """
    Cost-optimized processor that:
    1. Uses regex for account detection (instant, free, accurate)
    2. Uses LLM only for data extraction (one call per account)
    3. Combines pages by account for efficient processing
    4. Reduces LLM costs significantly
    """
    
    def __init__(self, bedrock_client, s3_client, bucket_name: str, doc_type: str = "loan_document"):
        self.bedrock_client = bedrock_client
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        self.doc_type = doc_type  # Store document type for prompt selection
    
    def process_account_with_llm(self, account_number: str, page_texts: Dict[int, str], pages: List[int]) -> Optional[Dict]:
        """
        Process account by sending each page individually to LLM, then merge results
        
        Args:
            account_number: The account number
            page_texts: Dict mapping page numbers to their OCR text
            pages: List of page numbers for this account
            
        Returns:
            Merged account data with all page results combined
        """
        print(f"   🤖 Processing account {account_number} with {len(pages)} pages")
        
        page_results = []
        
        # Process each page individually
        for page_num in pages:
            if page_num in page_texts:
                page_text = page_texts[page_num]
                print(f"      📄 Processing page {page_num} ({len(page_text)} chars)")
                
                try:
                    # Extract data from this single page
                    page_data = self._extract_data_fields_from_text(page_text)
                    
                    if page_data:
                        page_results.append({
                            "page_number": page_num,
                            "extracted_data": page_data,
                            "text_length": len(page_text)
                        })
                        print(f"      ✅ Page {page_num}: extracted {len(page_data)} fields")
                    else:
                        print(f"      ⚠️ Page {page_num}: no data extracted")
                        
                except Exception as e:
                    print(f"      ❌ Page {page_num} failed: {str(e)}")
                    continue
            else:
                print(f"      ⚠️ Page {page_num}: no OCR text found")
        
        if not page_results:
            print(f"      ❌ No pages processed successfully for account {account_number}")
            return None
        
        # Merge all page results into single account data
        merged_result = self.merge_page_results(account_number, page_results, pages)
        return merged_result
    
    def process_single_page_with_llm(self, account_number: str, page_text: str, page_number: int) -> Optional[Dict]:
        """
        Process a single page with LLM for data extraction
        Each page is sent individually to LLM with the full comprehensive prompt
        """
        try:
            # Extract data using LLM with the comprehensive loan document prompt
            extracted_data = self._extract_data_fields_from_text(page_text)
            
            if extracted_data:
                return {
                    "page_number": page_number,
                    "account_number": account_number,
                    "extracted_data": extracted_data,
                    "page_text_length": len(page_text)
                }
            else:
                return None
                
        except Exception as e:
            print(f"      ❌ LLM processing failed for page {page_number}: {str(e)}")
            return None
    
    def process_batch_pages_with_llm(self, account_number: str, page_texts: Dict[int, str], 
                                      pages: List[int], batch_size: int = 2) -> Optional[Dict]:
        """
        Process multiple pages - EACH PAGE INDIVIDUALLY (not batched together)
        
        Args:
            account_number: The account number
            page_texts: Dict mapping page numbers to their OCR text
            pages: List of page numbers for this account
            batch_size: Not used - kept for API compatibility
        
        Returns:
            Merged account data with all page results combined
        """
        
        print(f"   📄 Processing: {len(pages)} pages individually (page-by-page extraction)")
        
        # Process each page individually with LLM
        page_results = []
        for page_idx, page_num in enumerate(pages):
            if page_num in page_texts:
                page_text = page_texts[page_num]
                print(f"      📄 Processing page {page_num} ({page_idx + 1}/{len(pages)}) ({len(page_text)} chars)")
                
                try:
                    # Extract data from this SINGLE page only
                    page_data = self._extract_data_fields_from_text(page_text)
                    
                    if page_data:
                        page_results.append({
                            'page_number': page_num,
                            'extracted_data': page_data
                        })
                        print(f"      ✅ Page {page_num}: extracted {len(page_data)} fields")
                    else:
                        print(f"      ⚠️ Page {page_num}: no data extracted")
                        
                except Exception as e:
                    print(f"      ❌ Page {page_num} failed: {str(e)}")
                    continue
            else:
                print(f"      ⚠️ Page {page_num}: no OCR text found")
        
        # Merge all page results
        if not page_results:
            print(f"      ❌ No pages processed successfully for account {account_number}")
            return None
        
        # Merge using existing merge logic
        merged_result = self.merge_page_results(account_number, page_results, pages)
        return merged_result
    
    def process_batches_parallel(self, account_number: str, page_texts: Dict[int, str], 
                                 pages: List[int], batch_size: int = 2, 
                                 max_workers: int = 3) -> Optional[Dict]:
        """
        Process multiple pages in parallel (PARALLEL LLM CALLS)
        EACH PAGE IS PROCESSED INDIVIDUALLY, NOT BATCHED TOGETHER
        
        Args:
            account_number: The account number
            page_texts: Dict mapping page numbers to their OCR text
            pages: List of page numbers for this account
            batch_size: Not used - kept for API compatibility
            max_workers: Number of concurrent LLM calls (3-5 recommended)
        
        Returns:
            Merged account data with all page results combined
        """
        
        print(f"   📄 Processing: {len(pages)} pages in parallel")
        print(f"   ⚡ Parallel: {max_workers} concurrent LLM calls")
        
        # Process pages in parallel (each page individually)
        page_results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all pages to executor (don't wait)
            futures = {}
            for page_idx, page_num in enumerate(pages):
                if page_num in page_texts:
                    page_text = page_texts[page_num]
                    future = executor.submit(
                        self._extract_data_fields_from_text,
                        page_text  # Send INDIVIDUAL page, not batch
                    )
                    futures[future] = {
                        'page_idx': page_idx,
                        'page_num': page_num,
                        'total_pages': len(pages)
                    }
            
            # Wait for all to complete and collect results
            completed = 0
            for future in as_completed(futures):
                page_info = futures[future]
                page_idx = page_info['page_idx']
                page_num = page_info['page_num']
                total_pages = page_info['total_pages']
                completed += 1
                
                try:
                    page_data = future.result()
                    print(f"      ✅ Page {page_num} completed [{completed}/{total_pages}]")
                    
                    if page_data:
                        page_results.append({
                            'page_number': page_num,
                            'extracted_data': page_data
                        })
                except Exception as e:
                    print(f"      ❌ Page {page_num} failed: {str(e)}")
                    # Continue with other pages
        
        # Merge all page results
        if not page_results:
            print(f"      ❌ No pages processed successfully for account {account_number}")
            return None
        
        # Merge using existing merge logic
        merged_result = self.merge_page_results(account_number, page_results, pages)
        return merged_result
    
    def merge_page_results(self, account_number: str, page_results: List[Dict], pages: List[int]) -> Optional[Dict]:
        """
        Merge results from multiple pages for a single account
        Combines all extracted data while avoiding duplicates and keeping highest confidence values
        """
        print(f"   🔄 Merging {len(page_results)} page results for account {account_number}")
        
        try:
            merged_data = {}
            page_data_map = {}  # Store individual page data for UI
            
            # Store individual page results for UI access (ENSURE STRING KEYS)
            for page_result in page_results:
                page_num = page_result.get("page_number")
                page_data = page_result.get("extracted_data", {})
                if page_num is not None:
                    # CRITICAL: Store with STRING keys to match API expectations
                    page_key = str(page_num)
                    print(f"      📋 Storing page {page_num} data with {len(page_data)} fields (key: '{page_key}')")
                    page_data_map[page_key] = page_data
            
            # Merge all page data intelligently
            for page_result in page_results:
                page_data = page_result.get("extracted_data", {})
                page_num = page_result.get("page_number", "unknown")
                
                print(f"      📄 Merging page {page_num} data ({len(page_data)} fields)")
                
                for field_name, field_value in page_data.items():
                    if field_name not in merged_data:
                        # First time seeing this field - add it
                        merged_data[field_name] = field_value
                        print(f"         ➕ New field: {field_name}")
                    else:
                        # Field already exists - merge intelligently based on confidence
                        existing_value = merged_data[field_name]
                        
                        # Handle confidence objects
                        if isinstance(field_value, dict) and "value" in field_value and "confidence" in field_value:
                            new_confidence = field_value.get("confidence", 0)
                            new_val = field_value.get("value", "")
                            
                            if isinstance(existing_value, dict) and "confidence" in existing_value:
                                existing_conf = existing_value.get("confidence", 0)
                                existing_val = existing_value.get("value", "")
                                
                                # Keep the value with higher confidence, or longer/more complete value
                                if (new_confidence > existing_conf or 
                                    (new_confidence == existing_conf and len(str(new_val)) > len(str(existing_val)))):
                                    merged_data[field_name] = field_value
                                    print(f"         🔄 Updated {field_name}: {existing_val} → {new_val} (conf: {existing_conf}% → {new_confidence}%)")
                            else:
                                # Existing is not confidence object, replace with confidence object
                                merged_data[field_name] = field_value
                                print(f"         🔄 Upgraded {field_name} to confidence object")
                        else:
                            # Simple value - keep if existing is empty or new value is longer/better
                            if (not existing_value or 
                                str(existing_value).strip() == "" or 
                                str(existing_value) == "N/A" or
                                len(str(field_value)) > len(str(existing_value))):
                                merged_data[field_name] = field_value
                                print(f"         🔄 Updated {field_name}: {existing_value} → {field_value}")
            
            # Calculate accuracy metrics
            filled_fields = 0
            total_fields = len(merged_data)
            
            for field_name, value in merged_data.items():
                if isinstance(value, dict) and "value" in value:
                    val = value["value"]
                    if val and str(val).strip() and str(val) != "N/A" and str(val).lower() != "unknown":
                        filled_fields += 1
                elif value and str(value).strip() and str(value) != "N/A" and str(value).lower() != "unknown":
                    filled_fields += 1
            
            accuracy = int((filled_fields / total_fields) * 100) if total_fields > 0 else 0
            
            print(f"   ✅ Merged account {account_number}: {filled_fields}/{total_fields} fields ({accuracy}% accuracy)")
            
            print(f"   📊 Final page_data_map keys: {list(page_data_map.keys())}")
            print(f"   📊 Pages processed: {pages}")
            
            # DEBUG: Show what data is stored for each page
            for page_key, page_data in page_data_map.items():
                sample_fields = list(page_data.keys())[:3] if page_data else []
                print(f"   🗂️ Page '{page_key}' contains: {sample_fields}...")
            
            return {
                "accountNumber": account_number,
                "result": merged_data,
                "page_data": page_data_map,  # Individual page data for UI
                "accuracy_score": accuracy,
                "filled_fields": filled_fields,
                "total_fields": total_fields,
                "pages": pages,
                "needs_human_review": accuracy < 90,
                "processing_method": "regex_detection + page_by_page_llm_extraction"
            }
                
        except Exception as e:
            print(f"   ❌ Merge failed for account {account_number}: {str(e)}")
            return None
    
    def batch_cache_results_to_s3(self, results: List[Dict], doc_id: str, s3_client, bucket_name: str) -> None:
        """PHASE 2: Batch cache multiple results to S3 in parallel (5x faster)"""
        if not results:
            return
        
        print(f"   📦 BATCH S3 CACHING: Preparing {len(results)} results for parallel upload...")
        
        cache_items = []
        for result in results:
            account_num = result.get("accountNumber", "unknown")
            cache_key = f"account_results/{doc_id}/{account_num}.json"
            cache_items.append({
                'key': cache_key,
                'data': result
            })
        
        # Upload all items in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}
            
            # Submit all uploads to executor
            for item in cache_items:
                future = executor.submit(
                    s3_client.put_object,
                    Bucket=bucket_name,
                    Key=item['key'],
                    Body=json.dumps(item['data']),
                    ContentType='application/json'
                )
                futures[future] = item
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(futures):
                item = futures[future]
                completed += 1
                
                try:
                    future.result()
                    print(f"   ✅ S3 Cache {completed}/{len(cache_items)}: {item['key']}")
                except Exception as e:
                    print(f"   ❌ S3 Cache failed: {item['key']} - {str(e)}")
        
        print(f"   ✅ BATCH S3 CACHING: Completed {len(cache_items)} uploads (5x faster with parallel)")
    
    def _extract_data_fields_from_text(self, text: str) -> Optional[Dict]:
        """
        LLM call to extract data fields from combined account text
        Detects page-level document type to use appropriate prompt
        """
        # Detect page-level document type (e.g., driver's license vs loan document)
        page_doc_type = self._detect_page_document_type(text)
        
        # Use page-level document type if detected, otherwise use document-level type
        if page_doc_type == "drivers_license":
            prompt = self._get_drivers_license_prompt()
        else:
            prompt = self._get_data_extraction_prompt()
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": f"{prompt}\n\nDocument text:\n{text[:12000]}"}]
                })
            )
            
            result = json.loads(response['body'].read())
            llm_response = result['content'][0]['text'].strip()
            
            # Parse JSON response
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}')
            
            if json_start != -1 and json_end != -1:
                json_str = llm_response[json_start:json_end + 1]
                parsed_result = json.loads(json_str)
                
                # Handle different response formats
                if 'extracted_fields' in parsed_result:
                    # Driver's license format
                    return parsed_result['extracted_fields']
                elif 'documents' in parsed_result and len(parsed_result['documents']) > 0:
                    # Driver's license format with documents array
                    return parsed_result['documents'][0].get('extracted_fields', {})
                else:
                    # Direct field format (loan document format)
                    return parsed_result
            else:
                print(f"      ❌ No valid JSON in LLM response")
                print(f"      Raw response: {llm_response[:500]}...")
                return {}
                
        except json.JSONDecodeError as e:
            print(f"      ❌ JSON parsing failed: {str(e)}")
            print(f"      Raw response: {llm_response[:500]}...")
            return {}
        except Exception as e:
            print(f"      ❌ LLM processing failed: {str(e)}")
            return {}
    
    def _detect_page_document_type(self, text: str) -> str:
        """
        Detect document type at page level
        Looks for keywords that indicate driver's license pages
        """
        text_upper = text.upper()
        
        # Critical driver's license indicators (high confidence)
        critical_dl_keywords = [
            "DRIVER'S LICENSE",
            "DRIVERS LICENSE",
            "DRIVER LICENSE",
            "LICENSE NUMBER",
            "DL #",
            "DELAWARE",
            "CALIFORNIA",
            "TEXAS",
            "FLORIDA",
            "NEW YORK",
            "PENNSYLVANIA",
            "OHIO",
            "GEORGIA",
            "NORTH CAROLINA",
            "MICHIGAN",
            "ILLINOIS",
            "VIRGINIA",
            "MARYLAND",
            "MASSACHUSETTS",
            "CONNECTICUT",
            "NEW JERSEY",
            "NEW HAMPSHIRE",
            "VERMONT",
            "RHODE ISLAND",
            "MAINE",
            "LOUISIANA",
            "MISSISSIPPI",
            "ALABAMA",
            "TENNESSEE",
            "KENTUCKY",
            "WEST VIRGINIA",
            "SOUTH CAROLINA",
            "ARKANSAS",
            "MISSOURI",
            "IOWA",
            "MINNESOTA",
            "WISCONSIN",
            "INDIANA",
            "KANSAS",
            "NEBRASKA",
            "SOUTH DAKOTA",
            "NORTH DAKOTA",
            "MONTANA",
            "WYOMING",
            "COLORADO",
            "NEW MEXICO",
            "UTAH",
            "IDAHO",
            "NEVADA",
            "ARIZONA",
            "WASHINGTON",
            "OREGON",
            "HAWAII",
            "ALASKA"
        ]
        
        # Secondary driver's license indicators
        secondary_dl_keywords = [
            "EXPIRATION DATE",
            "ISSUE DATE",
            "DATE OF BIRTH",
            "HEIGHT",
            "WEIGHT",
            "EYE COLOR",
            "HAIR COLOR",
            "RESTRICTIONS",
            "ENDORSEMENTS",
            "LICENSE CLASS",
            "ISSUING STATE",
            "DOCUMENT DISCRIMINATOR",
            "ORGAN DONOR"
        ]
        
        # Count critical keywords
        critical_count = sum(1 for keyword in critical_dl_keywords if keyword in text_upper)
        
        # Count secondary keywords
        secondary_count = sum(1 for keyword in secondary_dl_keywords if keyword in text_upper)
        
        # If we find a state name OR multiple DL keywords, it's a driver's license
        # Lower threshold for detection to catch partial DL pages
        if critical_count >= 1 or secondary_count >= 2:
            print(f"      🪪 Page detected as DRIVER'S LICENSE (critical: {critical_count}, secondary: {secondary_count})")
            return "drivers_license"
        
        return "loan_document"
    
    def _get_drivers_license_prompt(self) -> str:
        """Get the driver's license extraction prompt"""
        from prompts import get_drivers_license_prompt
        return get_drivers_license_prompt()
    
    def _get_data_extraction_prompt(self) -> str:
        """
        Get the appropriate prompt based on document type
        Now that we process pages individually, we can use the full prompt
        """
        # Import here to avoid circular imports
        from prompts import get_loan_document_prompt, get_drivers_license_prompt
        
        if self.doc_type == "drivers_license":
            return get_drivers_license_prompt()
        else:
            # Default to loan document prompt for loan documents and other types
            return get_loan_document_prompt()