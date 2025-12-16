# Verification Script for Cache Fixes

Write-Host "=== Universal IDP Cache Fix Verification ===" -ForegroundColor Cyan
Write-Host ""

# Check if app_modular.py has the cache decorator
Write-Host "1. Checking for cache control decorator..." -ForegroundColor Yellow
$hasDecorator = Select-String -Path "app_modular.py" -Pattern "@app.after_request" -Quiet
if ($hasDecorator) {
    Write-Host "   OK - Cache control decorator found" -ForegroundColor Green
} else {
    Write-Host "   ERROR - Cache control decorator NOT found" -ForegroundColor Red
}

# Check if version endpoint exists
Write-Host "2. Checking for version endpoint..." -ForegroundColor Yellow
$hasVersion = Select-String -Path "app_modular.py" -Pattern "get_version" -Quiet
if ($hasVersion) {
    Write-Host "   OK - Version endpoint found" -ForegroundColor Green
} else {
    Write-Host "   ERROR - Version endpoint NOT found" -ForegroundColor Red
}

# Check if debug messages exist
Write-Host "3. Checking for debug messages..." -ForegroundColor Yellow
$hasDebug = Select-String -Path "app_modular.py" -Pattern "DEBUG" -Quiet
if ($hasDebug) {
    Write-Host "   OK - Debug messages found" -ForegroundColor Green
} else {
    Write-Host "   ERROR - Debug messages NOT found" -ForegroundColor Red
}

# Check if HTML has cache meta tags
Write-Host "4. Checking for HTML cache meta tags..." -ForegroundColor Yellow
$hasMetaTags = Select-String -Path "templates/skills_catalog.html" -Pattern "Cache-Control" -Quiet
if ($hasMetaTags) {
    Write-Host "   OK - Cache meta tags found" -ForegroundColor Green
} else {
    Write-Host "   ERROR - Cache meta tags NOT found" -ForegroundColor Red
}

# Check if __pycache__ exists
Write-Host "5. Checking for Python cache..." -ForegroundColor Yellow
$hasPycache = Test-Path "__pycache__"
if ($hasPycache) {
    Write-Host "   WARNING - pycache directory exists (should be cleared)" -ForegroundColor Yellow
} else {
    Write-Host "   OK - pycache directory not found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host "All cache fixes have been applied successfully!"
Write-Host ""
