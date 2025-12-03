# Page-by-Page Document Viewer - User Guide

## 🎉 New Feature: Side-by-Side Document Viewer

View your documents page-by-page with extracted data side-by-side for easy comparison and editing!

## ✨ Features

### 1. **Page Navigation**
- View each page of your PDF document as a high-quality image
- Navigate using:
  - **Previous/Next buttons**
  - **Page thumbnails** (click any thumbnail)
  - **Keyboard arrows** (← →)

### 2. **Side-by-Side View**
- **Left Panel**: Original document page
- **Right Panel**: Extracted data fields
- Compare the source document with extracted data in real-time

### 3. **Inline Editing**
- Click any field to edit
- Changes save immediately
- Accuracy score updates automatically
- Perfect for data verification and correction

### 4. **Page Thumbnails**
- Quick overview of all pages
- Click to jump to any page
- Active page highlighted

## 🚀 How to Use

### Step 1: Access the Page Viewer

From the **Dashboard** (http://localhost:5015/dashboard):

1. Find any PDF document in the list
2. Click the **"Pages"** button (blue button with grid icon)
3. The page viewer opens in a new tab

### Step 2: Navigate Pages

**Using Buttons:**
- Click **"← Previous"** to go to previous page
- Click **"Next →"** to go to next page

**Using Thumbnails:**
- Scroll through thumbnails at the top
- Click any thumbnail to jump to that page

**Using Keyboard:**
- Press **←** (left arrow) for previous page
- Press **→** (right arrow) for next page

### Step 3: View and Compare Data

**Left Side:**
- Shows the actual document page
- High-quality image (200 DPI)
- Zoom by scrolling

**Right Side:**
- Shows all extracted fields
- Organized by field name
- Color-coded accuracy badge

### Step 4: Edit Fields

1. **Click on any field value** in the right panel
2. An input box appears with Save/Cancel buttons
3. **Edit the value**
4. **Click "✓ Save"** or press **Enter**
5. The field updates and accuracy recalculates
6. Changes are saved to the database

**Keyboard Shortcuts:**
- **Enter** = Save changes
- **Escape** = Cancel editing

## 📊 What You'll See

### Page Navigation Bar
```
[← Previous]  [Next →]          Page 1 of 5
```

### Page Thumbnails
```
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│ P1 │ │ P2 │ │ P3 │ │ P4 │ │ P5 │
└────┘ └────┘ └────┘ └────┘ └────┘
  ↑ Active page highlighted
```

### Document View
```
┌─────────────────────────────────────────────────┐
│                                                 │
│                                                 │
│          [Document Page Image]                  │
│                                                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Extracted Data Panel
```
┌─────────────────────────────┐
│ Extracted Data              │
│ 92% Accuracy                │
├─────────────────────────────┤
│ Full Name                   │
│ John Doe              ✎     │
├─────────────────────────────┤
│ Date of Birth               │
│ 01/15/1980            ✎     │
├─────────────────────────────┤
│ SSN                         │
│ 123-45-6789           ✎     │
└─────────────────────────────┘
```

## 🎯 Use Cases

### 1. **Data Verification**
- Compare extracted data with source document
- Verify accuracy field by field
- Correct any mistakes immediately

### 2. **Multi-Page Documents**
- Navigate through long documents easily
- See which page contains which data
- Edit data while viewing the source

### 3. **Quality Assurance**
- Review OCR accuracy
- Identify missing fields
- Ensure data completeness

### 4. **Training & Review**
- Train staff on data extraction
- Review AI extraction quality
- Document verification workflow

## 💡 Tips & Tricks

### Tip 1: Use Keyboard Navigation
- Much faster than clicking buttons
- Press ← and → to flip through pages quickly

### Tip 2: Check Thumbnails First
- Get an overview of the document
- Identify pages with important data
- Jump directly to relevant pages

### Tip 3: Edit While Viewing
- No need to switch between views
- Edit fields while looking at the source
- Reduces errors and saves time

### Tip 4: Watch the Accuracy Score
- Updates in real-time as you edit
- Aim for 100% accuracy
- Green = good, Yellow = needs work, Red = many missing fields

## 🔧 Technical Details

### Page Generation
- PDF pages converted to PNG images
- 200 DPI resolution for clarity
- Images cached for fast loading
- Thumbnails generated automatically

### Data Synchronization
- Edits save immediately to database
- Accuracy recalculates automatically
- Changes persist across sessions
- No data loss

### Performance
- First load: Converts PDF to images (may take a few seconds)
- Subsequent loads: Uses cached images (instant)
- Smooth page navigation
- Responsive interface

## 📁 File Structure

When you view a document, the system creates:

```
ocr_results/
└── pages/
    └── [document_id]/
        ├── page_1.png
        ├── page_2.png
        ├── page_3.png
        └── ...
```

These images are cached and reused for faster loading.

## 🐛 Troubleshooting

### Issue: Pages Not Loading
**Solution**: 
- Check if the PDF file exists
- Ensure `pdf2image` is installed: `pip install pdf2image`
- Check server logs for errors

### Issue: Thumbnails Not Showing
**Solution**:
- Refresh the page
- Check browser console for errors
- Verify images were created in `ocr_results/pages/`

### Issue: Can't Edit Fields
**Solution**:
- Make sure you're clicking on the field value (not the label)
- Check if the field is editable (some complex fields may not be)
- Refresh the page and try again

### Issue: Slow Page Loading
**Solution**:
- First load converts PDF (takes time)
- Subsequent loads use cache (fast)
- Large PDFs may take longer
- Check your internet connection

## 🆚 Comparison: Page Viewer vs. Detail View

### Page Viewer (New)
✅ Side-by-side comparison
✅ Page-by-page navigation
✅ Visual verification
✅ Inline editing
✅ Perfect for multi-page documents

### Detail View (Original)
✅ All data at once
✅ Full JSON view
✅ Download options
✅ Account-based view (for loan docs)
✅ Better for single-page or simple documents

**Use both!** They complement each other.

## 🎓 Best Practices

1. **Start with Page Viewer** for initial review
2. **Use thumbnails** to get document overview
3. **Navigate page-by-page** for thorough verification
4. **Edit fields** while viewing source
5. **Check accuracy score** after edits
6. **Switch to Detail View** for final review

## 🚀 Quick Start

```
1. Go to Dashboard: http://localhost:5015/dashboard
2. Find a PDF document
3. Click "Pages" button
4. Navigate through pages
5. Edit fields as needed
6. Done!
```

## 📞 Support

If you encounter issues:
1. Check server logs
2. Verify PDF file exists
3. Check browser console (F12)
4. Restart server if needed

---

**Enjoy the new page-by-page viewer!** 🎉

This feature makes document verification and data correction much easier and more accurate.
