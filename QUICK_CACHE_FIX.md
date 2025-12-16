# Quick Cache Fix - TL;DR

## The Problem
Flask server was caching old Python code, so changes weren't taking effect.

## The Solution
Cache busting has been implemented at multiple levels.

## What to Do NOW

### Step 1: Stop Flask Server
```
Press Ctrl+C in the terminal running Flask
```

### Step 2: Clear Python Cache
```powershell
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "app\services\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
```

### Step 3: Restart Flask Server
```powershell
python app_modular.py
```

### Step 4: Clear Browser Cache
- **Hard Refresh**: `Ctrl + F5` (Windows/Linux) or `Cmd + Shift + R` (Mac)
- **Or use Incognito**: `Ctrl + Shift + N` (Chrome) or `Ctrl + Shift + P` (Firefox)

### Step 5: Test
1. Upload a new document
2. Open browser console (F12)
3. Look for debug messages like:
   - `[LOAD_SKILLS] Loaded X documents`
   - `[ROUTING] Doc: {id}, Type: death_certificate, URL: /document/{id}/pages`
   - `[DEBUG] Final status_message: ✅ Document uploaded - Death Certificate ready for viewing`

## Verify It's Working
- Non-loan docs should redirect to `/pages` (not `/accounts`)
- Status message should say "Death Certificate ready for viewing" (not "No explicitly labeled account numbers")
- Console should show correct routing decision

## If Still Not Working
1. Check Flask server console for `[DEBUG]` messages
2. Try a different browser
3. Restart your computer
4. Check CACHE_CLEARING_GUIDE.md for more options
