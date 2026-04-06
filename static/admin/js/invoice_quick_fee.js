'use strict';

// PATH: static/admin/js/invoice_quick_fee.js

(function () {

    // الحقول التي تختفي عند تفعيل Quick Fee
    const CUSTOMER_FIELD_IDS = [
        'receivable_account', 'revenue_account',
        'customer_name', 'customer_email', 'customer_phone', 'customer_address',
    ];

    // الحقول التي تظهر فقط عند تفعيل Quick Fee
    const FEE_FIELD_IDS = ['fee_type', 'fee_type_other'];

    function getFieldRow(fieldId) {
        // نبحث عن الحقل بـ id أو name ثم نطلع لـ .form-row
        const el = (
            document.getElementById('id_' + fieldId) ||
            document.querySelector('[name="' + fieldId + '"]') ||
            document.querySelector('.field-' + fieldId)
        );
        if (!el) return null;
        return (
            el.closest('.form-row') ||
            el.closest('fieldset') ||
            el.parentElement
        );
    }

    function setVisible(fieldId, visible) {
        const row = getFieldRow(fieldId);
        if (row) row.style.display = visible ? '' : 'none';
    }

    function getSelectedFeeType() {
        const checked = document.querySelector('input[name="fee_type"]:checked');
        return checked ? checked.value : '';
    }

    function applyToggle() {
        const checkbox = document.getElementById('id_is_quick_fee');
        if (!checkbox) return;

        const isQuickFee = checkbox.checked;

        // --- إخفاء/إظهار حقول العميل ---
        CUSTOMER_FIELD_IDS.forEach(id => setVisible(id, !isQuickFee));

        // --- إخفاء/إظهار حقول الرسوم ---
        setVisible('fee_type', isQuickFee);
        setVisible('fee_type_other', isQuickFee && getSelectedFeeType() === 'other');
    }

    function onFeeTypeChange() {
        const isOther = getSelectedFeeType() === 'other';
        setVisible('fee_type_other', isOther);
    }

    function init() {
        const checkbox = document.getElementById('id_is_quick_fee');
        if (!checkbox) return;

        // تفعيل الـ toggle عند تغيير الـ checkbox
        checkbox.addEventListener('change', applyToggle);

        // تفعيل إظهار/إخفاء حقل Other عند تغيير نوع الرسوم
        document.addEventListener('change', function (e) {
            if (e.target && e.target.name === 'fee_type') {
                onFeeTypeChange();
            }
        });

        // تطبيق الحالة الأولية فور تحميل الصفحة
        applyToggle();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();