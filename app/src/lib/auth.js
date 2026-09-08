"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { authToken, clearAuthToken, decodeJwtPayload, isTokenValid } from "./authFetch";
import { analytics } from "./analytics";

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
      // The account UUID, not `sub` — that is the email, and it must not reach
      // an analytics provider. Safe before consent resolves: nothing drains the
      // dataLayer until a provider actually loads, and if the answer is no it
      // never does.
      analytics.identify(payload.uid);
    }
    setLoading(false);
  }, []);

  const signOut = useCallback(() => {
    // Before the state clears: whoever signs in next on this machine should not
    // inherit the last person's id.
    analytics.reset();
    clearAuthToken();
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
