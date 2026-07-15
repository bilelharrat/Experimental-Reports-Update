// Retry policy for the report progress poll (ResearchView).
//
// Memo generation legitimately runs ~19-34 minutes, so the poll loop must
// survive transient blips (dev-server reload, laptop sleep, a read racing a
// write). Back off 1s -> 2s -> 5s as consecutive failures stack, and only
// give up after POLL_MAX_FAILURES straight failures.

export const POLL_MAX_FAILURES = 5;

export function pollDelayMs(consecutiveFailures) {
  if (consecutiveFailures <= 1) return 1000;
  if (consecutiveFailures === 2) return 2000;
  return 5000;
}
