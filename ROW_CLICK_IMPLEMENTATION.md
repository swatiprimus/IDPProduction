# Row Click Implementation - Complete

## Changes Made

### 1. Dashboard Row Click Behavior (skills_catalog.html)
- **Loan Documents (with accounts)**: Clicking the row opens the Account-Based Viewer (`/document/{id}/accounts`)
- **Other Documents (with PDF)**: Clicking the row opens the Page Viewer (`/document/{id}/pages`)
- **Documents without PDF**: Row click is disabled

### 2. Button Functionality Preserved
- **Green Button (🏦 Accounts)**: Only shown for loan documents with accounts - opens Account-Based Viewer
- **Blue Button (📄 Pages)**: Shown for all documents with PDF - opens Page Viewer
- Both buttons work independently and stop event propagation to prevent row click

### 3. Removed Old Document Detail Page
- Deleted route: `/document/<doc_id>` (view_document function)
- Deleted template: `templates/document_detail.html`
- Cleaned up unused code

## User Experience

### For Loan Documents:
1. Click anywhere on the row → Opens Account-Based Viewer
2. Click green "Accounts" button → Opens Account-Based Viewer
3. Click blue "Pages" button → Opens Page Viewer

### For Other Documents:
1. Click anywhere on the row → Opens Page Viewer
2. Click blue "Pages" button → Opens Page Viewer

## Technical Details

The row click handler intelligently determines which viewer to open:
```javascript
if (hasPDF && hasAccounts) {
    // Loan documents - open account viewer
    row.onclick = () => window.open(`/document/${skill.id}/accounts`, '_blank');
} else if (hasPDF) {
    // Other documents - open page viewer
    row.onclick = () => window.open(`/document/${skill.id}/pages`, '_blank');
} else {
    // No PDF - disable click
    row.style.cursor = 'default';
    row.onclick = null;
}
```

## Files Modified
1. `templates/skills_catalog.html` - Updated row click behavior
2. `universal_idp.py` - Removed old document detail route
3. `templates/document_detail.html` - Deleted (no longer needed)
