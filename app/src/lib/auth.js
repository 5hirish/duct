"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  SESSION_EXPIRED_EVENT,
  authToken,
  clearAuthToken,
  decodeJwtPayload,
  isTokenValid,
} from "./authFetch";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = authToken();
    if (isTokenValid(stored)) {
      const payload = decodeJwtPayload(stored);
      setToken(stored);
      setUser({
        email: payload.sub,
        name: payload.name,
        picture: payload.picture,
      });
    }
    setLoading(false);
  }, []);

  const signOut = useCallback(() => {
    clearAuthToken();
    setUser(null);
    setToken(null);
    router.replace("/");
  }, [router]);

  // A token can pass `isTokenValid` and still be refused by the backend — it is
  // never verified here, only read. authFetch retires such a session and fires
  // this; without listening, the app keeps rendering as though signed in.
  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, signOut);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, signOut);
  }, [signOut]);

  return (
    <AuthContext.Provider value={{ user, token, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

function AuthLoadingMessage({ message }) {
  return (
    <div
      className="flex min-h-dvh items-center justify-center bg-background px-4"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

export function AuthGuard({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/");
    }
  }, [loading, user, router]);

  if (loading) {
    return <AuthLoadingMessage message="Loading…" />;
  }
  if (!user) {
    return <AuthLoadingMessage message="Redirecting to sign in…" />;
  }
  return <>{children}</>;
}
