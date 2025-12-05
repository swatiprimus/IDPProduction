# How to Sync Code to GitHub

## The Problem
You're getting a 403 permission error when trying to push to GitHub:
```
remote: Permission to swatiprimus/IDPProduction.git denied to swati19a.
fatal: unable to access 'https://github.com/swatiprimus/IDPProduction.git/': The requested URL returned error: 403
```

This means GitHub is rejecting your credentials.

## Solution Options

### Option 1: Use Personal Access Token (Recommended)

#### Step 1: Create a Personal Access Token
1. Go to GitHub: https://github.com/settings/tokens
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a name: "IDP Development"
4. Select scopes:
   - ✅ **repo** (Full control of private repositories)
5. Click **"Generate token"**
6. **COPY THE TOKEN** (you won't see it again!)

#### Step 2: Configure Git to Use Token
```powershell
# Set your GitHub username
git config user.name "swatiprimus"

# Set your GitHub email
git config user.email "your-email@example.com"

# Store credentials (so you don't have to enter token every time)
git config credential.helper store
```

#### Step 3: Push with Token
```powershell
# When you push, use your token as the password
git push origin main

# When prompted:
# Username: swatiprimus
# Password: [paste your token here]
```

After the first push, Git will remember your credentials.

### Option 2: Use SSH (More Secure)

#### Step 1: Generate SSH Key
```powershell
# Generate SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"

# Press Enter to accept default location
# Press Enter twice for no passphrase (or set one if you want)
```

#### Step 2: Add SSH Key to GitHub
```powershell
# Copy your public key
Get-Content ~/.ssh/id_ed25519.pub | clip
```

Then:
1. Go to GitHub: https://github.com/settings/keys
2. Click **"New SSH key"**
3. Title: "IDP Development PC"
4. Paste the key
5. Click **"Add SSH key"**

#### Step 3: Change Remote to SSH
```powershell
# Change remote URL from HTTPS to SSH
git remote set-url origin git@github.com:swatiprimus/IDPProduction.git

# Verify
git remote -v

# Now push
git push origin main
```

### Option 3: Use GitHub Desktop (Easiest)

1. Download GitHub Desktop: https://desktop.github.com/
2. Sign in with your GitHub account
3. Add your repository
4. Click "Push origin" button

## Quick Fix (Temporary)

If you just want to push right now:

```powershell
# Push with username in URL
git push https://swatiprimus@github.com/swatiprimus/IDPProduction.git main

# When prompted for password, use your Personal Access Token
```

## Current Status

Your local repository has:
- ✅ 3 commits ready to push
- ✅ All changes committed
- ✅ No uncommitted files
- ❌ Can't push due to authentication

## What to Do Now

**Recommended Steps:**

1. **Create Personal Access Token** (see Option 1 above)
2. **Configure Git credentials:**
   ```powershell
   git config credential.helper store
   ```
3. **Push with token:**
   ```powershell
   git push origin main
   # Username: swatiprimus
   # Password: [your token]
   ```

## Verify Sync

After pushing successfully:

```powershell
# Check status
git status

# Should show:
# "Your branch is up to date with 'origin/main'"
```

Then go to GitHub and verify your commits are there:
https://github.com/swatiprimus/IDPProduction

## Common Issues

### Issue 1: "Permission denied"
**Solution**: Make sure you're using the correct username (`swatiprimus`, not `swati19a`)

### Issue 2: "Authentication failed"
**Solution**: Use Personal Access Token instead of password

### Issue 3: "Repository not found"
**Solution**: Check if you have access to the repository

### Issue 4: Token doesn't work
**Solution**: Make sure you selected the "repo" scope when creating the token

## Need Help?

If you're still having issues:

1. Check your GitHub account: https://github.com/swatiprimus
2. Verify repository exists: https://github.com/swatiprimus/IDPProduction
3. Check if you're logged into the correct GitHub account
4. Try using GitHub Desktop as an alternative

---

**Quick Command Reference:**

```powershell
# Check status
git status

# See what needs to be pushed
git log origin/main..HEAD

# Push to GitHub
git push origin main

# Force push (use carefully!)
git push origin main --force
```
