import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { errorMessage } from "./format";

export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

/** Runs an async loader when its dependencies change; stale responses are discarded. */
export function useAsync<T>(loader: () => Promise<T> | null, deps: DependencyList): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: false });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const run = useCallback(loader, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const ticket = ++latest.current;
    const promise = run();
    if (!promise) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    setState((current) => ({ ...current, loading: true, error: null }));
    promise.then(
      (data) => {
        if (ticket === latest.current) setState({ data, error: null, loading: false });
      },
      (error: unknown) => {
        if (ticket === latest.current) setState({ data: null, error: errorMessage(error), loading: false });
      },
    );
  }, [run, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, reload };
}
