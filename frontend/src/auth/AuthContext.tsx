import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../api";
import type { CurrentUser, LoginRequest, Membership } from "../types";

interface AuthContextValue {
  currentUser: CurrentUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  selectedProject: Membership | null;
  setSelectedProjectId: (projectId: string) => void;
  login: (body: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  // Re-seed the session after a public auth call that returns a CurrentUser
  // (signup / accept-invitation) so the guard sees the new session immediately.
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectIdRaw] = useState<string | null>(() =>
    localStorage.getItem("selectedProjectId"),
  );

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.me,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1,
  });

  useEffect(() => {
    const onUnauthorized = () => {
      queryClient.setQueryData(["auth", "me"], null);
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, [queryClient]);

  const currentUser = meQuery.data ?? null;
  const selectedProject = useMemo(() => {
    if (!currentUser?.memberships.length) return null;
    return (
      currentUser.memberships.find((m) => m.project_id === selectedProjectId) ??
      currentUser.memberships[0]
    );
  }, [currentUser, selectedProjectId]);

  useEffect(() => {
    if (selectedProject?.project_id) {
      localStorage.setItem("selectedProjectId", selectedProject.project_id);
    } else {
      localStorage.removeItem("selectedProjectId");
    }
  }, [selectedProject?.project_id]);

  const loginMutation = useMutation({
    mutationFn: api.login,
    onSuccess: (data) => {
      queryClient.setQueryData(["auth", "me"], data);
    },
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      queryClient.clear();
      localStorage.removeItem("selectedProjectId");
    },
  });

  const login = useCallback(
    async (body: LoginRequest) => {
      await loginMutation.mutateAsync(body);
    },
    [loginMutation],
  );

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync();
  }, [logoutMutation]);

  const setSelectedProjectId = useCallback((projectId: string) => {
    setSelectedProjectIdRaw(projectId);
  }, []);

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      currentUser,
      isLoading: meQuery.isLoading,
      isAuthenticated: Boolean(currentUser),
      isAdmin: Boolean(currentUser?.user.is_tenant_admin),
      selectedProject,
      setSelectedProjectId,
      login,
      logout,
      refresh,
    }),
    [
      currentUser,
      login,
      logout,
      refresh,
      meQuery.isLoading,
      selectedProject,
      setSelectedProjectId,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
