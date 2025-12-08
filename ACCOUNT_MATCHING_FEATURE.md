# Account Number Matching & Update Feature

## Overview
The system now automatically detects when a newly uploaded document contains an account number that already exists in the database. When a match is found, the system intelligently merges the new information with the existing record and highlights the changes for review.

## How It Works

### 1. Account Number Detection
When a document is uploaded, the system:
- Extracts the account number from the document
- Normalizes it (removes spaces, dashes) for comparison
- Searches through all existing documents for a match
- Checks in multiple locations:
  - `basic_fields.account_number`
  - `documents[].extracted_fields.account_number`
  - `documents[].accounts[].accountNumber`

### 2. Automatic Merging
If an existing account is found:
- **Only changed fields are updated** - unchanged data remains intact
- **New fields are added** - if the new document has fields not in the existing record
- **Change tracking** - all modifications are logged with:
  - Field name
  - Change type (added/updated)
  - Old value (for updates)
  - New value
- **Metadata updates**:
  - `last_updated` - timestamp of the merge
  - `update_source_filename` - name of the file that triggered the update
  - `needs_review` - flag set to `true`
  - `changes` - array of all changes made

### 3. Visual Indicators

#### Dashboard View
- Updated documents are highlighted with a **yellow background**
- A **"Needs Review"** badge shows the number of changes
- Hover over the badge to see a tooltip with change details
- The row has a distinct left border to draw attention

#### Document Viewer
- A **notification banner** appears at the top showing:
  - Warning icon
  - "This document has been updated and needs review"
  - Number of fields changed
  - Source filename (if available)
  - "Mark as Reviewed" button

### 4. Review Process
1. Open the updated document from the dashboard
2. Review the changes in the document viewer
3. Verify the updated information is correct
4. Click **"Mark as Reviewed"** button
5. The document is marked as reviewed and the banner disappears
6. Changes are moved to history for audit trail

## Example Scenarios

### Scenario 1: Name Update
**Existing Record:**
```json
{
  "account_number": "0210630620",
  "account_holder_name": "John Doe",
  "ssn": "123-45-6789"
}
```

**New Upload:**
```json
{
  "account_number": "0210630620",
  "account_holder_name": "John A. Doe",
  "ssn": "123-45-6789"
}
```

**Result:**
- Name is updated from "John Doe" to "John A. Doe"
- SSN remains unchanged
- 1 change tracked: `account_holder_name` updated
- Document flagged for review

### Scenario 2: Additional Information
**Existing Record:**
```json
{
  "account_number": "468869904",
  "account_holder_name": "Jane Smith"
}
```

**New Upload:**
```json
{
  "account_number": "468869904",
  "account_holder_name": "Jane Smith",
  "phone": "(555) 123-4567",
  "email": "jane@example.com"
}
```

**Result:**
- Name remains unchanged
- Phone and email are added
- 2 changes tracked: `phone` added, `email` added
- Document flagged for review

### Scenario 3: Multiple Accounts
For loan documents with multiple accounts:
- Each account is matched individually
- Changes are tracked per account
- All accounts in the document are merged appropriately

## API Endpoints

### Mark Document as Reviewed
```
POST /api/document/<doc_id>/mark-reviewed
```

**Response:**
```json
{
  "success": true,
  "message": "Document marked as reviewed"
}
```

**Effect:**
- Sets `needs_review` to `false`
- Adds `reviewed_at` timestamp
- Moves changes to `changes_history` for audit trail

## Database Structure

### Document Record with Changes
```json
{
  "id": "abc123",
  "filename": "account_update.pdf",
  "account_number": "0210630620",
  "needs_review": true,
  "last_updated": "2025-12-08T14:30:00",
  "update_source_filename": "new_account_info.pdf",
  "changes": [
    {
      "field": "basic_fields.account_holder_name",
      "change_type": "updated",
      "old_value": "John Doe",
      "new_value": "John A. Doe"
    },
    {
      "field": "basic_fields.phone",
      "change_type": "added",
      "new_value": "(555) 123-4567"
    }
  ],
  "changes_history": [
    {
      "changes": [...],
      "reviewed_at": "2025-12-07T10:15:00"
    }
  ]
}
```

## Benefits

1. **Data Integrity** - Prevents duplicate account records
2. **Audit Trail** - Complete history of all changes
3. **Efficiency** - Automatic merging saves manual work
4. **Transparency** - Clear visibility of what changed
5. **Control** - Review process ensures accuracy

## Technical Implementation

### Key Functions

#### `find_existing_document_by_account(account_number)`
Searches for an existing document with the given account number.

#### `merge_document_fields(existing_doc, new_doc)`
Merges new document fields into existing document, tracking all changes.

#### Process Flow
1. Document uploaded → `process_document()`
2. Document processed → `process_job()`
3. Account number extracted
4. Check for existing account → `find_existing_document_by_account()`
5. If found → `merge_document_fields()`
6. Save merged document → `save_documents_db()`
7. Display with review indicator

## Future Enhancements

Potential improvements:
- Email notifications when documents are updated
- Detailed change diff view
- Approval workflow for sensitive changes
- Automatic conflict resolution rules
- Batch review for multiple updated documents
