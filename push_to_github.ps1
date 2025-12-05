# Quick script to push code to GitHub
# Run this after setting up your Personal Access Token

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Push Code to GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if there are commits to push
$status = git status --porcelain
$ahead = git rev-list --count origin/main..HEAD 2>$null

if ($ahead -eq $null) {
    Write-Host "⚠️  Cannot determine commits ahead. Checking remote..." -ForegroundColor Yellow
    git fetch origin
    $ahead = git rev-list --count origin/main..HEAD 2>$null
}

Write-Host "Current Status:" -ForegroundColor Yellow
Write-Host "  Commits to push: $ahead" -ForegroundColor White
Write-Host ""

if ($ahead -gt 0) {
    Write-Host "📦 You have $ahead commit(s) to push" -ForegroundColor Green
    Write-Host ""
    
    # Show commits
    Write-Host "Commits to be pushed:" -ForegroundColor Yellow
    git log origin/main..HEAD --oneline
    Write-Host ""
    
    # Ask for confirmation
    $confirm = Read-Host "Do you want to push these commits? (y/n)"
    
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        Write-Host ""
        Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
        Write-Host ""
        
        # Try to push
        git push origin main
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "✅ Successfully pushed to GitHub!" -ForegroundColor Green
            Write-Host ""
            Write-Host "View your code at:" -ForegroundColor Cyan
            Write-Host "https://github.com/swatiprimus/IDPProduction" -ForegroundColor White
        } else {
            Write-Host ""
            Write-Host "❌ Push failed!" -ForegroundColor Red
            Write-Host ""
            Write-Host "Common solutions:" -ForegroundColor Yellow
            Write-Host "1. Create a Personal Access Token:" -ForegroundColor White
            Write-Host "   https://github.com/settings/tokens" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "2. Configure Git credentials:" -ForegroundColor White
            Write-Host "   git config credential.helper store" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "3. Try pushing with username in URL:" -ForegroundColor White
            Write-Host "   git push https://swatiprimus@github.com/swatiprimus/IDPProduction.git main" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "See GIT_SYNC_INSTRUCTIONS.md for detailed help" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Push cancelled" -ForegroundColor Yellow
    }
} else {
    Write-Host "✅ Everything is up to date!" -ForegroundColor Green
    Write-Host "No commits to push." -ForegroundColor White
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
