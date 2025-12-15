/**
 * Background Processing UI Helper
 * Add this to your HTML templates to automatically refresh documents when background processing completes
 */

class BackgroundProcessingHelper {
    constructor() {
        this.checkInterval = 5000; // Check every 5 seconds
        this.activeChecks = new Set();
    }

    /**
     * Start monitoring a document for background processing completion
     * @param {string} docId - Document ID to monitor
     * @param {function} onComplete - Callback when processing completes
     * @param {function} onProgress - Callback for progress updates (optional)
     */
    monitorDocument(docId, onComplete, onProgress = null) {
        if (this.activeChecks.has(docId)) {
            console.log(`Already monitoring document ${docId}`);
            return;
        }

        this.activeChecks.add(docId);
        console.log(`Starting background processing monitor for document ${docId}`);

        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/document/${docId}/background-status`);
                const result = await response.json();

                if (result.success && result.status) {
                    const status = result.status;
                    const stage = status.stage;
                    const progress = status.progress || 0;

                    // Call progress callback if provided
                    if (onProgress) {
                        onProgress(stage, progress, status);
                    }

                    // Check if processing is complete
                    if (stage === 'completed' || progress >= 100) {
                        console.log(`Background processing completed for document ${docId}`);
                        this.activeChecks.delete(docId);
                        
                        // Refresh document data
                        await this.refreshDocumentData(docId);
                        
                        // Call completion callback
                        if (onComplete) {
                            onComplete(status);
                        }
                        
                        return; // Stop checking
                    }

                    // Continue checking if still processing
                    if (this.activeChecks.has(docId)) {
                        setTimeout(checkStatus, this.checkInterval);
                    }
                } else {
                    // No background processing found, stop checking
                    this.activeChecks.delete(docId);
                }
            } catch (error) {
                console.error(`Error checking background status for ${docId}:`, error);
                this.activeChecks.delete(docId);
            }
        };

        // Start checking
        checkStatus();
    }

    /**
     * Refresh document data from background processing results
     * @param {string} docId - Document ID to refresh
     */
    async refreshDocumentData(docId) {
        try {
            const response = await fetch(`/api/document/${docId}/refresh-from-background`, {
                method: 'POST'
            });
            const result = await response.json();

            if (result.success) {
                console.log(`Document ${docId} refreshed with background processing results`);
                
                // Trigger page reload or update UI
                if (typeof window.loadSkills === 'function') {
                    window.loadSkills(); // Reload document list
                }
                
                // Trigger custom event for other components to listen
                window.dispatchEvent(new CustomEvent('documentUpdated', {
                    detail: { docId, result }
                }));
                
                return result;
            } else {
                console.warn(`Failed to refresh document ${docId}:`, result.message);
            }
        } catch (error) {
            console.error(`Error refreshing document ${docId}:`, error);
        }
    }

    /**
     * Check if a document is currently being processed in background
     * @param {string} docId - Document ID to check
     * @returns {Promise<object>} Processing status
     */
    async checkProcessingStatus(docId) {
        try {
            const response = await fetch(`/api/document/${docId}/background-status`);
            const result = await response.json();
            return result;
        } catch (error) {
            console.error(`Error checking processing status for ${docId}:`, error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Force start background processing for a document
     * @param {string} docId - Document ID to process
     * @returns {Promise<object>} Result of force processing
     */
    async forceBackgroundProcessing(docId) {
        try {
            const response = await fetch(`/api/document/${docId}/force-background-processing`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                console.log(`Forced background processing for document ${docId}`);
                // Start monitoring the document
                this.monitorDocument(docId, () => {
                    console.log(`Forced processing completed for document ${docId}`);
                });
            }
            
            return result;
        } catch (error) {
            console.error(`Error forcing background processing for ${docId}:`, error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Stop monitoring a document
     * @param {string} docId - Document ID to stop monitoring
     */
    stopMonitoring(docId) {
        this.activeChecks.delete(docId);
        console.log(`Stopped monitoring document ${docId}`);
    }

    /**
     * Stop all monitoring
     */
    stopAllMonitoring() {
        this.activeChecks.clear();
        console.log('Stopped all background processing monitoring');
    }
}

// Create global instance
window.backgroundProcessingHelper = new BackgroundProcessingHelper();

// Auto-start monitoring for loan documents when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on a document page
    const urlPath = window.location.pathname;
    const docMatch = urlPath.match(/\/document\/([^\/]+)/);
    
    if (docMatch) {
        const docId = docMatch[1];
        console.log(`Auto-starting background processing monitor for document ${docId}`);
        
        // Start monitoring with UI updates
        window.backgroundProcessingHelper.monitorDocument(
            docId,
            (status) => {
                // On completion, show notification and refresh
                console.log('Background processing completed!', status);
                
                // Show success message
                if (typeof showNotification === 'function') {
                    showNotification('Background processing completed! Document updated with extracted data.', 'success');
                }
                
                // Refresh the page to show updated data
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            },
            (stage, progress, status) => {
                // On progress, update UI
                console.log(`Background processing: ${stage} (${progress}%)`);
                
                // Update progress indicator if it exists
                const progressElement = document.getElementById('background-progress');
                if (progressElement) {
                    progressElement.innerHTML = `
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <div class="progress-text">${stage}: ${progress}%</div>
                    `;
                }
            }
        );
    }
});

// Utility function to show notifications (implement based on your UI framework)
function showNotification(message, type = 'info') {
    // Simple alert fallback - replace with your notification system
    if (type === 'success') {
        console.log('✅ ' + message);
    } else if (type === 'error') {
        console.error('❌ ' + message);
    } else {
        console.log('ℹ️ ' + message);
    }
    
    // You can replace this with your actual notification system
    // For example: toast notifications, modal dialogs, etc.
}