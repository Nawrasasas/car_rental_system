document.addEventListener("DOMContentLoaded", function () {
    // --- نحدد جدول نتائج العقود داخل صفحة القائمة ---
    const resultTable = document.querySelector("#result_list");

    // --- إذا لم يوجد الجدول نخرج مباشرة ---
    if (!resultTable) {
        return;
    }

    // --- نمر على كل صف داخل tbody فقط ---
    const rows = resultTable.querySelectorAll("tbody tr");

    rows.forEach(function (row) {
        // --- نبحث عن أول رابط حقيقي داخل الصف، وغالبًا يكون رابط فتح العقد ---
        const firstLink = row.querySelector("th a, td a");

        // --- إذا لم نجد رابطًا فلا نجعل الصف قابلاً للضغط ---
        if (!firstLink) {
            return;
        }

        // --- نعطي شكل بصري أن الصف قابل للضغط ---
        row.style.cursor = "pointer";

        // --- عند الضغط على الصف ---
        row.addEventListener("click", function (event) {
            // --- نتحقق إن كان المستخدم ضغط على عنصر تفاعلي لا يجب خطفه ---
            const ignoredElement = event.target.closest(
                'a, button, input, select, textarea, label'
            );

            // --- إذا ضغط على عنصر تفاعلي نتركه يعمل طبيعيًا ---
            if (ignoredElement) {
                return;
            }

            // --- نفتح صفحة العقد من خلال الرابط الأساسي في الصف ---
            window.location.href = firstLink.href;
        });
    });
});