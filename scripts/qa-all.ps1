$ErrorActionPreference = "Stop"

$backendPath = "C:/Users/Pruthviraj/OneDrive/Desktop/Project/as9100d-erp-backend"
$pythonExe = "C:/Users/Pruthviraj/OneDrive/Desktop/Project/.venv/Scripts/python.exe"
$base = "http://127.0.0.1:8000/api/v1"

Write-Output "[QA] Starting full backend validation"

Push-Location $backendPath
try {
    Write-Output "[QA] Step 1/3: Full test suite"
    & $pythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Full test suite failed" }

    Write-Output "[QA] Step 2/3: Smoke test suite"
    & $pythonExe -m pytest -m "not slow" -q
    if ($LASTEXITCODE -ne 0) { throw "Smoke test suite failed" }

    Write-Output "[QA] Step 3/3: Live API sanity checks"

    $openapi = Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" -UseBasicParsing
    if ($openapi.StatusCode -ne 200) { throw "OpenAPI endpoint failed" }

    try {
        Invoke-WebRequest -Uri "$base/auth/me" -UseBasicParsing | Out-Null
        throw "Unauthenticated /auth/me unexpectedly returned 200"
    } catch {
        if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 401) {
            throw "Unauthenticated /auth/me did not return 401"
        }
    }

    $uid = Get-Random -Minimum 10000 -Maximum 99999
    $username = "qaall$uid"
    $email = "$username@example.com"
    $password = "Test@12345"

    $createBody = @{
        username = $username
        email = $email
        password = $password
        role = "Sales"
    } | ConvertTo-Json

    $createResp = Invoke-RestMethod -Method Post -Uri "$base/users/" -ContentType "application/json" -Body $createBody
    if (-not $createResp.id) { throw "User creation failed in live checks" }

    $loginBody = @{
        username = $username
        password = $password
    } | ConvertTo-Json
    $loginResp = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body $loginBody

    $userToken = $loginResp.access_token
    if (-not $userToken) { throw "Login did not return access token" }

    $userHeaders = @{ Authorization = "Bearer $userToken" }

    $meResp = Invoke-WebRequest -Uri "$base/auth/me" -Headers $userHeaders -UseBasicParsing
    if ($meResp.StatusCode -ne 200) { throw "Authenticated /auth/me check failed" }

    $salesResp = Invoke-WebRequest -Uri "$base/sales/enquiry?limit=2&offset=0" -Headers $userHeaders -UseBasicParsing
    if ($salesResp.StatusCode -ne 200) { throw "Sales list endpoint check failed" }

    $adminToken = & $pythonExe -c "from sqlalchemy import select; from app.db.session import SessionLocal; from app.models.user import User; from app.core.security import create_access_token; db=SessionLocal(); admin=db.scalar(select(User).where(User.username=='admin')); db.close(); print(create_access_token(str(admin.id)) if admin else '')"
    $adminToken = ($adminToken | Select-Object -Last 1).Trim()
    if (-not $adminToken) { throw "Could not create admin token for engineering checks" }

    $adminHeaders = @{ Authorization = "Bearer $adminToken" }

    $engListResp = Invoke-WebRequest -Uri "$base/engineering/drawing?limit=2&offset=0" -Headers $adminHeaders -UseBasicParsing
    if ($engListResp.StatusCode -ne 200) { throw "Engineering list endpoint check failed" }

    $drawNo = "DRW-QA-$(Get-Random -Minimum 100000 -Maximum 999999)"
    $drawBody = @{
        drawing_number = $drawNo
        part_name = "QA All Part"
        description = "Created by qa-all"
        is_active = $true
    } | ConvertTo-Json

    $drawResp = Invoke-WebRequest -Method Post -Uri "$base/engineering/drawing" -Headers $adminHeaders -ContentType "application/json" -Body $drawBody -UseBasicParsing
    if ($drawResp.StatusCode -ne 201) { throw "Engineering create drawing check failed" }

    Write-Output "[QA] PASS: Full tests, smoke tests, and live API checks completed successfully"
}
finally {
    Pop-Location
}
