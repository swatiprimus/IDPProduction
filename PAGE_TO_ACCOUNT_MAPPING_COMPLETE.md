# ✅ Page-to-Account Mapping - COMPLETE!

## 🎉 What's New

### Dynamic Data Display Based on Page
- **Each page shows its associated account data**
- Navigate to Page 1 → See Account 1 data
- Navigate to Page 2 → See Account 2 data (if different account)
- Navigate to Page 3 → See Account 3 data (if different account)

### Intelligent Account Mapping
- System automatically maps pages to accounts
- For loan documents: Pages distributed across accounts
- For regular documents: Shows all document data

### Page-Specific Editing
- Edit fields for the account shown on current page
- Save updates to the correct account
- Each page/account is independent

## ✨ How It Works

### For Loan Documents with Multiple Accounts

**Example: 3-page document with 2 accounts**
```
Page 1 → Account 123456789
  - Shows Account 123456789 data
  - Edit fields for this account
  - Save updates this account

Page 2 → Account 987654321  
  - Shows Account 987654321 data
  - Edit fields for this account
  - Save updates this account

Page 3 → Account 987654321
  - Shows Account 987654321 data
  - Same account as Page 2
```

### For Regular Documents

**Example: Death Certificate (3 pages)**
```
Page 1 → All document data
Page 2 → All document data
Page 3 → All document data
  - Same data on all pages
  - Edit any field on any page
  - Changes apply to the document
```

## 📊 Visual Indicators

### Page Header Shows Account Info
```
┌─────────────────────────────────┐
│ Extracted Data                  │
│ Page 1 - Account 123456789      │ ← Shows which account
│ 92% Accuracy                    │
│ [📝 Edit Page]                  │
└─────────────────────────────────┘
```

### Navigate to Different Page
```
┌─────────────────────────────────┐
│ Extracted Data                  │
│ Page 2 - Account 987654321      │ ← Different account!
│ 85% Accuracy                    │
│ [📝 Edit Page]                  │
└─────────────────────────────────┘
```

## 🎯 Workflow

### Step 1: Open Page Viewer
1. Go to dashboard
2. Click "Pages" button on loan document
3. Page viewer opens

### Step 2: Navigate Pages
- Page 1 loads → Shows Account 1 data
- Click "Next →" → Shows Account 2 data (if different)
- Click "Next →" → Shows Account 3 data (if different)

### Step 3: Edit Account Data
1. Click "📝 Edit Page"
2. Edit fields for current account
3. Click "✓ Save Page"
4. Changes save to that specific account

### Step 4: Move to Next Account
1. Click "Next →"
2. See different account data
3. Edit if needed
4. Save changes

## 🔧 Technical Details

### Page-to-Account Mapping Algorithm
```
For loan documents with N accounts and M pages:
- Pages per account = M / N
- Page 0 to (M/N - 1) → Account 0
- Page (M/N) to (2M/N - 1) → Account 1
- And so on...
```

**Example:**
- 6 pages, 2 accounts
- Pages per account = 6 / 2 = 3
- Pages 0-2 → Account 0
- Pages 3-5 → Account 1

### API Response
```json
{
  "success": true,
  "pages": [
    {
      "page_number": 1,
      "url": "/api/document/abc123/page/0",
      "account_index": 0,
      "account_number": "123456789"
    },
    {
      "page_number": 2,
      "url": "/api/document/abc123/page/1",
      "account_index": 0,
      "account_number": "123456789"
    },
    {
      "page_number": 3,
      "url": "/api/document/abc123/page/2",
      "account_index": 1,
      "account_number": "987654321"
    }
  ],
  "has_accounts": true,
  "total_accounts": 2
}
```

### Frontend Logic
```javascript
// Get current page info
const currentPage = pagesData.pages[currentPageIndex];
const accountIndex = currentPage.account_index;
const accountNumber = currentPage.account_number;

// Show account-specific data
if (hasAccounts && accountIndex !== undefined) {
    const account = docData.accounts[accountIndex];
    fields = account.result;
    accuracy = account.accuracy_score;
}
```

## 📝 Usage Examples

### Example 1: Loan Document with 2 Accounts

**Page 1:**
```
Document Page: [Shows page 1 image]
Extracted Data: Page 1 - Account 123456789
  - AccountHolderNames: John Doe
  - AccountType: Personal
  - SSN: 123-45-6789
  - [Edit Page] [Save Page]
```

**Page 2:**
```
Document Page: [Shows page 2 image]
Extracted Data: Page 2 - Account 987654321
  - AccountHolderNames: Jane Smith
  - AccountType: Business
  - SSN: 987-65-4321
  - [Edit Page] [Save Page]
```

### Example 2: Regular Document

**All Pages:**
```
Document Page: [Shows current page image]
Extracted Data: Page X Data
  - Full Name: Mary J. Carbaugh
  - Date of Death: January 9, 2016
  - SSN: 221-28-5988
  - [Edit Page] [Save Page]
```

## 🎓 Best Practices

### 1. **Review Each Account Separately**
- Navigate page by page
- Review data for each account
- Edit as needed
- Save before moving to next

### 2. **Check Account Numbers**
- Page header shows account number
- Verify you're editing the right account
- Each account is independent

### 3. **Save Per Account**
- Save changes for current account
- Move to next page/account
- Save changes for that account
- Organized workflow

### 4. **Use Page Navigation**
- Use arrows to move between pages
- Watch the account number change
- Edit the account shown on current page

## 🆚 Comparison

### Before (All Data on All Pages)
- Page 1 → Shows all accounts data
- Page 2 → Shows all accounts data
- Page 3 → Shows all accounts data
- Confusing which data belongs to which page

### After (Page-Specific Data)
- Page 1 → Shows Account 1 data only
- Page 2 → Shows Account 2 data only
- Page 3 → Shows Account 3 data only
- Clear mapping between page and account

## ⚠️ Important Notes

### Account Distribution
- Pages are distributed evenly across accounts
- If 6 pages and 2 accounts: 3 pages per account
- If 5 pages and 2 accounts: 2-3 pages per account

### Editing Scope
- Edits apply to the account shown on current page
- Saving Page 1 updates Account 1
- Saving Page 2 updates Account 2
- Each account is independent

### Navigation Warning
- If you have unsaved edits and switch pages
- System warns you
- Choose to save or discard

## ✅ Status

**Server**: Running on http://127.0.0.1:5015
**Feature**: Fully functional
**Mapping**: Automatic page-to-account mapping
**Editing**: Account-specific updates

## 🚀 Quick Start

```
1. Go to: http://localhost:5015/dashboard
2. Upload: A loan document with multiple accounts
3. Click: "Pages" button
4. Navigate: Through pages
5. Observe: Data changes based on page/account
6. Edit: Fields for current account
7. Save: Updates that specific account
```

---

**The page-to-account mapping is ready!** 🎉

Now each page shows its associated account data, making it easy to review and edit account-specific information!
