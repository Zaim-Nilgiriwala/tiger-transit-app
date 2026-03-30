while ($true) {
    Write-Output ''
    Write-Output ('=' * 60)
    Write-Output ('CHECK: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    Write-Output ('=' * 60)
    Write-Output ''
    Write-Output 'COLLECTOR OUTPUT (last 15 lines):'
    Get-Content 'C:\Users\ryanp\AppData\Local\Temp\claude\C--Users-ryanp-OneDrive-Desktop-code-Tiger-Transit-mobile-src-ETA-Model\tasks\bca9b0d.output' -Tail 15
    Write-Output ''
    Write-Output 'DATA FILES:'
    Get-ChildItem 'C:\Users\ryanp\OneDrive\Desktop\code\Tiger Transit\mobile\src\ETA-Model\raw_data\raw_data_2026-01*' | ForEach-Object { '{0} {1,15:N0} bytes {2}' -f $_.Name, $_.Length, $_.LastWriteTime }
    Write-Output ''
    $proc = Get-Process -Name node -ErrorAction SilentlyContinue
    if ($proc) { Write-Output ('Node process alive: PID ' + $proc.Id + ', CPU: ' + $proc.CPU) } else { Write-Output 'WARNING: Node process NOT FOUND - collector may have crashed!'; break }
    Start-Sleep -Seconds 300
}
