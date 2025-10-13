#!/usr/bin/env python3
"""
simple_idp_ui.py

Simple UI for PDF upload and custom prompt-based IDP processing
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import boto3
import time
import tempfile
from pathlib import Path
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# AWS Configuration
S3_BUCKET = "awsidpdocs"
AWS_REGION = 'us-east-1'

# Available Bedrock models for text/document processing
BEDROCK_MODELS = {
    'claude-3-haiku': 'anthropic.claude-3-haiku-20240307-v1:0',      # Fast, cost-effective
    'claude-3-sonnet': 'anthropic.claude-3-sonnet-20240229-v1:0',    # Balanced performance
    'claude-3-opus': 'anthropic.claude-3-opus-20240229-v1:0',        # Most capable
    'claude-3.5-sonnet': 'anthropic.claude-3-5-sonnet-20240620-v1:0', # Latest, best for complex tasks
    'titan-text': 'amazon.titan-text-express-v1',                    # Amazon's text model
    'llama2-70b': 'meta.llama2-70b-chat-v1',                        # Meta's large model
    'cohere-command': 'cohere.command-text-v14'                      # Cohere's text model
}

# Default model - Claude 3.5 Sonnet is best for complex document analysis
BEDROCK_MODEL = BEDROCK_MODELS['claude-3.5-sonnet']

# Initialize AWS clients
s3 = boto3.client('s3', region_name=AWS_REGION)
textract = boto3.client('textract', region_name=AWS_REGION)
bedrock = boto3.client('bedrock-runtime', region_name=AWS_REGION)

# Temporary storage for processing results
TEMP_DIR = Path("temp_processing")
TEMP_DIR.mkdir(exist_ok=True)

@app.route('/')
def index():
    """Main upload page"""
    return render_template('simple_idp.html')

@app.route('/api/models')
def get_models():
    """Get available Bedrock models"""
    model_info = {
        'claude-3-haiku': {
            'name': 'Claude 3 Haiku',
            'description': 'Fast and cost-effective for simple tasks',
            'best_for': 'Quick extractions, simple documents'
        },
        'claude-3-sonnet': {
            'name': 'Claude 3 Sonnet', 
            'description': 'Balanced performance and capability',
            'best_for': 'Most document types, good accuracy'
        },
        'claude-3-opus': {
            'name': 'Claude 3 Opus',
            'description': 'Most capable but slower and more expensive',
            'best_for': 'Complex documents, highest accuracy'
        },
        'claude-3.5-sonnet': {
            'name': 'Claude 3.5 Sonnet',
            'description': 'Latest model with best performance (Recommended)',
            'best_for': 'All document types, best overall choice'
        },
        'titan-text': {
            'name': 'Amazon Titan Text',
            'description': 'Amazon\'s text model, good for structured data',
            'best_for': 'Forms, structured documents'
        },
        'llama2-70b': {
            'name': 'Llama 2 70B',
            'description': 'Meta\'s large language model',
            'best_for': 'General text processing'
        },
        'cohere-command': {
            'name': 'Cohere Command',
            'description': 'Cohere\'s text understanding model',
            'best_for': 'Text analysis and summarization'
        }
    }
    
    return jsonify({
        'success': True,
        'models': model_info,
        'default': 'claude-3.5-sonnet'
    })

@app.route('/api/process', methods=['POST'])
def process_document():
    """Process uploaded PDF with custom prompt"""
    try:
        # Check if file was uploaded
        if 'pdf_file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['pdf_file']
        prompt = request.form.get('prompt', '').strip()
        selected_model = request.form.get('model', 'claude-3.5-sonnet')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not prompt:
            return jsonify({'success': False, 'message': 'Please provide a prompt'})
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'message': 'Please upload a PDF file'})
        
        # Validate model selection
        if selected_model not in BEDROCK_MODELS:
            selected_model = 'claude-3.5-sonnet'
        
        # Generate unique processing ID
        process_id = str(uuid.uuid4())
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_pdf_path = TEMP_DIR / f"{process_id}_{filename}"
        file.save(temp_pdf_path)
        
        # Start processing with selected model
        result = process_pdf_with_prompt(temp_pdf_path, prompt, process_id, selected_model)
        
        # Clean up temporary file
        temp_pdf_path.unlink()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Processing error: {str(e)}'
        })

def process_pdf_with_prompt(pdf_path: Path, prompt: str, process_id: str, model_key: str = 'claude-3.5-sonnet') -> dict:
    """Process PDF through Textract and Claude with custom prompt"""
    try:
        # Step 1: Upload PDF to S3
        s3_key = f"temp_processing/{process_id}/{pdf_path.name}"
        s3.upload_file(str(pdf_path), S3_BUCKET, s3_key)
        
        # Step 2: Start Textract job
        textract_response = textract.start_document_analysis(
            DocumentLocation={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}},
            FeatureTypes=['FORMS', 'TABLES']
        )
        
        job_id = textract_response['JobId']
        
        # Step 3: Wait for Textract to complete
        extracted_text = wait_for_textract_and_extract(job_id)
        
        if not extracted_text:
            return {'success': False, 'message': 'Failed to extract text from PDF'}
        
        # Step 4: Process with selected model using custom prompt
        result_json = process_with_bedrock_model(extracted_text, prompt, model_key)
        
        # Step 5: Save result for download
        json_file, text_file = save_result_for_download(result_json, process_id, extracted_text)
        
        # Step 6: Clean up S3
        s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        
        return {
            'success': True,
            'message': 'Processing completed successfully',
            'result': result_json,
            'download_id': process_id,
            'extracted_text_preview': extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text,
            'text_length': len(extracted_text)
        }
        
    except Exception as e:
        return {'success': False, 'message': f'Processing failed: {str(e)}'}

def wait_for_textract_and_extract(job_id: str) -> str:
    """Wait for Textract job and extract text"""
    try:
        # Poll for completion
        while True:
            response = textract.get_document_analysis(JobId=job_id)
            status = response['JobStatus']
            
            if status == 'SUCCEEDED':
                break
            elif status == 'FAILED':
                raise Exception("Textract job failed")
            
            time.sleep(2)  # Wait 2 seconds before checking again
        
        # Get all blocks
        all_blocks = []
        next_token = None
        
        while True:
            if next_token:
                response = textract.get_document_analysis(JobId=job_id, NextToken=next_token)
            else:
                response = textract.get_document_analysis(JobId=job_id)
            
            all_blocks.extend(response['Blocks'])
            next_token = response.get('NextToken')
            
            if not next_token:
                break
        
        # Extract text from blocks
        text_lines = []
        for block in all_blocks:
            if block['BlockType'] == 'LINE':
                text_lines.append(block['Text'])
        
        return '\n'.join(text_lines)
        
    except Exception as e:
        print(f"Textract error: {e}")
        return ""

def process_with_bedrock_model(text: str, user_prompt: str, model_key: str = 'claude-3.5-sonnet') -> dict:
    """Process extracted text with selected Bedrock model using user's custom prompt"""
    try:
        model_id = BEDROCK_MODELS.get(model_key, BEDROCK_MODELS['claude-3.5-sonnet'])
        
        # Construct the full prompt
        full_prompt = f"""
        You are an expert document analysis AI. A user has uploaded a document and wants specific information extracted.

        User's Request: {user_prompt}

        Document Text:
        {text}

        Instructions:
        1. Analyze the document text carefully
        2. Extract the information requested by the user
        3. Return the result as a well-structured JSON object
        4. If the requested information is not found, indicate this clearly
        5. Be accurate and thorough in your analysis
        6. Include confidence levels where appropriate

        Return ONLY valid JSON (no markdown formatting or explanations outside the JSON).
        """
        
        # Different models have different request formats
        if model_key.startswith('claude'):
            # Claude models use the messages format
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "temperature": 0,
                "messages": [{"role": "user", "content": full_prompt}]
            })
        elif model_key == 'titan-text':
            # Amazon Titan format
            body = json.dumps({
                "inputText": full_prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 4000,
                    "temperature": 0,
                    "topP": 1
                }
            })
        elif model_key == 'llama2-70b':
            # Llama format
            body = json.dumps({
                "prompt": full_prompt,
                "max_gen_len": 4000,
                "temperature": 0,
                "top_p": 1
            })
        elif model_key == 'cohere-command':
            # Cohere format
            body = json.dumps({
                "prompt": full_prompt,
                "max_tokens": 4000,
                "temperature": 0,
                "p": 1
            })
        else:
            # Default to Claude format
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "temperature": 0,
                "messages": [{"role": "user", "content": full_prompt}]
            })
        
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body
        )
        
        raw_bytes = response["body"].read()
        resp_obj = json.loads(raw_bytes)
        
        # Extract text based on model response format
        if model_key.startswith('claude'):
            model_text = resp_obj["content"][0]["text"]
        elif model_key == 'titan-text':
            model_text = resp_obj["results"][0]["outputText"]
        elif model_key == 'llama2-70b':
            model_text = resp_obj["generation"]
        elif model_key == 'cohere-command':
            model_text = resp_obj["generations"][0]["text"]
        else:
            model_text = resp_obj.get("content", [{}])[0].get("text", str(resp_obj))
        
        # Clean up response
        clean_text = model_text.strip()
        
        # Remove markdown code blocks if present
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]
        if clean_text.startswith('```'):
            clean_text = clean_text[3:]
        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]
        
        clean_text = clean_text.strip()
        
        # Parse JSON
        try:
            result_json = json.loads(clean_text)
            # Add metadata about the processing
            result_json["_metadata"] = {
                "model_used": model_key,
                "model_id": model_id,
                "processing_timestamp": time.time()
            }
            return result_json
        except json.JSONDecodeError:
            # If JSON parsing fails, return the text as a message
            return {
                "extraction_result": clean_text,
                "note": "The AI response could not be parsed as JSON, returning as text",
                "_metadata": {
                    "model_used": model_key,
                    "model_id": model_id,
                    "processing_timestamp": time.time()
                }
            }
        
    except Exception as e:
        return {
            "error": f"Model processing failed: {str(e)}",
            "model_used": model_key,
            "extracted_text_sample": text[:200] + "..." if len(text) > 200 else text
        }

def save_result_for_download(result_json: dict, process_id: str, extracted_text: str = "") -> tuple:
    """Save result JSON and text for download"""
    # Save JSON file
    json_file = TEMP_DIR / f"result_{process_id}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)
    
    # Save text file
    text_file = TEMP_DIR / f"extracted_text_{process_id}.txt"
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(extracted_text)
    
    return json_file, text_file

@app.route('/api/download/<download_id>/<file_type>')
def download_result(download_id, file_type):
    """Download processed result (json or text)"""
    try:
        if file_type == 'json':
            result_file = TEMP_DIR / f"result_{download_id}.json"
            download_name = f"idp_result_{download_id}.json"
            mimetype = 'application/json'
        elif file_type == 'text':
            result_file = TEMP_DIR / f"extracted_text_{download_id}.txt"
            download_name = f"extracted_text_{download_id}.txt"
            mimetype = 'text/plain'
        else:
            return jsonify({'error': 'Invalid file type'}), 400
        
        if not result_file.exists():
            return jsonify({'error': 'File not found or expired'}), 404
        
        return send_file(
            result_file,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup/<process_id>', methods=['DELETE'])
def cleanup_files(process_id):
    """Clean up temporary files"""
    try:
        # Clean up both JSON and text files
        json_file = TEMP_DIR / f"result_{process_id}.json"
        text_file = TEMP_DIR / f"extracted_text_{process_id}.txt"
        
        if json_file.exists():
            json_file.unlink()
        if text_file.exists():
            text_file.unlink()
        
        return jsonify({'success': True, 'message': 'Files cleaned up'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5004)