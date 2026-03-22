(function () {
    // --- التحقق هل الملف المختار صورة ---
    function isImageFile(file) {
        return !!(file && file.type && file.type.startsWith("image/"));
    }

    // --- إنشاء صندوق المعاينة إذا لم يكن موجودًا داخل بطاقة المرفق ---
    function getOrCreatePreviewBox(input) {
        var card = input.closest(".vehicle-document-card-inner");
        if (!card) return null;

        var existing = card.querySelector(".vehicle-inline-preview-box");
        if (existing) return existing;

        var box = document.createElement("div");
        box.className = "vehicle-inline-preview-box";

        var label = document.createElement("div");
        label.className = "vehicle-inline-preview-label";
        label.textContent = "Preview";

        var link = document.createElement("a");
        link.className = "vehicle-inline-preview-link";
        link.target = "_blank";
        link.style.display = "none";

        var img = document.createElement("img");
        img.className = "vehicle-inline-preview-image";

        var note = document.createElement("div");
        note.className = "vehicle-inline-preview-note";
        note.textContent = "اختر صورة للمعاينة";

        link.appendChild(img);
        box.appendChild(label);
        box.appendChild(link);
        box.appendChild(note);

        input.insertAdjacentElement("afterend", box);

        return box;
    }

    // --- تحديث المعاينة عند اختيار ملف جديد ---
    function updatePreview(input) {
        var box = getOrCreatePreviewBox(input);
        if (!box) return;

        var link = box.querySelector(".vehicle-inline-preview-link");
        var img = box.querySelector(".vehicle-inline-preview-image");
        var note = box.querySelector(".vehicle-inline-preview-note");
        var file = input.files[0];

        // --- لا يوجد ملف مختار ---
        if (!file) {
            img.removeAttribute("src");
            link.removeAttribute("href");
            link.style.display = "none";
            note.textContent = "اختر صورة للمعاينة";
            note.style.display = "block";
            box.classList.remove("has-image");
            return;
        }

        // --- الملف ليس صورة ---
        if (!isImageFile(file)) {
            img.removeAttribute("src");
            link.removeAttribute("href");
            link.style.display = "none";
            note.textContent = "الملف ليس صورة";
            note.style.display = "block";
            box.classList.remove("has-image");
            return;
        }

        // --- إنشاء رابط مؤقت للصورة المختارة قبل الحفظ ---
        var objectUrl = URL.createObjectURL(file);

        img.src = objectUrl;
        link.href = objectUrl;
        link.style.display = "inline-block";
        note.style.display = "none";
        box.classList.add("has-image");
    }

    // --- ربط كل حقول الملف داخل معرض مرفقات السيارة فقط ---
    function bindAll() {
        document.querySelectorAll(".vehicle-documents-gallery input[type='file']").forEach(function (input) {
            if (input.dataset.previewBound === "1") return;

            input.dataset.previewBound = "1";

            input.addEventListener("change", function () {
                updatePreview(input);
            });

            getOrCreatePreviewBox(input);
        });
    }

    // --- تشغيل أولي بعد تحميل الصفحة ---
    document.addEventListener("DOMContentLoaded", function () {
        bindAll();
    });

    // --- مراقبة إضافة inline جديد من زر Add another ---
    new MutationObserver(function () {
        bindAll();
    }).observe(document.body, {
        childList: true,
        subtree: true
    });
})();