import { useEffect, useState } from "react";

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** Run an API call when `key` changes; the latest call wins. */
export function useApi<T>(
  key: string,
  load: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Loadable<T> {
  const [result, setResult] = useState<{ key: string; value: Loadable<T> }>({
    key,
    value: { state: "loading" },
  });

  useEffect(() => {
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
  }, [key]);

  return result.key === key ? result.value : { state: "loading" };
}
