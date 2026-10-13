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
  /** EVERY role the signed-in user holds on the selected project, not just one.
   *
   *  Memberships are stored one row per role, so a tech lead who is also product owner has two
   *  rows for the same project and `selectedProject` is whichever came back first. Screens that
   *  asked `selectedProject.role === requiredRole` therefore hid the decision on gates the
   *  SERVER would have accepted — `decide_gate` checks all of a user's rows
   *  (`role__in=[required, admin]`), so the rules were never the problem, only the screen.
   *  Ask `hasRole` instead of comparing a single role anywhere. */
  selectedProjectRoles: string[];
  /** True when the user holds `role` on the selected project — or is a workspace admin, who
   *  can decide anything. The one place that decision is made. */
  hasRole: (role: string | null | undefined) => boolean;
  /** The user's projects, ONE entry each. `currentUser.memberships` has a row per role, so
   *  rendering it directly lists a project once per role (and trips React's duplicate-key
   *  warning). Anything showing a list of projects wants this. */
  projects: Membership[];
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

  // All of them, not the first. See the note on `selectedProjectRoles` above.
  const selectedProjectRoles = useMemo(
    () =>
      selectedProject
        ? (currentUser?.memberships ?? [])
            .filter((m) => m.project_id === selectedProject.project_id)
            .map((m) => m.role)
        : [],
    [currentUser, selectedProject],
  );

  // One entry per project, keeping the first row's details. Deliberately NOT sorted or
  // re-ordered — the switcher's order should stay whatever the API sent.
  const projects = useMemo(
    () => [...new Map((currentUser?.memberships ?? []).map((m) => [m.project_id, m])).values()],
    [currentUser],
  );

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
      selectedProjectRoles,
      // A workspace admin decides anything, matching `decide_gate`'s own fallback — the two
      // must agree, or a screen offers a button the server refuses (or hides one it allows).
      hasRole: (role: string | null | undefined) =>
        Boolean(currentUser?.user.is_tenant_admin) ||
        (Boolean(role) && selectedProjectRoles.includes(role as string)),
      projects,
      setSelectedProjectId,
      login,
      logout,
      refresh,
    }),
    [
      currentUser,
      login,
      logout,
      projects,
      refresh,
      meQuery.isLoading,
      selectedProject,
      selectedProjectRoles,
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
