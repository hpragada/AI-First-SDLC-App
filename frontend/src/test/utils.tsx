import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../auth/AuthContext";

// Render a component inside the providers every screen assumes: TanStack Query,
// the router, and AuthContext. `fetch` should be stubbed by the test; AuthProvider
// settles to "unauthenticated" (screens fall back to gallery copy) unless the test
// stubs `/auth/me/`.
export function renderWithProviders(ui: ReactElement, { route = "/" } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>{children}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

// Minimal fetch stub: every call resolves to `body` with the given status.
export function stubFetchJson(status: number, body: unknown) {
  return async () =>
    ({
      ok: status < 400,
      status,
      statusText: "stub",
      text: async () => (body === undefined ? "" : JSON.stringify(body)),
    }) as Response;
}
