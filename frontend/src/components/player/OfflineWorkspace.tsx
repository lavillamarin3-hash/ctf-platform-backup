import { useEffect, useState } from "react";
import type { Run } from "../../api";
import { request } from "../../services/api/client";
import { KaliPanel } from './KaliPanel';

type Bundle = { title: string; brief: string; kali_command?: string };

export function OfflineWorkspace({ run, onClose, onSubmit }: {
  run: Run; onClose: (id: number) => Promise<void>;
  onSubmit: (code: string, flag: string) => Promise<{ message: string }>;
}) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [answer, setAnswer] = useState("");
  const [flag, setFlag] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [now, setNow] = useState(Date.now());
  const expired = new Date(run.expires_at).getTime() <= now;
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    let alive = true;
    setError("");
    request<Bundle>(`/runs/${run.id}/offline`).then(data => { if (alive) setBundle(data); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : "No se pudo cargar el ejercicio."); });
    return () => { alive = false; };
  }, [run.id, reload]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo completar la operación."); }
    finally { setBusy(false); }
  }
  return <section className="glass-panel" style={{ padding: "1.25rem" }} aria-label="Ejercicio de análisis en Kali">
    <span className="eyebrow accent">ANÁLISIS EN KALI · CORRIDA {run.id}</span>
    <h3>{bundle?.title ?? "Preparando archivos…"}</h3>
    <p>Disponible hasta {new Date(run.expires_at).toLocaleString()}. {expired && "La corrida caducó. Ciérrala para iniciar otra."}</p>
    {bundle && <>
      <p>{bundle.brief}</p>
      <p>Analiza las evidencias desde Kali. Prepara tu carpeta de trabajo con el comando de la terminal y consulta las pistas del reto cuando necesites orientación.</p>
      {!expired && <KaliPanel run={run} command={bundle.kali_command} />}
      <form onSubmit={event => { event.preventDefault(); void perform(async () => {
        setFlag("");
        const result = await request<{flag: string | null; message: string}>(`/runs/${run.id}/offline/answer`, { method: "POST", body: JSON.stringify({ value: answer }) });
        setFlag(result.flag ?? ""); setMessage(result.message);
      }); }}>
        <label style={{ display: "block", margin: "1rem 0" }}>Tu respuesta (según el formato del objetivo)
          <input style={{ display: "block", width: "100%" }} required maxLength={200} value={answer} onChange={event => { setAnswer(event.target.value); setFlag(""); }} />
        </label>
        <button className="primary-action" disabled={busy || expired}>Validar respuesta</button>
      </form>
      {flag && <div className="instruction-box"><p>El análisis es correcto. Registra el resultado para sumar los puntos.</p>
        <button className="primary-action" disabled={busy || expired} onClick={() => void perform(async () => {
          const result = await onSubmit(run.challenge_code, flag); setMessage(result.message);
        })}>Registrar puntos</button>
      </div>}
    </>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    {!bundle && error && <button className="secondary-action" onClick={() => setReload(value => value+1)}>Reintentar carga</button>}
    <button className="secondary-action" disabled={busy} style={{ marginTop: "1rem" }} onClick={() => void perform(() => onClose(run.id))}>Cerrar ejercicio</button>
  </section>;
}
