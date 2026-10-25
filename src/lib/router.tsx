import { useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

/**
 * A minimal History API router. Paths are app-relative; the Vite base path
 * (import.meta.env.BASE_URL, e.g. a Figma Make preview prefix) is added and
 * removed here so pages never see it.
 */
const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");
const listeners = new Set<() => void>();

function strip(pathname: string): string {
  const path = BASE && pathname.startsWith(BASE) ? pathname.slice(BASE.length) : pathname;
  return path.replace(/\/+$/, "") || "/";
}

function snapshot(): string {
  return strip(window.location.pathname) + window.location.search;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function navigate(to: string, options: { replace?: boolean } = {}): void {
  const url = `${BASE}${to.startsWith("/") ? to : `/${to}`}`;
  if (options.replace) window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
  listeners.forEach((listener) => listener());
  window.scrollTo({ top: 0 });
}

export function useLocation(): { path: string; search: URLSearchParams } {
  const current = useSyncExternalStore(subscribe, snapshot, () => "/");
  const [path, query = ""] = current.split("?");
  return { path, search: new URLSearchParams(query) };
}

export function Link({ to, onClick, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  function handle(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(to);
  }
  return <a href={`${BASE}${to}`} onClick={handle} {...props} />;
}
