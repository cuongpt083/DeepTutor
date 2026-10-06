import { apiFetch, apiUrl } from "@/lib/api";

export type AntigravityOAuthStatus = {
  connected: boolean;
  email: string;
  project_id: string;
  models: string[];
  expires_at?: number;
};

export type AntigravityLoginStart = {
  operation_id: string;
  authorize_url: string;
  redirect_uri: string;
};

export class AntigravityOAuthApiError extends Error {
  code: string;
  httpStatus: number;

  constructor(code: string, message: string, httpStatus = 400) {
    super(message);
    this.name = "AntigravityOAuthApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

const BASE = "/api/settings/providers/google-antigravity/oauth";

async function requestAntigravity<T>(
  path: string,
  method: "GET" | "POST",
  body?: unknown,
): Promise<T> {
  const response = await apiFetch(apiUrl(`${BASE}${path}`), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    skipAuthRedirect: true,
  });

  if (!response.ok) {
    let code = "request_failed";
    let message = `Antigravity request failed with status ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        message = data.detail;
        if (response.status === 403 && data.detail.includes("disabled")) {
          code = "provider_disabled";
        } else if (data.detail.includes("ANTIGRAVITY_CLIENT_ID")) {
          code = "missing_credentials";
        }
      } else if (data.detail?.code) {
        code = data.detail.code;
        message = data.detail.message || message;
      }
    } catch {
      // response wasn't JSON
    }
    throw new AntigravityOAuthApiError(code, message, response.status);
  }

  return (await response.json()) as T;
}

export function getAntigravityStatus(): Promise<AntigravityOAuthStatus> {
  return requestAntigravity<AntigravityOAuthStatus>("/status", "GET");
}

export function startAntigravityLogin(credentials?: {
  client_id?: string;
  client_secret?: string;
}): Promise<AntigravityLoginStart> {
  return requestAntigravity<AntigravityLoginStart>(
    "/start",
    "POST",
    credentials || {},
  );
}

export function completeAntigravityLogin(
  callbackUrl: string,
): Promise<{ status: string; email?: string; project_id?: string }> {
  return requestAntigravity<{ status: string; email?: string; project_id?: string }>(
    "/complete",
    "POST",
    { callback_url: callbackUrl },
  );
}

export function disconnectAntigravity(): Promise<{ status: string }> {
  return requestAntigravity<{ status: string }>("/disconnect", "POST");
}
