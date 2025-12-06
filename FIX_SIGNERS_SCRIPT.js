// Copy and paste this into your browser console (F12)
// This will diagnose and fix signer display issues

// STEP 1: Get the document ID from the current page
const docId = window.location.pathname.split('/')[2] || prompt('Enter document ID:');
const accountIndex = 0; // Change if needed
const pageNum = 0; // Change if needed

console.log('=== SIGNER DIAGNOSTIC TOOL ===');
console.log('Document ID:', docId);

// STEP 2: Check what fields exist in the cache
async function checkFields() {
    console.log('\n1. Checking cached fields...');
    
    try {
        const response = await fetch(`/api/document/${docId}/debug-cache/${accountIndex}/${pageNum}`);
        const data = await response.json();
        
        console.log('Total fields:', data.total_fields);
        console.log('All field keys:', data.all_keys);
        console.log('Signer-related keys:', data.signer_keys);
        
        // Check if signers exist
        const signerPattern = /signer/i;
        const signerFields = data.all_keys.filter(k => signerPattern.test(k));
        
        console.log('\n2. Signer field analysis:');
        console.log('Fields containing "signer":', signerFields);
        
        if (signerFields.length === 0) {
            console.warn('⚠️ NO SIGNER FIELDS FOUND!');
            console.log('This document may not have signer data, or it was not extracted.');
            return false;
        }
        
        // Check field format
        const flatFormat = signerFields.filter(k => /signer\d+_/i.test(k));
        const nestedFormat = signerFields.filter(k => /^Signer\d+$/i.test(k));
        
        console.log('Flat format fields (Signer1_Name):', flatFormat);
        console.log('Nested format fields (Signer1):', nestedFormat);
        
        if (nestedFormat.length > 0) {
            console.warn('⚠️ NESTED FORMAT DETECTED - Need to migrate cache!');
            return 'migrate';
        }
        
        if (flatFormat.length > 0) {
            console.log('✓ Flat format detected - should work!');
            return 'ok';
        }
        
        console.log('Sample signer data:', data.sample_data);
        return 'unknown';
        
    } catch (error) {
        console.error('Error checking fields:', error);
        return false;
    }
}

// STEP 3: Migrate cache if needed
async function migrateCache() {
    console.log('\n3. Migrating cache to flatten nested objects...');
    
    try {
        const response = await fetch(`/api/document/${docId}/migrate-cache`, {method: 'POST'});
        const data = await response.json();
        
        console.log('Migration result:', data);
        
        if (data.success) {
            console.log('✓ Cache migrated successfully!');
            console.log(`Updated ${data.message}`);
            return true;
        } else {
            console.error('✗ Migration failed:', data.message);
            return false;
        }
    } catch (error) {
        console.error('Error migrating cache:', error);
        return false;
    }
}

// STEP 4: Clear cache if migration doesn't work
async function clearCache() {
    console.log('\n4. Clearing cache to force re-extraction...');
    
    try {
        const response = await fetch(`/api/document/${docId}/clear-cache`, {method: 'POST'});
        const data = await response.json();
        
        console.log('Clear cache result:', data);
        
        if (data.success) {
            console.log('✓ Cache cleared successfully!');
            console.log('Click on pages to re-extract with new prompts.');
            return true;
        } else {
            console.error('✗ Clear cache failed:', data.message);
            return false;
        }
    } catch (error) {
        console.error('Error clearing cache:', error);
        return false;
    }
}

// STEP 5: Run the diagnostic
async function runDiagnostic() {
    const status = await checkFields();
    
    if (status === false) {
        console.log('\n❌ PROBLEM: No signer fields found or error occurred');
        console.log('SOLUTION: Document may not have signers, or extraction failed');
        console.log('Try: Clear cache and re-extract');
        
        const shouldClear = confirm('Clear cache and re-extract?');
        if (shouldClear) {
            await clearCache();
            alert('Cache cleared! Click on pages to re-extract.');
        }
        return;
    }
    
    if (status === 'migrate') {
        console.log('\n⚠️ PROBLEM: Signers in nested format');
        console.log('SOLUTION: Migrate cache to flatten');
        
        const shouldMigrate = confirm('Migrate cache to fix signer format?');
        if (shouldMigrate) {
            const success = await migrateCache();
            if (success) {
                alert('Cache migrated! Refreshing page...');
                location.reload();
            } else {
                console.log('Migration failed. Try clearing cache instead.');
                const shouldClear = confirm('Clear cache and re-extract?');
                if (shouldClear) {
                    await clearCache();
                    alert('Cache cleared! Click on pages to re-extract.');
                }
            }
        }
        return;
    }
    
    if (status === 'ok') {
        console.log('\n✓ SIGNERS SHOULD BE WORKING!');
        console.log('If not visible, try:');
        console.log('1. Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)');
        console.log('2. Clear browser cache');
        console.log('3. Open in incognito/private window');
        
        const shouldRefresh = confirm('Hard refresh the page now?');
        if (shouldRefresh) {
            location.reload(true);
        }
        return;
    }
    
    console.log('\n❓ UNKNOWN STATUS');
    console.log('Check the console output above for details');
}

// Run it!
runDiagnostic();
