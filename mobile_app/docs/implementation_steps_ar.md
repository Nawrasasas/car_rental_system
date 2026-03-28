# خطوات التنفيذ (بالعربية)

1. **فحص الباك إند الحالي**
   - راجعت بنية Django الحالية: التطبيقات، النماذج، وملفات `urls.py` و`views.py`.
   - النتيجة: النظام يعتمد غالبًا على Django Admin وTemplate Views، ولا توجد REST APIs فعلية رغم وجود `rest_framework` في الإعدادات.

2. **تحديد واجهات API المطلوبة للموبايل**
   - وضعت عقد API واضح لـ MVP في `backend_api_plan.md`.
   - يشمل: تسجيل الدخول، ملخص الداشبورد، السيارات، العقود، وإنشاء عقد.

3. **إنشاء تطبيق Flutter في مجلد منفصل**
   - أنشأت المجلد: `mobile_app/` بدون تعديل مسارات Django.
   - أضفت `pubspec.yaml` و`README.md`.

4. **تصميم هيكل Clean Architecture مبسط**
   - `core/`: عميل API، التخزين المحلي للتوكن، الثوابت، Result.
   - `features/auth|dashboard|vehicles|rentals`: تقسيم `domain/data/presentation`.

5. **تنفيذ المصادقة (Login)**
   - شاشة Login + `AuthController` + `AuthRepository`.
   - حفظ التوكن محليًا في `SharedPreferences`.

6. **تنفيذ Dashboard**
   - شاشة تعرض مؤشرات MVP الأساسية.
   - مربوطة بـ endpoint مخطط له (`/dashboard/summary/`) مع معالجة حالة عدم جاهزية API.

7. **تنفيذ Vehicles**
   - شاشة قائمة سيارات.
   - شاشة تفاصيل سيارة.

8. **تنفيذ Rentals**
   - شاشة قائمة عقود.
   - شاشة تفاصيل عقد.
   - شاشة إنشاء عقد جديدة (Create Rental Form).

9. **تأكيد عدم كسر الباك إند الحالي**
   - كل التغييرات داخل `mobile_app/` فقط.
   - لا تعديلات على نماذج Django أو المسارات الحالية.

10. **التوثيق والتسليم**
   - توثيق خطة API والإعدادات وخطوات التشغيل.
