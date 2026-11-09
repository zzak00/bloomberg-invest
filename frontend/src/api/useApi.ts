import { useEffect, useState } from "react";

export type Loadable<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

type Load<T> = () => Promise<{ data?: T; error?: unknown; response: Response }>;

/** Run an API call when `key` changes; the latest call wins. With no call (`null`), idle. */
export function useApi<T>(key: string, load: Load<T>): Exclude<Loadable<T>, { state: "idle" }>;
export function useApi<T>(key: string, load: Load<T> | null): Loadable<T>;
export function useApi<T>(key: string, load: Load<T> | null): Loadable<T> {
  const [result, setResult] = useState<{ key: string; value: Loadable<T> }>({
    key,
    value: { state: "loading" },
  });

  const idle = load === null;
  useEffect(() => {
    if (!load) return;
    let current = true;
    load()
      .then(({ data, response }) => {
        if (!current) return;
        setResult({
          key,
          value:
            data !== undefined
              ? { state: "ready", data }
              : { state: "error", message: `${response.status} ${response.statusText}` },
        });
      })
      .catch((error: unknown) => {
        if (current) setResult({ key, value: { state: "error", message: String(error) } });
      });
    return () => {
      current = false;
    };
    // `load` is a fresh closure on every render; `key` names what it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, idle]);

  if (idle) return { state: "idle" };
  return result.key === key ? result.value : { state: "loading" };
}
