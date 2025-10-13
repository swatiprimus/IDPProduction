#!/usr/bin/env python3
"""
start_idp_platform.py

Startup script for the Unified IDP Platform
Checks dependencies and starts the main application
"""

import sys
import subprocess
import importlib
import os
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = [
        'flask',
        'boto3',
        'pymongo',
        'sentence_transformers',
        'numpy',
        'werkzeug'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package.replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} - MISSING")
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False
    
    return True

def check_aws_credentials():
    """Check if AWS credentials are configured"""
    try:
        import boto3
        
        # Try to create a client to test credentials
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.list_buckets()
        print("✅ AWS credentials configured")
        return True
    except Exception as e:
        print(f"❌ AWS credentials issue: {e}")
        print("Configure AWS credentials with: aws configure")
        return False

def check_mongodb_connection():
    """Check MongoDB connection"""
    try:
        from mongodb_rag_indexer import MongoDBRAGIndexer, MONGODB_CONFIG
        indexer = MongoDBRAGIndexer(MONGODB_CONFIG)
        if indexer.db:
            print("✅ MongoDB connected")
            return True
        else:
            print("❌ MongoDB connection failed")
            return False
    except Exception as e:
        print(f"⚠️  MongoDB connection issue: {e}")
        print("MongoDB is optional but recommended for RAG search")
        return False

def create_directories():
    """Create necessary directories"""
    directories = [
        'temp_processing',
        'templates'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"📁 Created directory: {directory}")

def main():
    """Main startup function"""
    print("🚀 Starting Unified IDP Platform")
    print("=" * 50)
    
    print("\n📋 Checking Dependencies...")
    if not check_dependencies():
        print("\n❌ Please install missing dependencies first")
        sys.exit(1)
    
    print("\n🔐 Checking AWS Configuration...")
    aws_ok = check_aws_credentials()
    
    print("\n🗄️  Checking MongoDB Connection...")
    mongodb_ok = check_mongodb_connection()
    
    print("\n📁 Creating Directories...")
    create_directories()
    
    print("\n" + "=" * 50)
    
    if not aws_ok:
        print("❌ AWS credentials required for document processing")
        sys.exit(1)
    
    if not mongodb_ok:
        print("⚠️  MongoDB not available - RAG search will be limited")
    
    print("✅ All checks passed!")
    print("\n🌟 Features Available:")
    print("   📄 Document Upload & Processing")
    print("   🤖 AI Classification & Quality Assessment")
    print("   💾 S3 Caching for Cost Optimization")
    print("   🔍 RAG Search" + (" (Limited)" if not mongodb_ok else ""))
    print("   📊 Real-time Statistics")
    
    print("\n🚀 Starting application...")
    print("📱 Access at: http://localhost:5000")
    print("⏹️  Press Ctrl+C to stop")
    print("=" * 50)
    
    # Start the unified IDP application
    try:
        from unified_idp_ui import app
        app.run(debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"\n❌ Application error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()