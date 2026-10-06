"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, LogIn, LogOut, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import Button from "@/components/ui/Button";
import {
  AntigravityOAuthApiError,
  completeAntigravityLogin,
  disconnectAntigravity,
  getAntigravityStatus,
  startAntigravityLogin,
  type AntigravityLoginStart,
  type AntigravityOAuthStatus,
} from "@/lib/antigravity-oauth";
import { inputClass } from "./shared";

export function AntigravityOAuthCard() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<AntigravityOAuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loginStart, setLoginStart] = useState<AntigravityLoginStart | null>(null);
  const [callbackUrl, setCallbackUrl] = useState("");

  // Optional manual credentials if server requires them
  const [showCredentials, setShowCredentials] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await getAntigravityStatus();
      setStatus(next);
      if (next.connected) {
        setLoginStart(null);
        setCallbackUrl("");
      }
    } catch (err) {
      if (err instanceof AntigravityOAuthApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(String(err));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll status while waiting for login
  useEffect(() => {
    if (!loginStart || status?.connected) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loginStart, status?.connected, refresh]);

  const handleStartLogin = async () => {
    setWorking(true);
    setErrorMessage(null);
    let popup: Window | null = null;
    try {
      popup = window.open("about:blank", "_blank");
    } catch {
      popup = null;
    }

    try {
      const credentials =
        clientId && clientSecret
          ? { client_id: clientId.trim(), client_secret: clientSecret.trim() }
          : undefined;
      const res = await startAntigravityLogin(credentials);
      setLoginStart(res);
      if (popup && !popup.closed) {
        popup.location.href = res.authorize_url;
      } else {
        window.open(res.authorize_url, "_blank");
      }
    } catch (err) {
      popup?.close();
      if (err instanceof AntigravityOAuthApiError) {
        setErrorMessage(err.message);
        if (err.code === "missing_credentials") {
          setShowCredentials(true);
        }
      } else {
        setErrorMessage(String(err));
      }
    } finally {
      setWorking(false);
    }
  };

  const handleCompleteCallback = async () => {
    if (!callbackUrl.trim()) return;
    setWorking(true);
    setErrorMessage(null);
    try {
      await completeAntigravityLogin(callbackUrl.trim());
      setCallbackUrl("");
      setLoginStart(null);
      await refresh();
    } catch (err) {
      if (err instanceof AntigravityOAuthApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(String(err));
      }
    } finally {
      setWorking(false);
    }
  };

  const handleDisconnect = async () => {
    setWorking(true);
    setErrorMessage(null);
    try {
      await disconnectAntigravity();
      setLoginStart(null);
      await refresh();
    } catch (err) {
      if (err instanceof AntigravityOAuthApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(String(err));
      }
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/20 p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-[var(--foreground)]">
            {t("Google Antigravity OAuth")}
          </h4>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            {t("Authenticate directly with your Google account via OAuth 2.0 PKCE.")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading || working}
          className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] disabled:opacity-40"
          title={t("Refresh status")}
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {status?.connected ? (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3.5 space-y-2">
          <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 size={16} />
            <span className="text-xs font-medium">{t("Connected")}</span>
          </div>
          {status.email && (
            <p className="text-xs text-[var(--foreground)]">
              <span className="text-[var(--muted-foreground)]">{t("Account")}: </span>
              {status.email}
            </p>
          )}
          {status.project_id && (
            <p className="text-xs text-[var(--foreground)]">
              <span className="text-[var(--muted-foreground)]">{t("Project")}: </span>
              {status.project_id}
            </p>
          )}
          <div className="pt-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleDisconnect}
              disabled={working}
              className="text-xs text-red-600 dark:text-red-400 hover:bg-red-500/10"
            >
              <LogOut size={13} className="mr-1.5" />
              {t("Disconnect")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleStartLogin}
              disabled={working}
              className="text-xs"
            >
              {working ? (
                <Loader2 size={13} className="mr-1.5 animate-spin" />
              ) : (
                <LogIn size={13} className="mr-1.5" />
              )}
              {t("Sign in with Google")}
            </Button>
            {!showCredentials && (
              <button
                type="button"
                onClick={() => setShowCredentials(true)}
                className="text-xs text-[var(--muted-foreground)] hover:underline"
              >
                {t("Configure OAuth Client ID")}
              </button>
            )}
          </div>

          {showCredentials && (
            <div className="rounded-lg border border-[var(--border)] p-3 space-y-3 bg-[var(--background)]">
              <div className="text-xs font-medium text-[var(--foreground)]">
                {t("Custom Google OAuth Client (Optional)")}
              </div>
              <div className="space-y-2">
                <label className="block text-xs text-[var(--muted-foreground)]">
                  {t("Client ID")}
                  <input
                    type="text"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="123456789-xyz.apps.googleusercontent.com"
                    className={`mt-1 block w-full ${inputClass}`}
                  />
                </label>
                <label className="block text-xs text-[var(--muted-foreground)]">
                  {t("Client Secret")}
                  <input
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder="GOCSPX-..."
                    className={`mt-1 block w-full ${inputClass}`}
                  />
                </label>
              </div>
            </div>
          )}

          {loginStart && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3.5 space-y-3">
              <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400 text-xs font-medium">
                <Loader2 size={14} className="animate-spin" />
                <span>{t("Waiting for authorization in browser...")}</span>
              </div>
              <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">
                {(loginStart.loopback ??
                  /localhost|127\.0\.0\.1/i.test(loginStart.redirect_uri))
                  ? t(
                      "Firefox cannot connect to localhost:51121. That is expected on a remote host or HTTPS reverse proxy. Copy the full address bar URL (it starts with http://localhost:51121/oauth-callback?code=) and paste it below. Do not close that tab first.",
                    )
                  : t(
                      "After Google redirects, this page will finish sign-in automatically. If it does not, paste the callback URL below.",
                    )}
              </p>
              <div className="flex items-center gap-2">
                <a
                  href={loginStart.authorize_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-[var(--primary)] hover:underline"
                >
                  <ExternalLink size={12} />
                  {t("Open authorization page")}
                </a>
              </div>
              <div className="space-y-1.5">
                <input
                  type="text"
                  value={callbackUrl}
                  onChange={(e) => setCallbackUrl(e.target.value)}
                  placeholder="http://localhost:51121/oauth-callback?code=..."
                  className={`w-full ${inputClass} text-xs`}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCompleteCallback}
                  disabled={!callbackUrl.trim() || working}
                  className="text-xs"
                >
                  {t("Complete sign-in")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {errorMessage && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-400">
          {errorMessage}
        </div>
      )}
    </div>
  );
}
