// Client-side session management for the authenticated dashboard
// (roadmap step 233). apps/api has no session/cookie mechanism of its
// own -- every authenticated route is a plain Bearer JWT (Milestone 2)
// -- so this mirrors the SAME "hold the token in the browser, send it
// as Authorization: Bearer" model the anonymous-conversation flow
// (lib/conversationStore.ts, apps/widget/src/voice.ts) already uses
// for this app's whole existence, rather than introducing a second,
// httpOnly-cookie-based session architecture that would need apps/web
// to proxy every API call through its own backend (a real, much larger
// change nothing in this step asks for).
//
// Refresh tokens rotate on every use (apps/api's own single-use design,
// routers/auth.py:refresh) -- refreshAccessToken() always stores the
// NEW refresh_token it gets back, never reuses the old one.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACCESS_TOKEN_KEY = "agentforge:access_token";
const REFRESH_TOKEN_KEY = "agentforge:refresh_token";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
  is_platform_admin: boolean;
}

export type LoginResult =
  | { ok: true }
  | { ok: false; reason: "invalid_credentials" | "unknown" }
  | { ok: false; reason: "mfa_required"; mfaTicket: string };

export type SignupResult =
  { ok: true } | { ok: false; reason: "email_taken" | "invalid" | "unknown" };

export type MfaVerifyResult = { ok: true } | { ok: false; reason: "invalid_code" | "unknown" };

function readToken(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(key);
}

function storeTokens(accessToken: string, refreshToken: string): void {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function getAccessToken(): string | null {
  return readToken(ACCESS_TOKEN_KEY);
}

export function clearSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (response.status === 401) {
    return { ok: false, reason: "invalid_credentials" };
  }
  if (!response.ok) {
    return { ok: false, reason: "unknown" };
  }

  const body = (await response.json()) as
    { access_token: string; refresh_token: string } | { mfa_required: true; mfa_ticket: string };

  if ("mfa_required" in body) {
    return { ok: false, reason: "mfa_required", mfaTicket: body.mfa_ticket };
  }

  storeTokens(body.access_token, body.refresh_token);
  return { ok: true };
}

export async function signup(
  email: string,
  password: string,
  fullName: string,
): Promise<SignupResult> {
  const response = await fetch(`${API_BASE_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName }),
  });

  if (response.status === 409) {
    return { ok: false, reason: "email_taken" };
  }
  if (response.status === 422) {
    return { ok: false, reason: "invalid" };
  }
  if (!response.ok) {
    return { ok: false, reason: "unknown" };
  }

  // POST /auth/signup returns 201 + the created user only, no tokens
  // (schemas/auth.py:SignupRequest / routers/auth.py's own signup
  // handler) -- log the new account in immediately so signup is one
  // real step for the user, not two.
  const loginResult = await login(email, password);
  return loginResult.ok ? { ok: true } : { ok: false, reason: "unknown" };
}

export async function verifyMfa(mfaTicket: string, code: string): Promise<MfaVerifyResult> {
  const response = await fetch(`${API_BASE_URL}/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mfa_ticket: mfaTicket, code }),
  });

  if (response.status === 401) {
    return { ok: false, reason: "invalid_code" };
  }
  if (!response.ok) {
    return { ok: false, reason: "unknown" };
  }

  const body = (await response.json()) as { access_token: string; refresh_token: string };
  storeTokens(body.access_token, body.refresh_token);
  return { ok: true };
}

export async function logout(): Promise<void> {
  const refreshToken = readToken(REFRESH_TOKEN_KEY);
  clearSession();
  if (!refreshToken) {
    return;
  }
  // Best-effort -- the local session is already cleared either way.
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).catch(() => {
    // Real, honest no-op -- nothing left to report this to.
  });
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = readToken(REFRESH_TOKEN_KEY);
  if (!refreshToken) {
    return null;
  }
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clearSession();
    return null;
  }
  const body = (await response.json()) as { access_token: string; refresh_token: string };
  storeTokens(body.access_token, body.refresh_token);
  return body.access_token;
}

// Wraps fetch with the current access token, retrying exactly once
// after a silent refresh on a 401 -- apps/api's own access tokens are
// short-lived (15 minutes), so a dashboard session that only ever used
// the token it logged in with would silently start failing well within
// one real sitting.
export async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const attempt = async (token: string | null): Promise<Response> =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });

  const response = await attempt(getAccessToken());
  if (response.status !== 401) {
    return response;
  }
  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    return response;
  }
  return attempt(refreshed);
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  if (!getAccessToken()) {
    return null;
  }
  const response = await authorizedFetch("/auth/me");
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as AuthUser;
}
