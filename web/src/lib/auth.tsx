"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, AUTH_CHANGED, authToken, Me, setAuthToken } from "./api";

type Status = "loading" | "guest" | "signed-in";

const AuthContext = createContext<{ me: Me | null; status: Status; refresh: () => Promise<void> }>({
  me: null,
  status: "loading",
  refresh: async () => undefined,
});

/** Who is using the app: an account (token in localStorage) or a guest on this device. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  const refresh = useCallback(async () => {
    if (!authToken()) {
      setMe(null);
      setStatus("guest");
      return;
    }
    try {
      setMe(await api.me());
      setStatus("signed-in");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setAuthToken(null); // expired or signed out elsewhere
      else setStatus((s) => (s === "loading" ? "guest" : s)); // server unreachable: keep the token, try again later
    }
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(AUTH_CHANGED, refresh);
    return () => window.removeEventListener(AUTH_CHANGED, refresh);
  }, [refresh]);

  return <AuthContext.Provider value={{ me, status, refresh }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function initials(name: string | undefined | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

export function firstName(name: string | undefined | null): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}
