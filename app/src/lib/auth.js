"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AUTH_TOKEN_KEY, decodeJwtPayload, isTokenValid } from "./authFetch";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem(AUTH_TOKEN_KEY);
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
    localStorage.removeItem(AUTH_TOKEN_KEY);
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
