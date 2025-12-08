#!/bin/bash

echo "=========================================="
echo "Starting Universal IDP - Modular Version"
echo "=========================================="
echo ""
echo "✓ Using Modular Services:"
echo "  - textract_service.py (OCR)"
echo "  - account_splitter.py (Account detection)"
echo "  - document_detector.py (Type detection)"
echo "  - loan_processor.py (Loan processing)"
echo ""
echo "✓ Features:"
echo "  - Clean, organized code"
echo "  - Easy to maintain and test"
echo "  - Same functionality as universal_idp.py"
echo "  - Comprehensive logging"
echo ""
echo "=========================================="
echo "Starting Flask server on port 5015..."
echo "=========================================="
echo ""

python app_modular.py
