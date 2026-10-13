import { useEffect, useState } from "react";

import { DEFAULT_SCREEN, SCREENS } from "./screens";

function current(): string {
  const id = window.location.hash.replace(/^#\/?/, "");
  return SCREENS.some((s) => s.id === id) ? id : DEFAULT_SCREEN;
}

/** Minimal hash router: `#/jobs`, `#/setup`, … (no router dependency needed yet). */
export function useHashRoute(): [string, (id: string) => void] {
  const [route, setRoute] = useState(current);
  useEffect(() => {
    const onChange = () => setRoute(current());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [route, (id: string) => (window.location.hash = `/${id}`)];
}
