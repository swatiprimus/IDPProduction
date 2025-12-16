# Cache Clearing Guide

## Why Cache Matters
When you modify Python code, the Flask server may still serve old cached responses. Similarly, browsers cache HTML, CSS, and JavaScript files. This can prevent you from seeing the effects of your code changes.

## How to Clear Cache

### Option 1: Hard Refresh Browser (Quickest)
1. **Windows/Linux**: Press `Ctrl + Shift + Delete` to open browser cache settings
2. **Mac**: Press `Cmd + Shift + Delete` to open browser cache settings
3. Or use **Hard Refresh**: `Ctrl + F5` (Windows/Linux) or `Cmd + Shift + R` (Mac)

### Option 2: Clear Browser Cache Manually
1. Open your browser settings
2. Go to Privacy/History
3. Clear browsing data (select "All time")
4. Check: Cookies, Cached images and files
5. Click "Clear data"

### Option 3: Restart Flask Server (Recommended)
The Flask server now has automatic cache-busting headers enabled, but to ensure Python bytecode is cleared:

1. **Stop the Flask server** (Ctrl+C in terminal)
2. **Clear Python cache**:
   ```powershell
   Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
   Remove-Item -Path "app\services\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
   ```
3. **Restart Flask server**:
   ```powershell
   python app_modular.py
   ```
4. **Hard refresh browser**: `Ctrl + F5`

### Option 4: Use Incognito/Private Mode
Open a new Incognito/Private window - it won't use cached files:
- **Chrome**: `Ctrl + Shift + N`
- **Firefox**: `Ctrl + Shift + P`
- **Edge**: `Ctrl + Shift + P`

## What Was Changed
- Added `@app.after_request` decorator to Flask app to set cache-control headers
- Added meta tags to HTML for cache control
- Added cache-busting timestamp to API calls
- Cleared __pycache__ directories

## Verification
After clearing cache, you should see:
1. Console logs showing `[DEBUG]` messages
2. Correct status messages based on document type
3. Correct redirect URLs in the routing logs

## If Still Not Working
1. Check browser console (F12) for any errors
2. Check Flask server console for debug output
3. Verify the file was actually saved (check app_modular.py line 3330-3340)
4. Try a different browser
5. Restart your computer (nuclear option)
