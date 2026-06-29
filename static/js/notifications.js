/* ============================================================
   NeuroSight — Shared Notifications & Alerts Engine v2
   Features: rich toasts, snooze, price + % + volume alerts,
   sound notifications, alert notes, recurring alerts, expiry,
   local fallback storage, categorised notification history.
   ============================================================ */
(function () {
    'use strict';

    /* ─────────────────────────────────────────────────────────
       CONSTANTS & SETTINGS
    ───────────────────────────────────────────────────────── */
    const STORAGE_KEY      = 'ns_notifications';
    const SETTINGS_KEY     = 'ns_alert_settings';
    const SNOOZE_KEY       = 'ns_snoozed_alerts';
    const MAX_NOTIFS       = 50;
    const ALERT_CHECK_FREQ = 60000;

    function getSettings() {
        try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function saveSettings(s) { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); }
    function getSetting(key, def) { const s = getSettings(); return key in s ? s[key] : def; }
    function setSetting(key, val) { const s = getSettings(); s[key] = val; saveSettings(s); }

    window.nsToggleSound = function () {
        const cur = getSetting('sound', true);
        setSetting('sound', !cur);
        nsToast('Sound Notifications', (!cur ? 'Enabled' : 'Disabled'), 'info', 2000);
    };

    window.setSoundPref = function (val) { setSetting('sound', val); };

    /* ─────────────────────────────────────────────────────────
       SOUND  (Web Audio API — no external files needed)
    ───────────────────────────────────────────────────────── */
    function playAlertSound(type) {
        if (!getSetting('sound', true)) return;
        try {
            const ctx  = new (window.AudioContext || window.webkitAudioContext)();
            const osc  = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            if (type === 'price-up') {
                osc.frequency.setValueAtTime(880,  ctx.currentTime);
                osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.12);
            } else if (type === 'price-down') {
                osc.frequency.setValueAtTime(660, ctx.currentTime);
                osc.frequency.setValueAtTime(440, ctx.currentTime + 0.12);
            } else {
                osc.frequency.setValueAtTime(820, ctx.currentTime);
            }
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
            osc.type = 'sine';
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.35);
        } catch (e) { /* browser blocked audio */ }
    }

    /* ─────────────────────────────────────────────────────────
       TOAST CONTAINER
    ───────────────────────────────────────────────────────── */
    function ensureToastContainer() {
        let c = document.getElementById('ns-toast-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'ns-toast-container';
            c.className = 'ns-toast-container';
            document.body.appendChild(c);
        }
        return c;
    }

    /* ─────────────────────────────────────────────────────────
       TOAST API
    ───────────────────────────────────────────────────────── */
    const ICONS = {
        success: '✓', error: '✕', warning: '⚠', info: 'ℹ',
        'price-up': '▲', 'price-down': '▼', alert: '🔔', system: '⚙'
    };

    const TYPE_COLORS = {
        success:      { bg: 'rgba(23,191,99,0.18)',   border: 'rgba(23,191,99,0.5)',   icon: '#17bf63' },
        error:        { bg: 'rgba(224,36,94,0.18)',   border: 'rgba(224,36,94,0.5)',   icon: '#e0245e' },
        warning:      { bg: 'rgba(255,173,31,0.18)',  border: 'rgba(255,173,31,0.5)',  icon: '#ffad1f' },
        info:         { bg: 'rgba(29,161,242,0.18)',  border: 'rgba(29,161,242,0.5)',  icon: '#1da1f2' },
        'price-up':   { bg: 'rgba(23,191,99,0.18)',   border: 'rgba(23,191,99,0.5)',   icon: '#17bf63' },
        'price-down': { bg: 'rgba(224,36,94,0.18)',   border: 'rgba(224,36,94,0.5)',   icon: '#e0245e' },
        alert:        { bg: 'rgba(139,92,246,0.18)',  border: 'rgba(139,92,246,0.5)',  icon: '#8b5cf6' },
        system:       { bg: 'rgba(100,116,139,0.18)', border: 'rgba(100,116,139,0.5)', icon: '#64748b' },
    };

    window.nsToast = function (title, msg, type, duration, opts) {
        type     = type     || 'info';
        duration = duration || 4500;
        opts     = opts     || {};
        const container = ensureToastContainer();
        const colors    = TYPE_COLORS[type] || TYPE_COLORS.info;

        const el = document.createElement('div');
        el.className = 'ns-toast ' + type;
        el.style.cssText = 'background:' + colors.bg + ';border-left:4px solid ' + colors.border + ';';

        const snoozeBtn = opts.snooze
            ? '<button class="ns-toast-snooze">\u23F8 Snooze 30m</button>'
            : '';

        el.innerHTML =
            '<span class="ns-toast-icon" style="color:' + colors.icon + '">' + (ICONS[type] || 'ℹ') + '</span>' +
            '<div class="ns-toast-body">' +
            '  <div class="ns-toast-title">' + title + '</div>' +
            '  <div class="ns-toast-msg">' + msg + '</div>' +
            '  ' + snoozeBtn +
            '</div>' +
            '<button class="ns-toast-close" aria-label="Close">&times;</button>';

        container.appendChild(el);

        if (opts.snooze) {
            el.querySelector('.ns-toast-snooze').onclick = function (e) {
                e.stopPropagation();
                snoozeAlert(opts.alertId || title);
                dismissToast(el);
                nsToast('Snoozed', 'Alert paused for 30 minutes', 'info', 2500);
            };
        }

        el.querySelector('.ns-toast-close').onclick = function (e) {
            e.stopPropagation();
            dismissToast(el);
        };
        el.onclick = function () { dismissToast(el); };

        requestAnimationFrame(function () { el.classList.add('show'); });
        const timer = setTimeout(function () { dismissToast(el); }, duration);
        el._timer   = timer;

        playAlertSound(type);
        addNotification({ title: title, msg: msg, type: type, ts: Date.now(), category: opts.category || type });
    };

    function dismissToast(el) {
        if (el._dismissed) return;
        el._dismissed = true;
        clearTimeout(el._timer);
        el.classList.remove('show');
        el.classList.add('exit');
        setTimeout(function () { el.remove(); }, 400);
    }

    /* ─────────────────────────────────────────────────────────
       SNOOZE
    ───────────────────────────────────────────────────────── */
    function snoozeAlert(alertId) {
        try {
            const snoozed = JSON.parse(localStorage.getItem(SNOOZE_KEY) || '{}');
            snoozed[String(alertId)] = Date.now() + 30 * 60 * 1000;
            localStorage.setItem(SNOOZE_KEY, JSON.stringify(snoozed));
        } catch (e) {}
    }

    function isSnoozed(alertId) {
        try {
            const snoozed = JSON.parse(localStorage.getItem(SNOOZE_KEY) || '{}');
            const until   = snoozed[String(alertId)];
            return until && Date.now() < until;
        } catch (e) { return false; }
    }

    /* ─────────────────────────────────────────────────────────
       NOTIFICATION STORE
    ───────────────────────────────────────────────────────── */
    function getNotifications() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
        catch (e) { return []; }
    }

    function saveNotifications(list) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_NOTIFS)));
    }

    function addNotification(n) {
        const list = getNotifications();
        list.unshift(Object.assign({}, n, {
            id: Date.now() + '_' + Math.random().toString(36).slice(2, 6),
            read: false
        }));
        saveNotifications(list);
        updateBellBadge();
        renderNotifList();
    }

    window.nsGetNotifications = getNotifications;

    function getUnreadCount() {
        return getNotifications().filter(function (n) { return !n.read; }).length;
    }

    /* ─────────────────────────────────────────────────────────
       BELL BADGE
    ───────────────────────────────────────────────────────── */
    function updateBellBadge() {
        const badge = document.getElementById('ns-bell-badge');
        if (!badge) return;
        const count = getUnreadCount();
        badge.textContent   = count > 9 ? '9+' : (count || '');
        badge.style.display = count > 0 ? '' : 'none';
        badge.setAttribute('data-count', count);
    }

    /* ─────────────────────────────────────────────────────────
       NOTIFICATION DROPDOWN — RICH RENDER
    ───────────────────────────────────────────────────────── */
    const NOTIF_ICONS = {
        success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️',
        'price-up': '📈', 'price-down': '📉', alert: '🔔', system: '⚙️',
    };

    function renderNotifList() {
        const listEl = document.getElementById('ns-notif-list');
        if (!listEl) return;
        const items = getNotifications();
        if (items.length === 0) {
            listEl.innerHTML = '<div class="ns-notif-empty"><div style="font-size:2rem;margin-bottom:8px;">🔔</div><p>No notifications yet</p></div>';
            return;
        }
        listEl.innerHTML = items.map(function (n) {
            const ago  = timeAgo(n.ts);
            const icon = NOTIF_ICONS[n.type] || '🔔';
            return '<div class="ns-notif-item ' + (n.read ? '' : 'unread') + '" data-id="' + n.id + '" onclick="nsMarkOneRead(\'' + n.id + '\')">' +
                '<span class="ni-icon">' + icon + '</span>' +
                '<div class="ni-body">' +
                '  <div class="ni-title">' + n.title + '</div>' +
                '  <div class="ni-desc">' + n.msg + '</div>' +
                '  <div class="ni-time">' + ago + '</div>' +
                '</div>' +
                '<button class="ni-del" onclick="event.stopPropagation();nsDeleteNotif(\'' + n.id + '\')" title="Remove">\u2715</button>' +
                '</div>';
        }).join('');
    }

    window.nsDeleteNotif = function (id) {
        saveNotifications(getNotifications().filter(function (n) { return n.id !== id; }));
        updateBellBadge();
        renderNotifList();
    };

    window.nsMarkOneRead = function (id) {
        const list = getNotifications();
        const item = list.find(function (n) { return n.id === id; });
        if (item) { item.read = true; saveNotifications(list); updateBellBadge(); renderNotifList(); }
    };

    function timeAgo(ts) {
        const diff = Date.now() - ts;
        if (diff < 60000)    return 'Just now';
        if (diff < 3600000)  return Math.floor(diff / 60000)    + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000)  + 'h ago';
        return                      Math.floor(diff / 86400000) + 'd ago';
    }

    window.nsClearNotifications = function () {
        saveNotifications([]);
        updateBellBadge();
        renderNotifList();
    };

    window.nsMarkAllRead = function () {
        const list = getNotifications();
        list.forEach(function (n) { n.read = true; });
        saveNotifications(list);
        updateBellBadge();
        renderNotifList();
    };

    /* ─────────────────────────────────────────────────────────
       BELL TOGGLE
    ───────────────────────────────────────────────────────── */
    window.nsToggleNotifDropdown = function () {
        const dd = document.getElementById('ns-notif-dropdown');
        if (!dd) return;
        if (dd.classList.contains('open')) {
            dd.classList.remove('open');
        } else {
            dd.classList.add('open');
            nsMarkAllRead();
        }
    };

    document.addEventListener('click', function (e) {
        const dd   = document.getElementById('ns-notif-dropdown');
        const bell = document.getElementById('ns-bell-wrap');
        if (dd && dd.classList.contains('open') && bell && !bell.contains(e.target)) {
            dd.classList.remove('open');
        }
    });

    /* ─────────────────────────────────────────────────────────
       ALERT MODAL — SHOW / CLOSE / INJECT
    ───────────────────────────────────────────────────────── */
    window.nsShowAlertModal = function (preSymbol) {
        ensureAlertModal();
        const overlay = document.getElementById('ns-alert-modal-overlay');
        if (!overlay) return;
        overlay.classList.add('show');
        if (preSymbol) {
            const sym = document.getElementById('ns-alert-symbol');
            if (sym) sym.value = preSymbol;
        }
        loadActiveAlerts();
    };

    window.nsCloseAlertModal = function () {
        const overlay = document.getElementById('ns-alert-modal-overlay');
        if (overlay) overlay.classList.remove('show');
    };

    /* ─────────────────────────────────────────────────────────
       BUILD & INJECT ENHANCED ALERT MODAL
    ───────────────────────────────────────────────────────── */
    function ensureAlertModal() {
        /* If an old modal exists without tabs, remove it and rebuild */
        const existing = document.getElementById('ns-alert-modal-overlay');
        if (existing) {
            if (!existing.querySelector('.ns-alert-tabs')) {
                existing.remove();
            } else {
                return; // already the new version
            }
        }

        const overlay = document.createElement('div');
        overlay.id        = 'ns-alert-modal-overlay';
        overlay.className = 'ns-alert-modal-overlay';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) nsCloseAlertModal();
        });
        overlay.innerHTML = _buildAlertModalHTML();
        document.body.appendChild(overlay);

        if (!document.getElementById('ns-alert-styles')) {
            _injectAlertStyles();
        }
    }

    function _buildAlertModalHTML() {
        const soundChecked = getSetting('sound', true) ? 'checked' : '';
        return (
            '<div class="ns-alert-modal ns-alert-modal-v2">' +

            /* Header */
            '<div class="ns-alert-header">' +
            '  <div style="display:flex;align-items:center;gap:10px;">' +
            '    <div style="width:36px;height:36px;background:linear-gradient(135deg,#8b5cf6,#6366f1);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;">🔔</div>' +
            '    <div>' +
            '      <div style="font-size:1.05rem;font-weight:700;color:#fff;">Price Alerts</div>' +
            '      <div style="font-size:0.72rem;color:#8899a6;">Get notified when targets are hit</div>' +
            '    </div>' +
            '  </div>' +
            '  <button class="ns-alert-close" onclick="nsCloseAlertModal()">\u2715</button>' +
            '</div>' +

            /* Tabs */
            '<div class="ns-alert-tabs">' +
            '  <button class="ns-tab active" onclick="nsSelectAlertTab(\'price\',this)">\uD83D\uDCB0 Price</button>' +
            '  <button class="ns-tab" onclick="nsSelectAlertTab(\'percent\',this)">\uD83D\uDCCA % Move</button>' +
            '  <button class="ns-tab" onclick="nsSelectAlertTab(\'volume\',this)">\uD83D\uDCC8 Volume</button>' +
            '</div>' +

            /* Form */
            '<div class="ns-alert-form">' +

            /* Asset selector */
            '<div class="ns-alert-form-group">' +
            '  <label>Asset</label>' +
            '  <select id="ns-alert-symbol" class="ns-select">' +
            '    <optgroup label="\uD83E\uDD16 AI-Predicted">' +
            '      <option value="AAPL">\uD83C\uDF4E Apple (AAPL)</option>' +
            '      <option value="NVDA">\uD83D\uDFE2 NVIDIA (NVDA)</option>' +
            '      <option value="TSLA">\u26A1 Tesla (TSLA)</option>' +
            '      <option value="GC=F">\uD83E\uDD47 Gold (GC=F)</option>' +
            '    </optgroup>' +
            '    <optgroup label="\uD83D\uDCCA Live Market">' +
            '      <option value="MSFT">\uD83E\uDE9F Microsoft (MSFT)</option>' +
            '      <option value="GOOGL">\uD83D\uDD0D Alphabet (GOOGL)</option>' +
            '      <option value="AMZN">\uD83D\uDCE6 Amazon (AMZN)</option>' +
            '      <option value="META">\uD83D\uDC41 Meta (META)</option>' +
            '      <option value="AMD">\uD83D\uDD34 AMD (AMD)</option>' +
            '    </optgroup>' +
            '  </select>' +
            '</div>' +

            /* Price tab */
            '<div id="ns-tab-price" class="ns-tab-content active">' +
            '  <div class="ns-alert-form-row">' +
            '    <div class="ns-alert-form-group">' +
            '      <label>Condition</label>' +
            '      <select id="ns-alert-condition" class="ns-select">' +
            '        <option value="above">\uD83D\uDCC8 Goes above</option>' +
            '        <option value="below">\uD83D\uDCC9 Goes below</option>' +
            '      </select>' +
            '    </div>' +
            '    <div class="ns-alert-form-group">' +
            '      <label>Target Price ($)</label>' +
            '      <input type="number" id="ns-alert-price" class="ns-input" step="0.01" placeholder="0.00" min="0">' +
            '    </div>' +
            '  </div>' +
            '</div>' +

            /* Percent tab */
            '<div id="ns-tab-percent" class="ns-tab-content">' +
            '  <div class="ns-alert-form-row">' +
            '    <div class="ns-alert-form-group">' +
            '      <label>Direction</label>' +
            '      <select id="ns-alert-pct-dir" class="ns-select">' +
            '        <option value="up">\uD83D\uDCC8 Rises by %</option>' +
            '        <option value="down">\uD83D\uDCC9 Falls by %</option>' +
            '        <option value="either">\u2195 Either direction</option>' +
            '      </select>' +
            '    </div>' +
            '    <div class="ns-alert-form-group">' +
            '      <label>% Threshold</label>' +
            '      <input type="number" id="ns-alert-pct" class="ns-input" step="0.5" placeholder="5.0" min="0.1" max="100">' +
            '    </div>' +
            '  </div>' +
            '  <div class="ns-info-box">\u23F1 Monitors change from price at time of creation</div>' +
            '</div>' +

            /* Volume tab */
            '<div id="ns-tab-volume" class="ns-tab-content">' +
            '  <div class="ns-alert-form-group">' +
            '    <label>Volume multiplier (vs 20-day avg)</label>' +
            '    <select id="ns-alert-vol-mult" class="ns-select">' +
            '      <option value="1.5">1.5\u00D7 \u2014 Mild spike</option>' +
            '      <option value="2.0" selected>2.0\u00D7 \u2014 Significant spike</option>' +
            '      <option value="3.0">3.0\u00D7 \u2014 Extreme spike</option>' +
            '    </select>' +
            '  </div>' +
            '  <div class="ns-info-box">\uD83D\uDCCA Fires when intraday volume exceeds the multiplier</div>' +
            '</div>' +

            /* Note */
            '<div class="ns-alert-form-group" style="margin-top:12px;">' +
            '  <label>Note (optional)</label>' +
            '  <input type="text" id="ns-alert-note" class="ns-input" placeholder="e.g. earnings play, stop-loss…" maxlength="80">' +
            '</div>' +

            /* Options row */
            '<div class="ns-alert-options-row">' +
            '  <label class="ns-toggle-label" title="Re-fire each time condition is met">' +
            '    <input type="checkbox" id="ns-alert-recurring">' +
            '    <span class="ns-mini-toggle"></span> Recurring' +
            '  </label>' +
            '  <select id="ns-alert-expiry" class="ns-select" style="flex:1;padding:7px 10px;font-size:0.8rem;">' +
            '    <option value="never">No expiry</option>' +
            '    <option value="1d">Expires in 1 day</option>' +
            '    <option value="7d">Expires in 7 days</option>' +
            '    <option value="30d">Expires in 30 days</option>' +
            '  </select>' +
            '  <label class="ns-toggle-label" title="Play a sound when alert fires">' +
            '    <input type="checkbox" id="ns-alert-sound" ' + soundChecked + ' onchange="setSoundPref(this.checked)">' +
            '    <span class="ns-mini-toggle"></span> Sound' +
            '  </label>' +
            '</div>' +

            '</div>' + /* end .ns-alert-form */

            /* Active alerts */
            '<div id="ns-active-alerts" class="ns-active-alerts"></div>' +

            /* Actions */
            '<div class="ns-alert-actions">' +
            '  <button class="ns-alert-btn secondary" onclick="nsCloseAlertModal()">Cancel</button>' +
            '  <button class="ns-alert-btn primary" onclick="nsCreateAlert()">🔔 Set Alert</button>' +
            '</div>' +

            '</div>' /* end .ns-alert-modal-v2 */
        );
    }

    window.nsSelectAlertTab = function (tab, btn) {
        document.querySelectorAll('.ns-alert-tabs .ns-tab').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.ns-tab-content').forEach(function (t) { t.classList.remove('active'); });
        if (btn) btn.classList.add('active');
        const content = document.getElementById('ns-tab-' + tab);
        if (content) content.classList.add('active');
        const modal = document.querySelector('.ns-alert-modal-v2');
        if (modal) modal.dataset.activeTab = tab;
    };

    function _getActiveAlertTab() {
        const modal = document.querySelector('.ns-alert-modal-v2');
        return modal ? (modal.dataset.activeTab || 'price') : 'price';
    }

    /* ─────────────────────────────────────────────────────────
       CREATE ALERT
    ───────────────────────────────────────────────────────── */
    window.nsCreateAlert = async function () {
        const symbol    = document.getElementById('ns-alert-symbol');
        const note      = document.getElementById('ns-alert-note');
        const recurring = document.getElementById('ns-alert-recurring');
        const expiry    = document.getElementById('ns-alert-expiry');
        if (!symbol) return;

        const tab     = _getActiveAlertTab();
        const userId  = localStorage.getItem('user_id') || 'guest';
        var payload   = {
            stock_symbol: symbol.value,
            note:         note      ? note.value.trim()   : '',
            recurring:    recurring ? recurring.checked   : false,
            expiry:       expiry    ? expiry.value        : 'never',
        };

        if (tab === 'price') {
            const cond  = document.getElementById('ns-alert-condition');
            const price = document.getElementById('ns-alert-price');
            if (!price || !price.value) {
                nsToast('Missing value', 'Please enter a target price', 'error', 3000); return;
            }
            payload.alert_type   = cond ? cond.value : 'above';
            payload.target_price = parseFloat(price.value);
            price.value = '';

        } else if (tab === 'percent') {
            const dir = document.getElementById('ns-alert-pct-dir');
            const pct = document.getElementById('ns-alert-pct');
            if (!pct || !pct.value) {
                nsToast('Missing value', 'Please enter a % threshold', 'error', 3000); return;
            }
            payload.alert_type   = 'pct_' + (dir ? dir.value : 'up');
            payload.target_price = parseFloat(pct.value);
            pct.value = '';

        } else if (tab === 'volume') {
            const mult           = document.getElementById('ns-alert-vol-mult');
            payload.alert_type   = 'volume';
            payload.target_price = parseFloat(mult ? mult.value : '2.0');
        }

        try {
            const resp = await fetch('/api/user/' + userId + '/alerts', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload)
            });
            if (resp.ok) {
                const label = payload.note ? ' \u201C' + payload.note + '\u201D' : '';
                nsToast('Alert Set \u2705', symbol.value + ' \u2014 ' + _alertTypeLabel(payload.alert_type, payload.target_price) + label, 'success', 4000);
                if (note) note.value = '';
                loadActiveAlerts();
            } else {
                _storeLocalAlert(payload);
                nsToast('Alert saved locally', 'Server unavailable — will check when online', 'warning', 4000);
                loadActiveAlerts();
            }
        } catch (e) {
            _storeLocalAlert(payload);
            nsToast('Alert saved locally', 'No connection — stored in browser', 'warning', 4000);
            loadActiveAlerts();
        }
    };

    function _alertTypeLabel(type, val) {
        if (type === 'above')      return 'goes above $' + val;
        if (type === 'below')      return 'goes below $' + val;
        if (type === 'pct_up')     return 'rises '   + val + '%';
        if (type === 'pct_down')   return 'falls '   + val + '%';
        if (type === 'pct_either') return 'moves \u00B1'  + val + '%';
        if (type === 'volume')     return 'volume '  + val + '\u00D7 spike';
        return type;
    }

    function _storeLocalAlert(payload) {
        try {
            const local = JSON.parse(localStorage.getItem('ns_local_alerts') || '[]');
            local.push(Object.assign({}, payload, { alert_id: 'local_' + Date.now(), created_at: Date.now() }));
            localStorage.setItem('ns_local_alerts', JSON.stringify(local));
        } catch (e) {}
    }

    function _getLocalAlerts() {
        try { return JSON.parse(localStorage.getItem('ns_local_alerts') || '[]'); }
        catch (e) { return []; }
    }

    /* ─────────────────────────────────────────────────────────
       DELETE ALERT
    ───────────────────────────────────────────────────────── */
    window.nsDeleteAlert = async function (alertId) {
        if (String(alertId).startsWith('local_')) {
            const local = _getLocalAlerts().filter(function (a) { return a.alert_id !== alertId; });
            localStorage.setItem('ns_local_alerts', JSON.stringify(local));
            loadActiveAlerts();
            return;
        }
        const userId = localStorage.getItem('user_id') || 'guest';
        try {
            await fetch('/api/user/' + userId + '/alerts/' + alertId, { method: 'DELETE' });
            loadActiveAlerts();
        } catch (e) {}
    };

    /* ─────────────────────────────────────────────────────────
       LOAD & RENDER ACTIVE ALERTS
    ───────────────────────────────────────────────────────── */
    async function loadActiveAlerts() {
        const listEl = document.getElementById('ns-active-alerts');
        if (!listEl) return;
        const userId = localStorage.getItem('user_id') || 'guest';

        var alerts = [];
        try {
            const resp = await fetch('/api/user/' + userId + '/alerts');
            if (resp.ok) {
                const data = await resp.json();
                alerts = data.alerts || [];
            }
        } catch (e) {}

        // Merge local fallback
        alerts = alerts.concat(_getLocalAlerts());

        if (alerts.length === 0) {
            listEl.innerHTML = '<div class="ns-alerts-empty">No active alerts — set one above</div>';
            return;
        }

        listEl.innerHTML =
            '<div class="ns-active-alerts-title">Active Alerts (' + alerts.length + ')</div>' +
            alerts.map(function (a) {
                const icon  = (a.alert_type || '').startsWith('pct') ? '📊' :
                              a.alert_type === 'volume' ? '📈' :
                              a.alert_type === 'above'  ? '⬆️' : '⬇️';
                const label = _alertTypeLabel(a.alert_type || a.condition || 'above', a.target_price || 0);
                const nHtml = a.note      ? '<span class="aal-note">\u201C' + a.note + '\u201D</span>'  : '';
                const rHtml = a.recurring ? '<span class="aal-badge recurring">\u21BB rec</span>'        : '';
                const lHtml = String(a.alert_id || '').startsWith('local_')
                              ? '<span class="aal-badge local">local</span>' : '';
                const aid   = a.alert_id || a.id || '';
                return '<div class="ns-active-alert-item">' +
                    '<span class="aal-icon">' + icon + '</span>' +
                    '<div class="aal-body">' +
                    '  <span class="aal-info"><strong>' + a.stock_symbol + '</strong> ' + label + '</span>' +
                    nHtml +
                    '</div>' +
                    '<div class="aal-badges">' + rHtml + lHtml + '</div>' +
                    '<button class="aal-del" onclick="nsDeleteAlert(\'' + aid + '\')" title="Remove">\u2715</button>' +
                    '</div>';
            }).join('');
    }

    /* ─────────────────────────────────────────────────────────
       PRICE ALERT CHECKER  (runs every 60 s)
    ───────────────────────────────────────────────────────── */
    let _alertInterval = null;

    async function checkPriceAlerts() {
        const userId = localStorage.getItem('user_id') || 'guest';
        var alerts   = [];

        try {
            if (userId !== 'guest') {
                const resp = await fetch('/api/user/' + userId + '/alerts');
                if (resp.ok) {
                    const data = await resp.json();
                    alerts     = data.alerts || [];
                }
            }
        } catch (e) {}

        alerts = alerts.concat(_getLocalAlerts());
        if (alerts.length === 0) return;

        const symbols = [];
        alerts.forEach(function (a) {
            const sym = a.stock_symbol || a.symbol;
            if (sym && symbols.indexOf(sym) === -1) symbols.push(sym);
        });

        var prices = {};
        try {
            const pResp = await fetch('/api/stock/batch', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ symbols: symbols })
            });
            if (pResp.ok) prices = await pResp.json();
        } catch (e) { return; }

        alerts.forEach(function (a) {
            const alertId = a.alert_id || a.id || (String(a.stock_symbol) + '_' + a.alert_type);
            if (isSnoozed(alertId)) return;

            const sym     = a.stock_symbol || a.symbol;
            const sd      = prices[sym];
            if (!sd || sd.error) return;
            const current = parseFloat(sd.price || sd.current_price);
            if (!current) return;

            const target  = parseFloat(a.target_price);
            const atype   = a.alert_type || a.condition || 'above';
            var triggered = false;
            var msgExtra  = '';

            if (atype === 'above' && current >= target) {
                triggered = true;
                msgExtra  = '$' + current.toFixed(2) + ' \u2265 $' + target.toFixed(2);
            } else if (atype === 'below' && current <= target) {
                triggered = true;
                msgExtra  = '$' + current.toFixed(2) + ' \u2264 $' + target.toFixed(2);
            } else if (atype === 'pct_up' && a._ref_price) {
                const chg = (current - a._ref_price) / a._ref_price * 100;
                if (chg >= target) { triggered = true; msgExtra = '+' + chg.toFixed(2) + '% rise'; }
            } else if (atype === 'pct_down' && a._ref_price) {
                const chg = (a._ref_price - current) / a._ref_price * 100;
                if (chg >= target) { triggered = true; msgExtra = '-' + chg.toFixed(2) + '% drop'; }
            } else if (atype === 'pct_either' && a._ref_price) {
                const chg = Math.abs((current - a._ref_price) / a._ref_price * 100);
                if (chg >= target) { triggered = true; msgExtra = chg.toFixed(2) + '% move'; }
            }

            if (triggered) {
                const dir     = (atype === 'above' || atype === 'pct_up') ? 'price-up' : 'price-down';
                const noteStr = a.note ? ' \u00B7 \u201C' + a.note + '\u201D' : '';
                nsToast(
                    '\uD83D\uDEA8 ' + sym + ' Alert!',
                    msgExtra + noteStr,
                    dir, 10000,
                    { snooze: true, alertId: alertId, category: 'alert' }
                );
                if (!a.recurring) nsDeleteAlert(alertId);
            }
        });
    }

    function startAlertChecker() {
        if (_alertInterval) return;
        checkPriceAlerts();
        _alertInterval = setInterval(checkPriceAlerts, ALERT_CHECK_FREQ);
    }

    /* ─────────────────────────────────────────────────────────
       INJECT STYLES FOR ENHANCED ALERT MODAL
    ───────────────────────────────────────────────────────── */
    function _injectAlertStyles() {
        const s  = document.createElement('style');
        s.id     = 'ns-alert-styles';
        s.textContent =
        '.ns-alert-modal-v2{background:linear-gradient(180deg,#1a2332,#0f1419);border:1px solid rgba(29,161,242,0.3);border-radius:20px;width:90%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 64px rgba(0,0,0,.7);animation:nsModalIn .3s cubic-bezier(.34,1.56,.64,1)}' +
        '@keyframes nsModalIn{from{transform:scale(.92) translateY(20px);opacity:0}to{transform:scale(1) translateY(0);opacity:1}}' +
        '.ns-alert-header{display:flex;align-items:center;justify-content:space-between;padding:20px 20px 16px;border-bottom:1px solid rgba(255,255,255,.06)}' +
        '.ns-alert-close{width:32px;height:32px;background:rgba(224,36,94,.15);border:1px solid rgba(224,36,94,.3);border-radius:8px;color:#e0245e;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;transition:all .2s}' +
        '.ns-alert-close:hover{background:rgba(224,36,94,.3)}' +
        '.ns-alert-tabs{display:flex;gap:4px;padding:12px 20px;background:rgba(0,0,0,.2)}' +
        '.ns-tab{flex:1;padding:8px 4px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:8px;color:#8899a6;cursor:pointer;font-size:.78rem;font-weight:600;transition:all .2s}' +
        '.ns-tab:hover{background:rgba(29,161,242,.1);color:#1da1f2}' +
        '.ns-tab.active{background:linear-gradient(135deg,rgba(29,161,242,.25),rgba(29,161,242,.1));border-color:rgba(29,161,242,.4);color:#1da1f2}' +
        '.ns-alert-form{padding:16px 20px 0}' +
        '.ns-tab-content{display:none}.ns-tab-content.active{display:block}' +
        '.ns-alert-form-group{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}' +
        '.ns-alert-form-group label{font-size:.78rem;color:#8899a6;font-weight:500}' +
        '.ns-alert-form-row{display:flex;gap:10px}.ns-alert-form-row .ns-alert-form-group{flex:1}' +
        '.ns-select,.ns-input{padding:10px 12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:10px;color:#e1e8ed;font-size:.9rem;width:100%;box-sizing:border-box;transition:border-color .2s}' +
        '.ns-select:focus,.ns-input:focus{outline:none;border-color:rgba(29,161,242,.5);background:rgba(255,255,255,.07)}' +
        '.ns-info-box{background:rgba(29,161,242,.08);border:1px solid rgba(29,161,242,.2);border-radius:8px;padding:8px 12px;font-size:.78rem;color:#8899a6;margin-bottom:12px}' +
        '.ns-alert-options-row{display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap}' +
        '.ns-toggle-label{display:flex;align-items:center;gap:7px;font-size:.8rem;color:#8899a6;cursor:pointer;white-space:nowrap}' +
        '.ns-toggle-label input{display:none}' +
        '.ns-mini-toggle{width:34px;height:18px;background:rgba(255,255,255,.1);border-radius:12px;position:relative;transition:background .2s}' +
        '.ns-mini-toggle::after{content:"";position:absolute;top:2px;left:2px;width:14px;height:14px;background:#8899a6;border-radius:50%;transition:all .2s}' +
        '.ns-toggle-label input:checked + .ns-mini-toggle{background:linear-gradient(135deg,#1da1f2,#0d8bd9)}' +
        '.ns-toggle-label input:checked + .ns-mini-toggle::after{transform:translateX(16px);background:#fff}' +
        '.ns-active-alerts{margin:8px 20px;max-height:160px;overflow-y:auto;scrollbar-width:thin}' +
        '.ns-alerts-empty{text-align:center;padding:12px;color:#657786;font-size:.8rem}' +
        '.ns-active-alerts-title{font-size:.72rem;color:#8899a6;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}' +
        '.ns-active-alert-item{display:flex;align-items:center;gap:8px;padding:8px 10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;margin-bottom:6px}' +
        '.aal-icon{font-size:15px;flex-shrink:0}.aal-body{flex:1;min-width:0}' +
        '.aal-info{font-size:.83rem;color:#e1e8ed;display:block}.aal-note{font-size:.74rem;color:#8899a6;font-style:italic;display:block;margin-top:2px}' +
        '.aal-badges{display:flex;gap:4px}.aal-badge{font-size:.62rem;padding:2px 5px;border-radius:4px;font-weight:700}' +
        '.aal-badge.recurring{background:rgba(23,191,99,.2);color:#17bf63}.aal-badge.local{background:rgba(255,173,31,.2);color:#ffad1f}' +
        '.aal-del{background:rgba(224,36,94,.12);border:none;color:#e0245e;width:22px;height:22px;border-radius:5px;cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;transition:all .2s;flex-shrink:0}' +
        '.aal-del:hover{background:rgba(224,36,94,.3)}' +
        '.ns-alert-actions{display:flex;gap:10px;padding:16px 20px 20px;border-top:1px solid rgba(255,255,255,.06)}' +
        '.ns-alert-btn{flex:1;padding:12px;border-radius:10px;border:none;font-size:.9rem;font-weight:700;cursor:pointer;transition:all .2s}' +
        '.ns-alert-btn.secondary{background:rgba(255,255,255,.06);color:#8899a6;border:1px solid rgba(255,255,255,.1)}' +
        '.ns-alert-btn.secondary:hover{background:rgba(255,255,255,.1);color:#e1e8ed}' +
        '.ns-alert-btn.primary{background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;box-shadow:0 4px 12px rgba(139,92,246,.4)}' +
        '.ns-alert-btn.primary:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(139,92,246,.5)}' +
        /* notification items */
        '.ns-notif-item{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.04);cursor:pointer;transition:background .2s}' +
        '.ns-notif-item:hover{background:rgba(29,161,242,.06)}.ns-notif-item.unread{background:rgba(29,161,242,.05)}' +
        '.ns-notif-item.unread .ni-title{color:#fff}' +
        '.ni-icon{font-size:18px;flex-shrink:0;margin-top:1px}.ni-body{flex:1;min-width:0}' +
        '.ni-title{font-size:.85rem;font-weight:600;color:#c8d1d9;margin-bottom:2px}.ni-desc{font-size:.78rem;color:#8899a6;line-height:1.4}.ni-time{font-size:.72rem;color:#657786;margin-top:4px}' +
        '.ni-del{background:none;border:none;color:#8899a6;cursor:pointer;font-size:12px;padding:2px 4px;opacity:0;transition:opacity .2s;flex-shrink:0}' +
        '.ns-notif-item:hover .ni-del{opacity:1}.ni-del:hover{color:#e0245e}' +
        '.ns-notif-empty{text-align:center;padding:32px 16px;color:#8899a6}' +
        /* snooze button on toast */
        '.ns-toast-snooze{display:inline-block;margin-top:6px;padding:4px 10px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);border-radius:6px;color:#e1e8ed;font-size:.74rem;cursor:pointer;transition:all .2s}' +
        '.ns-toast-snooze:hover{background:rgba(255,255,255,.2)}';
        document.head.appendChild(s);
    }

    /* ─────────────────────────────────────────────────────────
       INIT
    ───────────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        ensureToastContainer();
        _injectAlertStyles();
        updateBellBadge();
        renderNotifList();
        startAlertChecker();
    });

})();
