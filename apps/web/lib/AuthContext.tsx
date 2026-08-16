"use client";

// React auth state for the dashboard (roadmap step 233). A Context
// Provider, not per-page fetching -- the SAME session (and its nav
// shell's own "who's logged in") needs to be visible to every route
// under app/dashboard, and localStorage-backed tokens (lib/auth.ts)
// are only ever readable client-side, so this can't be a Server
// Component the way a cookie-backed session could be.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  type AuthUser,
  clearSession,
  fetchCurrentUser,
  getAccessToken,
  logout as apiLogout,
} from "./auth";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  refreshUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Lazily seeded so the "no token at all" case resolves synchronously
  // on the very first render, rather than through a setState call
  // inside the effect below -- that path stays reserved for the
  // genuinely async verification a stored token still needs.
  const [status, setStatus] = useState<AuthStatus>(() =>
    getAccessToken() ? "loading" : "unauthenticated",
  );
  const [user, setUser] = useState<AuthUser | null>(null);

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setStatus("unauthenticated");
      return;
    }
    const currentUser = await fetchCurrentUser();
    if (currentUser) {
      setUser(currentUser);
      setStatus("authenticated");
    } else {
      clearSession();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      return;
    }
    let cancelled = false;
    fetchCurrentUser()
      .then((currentUser) => {
        if (cancelled) {
          return;
        }
        if (currentUser) {
          setUser(currentUser);
          setStatus("authenticated");
        } else {
          clearSession();
          setUser(null);
          setStatus("unauthenticated");
        }
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setStatus("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, refreshUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
