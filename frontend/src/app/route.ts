import { useCallback, useEffect, useState } from "react";

/** App location, kept in the URL hash so reloads and the back button work without a router. */
export type Route =
  | { page: "home" }
  | { page: "project"; projectId: string; version: number | null }
  | { page: "settings" }
  | { page: "dev" };

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "dev") return { page: "dev" };
  if (parts[0] === "p" && parts[1]) {
    const version = parts[2] === "v" && parts[3] ? Number.parseInt(parts[3], 10) : NaN;
    return { page: "project", projectId: parts[1], version: Number.isFinite(version) ? version : null };
  }
  return { page: "home" };
}

export function routeToHash(route: Route): string {
  switch (route.page) {
    case "home":
      return "#/";
    case "settings":
      return "#/settings";
    case "dev":
      return "#/dev";
    case "project":
      return `#/p/${encodeURIComponent(route.projectId)}${route.version !== null ? `/v/${route.version}` : ""}`;
  }
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((next: Route, replace = false) => {
    const hash = routeToHash(next);
    if (replace) window.history.replaceState(null, "", hash);
    else window.history.pushState(null, "", hash);
    setRoute(next);
  }, []);
  return { route, navigate };
}
