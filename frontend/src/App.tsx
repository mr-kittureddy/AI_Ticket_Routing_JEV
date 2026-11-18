import { useEffect, useRef } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { Dashboard } from "@/pages/Dashboard";

/** On in-app navigation, scroll to the top and move focus to <main> so keyboard and screen-reader users land on the new page. */
function RouteChangeHandler(): null {
  const { pathname } = useLocation();
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    window.scrollTo(0, 0);
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [pathname]);

  return null;
}

export function App(): JSX.Element {
  return (
    <>
      <RouteChangeHandler />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
