import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { getCurrentUser, login, logout } from "~/lib/api";
import type { AuthUser } from "~/lib/types";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCurrentUser()
      .then((response) => setUser(response.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener("chess-insighter:unauthorized", expire);
    return () => window.removeEventListener("chess-insighter:unauthorized", expire);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      signIn: async (email, password) => {
        const response = await login(email, password);
        setUser(response.user);
      },
      signOut: async () => {
        try {
          await logout();
        } finally {
          setUser(null);
        }
      },
    }),
    [loading, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return <div className="grid min-h-screen place-items-center text-sm text-[var(--ink-soft)]">Restoring your desk…</div>;
  }
  if (!user) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}
