console.log('✅ upload.js loaded');

const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const statusMessage = document.getElementById('statusMessage');
const documentsList = document.getElementById('documentsList');

// Click to select files
uploadZone.addEventListener('click', () => {
    fileInput.click();
});

// Drag and drop
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    fileInput.files = e.dataTransfer.files;
    uploadFiles();
});

// File input change
fileInput.addEventListener('change', () => {
    console.log('Files selected:', fileInput.files.length);
    uploadFiles();
});

async function uploadFiles() {
    const files = fileInput.files;
    console.log('uploadFiles() - files:', files.length);

    if (files.length === 0) {
        showStatus('No files selected', 'error');
        return;
    }

    // Filter PDFs
    const pdfFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    
    if (pdfFiles.length === 0) {
        showStatus('Only PDF files allowed', 'error');
        return;
    }

    showStatus(`Uploading ${pdfFiles.length} file(s)...`, 'loading');

    const formData = new FormData();
    pdfFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        console.log('Sending POST to /api/upload');
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);

        if (response.ok && data.uploaded && data.uploaded.length > 0) {
            showStatus(`✅ Uploaded ${data.uploaded.length} file(s)`, 'success');
            fileInput.value = '';
            setTimeout(() => {
                statusMessage.style.display = 'none';
                loadDocuments();
            }, 1000);
        } else {
            showStatus(`❌ ${data.error || 'Upload failed'}`, 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showStatus(`❌ Error: ${error.message}`, 'error');
    }
}

function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${type}`;
}

async function loadDocuments() {
    try {
        const response = await fetch('/api/documents');
        const data = await response.json();

        if (!data.success || !data.documents) {
            documentsList.innerHTML = '<div class="empty-state">Error loading documents</div>';
            return;
        }

        let docs = data.documents || [];
        
        // Sort by upload time descending (newest first)
        docs.sort((a, b) => new Date(b.upload_time) - new Date(a.upload_time));
        
        // Update count
        const countElement = document.getElementById('docCount');
        if (countElement) {
            countElement.textContent = docs.length;
        }
        
        if (docs.length === 0) {
            documentsList.innerHTML = '<div class="empty-state">📭 No documents yet</div>';
            return;
        }

        documentsList.innerHTML = docs.map(doc => `
            <div class="document-item ${doc.status}">
                <div style="flex: 1;">
                    <div class="doc-name">📄 ${doc.file_name}</div>
                    <div style="font-size: 0.9em; color: #666;">
                        ${(doc.size / 1024).toFixed(2)} KB • ${new Date(doc.upload_time).toLocaleString()}
                    </div>
                </div>
                <span class="doc-status status-${doc.status}">
                    ${doc.status === 'completed' ? '✅ DONE' : '⏳ PROCESSING'}
                </span>
                <button onclick="deleteDocument('${doc.file_key}')" class="delete-btn" title="Delete">🗑️</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading documents:', error);
        documentsList.innerHTML = `<div class="empty-state">Error: ${error.message}</div>`;
    }
}

async function deleteDocument(fileKey) {
    if (!confirm('Delete this document?')) return;
    
    try {
        const response = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_key: fileKey })
        });
        
        const data = await response.json();
        if (data.success) {
            showStatus('✅ Document deleted', 'success');
            setTimeout(() => loadDocuments(), 500);
        } else {
            showStatus('❌ Delete failed', 'error');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showStatus('❌ Error deleting document', 'error');
    }
}

// Load on page load
window.addEventListener('load', () => {
    console.log('Page loaded');
    loadDocuments();
});

// Auto-refresh every 5 seconds
setInterval(loadDocuments, 5000);
