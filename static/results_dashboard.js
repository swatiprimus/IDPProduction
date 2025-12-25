// Results Dashboard JavaScript

console.log('📊 Results Dashboard loaded');

// Load documents on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, loading documents...');
    loadDocuments();
    
    // Auto-refresh every 5 seconds
    setInterval(loadDocuments, 5000);
});

async function loadDocuments() {
    try {
        console.log('📋 Loading documents...');
        const response = await fetch('/api/documents');
        const data = await response.json();

        if (!data.success) {
            console.error('Error loading documents:', data);
            document.getElementById('resultsList').innerHTML = '<div class="empty-state"><p>Error loading documents</p></div>';
            return;
        }

        const documents = data.documents || [];
        console.log(`Found ${documents.length} documents`);

        // Update stats
        const completed = documents.filter(d => d.status === 'completed').length;
        const processing = documents.filter(d => d.status === 'pending' || d.status === 'in_progress').length;
        const failed = documents.filter(d => d.status === 'failed').length;

        document.getElementById('totalDocs').textContent = documents.length;
        document.getElementById('processedDocs').textContent = completed;
        document.getElementById('processingDocs').textContent = processing;
        document.getElementById('failedDocs').textContent = failed;

        if (documents.length === 0) {
            document.getElementById('resultsList').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><p>No documents yet</p></div>';
            return;
        }

        // Render documents
        const resultsList = document.getElementById('resultsList');
        resultsList.innerHTML = documents.map(doc => `
            <div class="result-item ${doc.status}">
                <div class="result-header">
                    <div class="result-name">📄 ${doc.file_name}</div>
                    <span class="result-status status-${doc.status}">${doc.status.toUpperCase()}</span>
                </div>
                <div class="result-info">
                    Size: ${(doc.size / 1024).toFixed(2)} KB
                </div>
                <div class="result-info">
                    Uploaded: ${new Date(doc.upload_time).toLocaleString()}
                </div>
                ${doc.document_type ? `<div class="result-type">Type: ${doc.document_type}</div>` : ''}
                ${doc.status === 'completed' ? `
                    <button class="view-result-btn" onclick="goToSkillsCatalog()">
                        👁️ View Result
                    </button>
                ` : ''}
            </div>
        `).join('');

        console.log('✅ Documents rendered');
    } catch (error) {
        console.error('❌ Error loading documents:', error);
        document.getElementById('resultsList').innerHTML = `<div class="empty-state"><p>Error: ${error.message}</p></div>`;
    }
}

function goToSkillsCatalog() {
    console.log('🚀 Navigating to skills_catalog.html via /results endpoint');
    window.location.href = '/results';
}
