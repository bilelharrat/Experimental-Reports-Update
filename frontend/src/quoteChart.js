/** Geometry helpers for the Yahoo-style quote chart. */

export function chartGeometry(points = [], { width = 720, height = 280, pad = 16 } = {}) {
  const values = (points || [])
    .map((point) => Number(point?.close))
    .filter((value) => Number.isFinite(value));
  if (!values.length) {
    return { line: "", area: "", min: 0, max: 0, coords: [] };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerW = Math.max(width - pad * 2, 1);
  const innerH = Math.max(height - pad * 2, 1);
  const coords = values.map((value, index) => {
    const x = pad + (index / Math.max(values.length - 1, 1)) * innerW;
    const y = pad + (1 - (value - min) / span) * innerH;
    return { x, y, value, point: points[index] };
  });
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  const area = [
    line,
    `L${coords[coords.length - 1].x.toFixed(1)} ${(height - pad).toFixed(1)}`,
    `L${coords[0].x.toFixed(1)} ${(height - pad).toFixed(1)} Z`,
  ].join(" ");
  return { line, area, min, max, coords };
}

export function chartDirection(points = [], previousClose = null) {
  if (!points.length) return 0;
  const last = Number(points[points.length - 1]?.close);
  const first = Number.isFinite(Number(previousClose))
    ? Number(previousClose)
    : Number(points[0]?.close);
  if (!Number.isFinite(last) || !Number.isFinite(first)) return 0;
  return last - first;
}

export function nearestChartCoord(coords = [], x = 0) {
  if (!coords.length) return null;
  let nearest = coords[0];
  let best = Math.abs(coords[0].x - x);
  for (const coord of coords) {
    const dist = Math.abs(coord.x - x);
    if (dist < best) {
      best = dist;
      nearest = coord;
    }
  }
  return nearest;
}

export function chartDragStats(start, end, coords = []) {
  const first = Number(start?.value);
  const last = Number(end?.value);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  const t0 = Number(start?.point?.t);
  const t1 = Number(end?.point?.t);
  const left = Math.min(Number(start?.x) || 0, Number(end?.x) || 0);
  const right = Math.max(Number(start?.x) || 0, Number(end?.x) || 0);
  const slice = (coords || []).filter(
    (coord) => coord.x >= left && coord.x <= right && Number.isFinite(coord.value),
  );
  const values = slice.length ? slice.map((coord) => coord.value) : [first, last];
  const change = last - first;
  return {
    start: first,
    end: last,
    change,
    changePct: first !== 0 ? (change / first) * 100 : 0,
    durationSec:
      Number.isFinite(t0) && Number.isFinite(t1) ? Math.abs(t1 - t0) : 0,
    high: Math.max(...values),
    low: Math.min(...values),
  };
}

export function formatChartDuration(seconds) {
  const sec = Math.abs(Math.round(Number(seconds) || 0));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.max(1, Math.round(sec / 60))}m`;
  if (sec < 86400) {
    const hours = Math.floor(sec / 3600);
    const minutes = Math.round((sec % 3600) / 60);
    return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  if (sec < 86400 * 14) return `${Math.max(1, Math.round(sec / 86400))}d`;
  if (sec < 86400 * 70) return `${Math.max(1, Math.round(sec / (86400 * 7)))}w`;
  if (sec < 86400 * 365) return `${Math.max(1, Math.round(sec / (86400 * 30)))}mo`;
  const years = sec / (86400 * 365);
  const rounded = years >= 10 ? Math.round(years) : Number(years.toFixed(1));
  return `${rounded}y`;
}

/** Cumulative VWAP across the visible session / range. */
export function volumeWeightedAverage(points = []) {
  let pv = 0;
  let vol = 0;
  return (points || []).map((point) => {
    const close = Number(point?.close);
    const volume = Number(point?.volume);
    if (!Number.isFinite(close)) return vol > 0 ? pv / vol : null;
    if (Number.isFinite(volume) && volume > 0) {
      pv += close * volume;
      vol += volume;
    }
    return vol > 0 ? pv / vol : null;
  });
}

export function movingAverage(points = [], window = 20) {
  const values = (points || []).map((point) => Number(point?.close));
  return values.map((_, index) => {
    if (index + 1 < window) return null;
    const slice = values.slice(index + 1 - window, index + 1);
    if (slice.some((value) => !Number.isFinite(value))) return null;
    return slice.reduce((sum, value) => sum + value, 0) / window;
  });
}

export function overlayPath(values = [], geometry, { height = 280, pad = 18 } = {}) {
  if (!geometry?.coords?.length) return "";
  const min = geometry.min;
  const max = geometry.max;
  const span = max - min || 1;
  const innerH = Math.max(height - pad * 2, 1);
  const parts = [];
  geometry.coords.forEach((coord, index) => {
    const value = Number(values[index]);
    if (!Number.isFinite(value)) return;
    const y = pad + (1 - (value - min) / span) * innerH;
    parts.push(`${parts.length === 0 ? "M" : "L"}${coord.x.toFixed(1)} ${y.toFixed(1)}`);
  });
  return parts.join(" ");
}

export function relativeStrength(points = [], period = 14) {
  const values = (points || []).map((point) => Number(point?.close));
  const rsi = values.map(() => null);
  if (values.filter(Number.isFinite).length <= period) return rsi;
  let gain = 0;
  let loss = 0;
  let counted = 0;
  for (let i = 1; i < values.length; i += 1) {
    if (!Number.isFinite(values[i]) || !Number.isFinite(values[i - 1])) continue;
    const delta = values[i] - values[i - 1];
    if (counted < period) {
      if (delta >= 0) gain += delta;
      else loss -= delta;
      counted += 1;
      if (counted === period) {
        gain /= period;
        loss /= period;
        rsi[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
      }
      continue;
    }
    gain = (gain * (period - 1) + Math.max(delta, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-delta, 0)) / period;
    rsi[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return rsi;
}

export function fibonacciLevels(high, low) {
  const top = Number(high);
  const bottom = Number(low);
  if (!Number.isFinite(top) || !Number.isFinite(bottom) || top === bottom) return [];
  const span = top - bottom;
  return [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].map((ratio) => ({
    ratio,
    value: top - span * ratio,
  }));
}

export function chartCsv(points = []) {
  const lines = ["timestamp,open,high,low,close,volume"];
  for (const point of points || []) {
    const stamp = Number.isFinite(Number(point?.t))
      ? new Date(Number(point.t) * 1000).toISOString()
      : "";
    lines.push(
      [stamp, point?.open ?? "", point?.high ?? "", point?.low ?? "", point?.close ?? "", point?.volume ?? ""].join(","),
    );
  }
  return lines.join("\n");
}

/** Rebase closes to % change from the first finite print for peer overlays. */
export function relativeSeries(points = []) {
  const values = (points || []).map((point) => Number(point?.close));
  const first = values.find((value) => Number.isFinite(value));
  if (!Number.isFinite(first) || first === 0) {
    return values.map(() => null);
  }
  return values.map((value) =>
    Number.isFinite(value) ? ((value - first) / first) * 100 : null,
  );
}

export function eventMarkers(points = [], events = []) {
  const stamps = (points || [])
    .map((point) => Number(point?.t))
    .filter((value) => Number.isFinite(value));
  if (!stamps.length) return [];
  const min = Math.min(...stamps);
  const max = Math.max(...stamps);
  const markers = [];
  for (const event of events || []) {
    const day = String(event?.date || event?.reported || "").slice(0, 10);
    if (!day) continue;
    const stamp = Date.parse(`${day}T16:00:00Z`) / 1000;
    if (!Number.isFinite(stamp) || stamp < min - 86400 || stamp > max + 86400) continue;
    let nearest = stamps[0];
    let best = Math.abs(stamps[0] - stamp);
    for (const candidate of stamps) {
      const dist = Math.abs(candidate - stamp);
      if (dist < best) {
        best = dist;
        nearest = candidate;
      }
    }
    if (best > 86400 * 3) continue;
    markers.push({
      t: nearest,
      label: event.label || "E",
      kind: event.kind || "earnings",
    });
  }
  return markers;
}

/** Compact SVG path for COMP table sparklines. */
export function sparklinePath(values = [], { width = 72, height = 22, pad = 2 } = {}) {
  const nums = (values || []).map(Number).filter(Number.isFinite);
  if (nums.length < 2) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const innerW = Math.max(width - pad * 2, 1);
  const innerH = Math.max(height - pad * 2, 1);
  return nums
    .map((value, index) => {
      const x = pad + (index / Math.max(nums.length - 1, 1)) * innerW;
      const y = pad + (1 - (value - min) / span) * innerH;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

export function formatChartStamp(ts, range = "1d") {
  if (!Number.isFinite(Number(ts))) return "";
  const date = new Date(Number(ts) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  if (range === "1d" || range === "5d") {
    return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  if (range === "5y" || range === "max") {
    return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function dailyReturns(points = []) {
  const closes = (points || []).map((point) => Number(point?.close));
  const out = [];
  for (let i = 1; i < closes.length; i += 1) {
    if (!Number.isFinite(closes[i]) || !Number.isFinite(closes[i - 1]) || closes[i - 1] === 0) {
      out.push(null);
      continue;
    }
    out.push((closes[i] - closes[i - 1]) / closes[i - 1]);
  }
  return out;
}

export function correlation(a = [], b = []) {
  const pairs = [];
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (Number.isFinite(a[i]) && Number.isFinite(b[i])) pairs.push([a[i], b[i]]);
  }
  if (pairs.length < 5) return null;
  const meanA = pairs.reduce((sum, row) => sum + row[0], 0) / pairs.length;
  const meanB = pairs.reduce((sum, row) => sum + row[1], 0) / pairs.length;
  let num = 0;
  let denA = 0;
  let denB = 0;
  for (const [x, y] of pairs) {
    const dx = x - meanA;
    const dy = y - meanB;
    num += dx * dy;
    denA += dx * dx;
    denB += dy * dy;
  }
  if (!denA || !denB) return null;
  return num / Math.sqrt(denA * denB);
}

export function betaVs(assetPoints = [], benchPoints = [], window = 60) {
  const asset = dailyReturns(assetPoints).slice(-window);
  const bench = dailyReturns(benchPoints).slice(-window);
  const pairs = [];
  const n = Math.min(asset.length, bench.length);
  for (let i = 0; i < n; i += 1) {
    if (Number.isFinite(asset[i]) && Number.isFinite(bench[i])) pairs.push([asset[i], bench[i]]);
  }
  if (pairs.length < 10) return { beta: null, corr: null, samples: pairs.length };
  const meanA = pairs.reduce((sum, row) => sum + row[0], 0) / pairs.length;
  const meanB = pairs.reduce((sum, row) => sum + row[1], 0) / pairs.length;
  let cov = 0;
  let varB = 0;
  for (const [a, b] of pairs) {
    cov += (a - meanA) * (b - meanB);
    varB += (b - meanB) ** 2;
  }
  return {
    beta: varB ? cov / varB : null,
    corr: correlation(
      pairs.map((row) => row[0]),
      pairs.map((row) => row[1]),
    ),
    samples: pairs.length,
  };
}

export function maxDrawdown(points = []) {
  let peak = null;
  let maxDd = 0;
  let trough = null;
  let peakAt = null;
  for (const point of points || []) {
    const close = Number(point?.close);
    if (!Number.isFinite(close)) continue;
    if (peak == null || close > peak) {
      peak = close;
      peakAt = point;
    }
    if (peak) {
      const dd = ((close - peak) / peak) * 100;
      if (dd < maxDd) {
        maxDd = dd;
        trough = point;
      }
    }
  }
  return { drawdown: maxDd, peak: peakAt, trough };
}

export function drawdownSeries(points = []) {
  let peak = null;
  return (points || []).map((point) => {
    const close = Number(point?.close);
    if (!Number.isFinite(close)) return null;
    if (peak == null || close > peak) peak = close;
    return peak ? ((close - peak) / peak) * 100 : 0;
  });
}

export function monthlySeasonality(points = []) {
  const buckets = Array.from({ length: 12 }, () => []);
  const closes = (points || [])
    .map((point) => ({
      t: Number(point?.t),
      close: Number(point?.close),
    }))
    .filter((row) => Number.isFinite(row.t) && Number.isFinite(row.close));
  for (let i = 1; i < closes.length; i += 1) {
    const prev = closes[i - 1];
    const cur = closes[i];
    if (!prev.close) continue;
    const month = new Date(cur.t * 1000).getUTCMonth();
    buckets[month].push(((cur.close - prev.close) / prev.close) * 100);
  }
  return buckets.map((values, month) => {
    const avg =
      values.length > 0 ? values.reduce((sum, n) => sum + n, 0) / values.length : null;
    return { month, avg, samples: values.length };
  });
}
