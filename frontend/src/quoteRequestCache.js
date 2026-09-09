/** In-flight dedupe for quote chart / workspace fetches. */

const inflight = new Map();

export function cachedRequest(key, factory) {
  const id = String(key || "");
  if (!id) return Promise.resolve(factory());
  if (inflight.has(id)) return inflight.get(id);
  const pending = Promise.resolve()
    .then(factory)
    .finally(() => {
      inflight.delete(id);
    });
  inflight.set(id, pending);
  return pending;
}

export function clearQuoteRequestCache() {
  inflight.clear();
}
