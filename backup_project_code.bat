@echo off
chcp 65001 > nul
echo --- BACKING UP PROJECT CODE ONLY ---

C:
cd C:\car_rental_enterprise

:: إنشاء مجلد النسخ الاحتياطي على القرص E
if not exist E:\car_rental_backups mkdir E:\car_rental_backups

:: إنشاء اسم بتاريخ ووقت
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set DT=%%i

:: نسخ المشروع
xcopy . E:\car_rental_backups\project_%DT% /E /I /Y /EXCLUDE:exclude.txt

echo --- BACKUP COMPLETED ---
pause