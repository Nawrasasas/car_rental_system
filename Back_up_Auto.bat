@echo off
echo --- STARTING AUTOMATIC CAR RENTAL BACKUP ---
C:
cd C:\car_rental_enterprise
call venv\Scripts\activate

:: تشغيل النسخ الاحتياطي لقاعدة البيانات
python manage.py auto_backup

:: --- السطر الجديد المضاف لضمان حفظ التصميم CSS ---
xcopy /E /I /Y "static" "backups\static_assets_backup"

echo --- BACKUP PROCESS FINISHED ---
pause