'use strict';

// PATH: static/admin/js/journal_item_currency.js

(function ($) {

    function buildApiUrl() {
        const parts = window.location.pathname.split('/');
        const idx   = parts.indexOf('journalentry');
        if (idx === -1) return null;
        return parts.slice(0, idx + 1).join('/') + '/api/exchange-rate/';
    }
    const RATE_API_URL = buildApiUrl();

    const rateCache = {};

    async function fetchRate(currency, date) {
        if (!currency || currency === 'USD') return 1.0;
        const key = `${currency}_${date}`;
        if (rateCache[key] !== undefined) return rateCache[key];
        try {
            const resp = await fetch(
                `${RATE_API_URL}?currency=${encodeURIComponent(currency)}&date=${encodeURIComponent(date)}`
            );
            const data = await resp.json();
            rateCache[key] = (resp.ok && data.rate) ? parseFloat(data.rate) : null;
        } catch (e) { rateCache[key] = null; }
        return rateCache[key];
    }

    function getEntryDate() {
        const el = document.getElementById('id_entry_date');
        return el ? el.value.trim() : '';
    }

    function updateBadge(input, currency) {
        let badge = input.parentElement.querySelector('.currency-badge');
        if (!currency || currency === 'USD') {
            if (badge) badge.remove();
            input.style.borderColor = '';
            return;
        }
        if (!badge) {
            badge = document.createElement('span');
            badge.className  = 'currency-badge';
            badge.style.cssText = (
                'display:inline-block; margin-left:4px; padding:2px 6px;'
                + ' background:#fef3c7; color:#92400e; font-size:11px;'
                + ' border-radius:3px; font-weight:600; vertical-align:middle;'
            );
            input.insertAdjacentElement('afterend', badge);
        }
        badge.textContent     = currency;
        input.style.borderColor = '#f59e0b';
    }

    function updateCurrencyBadges(row) {
        const currencyEl = row.querySelector('select[name$="-original_currency_code"]');
        const debitEl    = row.querySelector('input[name$="-debit"]');
        const creditEl   = row.querySelector('input[name$="-credit"]');
        if (!currencyEl || !debitEl || !creditEl) return;
        const currency = currencyEl.value;
        updateBadge(debitEl,  currency);
        updateBadge(creditEl, currency);
    }

    function getOrCreateHint(row) {
        let hint = row.querySelector('.rate-hint');
        if (!hint) {
            hint = document.createElement('div');
            hint.className    = 'rate-hint';
            hint.style.cssText = (
                'font-size:11px; margin-top:3px; padding:2px 5px;'
                + ' border-radius:3px; white-space:nowrap; display:none;'
            );
            const creditEl = row.querySelector('input[name$="-credit"]');
            if (creditEl && creditEl.closest('td')) {
                creditEl.closest('td').appendChild(hint);
            }
        }
        return hint;
    }

    function showHint(row, msg, isError) {
        const hint = getOrCreateHint(row);
        hint.textContent      = msg;
        hint.style.display    = 'block';
        hint.style.color      = isError ? '#dc2626' : '#15803d';
        hint.style.background = isError ? '#fef2f2' : '#f0fdf4';
    }

    function clearHint(row) {
        const hint = row.querySelector('.rate-hint');
        if (hint) { hint.textContent = ''; hint.style.display = 'none'; }
    }

    let pendingConversions = 0;

    async function handleAmountInput(row, side) {
        const currencyEl   = row.querySelector('select[name$="-original_currency_code"]');
        const debitEl      = row.querySelector('input[name$="-debit"]');
        const creditEl     = row.querySelector('input[name$="-credit"]');
        const origAmountEl = row.querySelector('input[name$="-original_amount"]');
        if (!currencyEl || !debitEl || !creditEl) return;

        const currency = currencyEl.value;
        const activeEl = side === 'debit' ? debitEl : creditEl;
        const otherEl  = side === 'debit' ? creditEl : debitEl;
        const amount   = parseFloat(activeEl.value.replace(/,/g, '').trim());

        if (isNaN(amount) || amount <= 0) { clearHint(row); return; }

        otherEl.value = '0.00';

        if (!currency || currency === 'USD') {
            if (origAmountEl) origAmountEl.value = amount.toFixed(2);
            clearHint(row);
            return;
        }

        const date = getEntryDate();
        if (!date) { showHint(row, '⚠ حدد تاريخ القيد أولاً', true); return; }

        pendingConversions++;
        showHint(row, '⏳ جاري جلب سعر الصرف...', false);

        const rate = await fetchRate(currency, date);
        pendingConversions--;

        if (rate === null) {
            showHint(row, `⚠ لا يوجد سعر صرف لـ ${currency} بتاريخ ${date}`, true);
            return;
        }

        const usdAmount = (amount * rate).toFixed(2);
        if (origAmountEl) origAmountEl.value = amount.toFixed(2);
        activeEl.value = usdAmount;

        const unitsPerUsd = Math.round(1 / rate).toLocaleString();
        showHint(row, `✓ ${amount.toLocaleString()} ${currency} ÷ ${unitsPerUsd} = ${parseFloat(usdAmount).toLocaleString()} USD`, false);
    }

    const setupDone = new WeakSet();

    function setupRow(row) {
        if (setupDone.has(row)) return;
        if (!row.querySelector('input[name$="-debit"]')) return;
        setupDone.add(row);

        const currencyEl = row.querySelector('select[name$="-original_currency_code"]');
        const debitEl    = row.querySelector('input[name$="-debit"]');
        const creditEl   = row.querySelector('input[name$="-credit"]');

        if (currencyEl) {
            currencyEl.addEventListener('change', () => {
                updateCurrencyBadges(row);
                clearHint(row);
            });
        }
        if (debitEl) {
            debitEl.addEventListener('blur',   () => handleAmountInput(row, 'debit'));
            debitEl.addEventListener('change', () => handleAmountInput(row, 'debit'));
        }
        if (creditEl) {
            creditEl.addEventListener('blur',   () => handleAmountInput(row, 'credit'));
            creditEl.addEventListener('change', () => handleAmountInput(row, 'credit'));
        }

        updateCurrencyBadges(row);
    }

    function findAllJournalRows() {
        return Array.from(
            document.querySelectorAll('tr input[name$="-debit"]')
        ).map(input => input.closest('tr')).filter(Boolean);
    }

    function getLastUsedCurrency() {
        const rows = findAllJournalRows();
        for (let i = rows.length - 1; i >= 0; i--) {
            const sel = rows[i].querySelector('select[name$="-original_currency_code"]');
            if (sel && sel.value && sel.value !== 'USD') return sel.value;
        }
        return null;
    }

    function inheritCurrencyOnNewRows() {
        findAllJournalRows().forEach(row => {
            if (setupDone.has(row)) return;
            const inheritedCurrency = getLastUsedCurrency();
            if (inheritedCurrency) {
                const sel = row.querySelector('select[name$="-original_currency_code"]');
                if (sel && sel.value === 'USD') {
                    sel.value = inheritedCurrency;
                }
            }
            setupRow(row);
            updateCurrencyBadges(row);
        });
    }

    function attachAddRowButton() {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('a, button');
            if (!btn) return;
            const text = btn.textContent.trim().toLowerCase();
            if (!text.includes('add another')) return;
            setTimeout(inheritCurrencyOnNewRows, 150);
        });
    }

    function startObserver() {
        const observer = new MutationObserver(inheritCurrencyOnNewRows);
        observer.observe(document.body, { childList: true, subtree: true });
    }

    function attachSubmitGuard() {
        document.addEventListener('submit', async function (e) {
            const rows = findAllJournalRows();
            const pending = rows.filter(row => {
                const currencyEl   = row.querySelector('select[name$="-original_currency_code"]');
                const origAmountEl = row.querySelector('input[name$="-original_amount"]');
                const debitEl      = row.querySelector('input[name$="-debit"]');
                const creditEl     = row.querySelector('input[name$="-credit"]');
                if (!currencyEl || !debitEl || !creditEl) return false;
                if (!currencyEl.value || currencyEl.value === 'USD') return false;
                if (origAmountEl && parseFloat(origAmountEl.value) > 0) return false;
                return parseFloat(debitEl.value) > 0 || parseFloat(creditEl.value) > 0;
            });

            if (pending.length === 0) return;

            e.preventDefault();
            e.stopImmediatePropagation();

            for (const row of pending) {
                const debitVal = parseFloat(row.querySelector('input[name$="-debit"]').value) || 0;
                await handleAmountInput(row, debitVal > 0 ? 'debit' : 'credit');
            }

            e.target.submit();
        }, true);
    }

    function init() {
        if (!RATE_API_URL) return;
        findAllJournalRows().forEach(row => setupRow(row));
        startObserver();
        attachSubmitGuard();
        attachAddRowButton();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})(django.jQuery);