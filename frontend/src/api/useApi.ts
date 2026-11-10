import { useEffect, useRef, useState } from "react";

export type Loadable<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** A loadable that can fetch again. `reload` keeps what is shown until the new answer lands. */
export type Reloadable<L> = L & { reload: () => Promise<void> };

type Load<T> = () => Promise<{ data?: T; error?: unknown; response: Response }>;

/** Run an API call when `key` changes; the latest call wins. With no call (`null`), idle. */
export function useApi<T>(key: string, load: Load<T>): Reloadable<Exclude<Loadable<T>, { state: "idle" }>>;
export function useApi<T>(key: string, load: Load<T> | null): Reloadable<Loadable<T>>;
export function useApi<T>(key: string, load: Load<T> | null): Reloadable<Loadable<T>> {
  const [result, setResult] = useState<{ key: string; value: Loadable<T> }>({
    key,
    value: { state: "loading" },
  });
  // Numbers each call, so only the latest one is applied.
  const calls = useRef({ latest: 0 });

  const run = async (call: Load<T>) => {
    const id = ++calls.current.latest;
    let value: Loadable<T>;
    try {
      const { data, response } = await call();
      value =
        data !== undefined
          ? { state: "ready", data }
          : { state: "error", message: `${response.status} ${response.statusText}` };
    } catch (error) {
      value = { state: "error", message: String(error) };
    }
    if (id === calls.current.latest) setResult({ key, value });
  };

  const idle = load === null;
  useEffect(() => {
    if (!load) return;
    const counter = calls.current;
    void run(load);
    return () => {
      counter.latest++;
    };
    // `load` and `run` are fresh closures on every render; `key` names what they load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, idle]);

  const reload = () => (load ? run(load) : Promise.resolve());
  if (idle) return { state: "idle", reload };
  return { ...(result.key === key ? result.value : { state: "loading" }), reload };
}
