import assert from 'node:assert/strict';
import { test } from 'node:test';
import { challengeClock } from '../src/lib/challengeClock.ts';

test('long challenges use hours instead of an overflowing minute counter', () => {
  const clock = challengeClock(86399, 1440);
  assert.deepEqual([clock.hours, clock.minutes, clock.seconds], ['23', '59', '59']);
  assert.equal(challengeClock(3600, 60).hours, '01');
});
test('warning and expiry boundaries follow the deadline without negative values', () => {
  assert.equal(challengeClock(301, 45).state, 'normal');
  assert.equal(challengeClock(300, 45).state, 'warning');
  assert.equal(challengeClock(60, 45).state, 'critical');
  assert.equal(challengeClock(.1, 45).seconds, '01');
  assert.equal(challengeClock(-4, 45).state, 'expired');
  assert.equal(challengeClock(-4, 45).seconds, '00');
  assert.equal(challengeClock(200, 45, true).percent, 0);
});
test('loading and progress stay finite when metadata is missing or inconsistent', () => {
  assert.equal(challengeClock(null, 60).minutes, '--');
  assert.equal(challengeClock(NaN, 60).state, 'loading');
  assert.equal(challengeClock(500, 1).percent, 100);
  assert.ok(Number.isFinite(challengeClock(20, NaN).percent));
});
