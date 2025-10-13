#!/usr/bin/env python3
"""
analytics_dashboard.py

Analytics dashboard for IDP platform insights
"""

from flask import Flask, render_template, jsonify, request
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import boto3
from mongodb_rag_indexer import MongoDBRAGIndexer, MONGODB_CONFIG

app = Flask(__name__)

class IDPAnalytics:
    def __init__(self):
        self.indexer = MongoDBRAGIndexer(MONGODB_CONFIG)
        self.s3 = boto3.client('s3', region_name='us-east-1')
    
    def get_processing_stats(self) -> dict:
        """Get overall processing statistics"""
        if not self.indexer.db:
            return {}
        
        accounts_col = self.indexer.db[MONGODB_CONFIG['collections']['accounts']]
        documents_col = self.indexer.db[MONGODB_CONFIG['collections']['documents']]
        
        stats = {
            'total_accounts': accounts_col.count_documents({}),
            'total_documents': documents_col.count_documents({}),
            'document_types': {},
            'account_types': {},
            'processing_timeline': {},
            'quality_metrics': {}
        }
        
        # Document type distribution
        pipeline = [
            {"$group": {"_id": "$document_type", "count": {"$sum": 1}}}
        ]
        doc_types = list(documents_col.aggregate(pipeline))
        stats['document_types'] = {item['_id']: item['count'] for item in doc_types}
        
        # Account type distribution
        pipeline = [
            {"$unwind": "$account_types"},
            {"$group": {"_id": "$account_types", "count": {"$sum": 1}}}
        ]
        acc_types = list(accounts_col.aggregate(pipeline))
        stats['account_types'] = {item['_id']: item['count'] for item in acc_types}
        
        # Processing timeline (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        pipeline = [
            {"$match": {"created_at": {"$gte": thirty_days_ago}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        timeline = list(documents_col.aggregate(pipeline))
        stats['processing_timeline'] = {item['_id']: item['count'] for item in timeline}
        
        return stats
    
    def get_document_insights(self) -> dict:
        """Get document-specific insights"""
        if not self.indexer.db:
            return {}
        
        accounts_col = self.indexer.db[MONGODB_CONFIG['collections']['accounts']]
        
        insights = {
            'top_states': {},
            'age_distribution': {},
            'account_purposes': {},
            'signer_analysis': {}
        }
        
        # Top states from addresses
        pipeline = [
            {"$unwind": "$signers"},
            {"$match": {"signers.Address": {"$regex": r"[A-Z]{2}$"}}},
            {"$group": {
                "_id": {"$substr": ["$signers.Address", -2, 2]},
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        states = list(accounts_col.aggregate(pipeline))
        insights['top_states'] = {item['_id']: item['count'] for item in states}
        
        # Account purposes
        pipeline = [
            {"$unwind": "$account_purposes"},
            {"$group": {"_id": "$account_purposes", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        purposes = list(accounts_col.aggregate(pipeline))
        insights['account_purposes'] = {item['_id']: item['count'] for item in purposes}
        
        return insights
    
    def get_quality_metrics(self) -> dict:
        """Get document quality metrics"""
        # This would integrate with the quality assessor
        return {
            'average_quality_score': 0.85,
            'documents_needing_review': 12,
            'common_issues': [
                'Missing signatures',
                'Unclear text in scanned documents',
                'Incomplete address information'
            ]
        }
    
    def get_search_analytics(self) -> dict:
        """Get search usage analytics"""
        # This would track search queries and results
        return {
            'popular_searches': [
                'loan documents',
                'driver license',
                'bank statement',
                'delaware customers'
            ],
            'search_success_rate': 0.78,
            'avg_results_per_search': 4.2
        }

# Initialize analytics
analytics = IDPAnalytics()

@app.route('/')
def dashboard():
    """Main analytics dashboard"""
    return render_template('analytics_dashboard.html')

@app.route('/api/stats')
def api_stats():
    """Get processing statistics"""
    try:
        stats = analytics.get_processing_stats()
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/insights')
def api_insights():
    """Get document insights"""
    try:
        insights = analytics.get_document_insights()
        return jsonify({
            'success': True,
            'data': insights
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/quality')
def api_quality():
    """Get quality metrics"""
    try:
        quality = analytics.get_quality_metrics()
        return jsonify({
            'success': True,
            'data': quality
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/search-analytics')
def api_search_analytics():
    """Get search analytics"""
    try:
        search_analytics = analytics.get_search_analytics()
        return jsonify({
            'success': True,
            'data': search_analytics
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)