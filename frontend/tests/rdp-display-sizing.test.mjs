import assert from "node:assert/strict";
import { test } from "node:test";
import { fitRdpScale } from "../src/lib/rdpDisplaySizing.ts";

test("fits a wide RDP desktop by viewport width", () => {
  assert.equal(fitRdpScale(800, 700, 1600, 900), 0.5);
});

test("fits a tall RDP desktop by viewport height", () => {
  assert.equal(fitRdpScale(1200, 600, 800, 1200), 0.5);
});

test("enlarges the same desktop when the viewport enters fullscreen", () => {
  const embedded = fitRdpScale(600, 400, 1200, 800);
  const fullscreen = fitRdpScale(1200, 800, 1200, 800);
  assert.equal(embedded, 0.5);
  assert.equal(fullscreen, 1);
});

test("applies manual zoom relative to the fitted desktop", () => {
  assert.equal(fitRdpScale(800, 600, 1600, 1200, 1.25), 0.625);
  assert.equal(fitRdpScale(800, 600, 1600, 1200, 0.75), 0.375);
});

test("falls back to a finite scale for missing or invalid dimensions", () => {
  for (const dimensions of [
    [0, 600, 800, 600],
    [800, 600, 0, 600],
    [800, Number.NaN, 800, 600],
    [800, 600, Number.POSITIVE_INFINITY, 600],
  ]) {
    assert.equal(fitRdpScale(...dimensions), 1);
  }
  assert.equal(fitRdpScale(800, 600, 1600, 1200, Number.NaN), 0.5);
  assert.equal(fitRdpScale(800, 600, 1600, 1200, Number.POSITIVE_INFINITY), 0.5);
});
