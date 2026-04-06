/**
 * payment_currency_ui.js
 *
 * الإصدار الجديد:
 * - لا يسمح بإدخال exchange_rate_to_usd يدويًا
 * - يوضح أن المبلغ يُدخل بالعملة المختارة
 * - يوضح أن المعادل بالدولار يُحسب تلقائيًا من Exchange Rates
 */

window.addEventListener('load', function () {
    (function ($) {
        var CURRENCY_META = {
            USD: { symbol: '$',   name: 'US Dollar' },
            IQD: { symbol: 'IQD', name: 'Iraqi Dinar' },
            SYP: { symbol: 'SYP', name: 'Syrian Pound' },
            AED: { symbol: 'AED', name: 'UAE Dirham' }
        };

        var $currencySelect  = $('#id_currency_code');
        var $amountPaidInput = $('#id_amount_paid');
        var $paymentDate     = $('#id_payment_date');

        var $amountField     = $('.field-amount_paid');
        var $amountUsdField  = $('.field-amount_usd');
        var $rateField       = $('.field-exchange_rate_to_usd');
        var $rateDateField   = $('.field-exchange_rate_date');

        function ensureHint($container, className, text, color) {
            var $hint = $container.find('.' + className);

            if ($hint.length === 0) {
                $container.append(
                    '<div class="' + className + '" style="margin-top:4px; font-size:12px; color:' + color + ';"></div>'
                );
                $hint = $container.find('.' + className);
            }

            $hint.text(text);
        }

        function updateUI() {
            var code = $currencySelect.val() || 'USD';
            var meta = CURRENCY_META[code] || CURRENCY_META['USD'];

            // =====================================================
            // تحديث تسمية حقل المبلغ
            // =====================================================
            var $amountLabel = $amountField.find('label').first();
            if ($amountLabel.length) {
                $amountLabel.text('Amount to Collect (' + meta.symbol + ')');
            }

            // =====================================================
            // توضيح للموظف ماذا يدخل هنا
            // =====================================================
            ensureHint(
                $amountField,
                'payment-collect-hint',
                'Enter the actual amount collected from the customer in ' + meta.name + '.',
                '#6b7280'
            );

            // =====================================================
            // توضيح أن الدولار يُحسب تلقائيًا
            // =====================================================
            var paymentDateText = $paymentDate.val() || 'the selected payment date';

            ensureHint(
                $amountUsdField,
                'payment-usd-hint',
                'USD equivalent is calculated automatically from Exchange Rates using ' + paymentDateText + '.',
                '#1d4ed8'
            );

            // =====================================================
            // إخفاء أي بقايا للحقل اليدوي القديم في شاشة الإدخال
            // =====================================================
            if ($rateField.length && $rateField.find('.readonly').length === 0) {
                $rateField.hide();
            }

            if ($rateDateField.length && $rateDateField.find('.readonly').length === 0) {
                $rateDateField.hide();
            }
        }

        $currencySelect.on('change', updateUI);
        $amountPaidInput.on('input', updateUI);
        $paymentDate.on('change', updateUI);

        updateUI();
    })(django.jQuery);
});