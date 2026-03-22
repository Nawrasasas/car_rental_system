import os
import subprocess
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'برمجة النسخ الاحتياطي التلقائي لقاعدة البيانات والملفات'

    def handle(self, *args, **options):
        import shutil  # لضغط الملفات
        
        # 1. إعداد المسار على القرص E
        base_backup_path = r'E:\CarRental_Full_Backup'
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        current_backup_folder = os.path.join(base_backup_path, timestamp)

        if not os.path.exists(current_backup_folder):
            os.makedirs(current_backup_folder)

        # 2. نسخ قاعدة البيانات (SQL)
        db_path = os.path.join(current_backup_folder, 'database_backup.sql')
        pg_dump_path = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
        db_config = settings.DATABASES['default']
        os.environ['PGPASSWORD'] = db_config['PASSWORD']

        try:
            self.stdout.write(self.style.WARNING(f'--- Starting Full Backup to Drive E ---'))
            
            # أمر الداتا بيز
            subprocess.run([
                pg_dump_path, '-U', db_config['USER'], '-h', 'localhost', 
                '-d', db_config['NAME'], '-f', db_path
            ], check=True)
            self.stdout.write(self.style.SUCCESS('1. Database SQL: Done!'))

            # 3. نسخ مجلد الصور (Media) - الأهم للمحاسبة والوثائق
            media_path = settings.MEDIA_ROOT
            if os.path.exists(media_path):
                shutil.make_archive(os.path.join(current_backup_folder, 'media_files'), 'zip', media_path)
                self.stdout.write(self.style.SUCCESS('2. Media Files (Photos): Zipped & Done!'))

            # 4. نسخ الكود المصدري (بدون الـ venv لأنه كبير)
            shutil.make_archive(os.path.join(current_backup_folder, 'source_code'), 'zip', settings.BASE_DIR)
            self.stdout.write(self.style.SUCCESS('3. Source Code: Zipped & Done!'))

            self.stdout.write(self.style.SUCCESS(f'\n✅ ALL SECURE! Check your E drive at: {current_backup_folder}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Backup failed: {str(e)}'))
        finally:
            if 'PGPASSWORD' in os.environ:
                del os.environ['PGPASSWORD']