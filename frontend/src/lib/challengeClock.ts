export function challengeClock(remaining: number | null, durationMinutes: number, expired = false) {
  const valid = remaining !== null && Number.isFinite(remaining);
  const seconds = expired ? 0 : valid ? Math.max(0, Math.ceil(remaining)) : 0;
  const duration = Number.isFinite(durationMinutes) && durationMinutes > 0 ? durationMinutes * 60 : 1;
  const state = expired || (valid && seconds === 0) ? 'expired'
    : !valid ? 'loading' : seconds <= 60 ? 'critical' : seconds <= 300 ? 'warning' : 'normal';
  const part = (value: number) => valid || expired ? String(value).padStart(2, '0') : '--';
  return {
    hours: part(Math.floor(seconds / 3600)), minutes: part(Math.floor(seconds / 60) % 60),
    seconds: part(seconds % 60), percent: Math.min(100, Math.max(0, seconds / duration * 100)), state,
  };
}
