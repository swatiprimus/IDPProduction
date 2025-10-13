#!/usr/bin/env python3
"""
quality_assessor.py

Assess document quality and completeness for IDP processing
"""

import json
import boto3
from typing import Dict, List
import re
from datetime import datetime

class DocumentQualityAssessor:
    def __init__(self, aws_region='us-east-1'):
        self.bedrock = boto3.client('bedrock-runtime', region_name=aws_region)
        
        # Quality criteria for different document types
        self.quality_criteria = {
            'drivers_license': {
                'required_fields': ['name', 'license_number', 'date_of_birth', 'address', 'state'],
                'optional_fields': ['expiration_date', 'class', 'restrictions'],
                'quality_indicators': ['clear_text', 'readable_photo', 'valid_format']
            },
            'bank_statement': {
                'required_fields': ['account_number', 'statement_period', 'beginning_balance', 'ending_balance'],
                'optional_fields': ['transactions', 'bank_name', 'customer_name'],
                'quality_indicators': ['complete_transactions', 'clear_amounts', 'valid_dates']
            },
            'loan_agreement': {
                'required_fields': ['borrower_name', 'loan_amount', 'interest_rate', 'term'],
                'optional_fields': ['collateral', 'guarantor', 'payment_schedule'],
                'quality_indicators': ['complete_terms', 'signatures_present', 'legal_format']
            }
        }
    
    def assess_quality(self, document_text: str, document_type: str = None) -> Dict:
        """Assess document quality and completeness"""
        
        # Auto-detect document type if not provided
        if not document_type:
            document_type = self._detect_document_type(document_text)
        
        # Get quality criteria for this document type
        criteria = self.quality_criteria.get(document_type, {})
        
        # Assess different quality aspects
        quality_assessment = {
            'document_type': document_type,
            'overall_score': 0.0,
            'completeness_score': 0.0,
            'readability_score': 0.0,
            'accuracy_score': 0.0,
            'missing_fields': [],
            'quality_issues': [],
            'recommendations': [],
            'assessment_details': {}
        }
        
        # Assess completeness
        completeness = self._assess_completeness(document_text, criteria)
        quality_assessment.update(completeness)
        
        # Assess readability
        readability = self._assess_readability(document_text)
        quality_assessment['readability_score'] = readability['score']
        quality_assessment['quality_issues'].extend(readability['issues'])
        
        # Assess accuracy using AI
        accuracy = self._assess_accuracy_with_ai(document_text, document_type)
        quality_assessment['accuracy_score'] = accuracy['score']
        quality_assessment['quality_issues'].extend(accuracy['issues'])
        
        # Calculate overall score
        quality_assessment['overall_score'] = (
            quality_assessment['completeness_score'] * 0.4 +
            quality_assessment['readability_score'] * 0.3 +
            quality_assessment['accuracy_score'] * 0.3
        )
        
        # Generate recommendations
        quality_assessment['recommendations'] = self._generate_recommendations(quality_assessment)
        
        return quality_assessment
    
    def _detect_document_type(self, text: str) -> str:
        """Simple document type detection"""
        text_lower = text.lower()
        
        if any(term in text_lower for term in ['driver', 'license', 'dl']):
            return 'drivers_license'
        elif any(term in text_lower for term in ['statement', 'account', 'balance']):
            return 'bank_statement'
        elif any(term in text_lower for term in ['loan', 'agreement', 'promissory']):
            return 'loan_agreement'
        else:
            return 'unknown'
    
    def _assess_completeness(self, text: str, criteria: Dict) -> Dict:
        """Assess document completeness based on required fields"""
        required_fields = criteria.get('required_fields', [])
        optional_fields = criteria.get('optional_fields', [])
        
        found_required = []
        found_optional = []
        missing_required = []
        
        text_lower = text.lower()
        
        # Check for required fields
        for field in required_fields:
            field_patterns = self._get_field_patterns(field)
            if any(re.search(pattern, text_lower) for pattern in field_patterns):
                found_required.append(field)
            else:
                missing_required.append(field)
        
        # Check for optional fields
        for field in optional_fields:
            field_patterns = self._get_field_patterns(field)
            if any(re.search(pattern, text_lower) for pattern in field_patterns):
                found_optional.append(field)
        
        completeness_score = len(found_required) / len(required_fields) if required_fields else 1.0
        
        return {
            'completeness_score': completeness_score,
            'found_required_fields': found_required,
            'found_optional_fields': found_optional,
            'missing_fields': missing_required
        }
    
    def _get_field_patterns(self, field: str) -> List[str]:
        """Get regex patterns for field detection"""
        patterns = {
            'name': [r'name\s*:?\s*[a-z\s]+', r'[a-z]+\s+[a-z]+'],
            'license_number': [r'licen[sc]e\s*#?\s*\d+', r'dl\s*#?\s*\d+'],
            'date_of_birth': [r'dob\s*:?\s*\d+', r'birth\s*:?\s*\d+'],
            'address': [r'address\s*:?\s*\d+', r'\d+\s+[a-z\s]+street'],
            'account_number': [r'account\s*#?\s*\d+', r'acct\s*#?\s*\d+'],
            'loan_amount': [r'amount\s*:?\s*\$?\d+', r'principal\s*:?\s*\$?\d+'],
            'interest_rate': [r'rate\s*:?\s*\d+\.?\d*%?', r'apr\s*:?\s*\d+']
        }
        
        return patterns.get(field, [field.replace('_', r'\s*')])
    
    def _assess_readability(self, text: str) -> Dict:
        """Assess text readability and OCR quality"""
        issues = []
        score = 1.0
        
        # Check for common OCR issues
        if len(re.findall(r'[^\w\s\.\,\!\?\-\(\)]', text)) > len(text) * 0.1:
            issues.append("High number of special characters - possible OCR errors")
            score -= 0.2
        
        # Check for fragmented words
        fragmented_words = len(re.findall(r'\b[a-z]{1,2}\b', text.lower()))
        if fragmented_words > 20:
            issues.append("Many short fragments - possible text fragmentation")
            score -= 0.3
        
        # Check for missing spaces
        if len(re.findall(r'[a-z][A-Z]', text)) > 10:
            issues.append("Missing spaces between words")
            score -= 0.2
        
        # Check text length
        if len(text.strip()) < 100:
            issues.append("Very short text - incomplete extraction")
            score -= 0.3
        
        return {
            'score': max(score, 0.0),
            'issues': issues
        }
    
    def _assess_accuracy_with_ai(self, text: str, document_type: str) -> Dict:
        """Use AI to assess document accuracy and consistency"""
        prompt = f"""
        Assess the accuracy and consistency of this {document_type} document.
        
        Check for:
        1. Internal consistency (dates, names, numbers match)
        2. Format validity (proper document structure)
        3. Data validity (realistic values, proper formats)
        4. Completeness of key information
        
        Return JSON:
        {{
            "accuracy_score": 0.85,
            "issues": ["list of specific issues found"],
            "inconsistencies": ["list of inconsistencies"],
            "validation_results": {{
                "dates_valid": true,
                "numbers_consistent": true,
                "format_correct": true
            }}
        }}
        
        Document text:
        {text[:1500]}
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
            accuracy_result = json.loads(clean_text)
            
            return {
                'score': accuracy_result.get('accuracy_score', 0.5),
                'issues': accuracy_result.get('issues', []),
                'validation_results': accuracy_result.get('validation_results', {})
            }
            
        except Exception as e:
            return {
                'score': 0.5,
                'issues': [f"AI assessment failed: {str(e)}"],
                'validation_results': {}
            }
    
    def _generate_recommendations(self, assessment: Dict) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []
        
        if assessment['overall_score'] < 0.7:
            recommendations.append("Document quality is below acceptable threshold - consider re-scanning")
        
        if assessment['missing_fields']:
            recommendations.append(f"Missing required fields: {', '.join(assessment['missing_fields'])}")
        
        if assessment['readability_score'] < 0.7:
            recommendations.append("Poor text quality - consider using higher resolution scan")
        
        if assessment['accuracy_score'] < 0.7:
            recommendations.append("Data inconsistencies found - manual review recommended")
        
        if not recommendations:
            recommendations.append("Document quality is acceptable for processing")
        
        return recommendations