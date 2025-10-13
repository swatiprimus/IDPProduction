#!/usr/bin/env python3
"""
enhanced_classifier.py

Advanced document classifier with confidence scoring and multi-model support
"""

import json
import boto3
from typing import Dict, List, Tuple
import re

class EnhancedDocumentClassifier:
    def __init__(self, aws_region='us-east-1'):
        self.bedrock = boto3.client('bedrock-runtime', region_name=aws_region)
        self.confidence_threshold = 0.8
        
        # Document type patterns for rule-based classification
        self.document_patterns = {
            'drivers_license': [
                r'driver.?s?\s+licen[sc]e',
                r'class\s+[a-z]\s+licen[sc]e',
                r'dl\s*#?\s*\d+',
                r'endorsements?:\s*none'
            ],
            'bank_statement': [
                r'account\s+statement',
                r'beginning\s+balance',
                r'ending\s+balance',
                r'deposits?\s+and\s+credits?'
            ],
            'tax_document': [
                r'form\s+1040',
                r'w-?2\s+wage',
                r'adjusted\s+gross\s+income',
                r'tax\s+year\s+\d{4}'
            ],
            'loan_agreement': [
                r'loan\s+agreement',
                r'promissory\s+note',
                r'principal\s+amount',
                r'interest\s+rate'
            ]
        }
    
    def classify_with_confidence(self, text: str) -> Dict:
        """Classify document with confidence scoring"""
        # Rule-based classification first
        rule_based_result = self._rule_based_classify(text)
        
        # AI-based classification
        ai_result = self._ai_classify(text)
        
        # Combine results
        final_classification = self._combine_classifications(rule_based_result, ai_result)
        
        return final_classification
    
    def _rule_based_classify(self, text: str) -> Dict:
        """Rule-based classification using patterns"""
        text_lower = text.lower()
        scores = {}
        
        for doc_type, patterns in self.document_patterns.items():
            score = 0
            matches = []
            
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    score += 1
                    matches.append(pattern)
            
            if score > 0:
                scores[doc_type] = {
                    'confidence': min(score / len(patterns), 1.0),
                    'matches': matches
                }
        
        return {
            'method': 'rule_based',
            'classifications': scores
        }
    
    def _ai_classify(self, text: str) -> Dict:
        """AI-based classification using Claude"""
        prompt = f"""
        Classify this document text and provide confidence scores.
        
        Return JSON with this exact structure:
        {{
            "primary_type": "document_type",
            "confidence": 0.95,
            "secondary_types": [
                {{"type": "other_type", "confidence": 0.3}}
            ],
            "key_indicators": ["list", "of", "key", "phrases"],
            "reasoning": "brief explanation"
        }}
        
        Document text:
        {text[:2000]}
        """
        
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]
            })
            
            response = self.bedrock.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                contentType="application/json",
                accept="application/json",
                body=body
            )
            
            result = json.loads(response["body"].read())
            ai_text = result["content"][0]["text"]
            
            # Parse JSON response
            clean_text = re.sub(r'^```(?:json)?|```$', '', ai_text.strip())
            classification = json.loads(clean_text)
            
            return {
                'method': 'ai_based',
                'classification': classification
            }
            
        except Exception as e:
            return {
                'method': 'ai_based',
                'error': str(e),
                'classification': None
            }
    
    def _combine_classifications(self, rule_result: Dict, ai_result: Dict) -> Dict:
        """Combine rule-based and AI classifications"""
        combined = {
            'final_classification': None,
            'confidence': 0.0,
            'methods_used': ['rule_based', 'ai_based'],
            'rule_based': rule_result,
            'ai_based': ai_result
        }
        
        # If AI classification succeeded and has high confidence
        if (ai_result.get('classification') and 
            ai_result['classification'].get('confidence', 0) > self.confidence_threshold):
            
            combined['final_classification'] = ai_result['classification']['primary_type']
            combined['confidence'] = ai_result['classification']['confidence']
            combined['reasoning'] = 'High confidence AI classification'
        
        # Otherwise, use rule-based if available
        elif rule_result.get('classifications'):
            best_rule = max(rule_result['classifications'].items(), 
                          key=lambda x: x[1]['confidence'])
            
            combined['final_classification'] = best_rule[0]
            combined['confidence'] = best_rule[1]['confidence']
            combined['reasoning'] = 'Rule-based classification'
        
        # Fallback to AI even with lower confidence
        elif ai_result.get('classification'):
            combined['final_classification'] = ai_result['classification']['primary_type']
            combined['confidence'] = ai_result['classification'].get('confidence', 0.5)
            combined['reasoning'] = 'Low confidence AI classification'
        
        return combined