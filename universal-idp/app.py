"""Main Flask application for Universal IDP."""

from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import time
import hashlib
import threading
from datetime import datetime
import logging

# Import our modules
from services.document_processor import document_processor
from utils.helpers import load_documents_db, save_documents_db, sanitize_filename
from config import OUTPUT_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variables
processed_documents = load_documents_db()
job_status_map = {}

@app.route("/")
def index():
    """Main page - Skills Catalog Dashboard."""
    return render_template("skills_catalog.html")

@app.route("/dashboard")
def dashboard():
    """Dashboard - Shows all processed documents as skills."""
    return render_template("skills_catalog.html")

@app.route("/codebase")
def codebase():
    """Codebase documentation."""
    return render_template("codebase_docs.html")

@app.route("/api/documents")
def get_all_documents():
    """API endpoint to get all processed documents."""
    return jsonify({"documents": processed_documents, "total": len(processed_documents)})

@app.route("/api/document/<doc_id>")
def get_document_detail(doc_id):
    """Get details of a specific document."""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return jsonify({"success": True, "document": doc})
    return jsonify({"success": False, "message": "Document not found"}), 404

@app.route("/document/<doc_id>/pages")
def view_document_pages(doc_id):
    """View document with unified page-by-page viewer."""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("unified_page_viewer.html", document=doc)
    return "Document not found", 404

@app.route("/document/<doc_id>/accounts")
def view_account_based(doc_id):
    """View document with account-based interface."""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("account_based_viewer.html", document=doc)
    return "Document not found", 404

@app.route("/process", methods=["POST"])
def process_document():
    """Upload and process document with parallel processing support."""
    try:
        f = request.files.get("file")
        if not f:
            return jsonify({"success": False, "message": "No file uploaded"}), 400
        
        # Read file content
        file_bytes = f.read()
        filename = sanitize_filename(f.filename)
        
        # Get document name from form (optional, defaults to filename)
        document_name = request.form.get("document_name", filename)
        
        # Determine if OCR is needed
        use_ocr = filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg'))
        
        # Generate job ID
        job_id = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:10]
        
        # Save PDF file if needed for page-level processing
        pdf_path = None
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(OUTPUT_DIR, f"{job_id}_{filename}")
            with open(pdf_path, 'wb') as pdf_file:
                pdf_file.write(file_bytes)
        
        # Initialize job status
        job_status_map[job_id] = {
            "status": "Queued for processing...",
            "progress": 0,
            "filename": filename,
            "document_name": document_name,
            "start_time": time.time()
        }
        
        # Start background processing in separate thread for parallel execution
        def process_in_background():
            global processed_documents, job_status_map
            try:
                logger.info(f"Starting parallel processing for job {job_id}: {filename}")
                
                # Ensure job status exists
                if job_id not in job_status_map:
                    job_status_map[job_id] = {
                        "status": "Processing started...",
                        "progress": 5,
                        "filename": filename,
                        "document_name": document_name,
                        "start_time": time.time()
                    }
                
                result = document_processor.process_document(
                    job_id, file_bytes, filename, use_ocr, document_name, pdf_path, job_status_map
                )
                
                # Add to processed documents
                processed_documents.append(result)
                save_documents_db(processed_documents)
                
                # Update final status
                if job_id in job_status_map:
                    job_status_map[job_id].update({
                        "status": "✅ Processing completed successfully",
                        "progress": 100,
                        "completed": True
                    })
                
                logger.info(f"Document processing completed: {job_id} - {filename}")
                
            except Exception as e:
                logger.error(f"Background processing failed for {job_id}: {str(e)}")
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"Full error details: {error_details}")
                
                if job_id in job_status_map:
                    job_status_map[job_id].update({
                        "status": f"❌ Error: {str(e)}",
                        "progress": 0,
                        "error": str(e),
                        "error_details": error_details,
                        "completed": True
                    })
                else:
                    # Create error status if job_id doesn't exist
                    job_status_map[job_id] = {
                        "status": f"❌ Error: {str(e)}",
                        "progress": 0,
                        "error": str(e),
                        "error_details": error_details,
                        "completed": True,
                        "filename": filename
                    }
        
        # Use daemon thread for automatic cleanup
        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True, 
            "job_id": job_id, 
            "use_ocr": use_ocr,
            "filename": filename,
            "message": f"Document {filename} queued for processing"
        })
        
    except Exception as e:
        logger.error(f"Document upload failed: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/status/<job_id>")
def get_status(job_id):
    """Get processing status with enhanced information."""
    if job_id in job_status_map:
        status = job_status_map[job_id].copy()
        
        # Check if processing is complete and clean up old jobs
        if status.get("completed", False):
            # Keep completed jobs for 30 seconds for final status check
            if "completion_time" not in status:
                status["completion_time"] = time.time()
                job_status_map[job_id] = status
            elif time.time() - status["completion_time"] > 30:
                # Clean up old completed jobs
                job_status_map.pop(job_id, None)
        
        return jsonify(status)
    else:
        # Check if document exists in processed documents
        doc = next((d for d in processed_documents if d["id"] == job_id), None)
        if doc:
            return jsonify({
                "status": "✅ Document already processed",
                "progress": 100,
                "completed": True,
                "found_in_db": True
            })
        
        return jsonify({
            "status": "Job not found",
            "progress": 0,
            "error": "Job ID not found in system"
        }), 404

@app.route("/api/document/<doc_id>/delete", methods=["DELETE", "POST"])
def delete_document(doc_id):
    """Delete a processed document."""
    global processed_documents
    
    try:
        # Find document
        doc = next((d for d in processed_documents if d["id"] == doc_id), None)
        if not doc:
            return jsonify({"success": False, "message": "Document not found"}), 404
        
        # Delete associated files
        if "ocr_file" in doc and os.path.exists(doc["ocr_file"]):
            os.remove(doc["ocr_file"])
            logger.info(f"Deleted OCR file: {doc['ocr_file']}")
        
        if "pdf_path" in doc and doc["pdf_path"] and os.path.exists(doc["pdf_path"]):
            os.remove(doc["pdf_path"])
            logger.info(f"Deleted PDF file: {doc['pdf_path']}")
        
        # Remove from processed documents
        processed_documents = [d for d in processed_documents if d["id"] != doc_id]
        save_documents_db(processed_documents)
        
        logger.info(f"Deleted document: {doc_id}")
        return jsonify({"success": True, "message": "Document deleted successfully"})
    
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to delete: {str(e)}"}), 500

@app.route("/api/document/<doc_id>/pdf")
def serve_pdf(doc_id):
    """Serve the PDF file for viewing."""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if not doc:
        return "Document not found", 404
    
    pdf_path = doc.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF file not found", 404
    
    return send_file(pdf_path, mimetype='application/pdf')

@app.route("/api/documents/cleanup", methods=["POST"])
def cleanup_old_documents():
    """Delete all old uploaded documents and OCR results."""
    global processed_documents
    
    try:
        deleted_count = 0
        
        # Delete all files in output directory
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file_path}: {str(e)}")
        
        # Clear processed documents database
        doc_count = len(processed_documents)
        processed_documents = []
        save_documents_db(processed_documents)
        
        # Clear job status map
        job_status_map.clear()
        
        logger.info(f"Cleanup completed: {deleted_count} files deleted, {doc_count} documents cleared")
        
        return jsonify({
            "success": True,
            "message": f"Cleanup completed successfully",
            "files_deleted": deleted_count,
            "documents_cleared": doc_count
        })
    
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        return jsonify({"success": False, "message": f"Cleanup failed: {str(e)}"}), 500

# Register blueprints for route handling
from routes.page_routes import bp as page_bp
from routes.account_routes import bp as account_bp
from routes.cache_routes import bp as cache_bp

app.register_blueprint(page_bp)
app.register_blueprint(account_bp)
app.register_blueprint(cache_bp)

if __name__ == "__main__":
    logger.info("Starting Universal IDP application")
    app.run(debug=True, port=5015)