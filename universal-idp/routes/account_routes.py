"""
Account-based viewer routes (loan documents).
"""
import json
import fitz
import re
from flask import Blueprint, jsonify, request
from services.aws_services import aws_services
from utils.helpers import flatten_nested_objects
from config import OUTPUT_DIR, S3_BUCKET

bp = Blueprint("account_routes", __name__)

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

@bp.route("/api/document/<doc_id>/accounts")
def get_accounts(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    doc_data = doc.get("documents", [{}])[0]
    accounts = doc_data.get("accounts", [])
    return jsonify(success=True, accounts=accounts, total=len(accounts))

@bp.route("/api/document/<doc_id>/account/<int:account_idx>/pages")
def get_account_pages(doc_id: str, account_idx: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    if account_idx >= len(accounts):
        return jsonify(success=False, message="Account index out of range"), 400
    target_acc = accounts[account_idx]["accountNumber"]

    # quick page→account map
    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify(success=False, message="PDF not found"), 404

    mapping = {}
    with fitz.open(pdf_path) as pdf:
        for pnum, page in enumerate(pdf):
            txt = page.get_text()
            norm = re.sub(r"\s|-", "", txt)
            if re.sub(r"\s|-", "", target_acc) in norm:
                mapping[pnum] = target_acc

    # assign continuous block
    if not mapping:
        return jsonify(success=False, message="No pages found for account"), 404
    start = min(mapping.keys())
    end = start
    for p in range(start + 1, len(pdf)):
        if p in mapping:
            end = p
        else:
            break
    pages = list(range(start, end + 1))
    return jsonify(success=True, pages=pages, account_number=target_acc, total_pages=len(pages))

@bp.route("/api/document/<doc_id>/account/<int:account_idx>/page/<int:page_num>/extract")
def extract_account_page(doc_id: str, account_idx: int, page_num: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    if account_idx >= len(accounts):
        return jsonify(success=False, message="Account index out of range"), 400
    account_number = accounts[account_idx]["accountNumber"]

    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify(success=False, message="PDF not found"), 404

    # cache key for account-level page
    key = f"page_data/{doc_id}/account_{account_idx}/page_{page_num}.json"
    cached = aws_services.get_from_s3(S3_BUCKET, key)
    if cached:
        cached["data"] = flatten_nested_objects(cached.get("data", {}))
        cached["cached"] = True
        return jsonify(cached)

    # extract text
    with fitz.open(pdf_path) as pdf:
        if page_num >= len(pdf):
            return jsonify(success=False, message="Page out of range"), 400
        page = pdf[page_num]
        text = page.get_text()
        if not text or len(text.strip()) < 50:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            text, _ = aws_services.textract.detect_document_text(Document={"Bytes": pix.tobytes("png")})

    # AI extraction
    from utils.document_types import document_type_detector
    from utils.prompts import prompt_manager
    detected = document_type_detector.detect_document_type(text)
    prompt = prompt_manager.get_prompt_for_type(detected)
    raw = aws_services.call_bedrock(prompt, text, MODEL_ID, max_tokens=8192)
    parsed = validate_json_response(raw)
    if not parsed or "documents" not in parsed:
        return jsonify(success=False, message="AI parse failed"), 500
    fields = flatten_nested_objects(parsed["documents"][0].get("extracted_fields", {}))
    fields["AccountNumber"] = account_number

    # save cache
    payload = {"account_number": account_number, "data": fields, "extracted_at": datetime.utcnow().isoformat()}
    aws_services.upload_to_s3(S3_BUCKET, key, json.dumps(payload).encode(), "application/json")
    return jsonify(success=True, page_number=page_num + 1, account_number=account_number, data=fields, cached=False)

@bp.route("/api/document/<doc_id>/account/<int:account_idx>/page/<int:page_num>/update", methods=["POST"])
def update_account_page(doc_id: str, account_idx: int, page_num: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    payload = request.get_json(force=True)
    if not payload or "page_data" not in payload:
        return jsonify(success=False, message="No page_data supplied"), 400
    accounts = doc.get("documents", [{}])[0].get("accounts", [])
    account_number = accounts[account_idx]["accountNumber"]
    key = f"page_data/{doc_id}/account_{account_idx}/page_{page_num}.json"
    existing = aws_services.get_from_s3(S3_BUCKET, key) or {}
    existing.update({"account_number": account_number, "data": payload["page_data"], "edited": True, "edited_at": datetime.utcnow().isoformat()})
    aws_services.upload_to_s3(S3_BUCKET, key, json.dumps(existing).encode(), "application/json")
    return jsonify(success=True, message=f"Account {account_number} page updated")