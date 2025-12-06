# Test Signer Detection

## Quick Test in Browser Console

Open browser console (F12) and run this test:

```javascript
// Test 1: Check if regex works
const testFields = {
    "Signer1_Name": "John Doe",
    "Signer1_SSN": "123-45-6789",
    "Signer2_Name": "Jane Doe",
    "Signer2_SSN": "987-65-4321",
    "AccountNumber": "12345",
    "AccountType": "Personal"
};

console.log("=== TESTING SIGNER DETECTION ===");

const signerGroups = {};
const regularFields = {};

for (const [key, value] of Object.entries(testFields)) {
    console.log(`Testing: ${key}`);
    
    if (key === 'AccountNumber') {
        console.log("  → Skipped (AccountNumber)");
        continue;
    }
    
    // Test the regex
    const signerFieldMatch = key.match(/^Signer_?(\d+)_(.+)$/i);
    if (signerFieldMatch && signerFieldMatch[1]) {
        const signerNum = parseInt(signerFieldMatch[1]);
        const fieldName = signerFieldMatch[2];
        console.log(`  ✓ MATCHED! Signer ${signerNum}, Field: ${fieldName}`);
        
        if (!signerGroups[signerNum]) {
            signerGroups[signerNum] = {};
        }
        signerGroups[signerNum][fieldName] = value;
    } else {
        console.log(`  → Regular field`);
        regularFields[key] = value;
    }
}

console.log("\n=== RESULTS ===");
console.log("Signer Groups:", signerGroups);
console.log("Regular Fields:", regularFields);
console.log("Number of signers:", Object.keys(signerGroups).length);
```

## Expected Output

You should see:
```
=== TESTING SIGNER DETECTION ===
Testing: Signer1_Name
  ✓ MATCHED! Signer 1, Field: Name
Testing: Signer1_SSN
  ✓ MATCHED! Signer 1, Field: SSN
Testing: Signer2_Name
  ✓ MATCHED! Signer 2, Field: Name
Testing: Signer2_SSN
  ✓ MATCHED! Signer 2, Field: SSN
Testing: AccountNumber
  → Skipped (AccountNumber)
Testing: AccountType
  → Regular field

=== RESULTS ===
Signer Groups: {1: {Name: "John Doe", SSN: "123-45-6789"}, 2: {Name: "Jane Doe", SSN: "987-65-4321"}}
Regular Fields: {AccountType: "Personal"}
Number of signers: 2
```

## Test 2: Check Actual Page Data

```javascript
// Get the current page data
const docId = "YOUR_DOC_ID";  // Replace with actual doc ID
const accountIndex = 0;  // Replace with actual account index
const pageNum = 0;  // Replace with actual page number

fetch(`/api/document/${docId}/debug-cache/${accountIndex}/${pageNum}`)
    .then(r => r.json())
    .then(data => {
        console.log("=== ACTUAL PAGE DATA ===");
        console.log("Total fields:", data.total_fields);
        console.log("All keys:", data.all_keys);
        console.log("Signer keys:", data.signer_keys);
        console.log("Sample data:", data.sample_data);
        
        // Test if any keys match signer pattern
        const signerPattern = /^Signer_?(\d+)_(.+)$/i;
        const matchingKeys = data.all_keys.filter(k => signerPattern.test(k));
        console.log("Keys matching signer pattern:", matchingKeys);
    });
```

## Test 3: Migrate and Check

```javascript
// Migrate the cache
fetch(`/api/document/${docId}/migrate-cache`, {method: 'POST'})
    .then(r => r.json())
    .then(data => {
        console.log("Migration result:", data);
        
        // Now check the data again
        return fetch(`/api/document/${docId}/debug-cache/${accountIndex}/${pageNum}`);
    })
    .then(r => r.json())
    .then(data => {
        console.log("After migration:");
        console.log("Signer keys:", data.signer_keys);
    });
```

## Common Issues

### Issue 1: No Signer Fields at All
**Symptom**: `signer_keys: []`
**Cause**: Document doesn't have signer data OR LLM didn't extract it
**Solution**: 
1. Check if document actually has signers
2. Clear cache and re-extract: `fetch('/api/document/DOC_ID/clear-cache', {method: 'POST'})`

### Issue 2: Nested Signer Objects
**Symptom**: `Signer1: {Name: "John", SSN: "123"}`
**Cause**: Old cache format
**Solution**: Run migration: `fetch('/api/document/DOC_ID/migrate-cache', {method: 'POST'})`

### Issue 3: Wrong Field Names
**Symptom**: Fields like `signer_1_name` (lowercase) or `Signer_Name` (no number)
**Cause**: LLM not following prompt
**Solution**: Clear cache and re-extract with updated prompt

### Issue 4: Browser Cache
**Symptom**: Changes not reflecting
**Solution**: 
1. Hard refresh: `Ctrl + Shift + R` (Windows) or `Cmd + Shift + R` (Mac)
2. Clear browser cache
3. Open in incognito/private window

## Debugging Checklist

- [ ] Run Test 1 - Does regex work? (Should always pass)
- [ ] Run Test 2 - What fields exist in cache?
- [ ] Check if document has signer data
- [ ] Run migration if needed
- [ ] Clear cache if needed
- [ ] Hard refresh browser
- [ ] Check server logs for flattening messages

## Server Log Messages to Look For

```
[DEBUG] Flattening signer object: Signer1 with X fields
[DEBUG] Created flat field: Signer1_Name = John Doe
[DEBUG] Applied flattening to cached data
```

If you don't see these, the flattening isn't happening.
