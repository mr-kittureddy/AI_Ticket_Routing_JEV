import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "@/App";
import { RoleProvider } from "@/context/RoleContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { isApiError } from "@/services/api";
import "./index.css";

const MAX_QUERY_RETRIES = 2;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Only transient failures (network, timeout, 502-504) are retried. A 401, 403, 404 or contract error is
      // permanent, so retrying would only delay the error message.
      retry: (failureCount, error) => failureCount < MAX_QUERY_RETRIES && isApiError(error) && error.isRetryable,
      refetchOnWindowFocus: false,
    },
    // A ticket submission must never be repeated automatically: the backend would reject the second copy as a
    // duplicate or, worse, process it twice.
    mutations: { retry: 0 },
  },
});

const container = document.getElementById("root");
if (container === null) {
  throw new Error('Missing <div id="root"> in index.html; the application cannot mount.');
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RoleProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </RoleProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
