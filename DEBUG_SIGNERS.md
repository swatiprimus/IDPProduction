# Debug Signers Not Showing - Step by Step

## Problem
Signer fields are showing as individual fields (Signer1_Address, Signer2_Address) instead of being grouped into collapsible "Signer 1", "Signer 2" sections.

## Root Cause
The issue is likely one of:
1. **Browser cache** - Old JavaScript is cached
2. **Data format** - Backend isn't flattening correctly
3. **Regex not matching** - Field names don't match expected pattern

## Step-by-Step Debugging

### Step 1: Clear Browser Cache (CRITICAL)
The browser is caching the old JavaScript. You MUST clear it:

**Option A: Hard Refresh**
- Windows: `Ctrl + Shift + R` or `Ctrl + F5`
- Mac: `Cmd + Shift + R`
- Do this 2-3 times!

**Option B: Clear Cache in DevTools**
1. Press `F12` to open DevTools
2. Go to "Network" tab
3. Check "Disable cache" checkbox
4. Keep DevTools open
5. Refresh the page

**Option C: Incognito/Private Window**
- Open in incognito mode (Ctrl + Shift + N)
- This bypasses all cache

### Step 2: Check Console Logs
Open browser console (F12) and look for these messages:

**What you SHOULD see:**
```
Processing field: Signer1_Name = John Doe
✓ MATCHED SIGNER FIELD: Signer1_Name -> Signer 1, Field: Name
✓ Created signer group 1
✓ Added to Signer 1: Name = John Doe
Processing field: Signer1_SSN = 123-45-6789
✓ MATCHED SIGNER FIELD: Signer1_SSN -> Signer 1, Field: SSN
✓ Added to Signer 1: SSN = 123-45-6789
...
Displaying 2 signer groups: [1, 2]
```

**What you might see (BAD):**
```
Processing field: Signer1_Name = John Doe
⚠️ Field contains 'signer' but didn't match regex: Signer1_Name
```

This means the regex isn't matching - check field names.

### Step 3: Inspect the Data
In console, type:
```javascript
// Get the current page data
fetch(window.location.href.replace('/accounts', '/api/document/YOUR_DOC_ID/account/0/page/0/data'))
  .then(r => r.json())
  .then(d => {
    console.log('Raw data:', d.data);
    console.log('Field names:', Object.keys(d.data));
    console.log('Signer fields:', Object.keys(d.data).filter(k => k.includes('Signer')));
  });
```

**Expected output:**
```
Signer fields: ["Signer1_Name", "Signer1_SSN", "Signer1_DateOfBirth", "Signer2_Name", ...]
```

**If you see:**
```
Signer fields: ["Signer1", "Signer2"]  ← Objects, not flat fields
```
Then the backend flattening isn't working.

### Step 4: Migrate the Cache
Run this in console to flatten existing cache:
```javascript
fetch('/api/document/YOUR_DOC_ID/migrate-cache', {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    console.log(d);
    alert('Migration complete! Refresh the page.');
  });
```

Replace `YOUR_DOC_ID` with your actual document ID (check URL).

### Step 5: Check Server Logs
Look at the server console for:
```
[DEBUG] Flattening signer object: Signer1 with 6 fields
[DEBUG] Created flat field: Signer1_Name = John Doe
[DEBUG] Created flat field: Signer1_SSN = 123-45-6789
[DEBUG] Applied flattening to cached data
```

If you don't see these, the backend isn't flattening.

### Step 6: Test the Regex
In browser console, test the regex:
```javascript
// Test the regex pattern
const testFields = [
  'Signer1_Name',
  'Signer_1_Name',
  'signer1_name',
  'Signer2_SSN',
  'AccountNumber'
];

testFields.forEach(field => {
  const match = field.match(/^Signer_?(\d+)_(.+)$/i);
  console.log(`${field}: ${match ? '✓ MATCH' : '✗ NO MATCH'}`, match);
});
```

**Expected output:**
```
Signer1_Name: ✓ MATCH ["Signer1_Name", "1", "Name"]
Signer_1_Name: ✓ MATCH ["Signer_1_Name", "1", "Name"]
signer1_name: ✓ MATCH ["signer1_name", "1", "name"]
Signer2_SSN: ✓ MATCH ["Signer2_SSN", "2", "SSN"]
AccountNumber: ✗ NO MATCH null
```

## Solutions

### Solution 1: Force Clear Cache
```javascript
// Run in console
localStorage.clear();
sessionStorage.clear();
location.reload(true);
```

### Solution 2: Migrate Cache
```javascript
// Get document ID from URL
const docId = window.location.pathname.split('/')[2];

// Migrate cache
fetch(`/api/document/${docId}/migrate-cache`, {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    console.log(d);
    location.reload();
  });
```

### Solution 3: Clear and Re-extract
```javascript
// Get document ID from URL
const docId = window.location.pathname.split('/')[2];

// Clear cache (forces re-extraction)
fetch(`/api/document/${docId}/clear-cache`, {method: 'POST'})
  .then(r => r.json())
  .then(d => {
    console.log(d);
    alert('Cache cleared! Click on pages to re-extract.');
  });
```

### Solution 4: Re-upload Document
The easiest solution - just upload the document again. New extraction will use correct format.

## Verification Checklist

After trying solutions, verify:

- [ ] Hard refreshed browser (Ctrl + Shift + R) multiple times
- [ ] Opened in incognito mode to test
- [ ] Console shows "✓ MATCHED SIGNER FIELD" messages
- [ ] Console shows "Displaying X signer groups"
- [ ] See "👥 Signers Information" header
- [ ] See "👤 Signer 1", "👤 Signer 2" collapsible sections
- [ ] Can click to expand/collapse signers
- [ ] Fields are grouped under each signer

## Still Not Working?

### Check Field Names
The fields MUST be named exactly:
- `Signer1_Name` ✓
- `Signer1_SSN` ✓
- `Signer_1_Name` ✓ (also works)
- `signer1_name` ✓ (case insensitive)

NOT:
- `Signer_Name` ✗ (missing number)
- `Signer1Name` ✗ (missing underscore)
- `Signer 1 Name` ✗ (spaces not allowed)

### Check Data Structure
In console:
```javascript
// Check if data is flat or nested
const data = /* your page data */;
console.log('Is Signer1 an object?', typeof data.Signer1 === 'object');
console.log('Has Signer1_Name?', 'Signer1_Name' in data);
```

Should see:
```
Is Signer1 an object? false
Has Signer1_Name? true
```

### Manual Test
Create a test page with known data:
```javascript
const testData = {
  AccountNumber: "123456",
  Signer1_Name: "John Doe",
  Signer1_SSN: "123-45-6789",
  Signer2_Name: "Jane Doe",
  Signer2_SSN: "987-65-4321"
};

// Test grouping logic
const signerGroups = {};
for (const [key, value] of Object.entries(testData)) {
  const match = key.match(/^Signer_?(\d+)_(.+)$/i);
  if (match) {
    const signerNum = parseInt(match[1]);
    const fieldName = match[2];
    if (!signerGroups[signerNum]) signerGroups[signerNum] = {};
    signerGroups[signerNum][fieldName] = value;
  }
}

console.log('Signer groups:', signerGroups);
// Should show: {1: {Name: "John Doe", SSN: "..."}, 2: {...}}
```

## Quick Fix Commands

Run these in browser console:

```javascript
// 1. Get document ID
const docId = window.location.pathname.split('/')[2];
console.log('Document ID:', docId);

// 2. Migrate cache
await fetch(`/api/document/${docId}/migrate-cache`, {method: 'POST'})
  .then(r => r.json())
  .then(d => console.log('Migration:', d));

// 3. Clear all cache
localStorage.clear();
sessionStorage.clear();

// 4. Hard reload
location.reload(true);
```

## Summary

The most common issue is **browser cache**. The fix:
1. Hard refresh (Ctrl + Shift + R) 3 times
2. Or open in incognito mode
3. Check console for "✓ MATCHED SIGNER FIELD" messages
4. If still not working, run migration script

The signers WILL display in collapsible sections once the cache is cleared!
