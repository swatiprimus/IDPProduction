"""
Page-level extraction and image serving.
"""
import json
import os
from datetime import datetime
import fitz
from flask import Blueprint, jsonify, send_file, request
from services.aws_services import aws_services
from services.ocr_service import ocr_service
from utils.helpers import flatten_nested_objects, validate_json_response
from utils.prompts import prompt_manager
from utils.document_types import document_type_detector
from config import OUTPUT_DIR, S3_BUCKET, MODEL_ID

bp = Blueprint("page_routes", __name__)

# ---------- helpers ----------
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

def _save_text_to_file(text: str, filename: str) -> str:
    from datetime import datetime
    safe = filename.replace("/", "_")
    path = f"{OUTPUT_DIR}/{datetime.now():%Y%m%d_%H%M%S}_{safe}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path

# ---------- routes ----------
@bp.route("/api/document/<doc_id>/pages")
def get_document_pages(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404

    pages_dir = f"{OUTPUT_DIR}/pages/{doc_id}"
    os.makedirs(pages_dir, exist_ok=True)

    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify(success=False, message="PDF not found"), 404

    # convert PDF → PNG once
    images = []
    with fitz.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf):
            img_path = f"{pages_dir}/page_{idx + 1}.png"
            if not os.path.exists(img_path):
                page.get_pixmap(matrix=fitz.Matrix(2, 2)).save(img_path)
            images.append(
                {
                    "page_number": idx + 1,
                    "url": f"/api/document/{doc_id}/page/{idx}",
                    "thumbnail": f"/api/document/{doc_id}/page/{idx}/thumbnail",
                }
            )
    return jsonify(success=True, pages=images, total_pages=len(images))

@bp.route("/api/document/<doc_id>/page/<int:page_num>")
def get_page_image(doc_id: str, page_num: int):
    path = f"{OUTPUT_DIR}/pages/{doc_id}/page_{page_num + 1}.png"
    if not os.path.exists(path):
        return "Page image not found", 404
    return send_file(path, mimetype="image/png")

@bp.route("/api/document/<doc_id>/page/<int:page_num>/thumbnail")
def get_page_thumbnail(doc_id: str, page_num: int):
    from PIL import Image
    import io

    path = f"{OUTPUT_DIR}/pages/{doc_id}/page_{page_num + 1}.png"
    if not os.path.exists(path):
        return "Thumbnail not found", 404
    img = Image.open(path)
    img.thumbnail((150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@bp.route("/api/document/<doc_id>/page/<int:page_num>/extract")
def extract_page_data(doc_id: str, page_num: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404

    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify(success=False, message="PDF not found"), 404

    # optional force re-extract
    force = request.args.get("force", "false").lower() == "true"

    # 1. try S3 cache first
    if not force:
        cached = aws_services.get_from_s3(S3_BUCKET, f"page_data/{doc_id}/page_{page_num}.json")
        if cached:
            cached["data"] = flatten_nested_objects(cached.get("data", {}))
            cached["cached"] = True
            return jsonify(cached)

    # 2. extract text from page
    with fitz.open(pdf_path) as pdf:
        if page_num >= len(pdf):
            return jsonify(success=False, message="Page out of range"), 400
        page = pdf[page_num]
        text = page.get_text()
        if not text or len(text.strip()) < 50:  # fallback OCR
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes(output="png")
            try:
                # Use Textract for OCR fallback
                text, _ = ocr_service.extract_text_with_textract(img_bytes, f"page_{page_num}.png")
            except Exception as e:
                # If OCR fails, use existing OCR text from document
                doc_ocr_file = doc.get("ocr_file")
                if doc_ocr_file and os.path.exists(doc_ocr_file):
                    with open(doc_ocr_file, 'r', encoding='utf-8') as f:
                        text = f.read()
                else:
                    text = f"Page {page_num + 1} - No text available"

    # 3. AI extraction
    detected_type = document_type_detector.detect_document_type(text)
    prompt = prompt_manager.get_prompt_for_type(detected_type)
    raw = aws_services.call_bedrock(prompt, text, MODEL_ID, max_tokens=8192)
    parsed = validate_json_response(raw)
    if not parsed or "documents" not in parsed:
        return jsonify(success=False, message="AI parse failed"), 500
    fields = flatten_nested_objects(parsed["documents"][0].get("extracted_fields", {}))

    # 4. save to cache
    payload = {"data": fields, "extracted_at": datetime.utcnow().isoformat()}
    aws_services.upload_to_s3(
        S3_BUCKET,
        f"page_data/{doc_id}/page_{page_num}.json",
        json.dumps(payload).encode(),
        "application/json",
    )
    return jsonify(success=True, page_number=page_num + 1, data=fields, cached=False)

@bp.route("/api/document/<doc_id>/page/<int:page_num>/update", methods=["POST"])
def update_page_data(doc_id: str, page_num: int):
    doc = _get_doc(doc_id)
    if not doc:
        return jsonify(success=False, message="Document not found"), 404
    payload = request.get_json(force=True)
    if not payload or "page_data" not in payload:
        return jsonify(success=False, message="No page_data supplied"), 400
    data = payload["page_data"]
    key = f"page_data/{doc_id}/page_{page_num}.json"
    existing = aws_services.get_from_s3(S3_BUCKET, key) or {}
    existing.update({"data": data, "edited": True, "edited_at": datetime.utcnow().isoformat()})
    aws_services.upload_to_s3(S3_BUCKET, key, json.dumps(existing).encode(), "application/json")
    return jsonify(success=True, message="Page updated")