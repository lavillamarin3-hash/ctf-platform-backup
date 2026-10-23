import { challengeClock } from '../../lib/challengeClock';

export function ChallengeClock({ remaining, durationMinutes, expired, hintsUsed, hintCount }: {
  remaining: number | null; durationMinutes: number; expired: boolean; hintsUsed: number; hintCount: number;
}) {
  const clock = challengeClock(remaining, durationMinutes, expired);
  const units = [[clock.hours, 'Horas'], [clock.minutes, 'Minutos'], [clock.seconds, 'Segundos']];
  const ends = clock.state === 'expired';
  const status = ends ? 'Plazo finalizado' : clock.state === 'critical' ? 'Último minuto'
    : clock.state === 'warning' ? 'Quedan 5 minutos o menos' : 'Reto en curso';
  return <section className={`challenge-clock ${clock.state}`} aria-label="Tiempo del reto">
    <div className="challenge-clock-heading">
      <span className="challenge-clock-label"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="13" r="8" /><path d="M12 9v4l3 2M9 2h6M12 2v3M18 5l2 2" /></svg>Tiempo restante</span>
      <span className="challenge-clock-badge" role="status">{status}</span>
    </div>
    <div className="challenge-clock-body">
      <div className="challenge-clock-display" role="timer" aria-live="off" aria-label={`${Number(clock.hours)} horas, ${Number(clock.minutes)} minutos y ${Number(clock.seconds)} segundos restantes`}>
        {units.map(([value, label], index) => <div className="challenge-clock-unit" key={label}>
          {index > 0 && <span className="challenge-clock-separator" aria-hidden="true">:</span>}
          <strong aria-hidden="true">{value}</strong><small aria-hidden="true">{label}</small>
        </div>)}
      </div>
      <div className="challenge-clock-context">
        <p>{ends ? 'Continúa aprendiendo' : 'Tu siguiente paso cuenta'}</p>
        <span>{ends ? 'Revisa la solución en el panel de ayudas.' : 'Investiga en Kali y consulta una pista si la necesitas.'}</span>
        <span className="challenge-clock-hints"><b>{hintsUsed} / {hintCount}</b> pistas consultadas</span>
      </div>
    </div>
    <div className="challenge-clock-progress" aria-hidden="true"><span style={{ width: `${clock.percent}%` }} /></div>
    <div className="challenge-clock-footer"><span>{ends ? 'Tiempo agotado' : 'Plazo original del reto'}</span><span>{durationMinutes} min en total</span></div>
  </section>;
}
