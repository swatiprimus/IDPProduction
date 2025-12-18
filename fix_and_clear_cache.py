#!/usr/bin/env python3
"""
Fix and Clear Cache Script
Clears all caches, pycache, and temporary files
"""

import os
import shutil
import json
from pathlib import Path

def clear_pycache():
    """Remove all __pycache__ directories"""
    print("🧹 Clearing __pycache__ directories...")
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                print(f"  ✅ Removed: {pycache_path}")
            except Exception as e:
                print(f"  ❌ Failed to remove {pycache_path}: {e}")

def clear_s3_cache():
    """Clear local S3 cache references"""
    print("\n🧹 Clearing S3 cache references...")
    cache_files = [
        'processed_documents.json',
        '.cache',
        '.s3_cache'
    ]
    
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            try:
                if os.path.isdir(cache_file):
                    shutil.rmtree(cache_file)
                else:
                    os.remove(cache_file)
                print(f"  ✅ Removed: {cache_file}")
            except Exception as e:
                print(f"  ❌ Failed to remove {cache_file}: {e}")

def clear_temp_files():
    """Clear temporary files"""
    print("\n🧹 Clearing temporary files...")
    temp_patterns = [
        'temp_*.png',
        '*.pyc',
        '.DS_Store'
    ]
    
    for pattern in temp_patterns:
        for file in Path('.').glob(f'**/{pattern}'):
            try:
                if file.is_file():
                    file.unlink()
                    print(f"  ✅ Removed: {file}")
            except Exception as e:
                print(f"  ❌ Failed to remove {file}: {e}")

def clear_ocr_results():
    """Clear OCR results directory"""
    print("\n🧹 Clearing OCR results...")
    if os.path.exists('ocr_results'):
        try:
            # Keep directory but clear contents
            for file in os.listdir('ocr_results'):
                file_path = os.path.join('ocr_results', file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"  ✅ Removed: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    print(f"  ✅ Removed: {file_path}")
        except Exception as e:
            print(f"  ❌ Failed to clear ocr_results: {e}")

def clear_incoming_documents():
    """Clear incoming documents"""
    print("\n🧹 Clearing incoming documents...")
    if os.path.exists('incoming_documents'):
        try:
            for file in os.listdir('incoming_documents'):
                file_path = os.path.join('incoming_documents', file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"  ✅ Removed: {file_path}")
        except Exception as e:
            print(f"  ❌ Failed to clear incoming_documents: {e}")

def reset_processed_documents():
    """Reset processed documents JSON"""
    print("\n🔄 Resetting processed documents...")
    try:
        processed_file = 'processed_documents.json'
        if os.path.exists(processed_file):
            os.remove(processed_file)
            print(f"  ✅ Removed: {processed_file}")
        
        # Create fresh empty file (flat array, not nested object)
        with open(processed_file, 'w') as f:
            json.dump([], f, indent=2)
        print(f"  ✅ Created fresh: {processed_file}")
    except Exception as e:
        print(f"  ❌ Failed to reset processed_documents.json: {e}")

def main():
    print("=" * 80)
    print("FIX AND CLEAR CACHE - COMPREHENSIVE CLEANUP")
    print("=" * 80)
    print()
    
    # Run all cleanup operations
    clear_pycache()
    clear_s3_cache()
    clear_temp_files()
    clear_ocr_results()
    clear_incoming_documents()
    reset_processed_documents()
    
    print()
    print("=" * 80)
    print("✅ CLEANUP COMPLETE")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Activate venv: venv\\Scripts\\activate")
    print("  2. Set environment: set FLASK_ENV=development & set FLASK_DEBUG=1")
    print("  3. Run app: python app_modular.py")
    print()

if __name__ == "__main__":
    main()
