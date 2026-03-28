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
        function isRentalFormPage() {
            // --- نتحقق أننا داخل صفحة نموذج العقد فقط ---
            return (
                $('#id_daily_rate').length > 0 ||
                $('#id_start_date').length > 0 ||
                $('#id_start_date_0').length > 0
              );
        }

        function calculateNow() {
            // --- لا نشغل أي شيء خارج صفحة العقد ---
            if (!isRentalFormPage()) return;

            let sDate = $('#id_start_date_0').val() || $('#id_start_date').val();
            let sTime = $('#id_start_date_1').val() || "00:00";

            let eDate = $('#id_end_date_0').val() || $('#id_end_date').val();
            let eTime = $('#id_end_date_1').val() || "00:00";

            let rate = parseFloat($('#id_daily_rate').val()) || 0;
            let vat = parseFloat($('#id_vat_percentage').val()) || 0;
            let deposit = parseFloat($('#id_deposit_amount').val()) || 0;
            let fines = parseFloat($('#id_traffic_fines').val()) || 0;
            let damageFees = parseFloat($('#id_damage_fees').val()) || 0;
            let otherCharges = parseFloat($('#id_other_charges').val()) || 0;

            let start = parseDateTime(sDate, sTime);
            let end = parseDateTime(eDate, eTime);

            ensurePaymentSummaryBoxes();

            if (start && end) {
                if (end >= start) {
                    start.setMinutes(0, 0, 0);
                    end.setMinutes(0, 0, 0);

                    let diffMs = end - start;
                    let dayMs = 1000 * 60 * 60 * 24;
                    let daysPart = Math.floor(diffMs / dayMs);
                    let remainingMs = diffMs % dayMs;
                    let days = Math.max(1, daysPart + (remainingMs > 0 ? 1 : 0));

                    $('.field-rental_days .readonly').text(days);

                    let base = days * rate;
                    let vatAmount = base * (vat / 100);

                    // --- Net Total النهائي الظاهري ---
                    // --- يشمل الإيجار + الضريبة + المخالفات + الأضرار + الرسوم الأخرى + التأمين ---
                    let finalTotal = base + vatAmount + fines + damageFees + otherCharges + deposit;

                    $('.field-net_total .readonly').text(finalTotal.toFixed(2));
                    updatePaymentSummaryLive();
                } else {
                    $('.field-rental_days .readonly').text('0');
                    $('.field-net_total .readonly').text('0.00');
                    updatePaymentSummaryLive();
                }
            } else {
                $('.field-rental_days .readonly').text('0');
                $('.field-net_total .readonly').text('0.00');
                updatePaymentSummaryLive();
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
            let $state = $('#rental-collection-state');

            // --- بعد الحفظ نعتمد على الأرقام القادمة من السيرفر لأنها الأصح ---
            if ($state.length) {
                let contractCollected = parseFloat($state.attr('data-contract-collected')) || 0;
                let depositCollected = parseFloat($state.attr('data-deposit-collected')) || 0;
                let fineCollected = parseFloat($state.attr('data-fine-collected')) || 0;

                return contractCollected + depositCollected + fineCollected;
            }

            // --- احتياط فقط قبل أول حفظ ---
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



        function buildPaymentSummaryBoxHtml(extraClass = '') {
            return `
                <div class="live-payment-summary-box rental-payment-summary ${extraClass}">
                    <div class="rental-payment-summary__title">
                        Payment Summary
                    </div>

                    <div class="rental-payment-summary__row">
                        <span class="rental-payment-summary__label">Net Total</span>
                        <span class="live-net-total-value rental-payment-summary__value">$0.00</span>
                    </div>

                    <div class="rental-payment-summary__row">
                        <span class="rental-payment-summary__label">Total Paid</span>
                        <span class="live-total-paid-value rental-payment-summary__value rental-payment-summary__value--paid">$0.00</span>
                    </div>

                    <div class="rental-payment-summary__row rental-payment-summary__row--last">
                        <span class="rental-payment-summary__label rental-payment-summary__label--strong">Remaining Balance</span>
                        <span class="live-remaining-balance-value rental-payment-summary__value rental-payment-summary__value--remaining">$0.00</span>
                    </div>
                </div>
            `;
        }

        function ensurePaymentSummaryBoxes() {
            // --- لا نظهر الصناديق إلا داخل صفحة العقد ---
            if (!isRentalFormPage()) return;

            if ($('.live-payment-summary-box').length) return;

            let attachmentsGroup = $('#attachments-group, #rentalattachment_set-group');
            let paymentsGroup = $('#payments-group');
            let topTarget = $('#content-main form .form-row, #content-main form fieldset.module').first();

            // --- الصندوق العلوي ---
            if (topTarget.length) {
                topTarget.before(buildPaymentSummaryBoxHtml('live-payment-summary-box--top'));
            }

            // --- الصندوق السفلي قبل المرفقات ---
            if (attachmentsGroup.length) {
                attachmentsGroup.before(buildPaymentSummaryBoxHtml('live-payment-summary-box--bottom'));
            } else if (paymentsGroup.length) {
                paymentsGroup.after(buildPaymentSummaryBoxHtml('live-payment-summary-box--bottom'));
            }

            // --- احتياط ---
            if (!$('.live-payment-summary-box').length) {
                $('#content-main form').prepend(buildPaymentSummaryBoxHtml('live-payment-summary-box--top'));
            }
        }

        function updatePaymentSummaryLive() {
            ensurePaymentSummaryBox();

            let netTotal = getNetTotalValue();
            let payments = getPaymentsTotal();
            let remaining = netTotal - payments;

            $('.live-net-total-value').text('$' + netTotal.toFixed(2));
            $('.live-total-paid-value').text('$' + payments.toFixed(2));
            $('.live-remaining-balance-value').text('$' + remaining.toFixed(2));
        }
        

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
    '#id_start_date, #id_start_date_0, #id_start_date_1, #id_end_date, #id_end_date_0, #id_end_date_1, #id_daily_rate, #id_vat_percentage, #id_deposit_amount, #id_traffic_fines, #id_damage_fees, #id_other_charges',
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
        formatUI();

        if (isRentalFormPage()) {
            calculateNow();
            setTimeout(function () {
                updatePaymentSummaryLive();
            }, 200);
        }

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