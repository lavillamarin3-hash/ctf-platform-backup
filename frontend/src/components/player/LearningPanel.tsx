import { useCallback, useEffect, useRef, useState } from 'react';
import type { Run } from '../../api';
import { request } from '../../services/api/client';
import { remainingLearningPoints } from '../../lib/learningPolicy';
import { ChallengeClock } from './ChallengeClock';

type Hint = { id: number; title: string; unlocked: boolean; content?: string; penalty_percent?: number };
type Solution = { steps: string[]; answer: string | null; note?: string };
type LearningState = {
  base_points: number; available_points: number; deadline: string; expired: boolean;
  hints_used: number; hints: Hint[]; solution_revealed: boolean;
  completed: boolean; awarded_points?: number; solution?: Solution;
  hint_count?: number; expired_points_percent?: number; duration_minutes?: number;
  solution_available?: boolean; solution_reason?: 'expired' | 'all_hints' | null;
};

export function LearningPanel({ run, completed, onComplete }: {
  run?: Run; completed: boolean; onComplete?: () => Promise<void>;
}) {
  const [data, setData] = useState<LearningState | null>(null);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const generation = useRef(0);
  const automaticSolution = useRef<{ runId: number; snapshot: LearningState } | null>(null);
  const automaticSolutionPending = useRef(false);
  const base = run ? `/runs/${run.id}/learning` : '';

  const load = useCallback(async () => {
    if (!base) return;
    const current = generation.current;
    try {
      const state = await request<LearningState>(base);
      if (generation.current === current) { setData(state); setError(''); }
    } catch (e) {
      if (generation.current === current) setError(e instanceof Error ? e.message : 'No se pudo consultar el puntaje.');
    }
  }, [base]);

  useEffect(() => {
    generation.current += 1;
    setData(null); setSolution(null); setError(''); setNotice(''); setBusy(false);
    automaticSolution.current = null;
    automaticSolutionPending.current = false;
    void load();
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    const poll = window.setInterval(() => void load(), 30_000);
    return () => { generation.current += 1; window.clearInterval(timer); window.clearInterval(poll); };
  }, [load]);
  useEffect(() => { if (completed) void load(); }, [completed, load]);

  const perform = async (action: (isCurrent: () => boolean) => Promise<void>) => {
    const current = generation.current;
    const isCurrent = () => generation.current === current;
    setBusy(true); setError('');
    try { await action(isCurrent); }
    catch (e) { if (isCurrent()) setError(e instanceof Error ? e.message : 'No se pudo completar la operación.'); }
    finally { if (isCurrent()) setBusy(false); }
  };
  const revealSolution = useCallback(async () => {
    if (!base) return;
    const current = generation.current;
    const state = await request<LearningState>(`${base}/solution`, { method: 'POST' });
    if (generation.current === current) { setData(state); setSolution(state.solution ?? null); setError(''); }
  }, [base]);
  const remaining = data ? Math.max(0, Math.ceil((new Date(data.deadline).getTime() - now) / 1000)) : null;
  const expired = Boolean(data && (data.expired || remaining === 0));
  const solutionAvailable = Boolean(data && (data.solution_available || expired));
  useEffect(() => {
    if (!run || !data || !solutionAvailable || solution || automaticSolutionPending.current
        || (automaticSolution.current?.runId === run.id && automaticSolution.current.snapshot === data)) return;
    const current = generation.current;
    // Un intento por consulta de metadatos: tras un fallo, el sondeo permite
    // reintentar sin que cada tick del contador genere nuevas solicitudes.
    automaticSolution.current = { runId: run.id, snapshot: data };
    automaticSolutionPending.current = true;
    void revealSolution()
      .catch(e => { if (generation.current === current) setError(e instanceof Error ? e.message : 'No se pudo cargar la solución.'); })
      .finally(() => { if (generation.current === current) automaticSolutionPending.current = false; });
  }, [run?.id, data, solutionAvailable, solution, revealSolution]);

  const expiredPointsPercent = data?.expired_points_percent ?? 25;
  const hintCount = data?.hint_count ?? data?.hints.length ?? 3;
  const reviewPoints = data ? (expired ? remainingLearningPoints(data.base_points, expiredPointsPercent) : data.available_points) : 0;
  return <section className="learning-panel" aria-label="Puntaje, tiempo y ayudas del reto">
    <div className="learning-panel-heading">
      <div><span className="eyebrow accent">TU PROGRESO EN EL RETO</span><h3>Puntaje, tiempo y ayudas</h3></div>
      {data && <strong className="learning-points" aria-live="polite">{data.available_points} <small>de {data.base_points} puntos</small></strong>}
    </div>
    <p>Investiga primero en la máquina virtual. Cada pista desbloquea una etapa guiada y aplica su descuento. La solución aparece al consultar todas las pistas o al agotar el tiempo. {data ? `Después del plazo queda el ${expiredPointsPercent}% del puntaje base. ` : ''}Cerrar o reabrir conserva las ayudas y el plazo.</p>
    {!run && <p className="field-help">Inicia el laboratorio para activar el tiempo y consultar tus pistas.</p>}
    {data && <>
      <ChallengeClock remaining={remaining} durationMinutes={data.duration_minutes ?? 60} expired={expired}
        hintsUsed={data.hints_used} hintCount={hintCount} />
      {data.completed && <p role="status">Reto completado. Se conservan los {data.awarded_points ?? data.available_points} puntos registrados.</p>}
      <div className="learning-hints">
        {data.hints.map(hint => <article key={hint.id}>
          <div className="learning-hint-heading"><strong>{hint.title}</strong>
            {!hint.unlocked && <button type="button" className="secondary-action" disabled={busy || expired || data.completed || run?.status !== 'active' || data.hints.some(previous => previous.id < hint.id && !previous.unlocked)} onClick={() => void perform(async (isCurrent) => {
              const state = await request<LearningState>(`${base}/hints/${hint.id}`, { method: 'POST' });
              if (!isCurrent()) return;
              setData(state); setNotice('Pista desbloqueada. El puntaje disponible ya incluye el descuento.');
            })}>Ver pista · −{hint.penalty_percent ?? 10}%</button>}
            {hint.unlocked && <small>Descuento aplicado: {hint.penalty_percent ?? 10}% de la base</small>}
          </div>
          {hint.unlocked && <ol className="learning-hint-steps">{(hint.content ?? '').split('\n').filter(line => line.trim()).map((line, index) => <li key={index}>{line.replace(/^\d+[.)]\s*/, '')}</li>)}</ol>}
        </article>)}
      </div>
      {solutionAvailable && <div className="learning-solution">
        <h4>Solución y explicación</h4>
        <p>{expired ? 'El tiempo terminó. Revisa el procedimiento y contrástalo con tu trabajo.' : 'Consultaste todas las pistas. Ya puedes revisar la resolución completa y continuar en la VM mientras quede tiempo.'}</p>
        {solution ? <>
          <ol>{solution.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
          {solution.answer && <div><strong>Respuesta de esta corrida</strong><pre>{solution.answer}</pre></div>}
          {solution.note && <p>{solution.note}</p>}
          {!data.completed && <button type="button" className="primary-action" disabled={busy} onClick={() => void perform(async (isCurrent) => {
            const result = await request<{ message: string }>(`${base}/complete`, { method: 'POST' });
            if (!isCurrent()) return;
            setNotice(result.message); await load();
            if (isCurrent()) await onComplete?.();
          })}>Registrar aprendizaje · {reviewPoints} puntos</button>}
        </> : <button type="button" className="secondary-action" disabled={busy} onClick={() => void perform(revealSolution)}>Mostrar solución</button>}
      </div>}
    </>}
    {notice && <p role="status">{notice}</p>}
    {completed && !data && <p>Los puntos que ya obtuviste se conservan. Inicia una nueva práctica para utilizar las ayudas.</p>}
    {error && !(completed && !data) && <p role="alert">{error}</p>}
  </section>;
}
