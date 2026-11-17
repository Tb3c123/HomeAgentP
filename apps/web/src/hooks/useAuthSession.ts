import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { AuthUser } from "../api/types";

interface UseAuthSessionOptions {
  setErrorMsg: (msg: string) => void;
  onLoggedOut?: () => void;
}

export function useAuthSession({ setErrorMsg, onLoggedOut }: UseAuthSessionOptions) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);
  const [usernameInput, setUsernameInput] = useState<string>("admin");
  const [passwordInput, setPasswordInput] = useState<string>("");
  const [loginBusy, setLoginBusy] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    apiClient
      .getMe()
      .then((me) => {
        if (!mounted) return;
        setUser(me);
        setAuthChecking(false);
      })
      .catch(() => {
        if (!mounted) return;
        setUser(null);
        setAuthChecking(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginBusy(true);
    setErrorMsg("");
    try {
      const authenticated = await apiClient.login(usernameInput, passwordInput);
      setUser(authenticated);
      setPasswordInput("");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoginBusy(false);
    }
  };

  const handleLogout = async () => {
    if (!user) return;
    try {
      await apiClient.logout(user.csrf_token);
    } finally {
      setUser(null);
      onLoggedOut?.();
    }
  };

  return {
    user,
    setUser,
    authChecking,
    usernameInput,
    setUsernameInput,
    passwordInput,
    setPasswordInput,
    loginBusy,
    handleLogin,
    handleLogout,
  };
}
