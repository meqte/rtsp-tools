@echo off
setlocal enabledelayedexpansion
chcp 936 >nul
title License Reset Tool

REM 获取当前批处理文件所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ================================================
echo              License Reset Tool
echo ================================================
echo.

REM 检查程序文件
if exist "main.py" (
    set "PROGRAM_TYPE=python"
    goto :file_found
)
if exist "*.exe" (
    set "PROGRAM_TYPE=exe"
    goto :file_found
)
echo Error: Program file not found
echo Please place this tool in the same directory as the program
echo.
pause
exit /b 1

:file_found
REM 从系统获取许可证信息（适用于exe和Python版本）
set "temp_dir=%TEMP%"
set "current_usage=0"
set "max_usage=50"
set "expiry_date=未知"
set "expiry_year=2025"
set "expiry_month=12"
set "expiry_day=31"

echo Reading license info from system...

REM 从注册表读取许可证信息
for /f "tokens=3" %%a in ('reg query "HKCU\Software\TempApp\License" /v expiry_date 2^>nul ^| findstr "expiry_date"') do (
    set "registry_expiry=%%a"
)
for /f "tokens=3" %%a in ('reg query "HKCU\Software\TempApp\License" /v max_usage 2^>nul ^| findstr "max_usage"') do (
    set "registry_max_usage_hex=%%a"
)

REM 如果注册表中有数据，使用注册表数据
if defined registry_expiry (
    for /f "tokens=1-3 delims=-" %%i in ("!registry_expiry!") do (
        set "expiry_year=%%i"
        set "expiry_month=%%j"
        set "expiry_day=%%k"
    )
    set "expiry_date=!expiry_year!-!expiry_month!-!expiry_day!"
    echo [OK] Registry expiry date: !expiry_date!
) else (
    echo [WARN] License info not found in registry, using defaults
    set "expiry_date=2025-12-31"
)

if defined registry_max_usage_hex (
    REM 将十六进制转换为十进制
    for /f "usebackq" %%i in (`powershell -command "[convert]::ToInt32('!registry_max_usage_hex!', 16)"`) do set "max_usage=%%i"
    echo [OK] Registry max usage: !max_usage!
) else (
    echo [WARN] Max usage not found in registry, using default: 50
)

REM 计算剩余天数（使用从系统读取的日期）
for /f "usebackq" %%i in (`powershell -command "try { (Get-Date '!expiry_year!-!expiry_month!-!expiry_day!') - (Get-Date) | Select-Object -ExpandProperty Days } catch { 0 }"`) do set "remaining_days=%%i"
if !remaining_days! lss 0 set "remaining_days=0"

REM Read current usage count from file content
for /f "delims=" %%i in ('dir "%temp_dir%\.app_usage_*" /b 2^>nul') do (
    set "usage_file=%temp_dir%\%%i"
    for /f "tokens=2 delims=|" %%j in ('type "!usage_file!" 2^>nul') do (
        set "current_usage=%%j"
    )
)

set /a "remaining_usage=!max_usage!-!current_usage!"
if !remaining_usage! lss 0 set "remaining_usage=0"

echo Current License Status:
echo ----------------------------------------
echo Expires: !expiry_date!
echo Days remaining: about !remaining_days! days
echo Used: !current_usage! / !max_usage!
echo Remaining: !remaining_usage! times
echo ----------------------------------------
echo.
echo Press any key to reset license to initial state...
pause >nul

echo.
echo Resetting license...

REM 删除所有许可证文件
set "deleted_count=0"
for %%f in ("%temp_dir%\.app_usage_*" "%temp_dir%\.app_backup_*" "%temp_dir%\.app_first_run_*") do (
    if exist "%%f" (
        del /f /q "%%f" >nul 2>&1
        if !errorlevel! equ 0 (
            set /a "deleted_count+=1"
        )
    )
)

REM 清除注册表记录
reg delete "HKCU\Software\TempApp\License" /f >nul 2>&1

echo.
echo [OK] Reset completed!
echo.
echo License reset to initial state:
echo - Used: 0 / 50
echo - Expires: 2025-12-31
echo - Status: Ready to use
echo.
echo Press any key to exit...
pause >nul