import { describe, expect, it } from "vitest";
import {
  chartCsv,
  chartDirection,
  chartDragStats,
  chartGeometry,
  eventMarkers,
  fibonacciLevels,
  formatChartDuration,
  formatChartStamp,
  movingAverage,
  nearestChartCoord,
  overlayPath,
  relativeSeries,
  relativeStrength,
  sparklinePath,
  volumeWeightedAverage,
} from "../src/quoteChart.js";

const points = [
  { t: 1_725_148_800, close: 100 },
  { t: 1_725_149_100, close: 110 },
  { t: 1_725_149_400, close: 105 },
];

describe("quoteChart", () => {
  it("builds a line and closed area path from closes", () => {
    const geo = chartGeometry(points, { width: 100, height: 50, pad: 10 });
    expect(geo.min).toBe(100);
    expect(geo.max).toBe(110);
    expect(geo.coords).toHaveLength(3);
    expect(geo.line.startsWith("M")).toBe(true);
    expect(geo.area.endsWith("Z")).toBe(true);
  });

  it("uses previous close for direction when present", () => {
    expect(chartDirection(points, 90)).toBe(15);
    expect(chartDirection(points, 120)).toBeLessThan(0);
    expect(chartDirection([])).toBe(0);
  });

  it("formats intraday stamps with a clock time", () => {
    expect(formatChartStamp(1_725_148_800, "1d")).toMatch(/\d/);
    expect(formatChartStamp("nope", "1d")).toBe("");
  });

  it("summarizes a dragged range with change, duration, high, and low", () => {
    const geo = chartGeometry(points, { width: 100, height: 50, pad: 10 });
    const stats = chartDragStats(geo.coords[0], geo.coords[2], geo.coords);
    expect(stats.change).toBe(5);
    expect(stats.changePct).toBe(5);
    expect(stats.high).toBe(110);
    expect(stats.low).toBe(100);
    expect(stats.durationSec).toBe(600);
    expect(nearestChartCoord(geo.coords, geo.coords[1].x)).toEqual(geo.coords[1]);
    expect(formatChartDuration(141)).toBe("2m");
    expect(formatChartDuration(3900)).toBe("1h 5m");
    const reverse = chartDragStats(geo.coords[2], geo.coords[0], geo.coords);
    expect(reverse.change).toBe(-5);
    expect(reverse.high).toBe(110);
  });

  it("computes SMA, RSI, Fibonacci, overlay path, and CSV", () => {
    const series = Array.from({ length: 20 }, (_, index) => ({
      t: 1_725_148_800 + index * 60,
      open: 100 + index,
      high: 101 + index,
      low: 99 + index,
      close: 100 + index,
      volume: 1000 + index,
    }));
    const sma = movingAverage(series, 5);
    expect(sma[3]).toBeNull();
    expect(sma[4]).toBe(102);
    const rsi = relativeStrength(series, 14);
    expect(rsi[14]).toBe(100);
    const levels = fibonacciLevels(110, 100);
    expect(levels).toHaveLength(7);
    expect(levels[0]).toEqual({ ratio: 0, value: 110 });
    expect(levels[3].value).toBeCloseTo(105);
    const geo = chartGeometry(series.slice(0, 3), { width: 100, height: 50, pad: 10 });
    expect(overlayPath([100, 110, 105], geo, { height: 50, pad: 10 })).toContain("M");
    const csv = chartCsv(series.slice(0, 2));
    expect(csv.split("\n")[0]).toBe("timestamp,open,high,low,close,volume");
    expect(csv).toContain("100");
    expect(relativeSeries([{ close: 100 }, { close: 110 }])).toEqual([0, 10]);
    expect(
      eventMarkers(series, [{ date: new Date(series[5].t * 1000).toISOString().slice(0, 10) }]),
    ).toHaveLength(1);
    expect(sparklinePath([100, 110, 105])).toContain("M");
    expect(volumeWeightedAverage([
      { close: 100, volume: 10 },
      { close: 110, volume: 10 },
    ])).toEqual([100, 105]);
  });
});
