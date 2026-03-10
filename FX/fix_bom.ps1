$files = @(
    'C:\dev\projects\BojkoFx\src\execution\ibkr_exec.py',
    'C:\dev\projects\BojkoFx\src\runners\run_paper_ibkr_gateway.py'
)
foreach ($path in $files) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $newBytes = $bytes[3..($bytes.Length - 1)]
        [System.IO.File]::WriteAllBytes($path, $newBytes)
        Write-Host "BOM removed: $path"
    } else {
        Write-Host "No BOM:      $path"
    }
    $check = [System.IO.File]::ReadAllBytes($path)
    Write-Host ("  First bytes: " + $check[0].ToString("X2") + " " + $check[1].ToString("X2") + " " + $check[2].ToString("X2"))
}

