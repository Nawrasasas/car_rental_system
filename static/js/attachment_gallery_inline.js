(function () {
    // --- التحقق هل الملف المختار صورة ---
    function isImageFile(file) {
        return !!(file && file.type && file.type.startsWith("image/"));
    }

    // --- إيجاد أو إنشاء حاوية عرض الصورة داخل البطاقة ---
    function getOrCreateImageContainer(card) {
        if (!card) return null;

        var existing = card.querySelector(".attachment-current-file");
        if (existing) return existing;

        var container = document.createElement("div");
        container.className = "attachment-current-file";

        var link = document.createElement("a");
        link.className = "attachment-current-image-link";
        link.target = "_blank";
        link.style.display = "none";

        var img = document.createElement("img");
        img.className = "attachment-current-image";
        img.style.display = "none";

        link.appendChild(img);
        container.appendChild(link);

        var fileRow = card.querySelector(".field-file");
        if (fileRow) {
            fileRow.insertAdjacentElement("afterbegin", container);
        } else {
            card.insertAdjacentElement("afterbegin", container);
        }

        return container;
    }

    // --- تحديث المعاينة داخل نفس مكان الصورة الحالية ---
    function updatePreview(input) {
        var card = input.closest(".attachment-card-inner");
        if (!card) return;

        var container = getOrCreateImageContainer(card);
        if (!container) return;

        var link = container.querySelector(".attachment-current-image-link");
        var img = container.querySelector(".attachment-current-image");
        var fileLink = container.querySelector(".attachment-current-file-link");
        var file = input.files[0];

        // --- إذا لم يختَر المستخدم ملفًا جديدًا، لا نغيّر العرض الحالي ---
        if (!file) {
            return;
        }

        // --- إذا الملف ليس صورة، لا نعرض معاينة صورة ---
        if (!isImageFile(file)) {
            if (img) {
                img.removeAttribute("src");
                img.style.display = "none";
            }

            if (link) {
                link.removeAttribute("href");
                link.style.display = "none";
            }

            if (fileLink) {
                fileLink.style.display = "inline-block";
            }

            return;
        }

        // --- إنشاء رابط مؤقت للصورة المختارة قبل الحفظ ---
        var objectUrl = URL.createObjectURL(file);

        // --- لو كانت هناك وصلة ملف نصية قديمة نخفيها مؤقتًا ---
        if (fileLink) {
            fileLink.style.display = "none";
        }

        img.src = objectUrl;
        img.style.display = "block";

        link.href = objectUrl;
        link.style.display = "block";
    }

    // --- ربط كل حقول الملفات داخل معرض المرفقات ---
    function bindAll() {
        document.querySelectorAll(".attachment-gallery input[type='file']").forEach(function (input) {
            if (input.dataset.previewBound === "1") return;

            input.dataset.previewBound = "1";

            input.addEventListener("change", function () {
                updatePreview(input);
            });
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