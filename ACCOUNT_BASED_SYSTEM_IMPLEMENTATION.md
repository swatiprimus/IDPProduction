# Account-Based Document System - Implementation Plan

## ✅ What I've Created

### 1. New Account-Based Viewer Template
**File**: `templates/account_based_viewer.html`

**Features**:
- ✅ Account list sidebar (left)
- ✅ 50/50 split view (document viewer + data panel)
- ✅ Page navigation (Previous/Next)
- ✅ Page-level editing
- ✅ JSON download per page
- ✅ Clean, modern UI

## 🚀 What Still Needs to Be Done

### Backend API Endpoints Needed

Add these to `universal_idp.py`:

```python
@app.route("/document/<doc_id>/accounts")
def view_account_based(doc_id):
    """View document with account-based interface"""
    doc = next((d for d in processed_documents if d["id"] == doc_id), None)
    if doc:
        return render_template("account_based_viewer.html", document=doc)
    return "Document not found", 404

@app.route("/api/document/<doc_id>/account/<int:account_index>/pages")
def get_account_pages(doc_id, account_index):
    """Get pages for a specific account"""
    # Return page count and URLs for this account's pages
    pass

@app.route("/api/document/<doc_id>/account/<int:account_index>/page/<int:page_num>")
def get_account_page_image(doc_id, account_index, page_num):
    """Get specific page image for an account"""
    # Return the page image
    pass

@app.route("/api/document/<doc_id>/split_by_account")
def split_document_by_account(doc_id):
    """Split PDF by account numbers and generate TIFFs"""
    # 1. Read PDF
    # 2. Detect account numbers on each page
    # 3. Group pages by account
    # 4. Generate TIFF for each account
    # 5. Return account mapping
    pass
```

### Dashboard Integration

Update `templates/skills_catalog.html` to add "Accounts" button:

```javascript
const accountsButton = hasPDF ? `
    <button onclick="event.stopPropagation();window.open('/document/${skill.id}/accounts','_blank')" 
            style="padding:6px 10px;background:#10b981;color:white;border:none;border-radius:6px;cursor:pointer;">
        🏦 Accounts
    </button>
` : '';
```

## 📋 Complete Implementation Steps

### Step 1: Add Backend Routes
1. Open `universal_idp.py`
2. Add the 4 new routes listed above
3. Implement PDF splitting logic
4. Implement TIFF generation per account

### Step 2: Update Dashboard
1. Open `templates/skills_catalog.html`
2. Add "Accounts" button next to "Pages" button
3. Link to `/document/<id>/accounts`

### Step 3: Test the System
1. Upload a loan document
2. Click "Accounts" button
3. See list of accounts
4. Click an account
5. Navigate through pages
6. Edit and save data
7. Download JSON

## 🎯 System Flow

```
1. User uploads PDF
   ↓
2. System processes and extracts accounts
   ↓
3. Dashboard shows document with "Accounts" button
   ↓
4. Click "Accounts" → Opens account-based viewer
   ↓
5. Left sidebar shows all accounts
   ↓
6. Click account → Shows first page
   ↓
7. Document viewer (50%) | Data panel (50%)
   ↓
8. Navigate pages with Previous/Next
   ↓
9. Click "Edit Page" → Edit fields
   ↓
10. Click "Save Page" → Saves to database
    ↓
11. Click "Download JSON" → Downloads page data
```

## 📊 UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: Document Name                                          │
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                       │
│ Accounts │  Document Viewer (50%)  │  Data Panel (50%)         │
│ List     │                          │                           │
│          │  ┌────────────────────┐  │  Extracted Data          │
│ Account  │  │                    │  │  Account 123456789       │
│ 123456   │  │                    │  │  Page 1                  │
│ [Active] │  │   [Page Image]     │  │                          │
│          │  │                    │  │  [Edit] [Save] [Cancel]  │
│ Account  │  │                    │  │  [Download JSON]         │
│ 789012   │  │                    │  │                          │
│          │  └────────────────────┘  │  Field 1: Value          │
│ Account  │  [← Prev] Page 1/3 [Next→] Field 2: Value          │
│ 345678   │                          │  Field 3: Value          │
│          │                          │                           │
└──────────┴──────────────────────────┴───────────────────────────┘
```

## ✨ Features Implemented

### Account List Sidebar
- ✅ Shows all accounts
- ✅ Displays account number
- ✅ Shows accuracy and field count
- ✅ Click to select account
- ✅ Active state highlighting

### Document Viewer (50% width)
- ✅ Shows current page image
- ✅ Previous/Next navigation
- ✅ Page counter (Page X of Y)
- ✅ Large, clear display

### Data Panel (50% width)
- ✅ Shows extracted data for current page
- ✅ Account and page info in header
- ✅ Edit mode toggle
- ✅ Save/Cancel buttons
- ✅ Download JSON button
- ✅ Field-by-field editing

### Editing Features
- ✅ Click "Edit Page" to enable editing
- ✅ Click any field to edit
- ✅ Save all changes at once
- ✅ Cancel to discard changes
- ✅ Updates database on save

### Download Features
- ✅ Download JSON for current page
- ✅ Includes account number and page number
- ✅ Contains all extracted data

## 🔧 Technical Requirements

### PDF Splitting by Account
```python
import fitz  # PyMuPDF
import re

def split_pdf_by_account(pdf_path):
    pdf = fitz.open(pdf_path)
    account_pages = {}
    
    for page_num in range(len(pdf)):
        page = pdf[page_num]
        text = page.get_text()
        
        # Detect account number
        account_match = re.search(r'ACCOUNT NUMBER[:\s]*([0-9]{6,15})', text)
        if account_match:
            account_num = account_match.group(1)
            if account_num not in account_pages:
                account_pages[account_num] = []
            account_pages[account_num].append(page_num)
    
    return account_pages
```

### TIFF Generation
```python
from PIL import Image

def generate_tiff_for_account(pdf_path, page_numbers, output_path):
    pdf = fitz.open(pdf_path)
    images = []
    
    for page_num in page_numbers:
        page = pdf[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    
    # Save as multi-page TIFF
    if images:
        images[0].save(output_path, save_all=True, append_images=images[1:], compression="tiff_deflate")
```

## 📝 Next Steps

1. **Implement backend routes** in `universal_idp.py`
2. **Add "Accounts" button** to dashboard
3. **Test with loan documents**
4. **Refine account detection** logic
5. **Add TIFF generation** functionality

## 🎉 Benefits

- ✅ Clear account separation
- ✅ Easy navigation per account
- ✅ Page-by-page review
- ✅ 50/50 split for easy comparison
- ✅ Individual page editing
- ✅ JSON export per page
- ✅ Professional, clean UI

---

**Status**: Template created, backend implementation needed
**File**: `templates/account_based_viewer.html` ✅
**Next**: Add backend API routes
