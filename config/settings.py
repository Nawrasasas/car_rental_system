import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-enterprise-demo-key'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "import_export", 
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.branches",
    "apps.vehicles",
    "apps.attachments",
    "apps.customers",
    "apps.rentals",
    "apps.payments",
    "apps.accounting",
    "apps.invoices",
    "apps.reports",
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'
# الإعدادات الحالية التي أرسلتها
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Baghdad'
USE_I18N = True
USE_TZ = True

# الإضافات الجديدة للتنسيق المطلوب:
USE_L10N = False  # تفعيل التنسيق المحلي
USE_THOUSAND_SEPARATOR = True  # تفعيل فواصل الآلاف للأرقام (مثلاً 1,525.00)

# ضبط صيغ التاريخ لتظهر وتُقبل كـ (يوم-شهر-سنة)
DATETIME_FORMAT = 'd-m-Y H:i'
DATE_FORMAT = 'd-m-Y'

# التنسيقات التي سيقبلها Django عند الكتابة في الخانات (Input)
DATETIME_INPUT_FORMATS = [
    '%d-%m-%Y %H:%M:%S',
    '%d-%m-%Y %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
]
DATETIME_FORMAT = 'd-m-Y H:i'
DATE_FORMAT = 'd-m-Y'

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
