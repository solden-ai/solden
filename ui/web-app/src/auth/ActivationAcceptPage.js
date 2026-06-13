import { useEffect, useState } from 'preact/hooks';
import { useLocation } from 'wouter-preact';
import { html } from '../utils/htm.js';
import { api, ApiError } from '../api/client.js';
import { logout, refreshSession, useSession } from './useSession.js';
import { GoogleMark, MicrosoftMark } from './OAuthIcons.js';
import { AuthShell } from './AuthLayout.js';

function ActivationAuthFrame({ children }) {
  return html`
    <${AuthShell}>
      <div class="cl-auth-card cl-auth-login-card">
        ${children}
      </div>
    <//>
  `;
}

function activationStatusMessage(status) {
  if (status === 'accepted') {
    return 'This workspace has already been activated. Sign in normally to continue.';
  }
  if (status === 'expired') {
    return 'This activation link has expired. Ask Solden to send a fresh setup link.';
  }
  if (status === 'owner_exists') {
    return 'This workspace already has an owner. Ask that owner to invite you from Settings.';
  }
  if (status && status !== 'pending') {
    return 'This activation link is no longer active. Ask Solden to send a fresh setup link.';
  }
  return '';
}

function activationErrorMessage(err) {
  const code = err instanceof ApiError ? err.status : 0;
  const detail = err?.payload?.detail;
  if (code === 404 || detail === 'activation_not_found') {
    return "We couldn't find this activation link. It may have been replaced.";
  }
  if (detail === 'activation_not_pending') {
    return 'This workspace has already been activated. Sign in normally.';
  }
  if (detail === 'activation_expired') {
    return 'This activation link has expired. Ask Solden to send a fresh setup link.';
  }
  if (detail === 'activation_owner_exists') {
    return 'This workspace already has an owner. Ask that owner to invite you.';
  }
  if (detail === 'activation_user_already_bound') {
    return 'This email already belongs to another workspace. Use the email Solden provisioned for this customer.';
  }
  if (detail === 'password_required_for_activation') {
    return 'Set a password to finish activating the workspace.';
  }
  return err?.message || 'Could not activate this workspace. Try again.';
}

function defaultDisplayName(email) {
  return (email || '')
    .split('@')[0]
    .replace(/[._-]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const ACTIVATION_NEXT_PATH = '/onboarding';

export function ActivationAcceptPage() {
  const { session, isAuthenticated, isLoading } = useSession();
  const [, navigate] = useLocation();

  const [token] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get('token') || '').trim();
  });

  const [preview, setPreview] = useState(undefined);
  const [previewError, setPreviewError] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    api(`/auth/activations/preview?token=${encodeURIComponent(token)}`, { retry: false })
      .then((res) => {
        if (cancelled) return;
        setPreview(res);
        setName(defaultDisplayName(res?.email || ''));
      })
      .catch((err) => {
        if (cancelled) return;
        setPreviewError(activationErrorMessage(err));
        setPreview(null);
      });
    return () => { cancelled = true; };
  }, [token]);

  if (!token) {
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">Activation link incomplete</h1>
        <p class="cl-auth-sub">
          The setup token is missing from this URL. Open the workspace
          activation link exactly as it was sent by Solden.
        </p>
      <//>
    `;
  }

  if (isLoading || preview === undefined) {
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">Checking activation link</h1>
        <p class="cl-auth-sub">Confirming this workspace setup link before we continue.</p>
      <//>
    `;
  }

  if (preview === null) {
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">Activation unavailable</h1>
        <p class="cl-auth-sub">${previewError}</p>
      <//>
    `;
  }

  const statusMessage = activationStatusMessage(preview.status);
  if (statusMessage) {
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">Activation unavailable</h1>
        <p class="cl-auth-sub">${statusMessage}</p>
      <//>
    `;
  }

  const activationEmail = (preview.email || '').toLowerCase().trim();
  const organizationName = preview.organization_name || 'your workspace';
  const sessionEmail = (session?.email || '').toLowerCase().trim();
  const sameUser = isAuthenticated && sessionEmail && sessionEmail === activationEmail;
  const wrongUser = isAuthenticated && sessionEmail && sessionEmail !== activationEmail;

  const acceptAsCurrentUser = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError('');
    try {
      await api('/auth/activations/accept', {
        method: 'POST',
        body: { token },
        retry: false,
      });
      await refreshSession();
      navigate(ACTIVATION_NEXT_PATH, { replace: true });
    } catch (err) {
      setError(activationErrorMessage(err));
      setSubmitting(false);
    }
  };

  if (sameUser) {
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">Activate your workspace</h1>
        <p class="cl-auth-sub">
          You're signed in as <strong>${activationEmail}</strong>.
          Activate setup for <strong>${organizationName}</strong>.
        </p>
        ${error ? html`<div class="cl-auth-error">${error}</div>` : null}
        <button
          class="cl-auth-btn cl-auth-btn-primary"
          onClick=${acceptAsCurrentUser}
          disabled=${submitting}>
          ${submitting ? 'Activating...' : 'Activate workspace'}
        </button>
      <//>
    `;
  }

  if (wrongUser) {
    const signOutAndStay = async () => {
      try {
        await logout();
      } catch {
        /* best-effort */
      }
      try {
        window.location.reload();
      } catch {
        /* no-op */
      }
    };
    return html`
      <${ActivationAuthFrame}>
        <h1 class="cl-auth-title">This link is for another email</h1>
        <p class="cl-auth-sub">
          The owner account is for <strong>${activationEmail}</strong>, but
          you're signed in as <strong>${sessionEmail}</strong>. Sign out,
          then open this activation link again.
        </p>
        <button
          class="cl-auth-btn cl-auth-btn-primary"
          onClick=${signOutAndStay}>
          Sign out
        </button>
      <//>
    `;
  }

  const submit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setError('');

    if (password.length < 12) {
      setError('Password must be at least 12 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await api('/auth/activations/accept', {
        method: 'POST',
        body: { token, password, name: name.trim() || undefined },
        retry: false,
      });
      await refreshSession();
      navigate(ACTIVATION_NEXT_PATH, { replace: true });
    } catch (err) {
      setError(activationErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const redirectPath = `${ACTIVATION_NEXT_PATH}?post_oauth=1`;
  const googleStart = `/auth/google/start?${new URLSearchParams({
    invite_token: token,
    redirect_path: redirectPath,
  }).toString()}`;
  const microsoftStart = `/auth/microsoft/start?${new URLSearchParams({
    invite_token: token,
    redirect_path: redirectPath,
  }).toString()}`;

  return html`
    <${ActivationAuthFrame}>
      <h1 class="cl-auth-title">Activate your workspace</h1>
      <p class="cl-auth-sub">
        Create your Solden access for <strong>${organizationName}</strong>.
        Use <strong>${activationEmail}</strong> to continue.
      </p>

      ${error ? html`<div class="cl-auth-error">${error}</div>` : null}

      <a
        class="cl-auth-btn cl-auth-btn-secondary"
        href=${googleStart}>
        <${GoogleMark} />
        <span>Continue with Google</span>
      </a>
      <a
        class="cl-auth-btn cl-auth-btn-secondary"
        href=${microsoftStart}>
        <${MicrosoftMark} />
        <span>Continue with Microsoft</span>
      </a>

      <div class="cl-auth-divider"><span>or</span></div>

      <form class="cl-auth-form" onSubmit=${submit} autoComplete="on">
        <label class="cl-auth-field">
          <span>Display name <em>(optional)</em></span>
          <input
            type="text"
            autoComplete="name"
            value=${name}
            onInput=${(e) => setName(e.currentTarget.value)}
            placeholder="Mo Mbalam"
          />
        </label>
        <label class="cl-auth-field">
          <span>Set a password</span>
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength=${12}
            value=${password}
            onInput=${(e) => setPassword(e.currentTarget.value)}
          />
        </label>
        <label class="cl-auth-field">
          <span>Confirm password</span>
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength=${12}
            value=${confirmPassword}
            onInput=${(e) => setConfirmPassword(e.currentTarget.value)}
          />
        </label>
        <button
          type="submit"
          class="cl-auth-btn cl-auth-btn-primary"
          disabled=${submitting || !password || !confirmPassword}>
          ${submitting ? 'Activating...' : 'Activate workspace'}
        </button>
      </form>

      <p class="cl-auth-fineprint">
        Use 12+ characters. Solden stores only a password hash.
      </p>
    <//>
  `;
}
