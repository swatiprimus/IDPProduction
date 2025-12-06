# Signer Display - Visual Guide

## New Signer Section Design

The signers are now displayed in beautiful, collapsible sections with a modern design.

## Visual Layout

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  👥 Signers Information                    [2 Signers] │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  👤 Signer 1                    [6 fields]         ▼   │  ← Click to collapse
├─────────────────────────────────────────────────────────┤
│  Name                                                   │
│  Danette Eberly                                         │
├─────────────────────────────────────────────────────────┤
│  SSN                                                    │
│  222-50-2263                                            │
├─────────────────────────────────────────────────────────┤
│  Date Of Birth                                          │
│  12/3/1956                                              │
├─────────────────────────────────────────────────────────┤
│  Address                                                │
│  512 PONDEROSA DR, BEAR, DE, 19701-2155                │
├─────────────────────────────────────────────────────────┤
│  Phone                                                  │
│  (302) 834-0382                                         │
├─────────────────────────────────────────────────────────┤
│  Drivers License                                        │
│  719077                                                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  👤 Signer 2                    [6 fields]         ▼   │  ← Click to collapse
├─────────────────────────────────────────────────────────┤
│  Name                                                   │
│  R Bruce Eberly                                         │
├─────────────────────────────────────────────────────────┤
│  SSN                                                    │
│  199400336                                              │
├─────────────────────────────────────────────────────────┤
│  Date Of Birth                                          │
│  11/17/1949                                             │
├─────────────────────────────────────────────────────────┤
│  Address                                                │
│  512 PONDEROSA DR, BEAR, DE, 19701-2155                │
├─────────────────────────────────────────────────────────┤
│  Phone                                                  │
│  (302) 834-0382                                         │
├─────────────────────────────────────────────────────────┤
│  Drivers License                                        │
│  651782                                                 │
└─────────────────────────────────────────────────────────┘
```

## Features

### 1. Section Header
- **Icon**: 👥 Signers Information
- **Badge**: Shows total number of signers (e.g., "2 Signers")
- **Color**: Light gray background with purple accent

### 2. Individual Signer Headers
- **Gradient Background**: Purple gradient (looks professional)
- **Icon**: 👤 for each signer
- **Signer Number**: "Signer 1", "Signer 2", etc.
- **Field Count Badge**: Shows how many fields (e.g., "6 fields")
- **Collapse Icon**: ▼ (down arrow when expanded, ► when collapsed)
- **Interactive**: Click to expand/collapse

### 3. Signer Fields
- **Left Border**: Purple accent line connecting to header
- **Clean Layout**: Each field on its own row
- **Editable**: Click any field to edit (if edit mode enabled)
- **Smart Display**: Only shows fields with actual values

### 4. Styling Details
- **Colors**: 
  - Header: Purple gradient (#667eea to #764ba2)
  - Text: White on header, dark on fields
  - Border: Purple accent (#667eea)
- **Spacing**: Proper margins between sections
- **Shadow**: Subtle shadow on headers for depth
- **Animation**: Smooth collapse/expand transition

## How It Works

### Data Structure
The backend flattens signer data:
```javascript
{
  "Signer1_Name": "Danette Eberly",
  "Signer1_SSN": "222-50-2263",
  "Signer1_DateOfBirth": "12/3/1956",
  "Signer2_Name": "R Bruce Eberly",
  "Signer2_SSN": "199400336",
  "Signer2_DateOfBirth": "11/17/1949"
}
```

### Frontend Grouping
The template groups fields by signer number:
```javascript
// Regex matches: Signer1_Name, Signer2_SSN, etc.
const signerFieldMatch = key.match(/^Signer_?(\d+)_(.+)$/i);

// Groups into:
signerGroups = {
  1: { Name: "Danette Eberly", SSN: "222-50-2263", ... },
  2: { Name: "R Bruce Eberly", SSN: "199400336", ... }
}
```

### Display Logic
1. Check if any signer fields exist
2. If yes, show "Signers Information" header
3. For each signer number (sorted):
   - Create collapsible header
   - Add all fields for that signer
   - Only show if signer has data

## Console Debugging

When viewing a page, check the browser console (F12) for:

```javascript
Signer fields found: ["Signer1_Name", "Signer1_SSN", "Signer1_DateOfBirth", ...]
Created signer group 1
Added to Signer 1: Name = Danette Eberly
Added to Signer 1: SSN = 222-50-2263
Created signer group 2
Added to Signer 2: Name = R Bruce Eberly
Displaying 2 signer groups: [1, 2]
Signer groups data: {1: {...}, 2: {...}}
```

## Interaction

### Collapse/Expand
Click on any signer header to toggle:
- **Expanded**: ▼ icon, fields visible
- **Collapsed**: ► icon, fields hidden

### Edit Fields
Click on any field value to edit (if edit mode enabled):
- Field becomes editable
- Save changes
- Updates cache in S3

## Migration Steps

To see the new design with existing documents:

1. **Migrate Cache** (updates existing data):
   ```javascript
   fetch('/api/document/YOUR_DOC_ID/migrate-cache', {method: 'POST'})
     .then(r => r.json())
     .then(d => console.log(d));
   ```

2. **Hard Refresh**:
   - Press `Ctrl + Shift + R` (Windows)
   - Or `Cmd + Shift + R` (Mac)

3. **Check Console**:
   - Look for "Displaying X signer groups"
   - Verify signer data is grouped correctly

## Troubleshooting

### No Signers Showing?

1. **Check Console**:
   ```
   Signer fields found: []  ← No signer fields detected
   ```

2. **Check Field Names**:
   - Must start with "Signer"
   - Must have number: Signer1, Signer2
   - Must have underscore: Signer1_Name

3. **Migrate Cache**:
   - Old cache may have nested objects
   - Run migration endpoint

4. **Re-upload Document**:
   - New extraction will use correct format

### Signers Not Grouped?

Check console for:
```
Created signer group 1  ← Should see this for each signer
Added to Signer 1: Name = ...  ← Should see this for each field
```

If not, the regex might not be matching. Check field names.

## Benefits

1. **Visual Hierarchy**: Clear separation between signers
2. **Space Efficient**: Collapsible sections save space
3. **Professional Look**: Modern gradient design
4. **Easy to Scan**: Icons and badges help identify sections
5. **Interactive**: Click to expand/collapse as needed
6. **Scalable**: Works with any number of signers

## Summary

✅ Beautiful gradient headers with icons
✅ Collapsible sections for each signer
✅ Field count badges
✅ Smart grouping by signer number
✅ Only shows signers with data
✅ Smooth animations
✅ Professional design

Your signers will now display in organized, collapsible sections!
