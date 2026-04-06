"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const TOKEN_KEY = "duct_auth_token";
const AuthContext = createContext(null);

function decodeJwtPayload(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

function isTokenValid(token) {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload || !payload.exp) return false;
  return payload.exp * 1000 > Date.now();
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
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
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setToken(null);
    router.replace("/");
  }, [router]);

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
