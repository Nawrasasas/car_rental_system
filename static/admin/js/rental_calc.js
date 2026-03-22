window.addEventListener('load', function () {
    (function ($) {

        function parseDateTime(dateStr, timeStr) {
            if (!dateStr) return null;

            timeStr = timeStr || "00:00";

            let year, month, day;

            // دعم yyyy-mm-dd
            if (dateStr.includes('-')) {
                let parts = dateStr.split('-');
                if (parts.length === 3) {
                    year = parseInt(parts[0], 10);
                    month = parseInt(parts[1], 10) - 1;
                    day = parseInt(parts[2], 10);
                }
            }
            // دعم dd/mm/yyyy
            else if (dateStr.includes('/')) {
                let parts = dateStr.split('/');
                if (parts.length === 3) {
                    day = parseInt(parts[0], 10);
                    month = parseInt(parts[1], 10) - 1;
                    year = parseInt(parts[2], 10);
                }
            } else {
                return null;
            }

            let hour = 0, minute = 0;
            if (timeStr.includes(':')) {
                let t = timeStr.split(':');
                hour = parseInt(t[0], 10) || 0;
                minute = parseInt(t[1], 10) || 0;
            }

            let dt = new Date(year, month, day, hour, minute, 0, 0);

            if (isNaN(dt.getTime())) return null;
            return dt;
        }

function calculateNow() {
    // --- قراءة تاريخ ووقت بداية العقد من الحقول المفردة أو الحقول المنفصلة الخاصة بـ Django ---
    let sDate = $('#id_start_date_0').val() || $('#id_start_date').val();
    let sTime = $('#id_start_date_1').val() || "00:00";

    // --- قراءة تاريخ ووقت نهاية العقد من الحقول المفردة أو الحقول المنفصلة الخاصة بـ Django ---
    let eDate = $('#id_end_date_0').val() || $('#id_end_date').val();
    let eTime = $('#id_end_date_1').val() || "00:00";

    // --- قراءة السعر اليومي ---
    let rate = parseFloat($('#id_daily_rate').val()) || 0;

    // --- قراءة نسبة الضريبة ---
    let vat = parseFloat($('#id_vat_percentage').val()) || 0;

    // --- قراءة غرامات المرور ---
    let fines = parseFloat($('#id_traffic_fines').val()) || 0;

    // --- قراءة غرامات الحوادث ---
    let damageFees = parseFloat($('#id_damage_fees').val()) || 0;

    // --- قراءة الرسوم أو الغرامات الأخرى ---
    let otherCharges = parseFloat($('#id_other_charges').val()) || 0;

    // --- تحويل النصوص إلى كائنات تاريخ فعلية ---
    let start = parseDateTime(sDate, sTime);
    let end = parseDateTime(eDate, eTime);

    // --- لا نكمل إلا إذا كان التاريخان صالحين ---
    if (start && end) {
        // --- إذا كان تاريخ النهاية بعد أو يساوي تاريخ البداية نحسب الأيام والإجمالي ---
        if (end >= start) {
            // --- حساب الفرق الكامل بالميلي ثانية ---
            let diffMs = end - start;

            // --- عدد الميلي ثانية في اليوم الواحد ---
            let dayMs = 1000 * 60 * 60 * 24;

            // --- الجزء الصحيح من الأيام ---
            let daysPart = Math.floor(diffMs / dayMs);

            // --- المدة المتبقية بعد خصم الأيام الصحيحة ---
            let remainingMs = diffMs % dayMs;

            // --- تحويل الباقي إلى ساعات ---
            let remainingHours = remainingMs / (1000 * 60 * 60);

            // --- نفس منطق النظام الحالي: إذا تبقى أكثر من ساعة نقرّب ليوم إضافي ---
            let days = Math.max(1, daysPart + (remainingHours > 1 ? 1 : 0));

            // --- تحديث عدد أيام الإيجار مباشرة قبل الحفظ ---
            $('.field-rental_days .readonly').text(days);

            // --- حساب إجمالي الإيجار الأساسي = عدد الأيام × السعر اليومي ---
            let base = days * rate;

            // --- حساب مبلغ الضريبة على الإجمالي الأساسي فقط ---
            let vatAmount = base * (vat / 100);

            // --- حساب الصافي النهائي شاملاً الضريبة وغرامات المرور وغرامات الحوادث والرسوم الأخرى ---
            let total = base + vatAmount + fines + damageFees + otherCharges;

            // --- تحديث قيمة Net Total مباشرة قبل الحفظ ---
            $('.field-net_total .readonly').text(total.toFixed(2));
        } else {
            // --- إذا كان تاريخ النهاية قبل البداية نعرض قيمًا صفرية ---
            $('.field-rental_days .readonly').text('0');
            $('.field-net_total .readonly').text('0.00');
        }
    }
}

        function formatUI() {
            $('.field-notes textarea, .field-notes input').css({
                'height': '30px',
                'width': '150px'
            });

            $('.field-DELETE input').hide();

            $('.field-DELETE').each(function () {
                let $cell = $(this);
                if ($cell.find('.btn-remove').length === 0) {
                    $cell.append(
                        '<button type="button" class="btn-remove" style="background:#dc2626; color:white; border:none; padding:3px 8px; border-radius:4px; cursor:pointer; font-size:10px;">REMOVE</button>'
                    );
                }
            });
        }

        $(document).on('change', 'input[type="file"]', function () {
            let input = this;
            if (input.files && input.files[0]) {
                let reader = new FileReader();
                let $preview = $(input).closest('tr').find('.field-file_preview');
                reader.onload = function (e) {
                    $preview.html(
                        '<img src="' + e.target.result + '" width="65" style="border-radius:4px; border:1px solid #16a34a;"/>'
                    );
                };
                reader.readAsDataURL(input.files[0]);
            }
        });

            function ensurePaymentSummaryBox() {
            if ($('#live-payment-summary-box').length) return;

            let attachmentsGroup = $('#attachments-group, #rentalattachment_set-group');
            let paymentsGroup = $('#payments-group');

            let html = `
                <div id="live-payment-summary-box" style="
                    margin:18px 0;
                    padding:16px 20px;
                    border-radius:10px;
                    border:2px solid #e5e7eb;
                    background:#f9fafb;
                    transition:all .2s ease;
                ">
                    <div style="display:flex; flex-direction:column; gap:10px; font-size:17px; font-weight:700;">
                        <div>
                            Net Total:
                            <span id="live-net-total-value" style="margin-left:8px; font-size:18px;">0.00</span>
                        </div>
                        <div>
                            Total Paid:
                            <span id="live-total-paid-value" style="margin-left:8px; font-size:18px;">0.00</span>
                        </div>
                        <div>
                            Remaining Balance:
                            <span id="live-remaining-balance-value" style="margin-left:8px; font-size:18px;">0.00</span>
                        </div>
                    </div>
                </div>
            `;

            if (attachmentsGroup.length) {
                attachmentsGroup.before(html);
            } else if (paymentsGroup.length) {
                paymentsGroup.after(html);
            }
        }

        function getNetTotalValue() {
            let text = '';

            if ($('.field-net_total .readonly').length) {
                text = $('.field-net_total .readonly').first().text();
            } else if ($('#id_net_total').length) {
                text = $('#id_net_total').val();
            }

            text = String(text || '').replace(/,/g, '').trim();
            let val = parseFloat(text);
            return isNaN(val) ? 0 : val;
        }

        function getPaymentsTotal() {
            let total = 0;

            $('input[name$="-amount_paid"]').each(function () {
                let name = $(this).attr('name') || '';

                if (name.indexOf('__prefix__') !== -1) return;

                let deleteName = name.replace('-amount_paid', '-DELETE');
                let deleteInput = $('input[name="' + deleteName + '"]');

                if (deleteInput.length && deleteInput.is(':checked')) return;

                let val = parseFloat($(this).val());
                if (!isNaN(val)) {
                    total += val;
                }
            });

            return total;
        }

        function ensurePaymentSummaryBox() {
            // --- إذا كان الصندوق موجودًا مسبقًا لا نعيد إنشاؤه ---
            if ($('#live-payment-summary-box').length) return;

            let attachmentsGroup = $('#attachments-group, #rentalattachment_set-group');
            let paymentsGroup = $('#payments-group');

            // --- نبني نفس تصميم الصندوق الأساسي الموجود في admin.py / admin_custom.css ---
            let html = `
                <div id="live-payment-summary-box" class="rental-payment-summary">
                    <div class="rental-payment-summary__title">
                        Payment Summary
                    </div>

                    <div class="rental-payment-summary__row">
                        <span class="rental-payment-summary__label">Net Total</span>
                        <span id="live-net-total-value" class="rental-payment-summary__value">$0.00</span>
                    </div>

                    <div class="rental-payment-summary__row">
                        <span class="rental-payment-summary__label">Total Paid</span>
                        <span id="live-total-paid-value" class="rental-payment-summary__value rental-payment-summary__value--paid">$0.00</span>
                    </div>

                    <div class="rental-payment-summary__row rental-payment-summary__row--last">
                        <span class="rental-payment-summary__label rental-payment-summary__label--strong">Remaining Balance</span>
                        <span id="live-remaining-balance-value" class="rental-payment-summary__value rental-payment-summary__value--remaining">$0.00</span>
                    </div>
                </div>
            `;

            // --- نضعه بنفس مكان الصندوق الحالي بين Payments و Attachments ---
            if (attachmentsGroup.length) {
                attachmentsGroup.before(html);
            } else if (paymentsGroup.length) {
                paymentsGroup.after(html);
            }
        }

        function updatePaymentSummaryLive() {
            // --- نتأكد من وجود الصندوق ---
            ensurePaymentSummaryBox();

            let netTotal = getNetTotalValue();
            let payments = getPaymentsTotal();
            let remaining = netTotal - payments;

            // --- نحدّث الأرقام فقط، بدون أي تغيير في الخلفية أو الحدود ---
            $('#live-net-total-value').text('$' + netTotal.toFixed(2));
            $('#live-total-paid-value').text('$' + payments.toFixed(2));
            $('#live-remaining-balance-value').text('$' + remaining.toFixed(2));
        }

        $(document).on('input change', 'input[name$="-amount_paid"], input[name$="-DELETE"]', function () {
            updatePaymentSummaryLive();
        });    
        
        



        $(document).on('click', '.btn-remove', function () {
            let row = $(this).closest('tr');
            let cb = row.find('input[type="checkbox"]');
            cb.prop('checked', !cb.prop('checked'));
            row.css('opacity', cb.prop('checked') ? '0.3' : '1');
            $(this).text(cb.prop('checked') ? 'UNDO' : 'REMOVE');
        });

        // تحديث فوري عند الكتابة أو تغيير التاريخ/الوقت
$(document).on(
    'input change',
    // --- نراقب كل الحقول التي تؤثر على صافي العقد حتى يتحدث Net Total فورًا ---
    '#id_start_date, #id_start_date_0, #id_start_date_1, #id_end_date, #id_end_date_0, #id_end_date_1, #id_daily_rate, #id_vat_percentage, #id_traffic_fines, #id_damage_fees, #id_other_charges',
    function () {

        // --- إعادة الحساب المباشر بمجرد أي تعديل ---
        calculateNow();

        // --- تحديث صندوق الملخص بعد لحظة قصيرة لضمان ظهور الرقم الجديد داخله أيضًا ---
        setTimeout(function () {
            updatePaymentSummaryLive();
        }, 50);

    }
);

        $(document).on('keyup change', '#id_start_date_0, #id_start_date_1, #id_end_date_0, #id_end_date_1', function () {
    calculateNow();
        });

        // التقاط اختيار التاريخ من التقويم المنبثق في Django admin
        $(document).on('click', '.calendar-link, .datetimeshortcuts a', function () {
    setTimeout(function(){
        calculateNow();
        }, 200);
        });


        // تشغيل أولي عند فتح الصفحة
        calculateNow();
        formatUI();
        setTimeout(function () {
            updatePaymentSummaryLive();
        }, 200);

        // إعادة التنسيق عند إضافة صفوف inline جديدة أو تحديث DOM
        $(document).on('click', '.add-row a, .grp-add-handler', function () {
            setTimeout(function () {
                formatUI();
                calculateNow();
                updatePaymentSummaryLive();
            }, 150);
        });

        $(document).ajaxComplete(function () {
            formatUI();
        });

    })(django.jQuery);
});
// ===============================
// --- جعل صف العقد كله يفتح صفحة العقد من قائمة العقود ---
document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("result_list");
    if (!table) return;

    const rows = table.querySelectorAll("tbody tr");

    rows.forEach(function (row) {
        const mainLink = row.querySelector("th a");
        if (!mainLink) return;

        row.style.cursor = "pointer";

        row.addEventListener("click", function (event) {
            const ignore = event.target.closest("a, input, select, textarea, button, label");
            if (ignore) return;

            window.location.href = mainLink.href;
        });
    });
});