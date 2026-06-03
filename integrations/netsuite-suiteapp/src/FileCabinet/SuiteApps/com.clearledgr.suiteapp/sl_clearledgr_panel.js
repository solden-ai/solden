/**
 * Solden — Suitelet that serves the panel HTML.
 *
 * Stitches panel.html / panel.js / panel.css from the File Cabinet into
 * a single document, embeds the bill id + account id + minted JWT as
 * <meta> tags, and returns the result as text/html. The User Event
 * Script's iframe `src` resolves to this Suitelet.
 *
 * Production auth: HMAC-signs a short-lived JWT using the shared secret
 * stored in `customrecord_cl_settings`; embeds it in <meta name="cl-token">.
 *
 * @NApiVersion 2.1
 * @NScriptType Suitelet
 */
define(['N/file', 'N/runtime', 'N/log', 'N/search', 'N/crypto', 'N/encode'],
(fileMod, runtime, log, searchMod, cryptoMod, encodeMod) => {

    const PANEL_FOLDER = 'SuiteApps/com.clearledgr.suiteapp/ui';
    const FILE_HTML = PANEL_FOLDER + '/panel.html';
    const FILE_JS = PANEL_FOLDER + '/panel.js';
    const FILE_CSS = PANEL_FOLDER + '/panel.css';

    const DEFAULT_API_BASE = 'https://api.soldenai.com';
    const DEFAULT_APP_BASE = 'https://workspace.soldenai.com';
    const SETTINGS_RECORD_TYPE = 'customrecord_cl_settings';
    const JWT_TTL_SECONDS = 15 * 60;

    function loadFileContents(path) {
        try {
            return fileMod.load({ id: path }).getContents();
        } catch (err) {
            log.error({
                title: 'Solden panel asset missing',
                details: 'File not found at ' + path + ' — did the SDF deploy include the FileCabinet folder?',
            });
            return '';
        }
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function loadSettings() {
        try {
            const result = searchMod.create({
                type: SETTINGS_RECORD_TYPE,
                filters: [['isinactive', 'is', 'F']],
                columns: [
                    'custrecord_cl_api_base',
                    'custrecord_cl_app_base',
                    'custrecord_cl_bundle_secret',
                    'custrecord_cl_org_id',
                ],
            }).run().getRange({ start: 0, end: 1 });
            if (!result || !result.length) return null;
            const row = result[0];
            return {
                apiBase: String(row.getValue({ name: 'custrecord_cl_api_base' }) || DEFAULT_API_BASE).trim(),
                appBase: String(row.getValue({ name: 'custrecord_cl_app_base' }) || DEFAULT_APP_BASE).trim(),
                bundleSecret: String(row.getValue({ name: 'custrecord_cl_bundle_secret' }) || '').trim(),
                orgId: String(row.getValue({ name: 'custrecord_cl_org_id' }) || '').trim(),
            };
        } catch (err) {
            log.error({ title: 'Solden panel settings load failed', details: String(err) });
            return null;
        }
    }

    function toBase64Url(value) {
        const base64 = encodeMod.convert({
            string: value,
            inputEncoding: encodeMod.Encoding.UTF_8,
            outputEncoding: encodeMod.Encoding.BASE_64,
        });
        return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
    }

    function base64ToBase64Url(value) {
        return String(value || '').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
    }

    function createSecretKey(secretRef) {
        const attempts = [
            { secret: secretRef, encoding: encodeMod.Encoding.UTF_8 },
            { guid: secretRef, encoding: encodeMod.Encoding.UTF_8 },
        ];
        for (let i = 0; i < attempts.length; i += 1) {
            try {
                return cryptoMod.createSecretKey(attempts[i]);
            } catch (_) {
                // Try the next accepted NetSuite secret reference shape.
            }
        }
        throw new Error('Could not load Solden bundle secret as NetSuite SecretKey');
    }

    function mintPanelJwt(settings, billId, accountId) {
        if (!settings || !settings.bundleSecret || !billId || !accountId) {
            return '';
        }
        const now = Math.floor(Date.now() / 1000);
        const currentUser = runtime.getCurrentUser ? runtime.getCurrentUser() : {};
        const header = {
            alg: 'HS256',
            typ: 'JWT',
        };
        const payload = {
            iss: 'solden-netsuite-suiteapp',
            aud: 'solden-netsuite-panel',
            accountId: String(accountId),
            billId: String(billId),
            userEmail: String((currentUser && currentUser.email) || ''),
            orgId: String(settings.orgId || ''),
            iat: now,
            exp: now + JWT_TTL_SECONDS,
        };
        const signingInput = toBase64Url(JSON.stringify(header)) + '.' + toBase64Url(JSON.stringify(payload));
        const hmac = cryptoMod.createHmac({
            algorithm: cryptoMod.HashAlg.SHA256,
            key: createSecretKey(settings.bundleSecret),
        });
        hmac.update({
            input: signingInput,
            inputEncoding: encodeMod.Encoding.UTF_8,
        });
        const signature = base64ToBase64Url(hmac.digest({
            outputEncoding: encodeMod.Encoding.BASE_64,
        }));
        return signingInput + '.' + signature;
    }

    function onRequest(context) {
        const billId = context.request.parameters.billId || '';
        const accountId = context.request.parameters.accountId || runtime.accountId || '';
        const settings = loadSettings();
        const apiBase = settings && settings.apiBase ? settings.apiBase : DEFAULT_API_BASE;
        const appBase = settings && settings.appBase ? settings.appBase : DEFAULT_APP_BASE;
        let token = '';
        let setupState = 'configured';
        try {
            token = mintPanelJwt(settings, billId, accountId);
        } catch (err) {
            setupState = 'auth_error';
            log.error({ title: 'Solden panel JWT mint failed', details: String(err) });
        }
        if (!settings || !settings.bundleSecret || !settings.orgId) {
            setupState = 'missing_settings';
        }

        const html = loadFileContents(FILE_HTML);
        const js = loadFileContents(FILE_JS);
        const css = loadFileContents(FILE_CSS);

        // Embed runtime config as meta tags. panel.js reads these on boot.
        const meta =
            '<meta name="cl-bill-id" content="' + escapeHtml(billId) + '">\n' +
            '<meta name="cl-account-id" content="' + escapeHtml(accountId) + '">\n' +
            '<meta name="cl-api-base" content="' + escapeHtml(apiBase) + '">\n' +
            '<meta name="cl-app-base" content="' + escapeHtml(appBase) + '">\n' +
            '<meta name="cl-setup-state" content="' + escapeHtml(setupState) + '">\n' +
            '<meta name="cl-token" content="' + escapeHtml(token) + '">\n';

        // Minimal stitching: replace placeholders inside panel.html.
        const composed = html
            .replace('<!--CL_META-->', meta)
            .replace('<!--CL_CSS-->', '<style>' + css + '</style>')
            .replace('<!--CL_JS-->', '<script>' + js + '</script>');

        context.response.setHeader({ name: 'Content-Type', value: 'text/html; charset=utf-8' });
        // Prevent NetSuite from caching the panel HTML — script changes
        // should reflect on next load without a Suitelet redeploy.
        context.response.setHeader({ name: 'Cache-Control', value: 'no-store' });
        context.response.write({ output: composed });
    }

    return { onRequest: onRequest };
});
