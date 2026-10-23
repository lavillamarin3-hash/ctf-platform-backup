import { useEffect, useState } from "react";
import type { Run } from "../../api";
import { request } from "../../services/api/client";
import { KaliPanel } from './KaliPanel';

type Bundle = {
  title: string; brief: string; clock_notes: string;
  kali_command?: string;
};
const fields = [
  ["session", "Sesión"], ["user", "Usuario"], ["request", "Solicitud HTTP"],
  ["destination", "IP de destino"], ["auth_utc", "Autenticación en UTC (ISO 8601)"],
] as const;

export function DfirWorkspace({ run, onClose, onSubmit }: {
  run: Run; onClose: (id: number) => Promise<void>;
  onSubmit: (code: string, flag: string) => Promise<{message: string}>;
}) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [answer, setAnswer] = useState<Record<string, string>>({});
  const [flag, setFlag] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const expired = new Date(run.expires_at).getTime() <= Date.now();
  useEffect(() => {
    let alive = true;
    request<Bundle>(`/runs/${run.id}/dfir`).then(data => { if (alive) setBundle(data); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : "No se pudo cargar el caso."); });
    return () => { alive = false; };
  }, [run.id]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo completar la operación."); }
    finally { setBusy(false); }
  }
  return <section className="glass-panel" style={{padding: "1.25rem"}} aria-label="Expediente forense">
    <span className="eyebrow accent">EXPEDIENTE · CORRIDA {run.id}</span>
    <h3>{bundle?.title ?? "Preparando expediente…"}</h3>
    <p>Disponible hasta {new Date(run.expires_at).toLocaleString()}. {expired && "La corrida ha caducado; ciérrala para iniciar otra."}</p>
    {bundle && <>
      <p>{bundle.brief}</p><p>{bundle.clock_notes}</p>
      <p>Investiga los registros y la calibración de relojes en Kali. El expediente completo se conserva en tu carpeta de la corrida; consulta las pistas para orientar el análisis.</p>
      {!expired && <KaliPanel run={run} command={bundle.kali_command} />}
      <form onSubmit={event => {
        event.preventDefault();
        void perform(async () => {
          setFlag("");
          const result = await request<{correct: boolean; flag: string | null; message: string}>(`/runs/${run.id}/dfir/answer`, {method: "POST", body: JSON.stringify(answer)});
          setMessage(result.message); setFlag(result.flag ?? "");
        });
      }}>
        <h3>Tu reconstrucción</h3>
        <div style={{display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem"}}>
          {fields.map(([key, label]) => <label key={key}>{label}<input style={{display: "block", width: "100%"}} required maxLength={100} value={answer[key] ?? ""} onChange={e => {setAnswer({...answer, [key]: e.target.value}); setFlag("");}} /></label>)}
        </div>
        <button className="primary-action" style={{marginTop: "1rem"}} disabled={busy || expired}>Validar correlación</button>
      </form>
      <label style={{display: "block", marginTop: "1rem"}}>Bloc de análisis (se descarta al salir)
        <textarea style={{width: "100%", minHeight: "8rem"}} value={notes} onChange={e => setNotes(e.target.value)} />
      </label>
      {flag && <div className="instruction-box">
        <p style={{overflowWrap: "anywhere"}}>{flag}</p>
        <div className="row-actions">
          <button className="secondary-action" disabled={busy || expired} onClick={() => void perform(async () => {await navigator.clipboard.writeText(flag); setMessage("Flag copiada.");})}>Copiar flag</button>
          <button className="primary-action" disabled={busy || expired} onClick={() => void perform(async () => {const result = await onSubmit("DFIR-01", flag); setMessage(result.message);})}>Enviar flag y registrar puntos</button>
        </div>
      </div>}
    </>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    <button className="secondary-action" style={{marginTop: "1rem"}} disabled={busy} onClick={() => void perform(() => onClose(run.id))}>Cerrar caso</button>
  </section>;
}
