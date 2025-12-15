"""
Clear / migrate S3 caches.
"""
import json
from flask import Blueprint, jsonify, request
from services.aws_services import aws_services
from utils.helpers import flatten_nested_objects
from config import S3_BUCKET

bp = Blueprint("cache_routes", __name__)

def _get_doc(doc_id: str):
    import sys
    # Get the app module from sys.modules to ensure we get the same instance
    app_module = sys.modules.get('app')
    if app_module and hasattr(app_module, 'processed_documents'):
        processed_documents = app_module.processed_documents
    else:
        # Fallback import
        from app import processed_documents
    
    return next((d for d in processed_documents if d["id"] == doc_id), None)

@bp.route("/api/document/<doc_id>/clear-cache", methods=["POST"])
def clear_entire_cache(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    deleted = 0
    # account pages
    for acc_idx in range(len(accounts)):
        for p in range(100):
            try:
                aws_services.delete_from_s3(S3_BUCKET, f"page_data/{doc_id}/account_{acc_idx}/page_{p}.json")
                deleted += 1
            except:
                break
    # regular pages
    for p in range(100):
        try:
            aws_services.delete_from_s3(S3_BUCKET, f"page_data/{doc_id}/page_{p}.json")
        except:
            break
    # mapping
    try:
        aws_services.delete_from_s3(S3_BUCKET, f"page_mapping/{doc_id}/mapping.json")
    except:
        pass
    # mark doc
    doc["cache_cleared"] = True
    doc["cache_cleared_at"] = datetime.utcnow().isoformat()
    return jsonify(success=True, message=f"Cache cleared ({deleted} entries)")

@bp.route("/api/document/<doc_id>/account/<int:account_idx>/clear-cache", methods=["POST"])
def clear_account_cache(doc_id: str, account_idx: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    if account_idx >= len(accounts):
        return jsonify(success=False, message="Account not found"), 404
    acc_num = accounts[account_idx]["accountNumber"]
    deleted = 0
    for p in range(100):
        try:
            aws_services.delete_from_s3(S3_BUCKET, f"page_data/{doc_id}/account_{account_idx}/page_{p}.json")
            deleted += 1
        except:
            break
    return jsonify(success=True, message=f"Cache cleared for Account {acc_num}", pages_cleared=deleted)

@bp.route("/api/document/<doc_id>/migrate-cache", methods=["POST"])
def migrate_cache(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    migrated = 0
    for acc_idx in range(len(accounts)):
        for p in range(100):
            key = f"page_data/{doc_id}/account_{acc_idx}/page_{p}.json"
            try:
                raw = aws_services.get_from_s3(S3_BUCKET, key)
                if not raw:
                    continue
                data = flatten_nested_objects(raw.get("data", {}))
                if data != raw.get("data"):
                    raw["data"] = data
                    raw["migrated"] = True
                    aws_services.upload_to_s3(S3_BUCKET, key, json.dumps(raw).encode(), "application/json")
                    migrated += 1
            except:
                break
    return jsonify(success=True, message=f"Cache migrated ({migrated} entries)")