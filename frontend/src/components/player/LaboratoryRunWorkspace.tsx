import { FormEvent, useEffect, useRef, useState } from "react";
import { Icon } from "../common";
import type { Run } from "../../models";
import { GuacamoleTerminal } from "./GuacamoleTerminal";

type SubmissionResult = { correct: boolean; challenge_completed: boolean; awarded_points: number; message: string };
type Notice = { kind: "success" | "error"; message: string } | null;
const storageKey = (id: number) => `ctf-laboratory-notes:${id}`;

export function LaboratoryRunWorkspace({ run, onClose, onSubmit }: {
  run: Run;
  onClose: (runId: number) => Promise<void>;
  onSubmit: (code: string, value: string) => Promise<SubmissionResult>;
}) {
  const workspaceRef = useRef<HTMLElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [notes, setNotes] = useState("");
  const [candidate, setCandidate] = useState("");
  const [selection, setSelection] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [closing, setClosing] = useState(false);
  const [expired, setExpired] = useState(Date.parse(run.expires_at) <= Date.now());

  // Recargar el mismo run tras validar conserva el candidato y el resultado.
  useEffect(() => {
    setCandidate(""); setSelection(""); setResult(null); setNotice(null);
    try { setNotes(sessionStorage.getItem(storageKey(run.id)) ?? ""); } catch { setNotes(""); }
  }, [run.id]);
  useEffect(() => {
    const check = () => setExpired(Date.parse(run.expires_at) <= Date.now());
    check(); const timer = window.setInterval(check, 1000);
    return () => window.clearInterval(timer);
  }, [run.expires_at]);
  useEffect(() => {
    const updateFullscreen = () => setFullscreen(document.fullscreenElement === workspaceRef.current);
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => document.removeEventListener("fullscreenchange", updateFullscreen);
  }, []);
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === workspaceRef.current) await document.exitFullscreen();
      else await workspaceRef.current?.requestFullscreen();
    } catch {
      setNotice({ kind: "error", message: "El navegador no permitió abrir la vista de pantalla completa." });
    }
  };
  const saveNotes = (value: string) => {
    setNotes(value);
    try { sessionStorage.setItem(storageKey(run.id), value); } catch { /* Las notas siguen en memoria. */ }
  };
  const prepare = (value: string, source: string) => {
    if (!value.trim()) { setNotice({ kind: "error", message: `${source} está vacío.` }); return; }
    setCandidate(value.trim()); setNotice({ kind: "success", message: "Texto listo para enviar. La validación se realiza en el backend." });
  };
  const pasteFlag = async () => {
    try { prepare(await navigator.clipboard.readText(), "El portapapeles"); }
    catch { setNotice({ kind: "error", message: "Pega directamente en el campo de flag con Ctrl+V o el menú del navegador." }); }
  };
  const copyFlag = async () => {
    if (!candidate.trim()) { setNotice({ kind: "error", message: "Primero prepara una flag para copiarla." }); return; }
    try { await navigator.clipboard.writeText(candidate.trim()); setNotice({ kind: "success", message: "Flag copiada al portapapeles." }); }
    catch { setNotice({ kind: "error", message: "No se pudo copiar automáticamente. Selecciona el campo y usa Ctrl+C." }); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!candidate.trim()) { setNotice({ kind: "error", message: "Pega una flag antes de enviarla." }); return; }
    setSubmitting(true); setNotice(null);
    try {
      const response = await onSubmit(run.challenge_code, candidate.trim());
      setResult(response); setNotice({ kind: response.correct ? "success" : "error", message: response.message });
    } catch (error) { setNotice({ kind: "error", message: error instanceof Error ? error.message : "No se pudo validar la flag." }); }
    finally { setSubmitting(false); }
  };
  const close = async () => {
    setClosing(true); setNotice(null);
    try { await onClose(run.id); sessionStorage.removeItem(storageKey(run.id)); }
    catch (error) { setNotice({ kind: "error", message: error instanceof Error ? error.message : "No se pudo limpiar. Conservamos la corrida para reintentar." }); }
    finally { setClosing(false); }
  };
  return <article className="laboratory-run-workspace" ref={workspaceRef}>
    <header className="laboratory-run-heading">
      <div><span className="eyebrow accent">LABORATORIO ASIGNADO</span><h2>{run.target_vm_name || run.challenge_code}</h2>
        <p>{run.challenge_code} · Conexión remota · Disponible hasta {new Date(run.expires_at).toLocaleString("es-ES")}</p></div>
      <div className="laboratory-run-heading-actions">
        <span className={`laboratory-state ${expired ? "pending" : "connected"}`}><span className="status-dot" />{expired ? "Tiempo agotado" : "Instancia reservada"}</span>
        <button type="button" className="secondary-action lab-fullscreen-action" aria-pressed={fullscreen} onClick={() => void toggleFullscreen()}>{fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}</button>
      </div>
    </header>
    <div className="laboratory-workspace-grid">
      {expired ? <section className="embedded-terminal-panel terminal-integration-notice"><h3>El laboratorio ha expirado</h3><p>La conexión remota se desconectó. La evidencia dinámica se limpia cuando corresponde; puedes reintentar el cierre si aparece un error.</p></section>
        : <GuacamoleTerminal key={run.id} runId={run.id} preferredProtocol={run.target_protocol} attackerOnly={run.challenge_code === "ESC-01-RECON"} onClipboard={(text) => { setSelection(text); setNotice({ kind: "success", message: "Selección recibida de la conexión. Pulsa Usar selección para preparar el envío." }); }} />}
      <form className="laboratory-flag-workspace" onSubmit={submit}>
        <div><span className="eyebrow accent">BLOC DE NOTAS Y FLAG</span><h3>Investiga, copia y valida</h3><p>Notas privadas de esta pestaña. Se eliminan al cerrar la corrida o salir de tu cuenta.</p></div>
        <label className="lab-notes-label" htmlFor={`lab-notes-${run.id}`}>Notas del laboratorio</label>
        <textarea id={`lab-notes-${run.id}`} className="lab-notebook" value={notes} onChange={(event) => saveNotes(event.target.value)} placeholder="Anota comandos y evidencias. Puedes pegar aquí la flag…" />
        {selection && <div className="terminal-clipboard-preview"><label htmlFor={`lab-selection-${run.id}`}>Selección recibida de la terminal</label>
          <textarea id={`lab-selection-${run.id}`} readOnly value={selection} />
          <button type="button" className="secondary-action" onClick={() => prepare(selection, "La selección")}>Usar selección</button></div>}
        <div className="lab-flag-actions">
          <button type="button" className="secondary-action" onClick={() => void pasteFlag()}>Pegar flag</button>
          <button type="button" className="secondary-action" onClick={() => prepare(notes, "El bloc")}>Usar notas</button>
          <button type="button" className="secondary-action" disabled={!candidate.trim()} onClick={() => void copyFlag()}>Copiar flag</button>
        </div>
        <label className="lab-notes-label" htmlFor={`lab-flag-${run.id}`}>Flag lista para enviar</label>
        <input id={`lab-flag-${run.id}`} className="lab-flag-candidate" value={candidate} onChange={(event) => setCandidate(event.target.value)} aria-describedby={candidate.length > 32 ? `lab-flag-preview-${run.id}` : undefined} autoComplete="off" spellCheck={false} placeholder="Pega la flag encontrada; no necesitas volver a escribirla" />
        {candidate.length > 32 && <div className="lab-flag-preview" id={`lab-flag-preview-${run.id}`} tabIndex={0}><span>Vista completa de la flag</span><code>{candidate}</code></div>}
        <button className="primary-action laboratory-submit-flag" disabled={submitting || closing || expired || !candidate.trim()}><Icon name="flag" />{submitting ? "Validando…" : "Enviar flag"}</button>
        {notice && <p className={`laboratory-feedback ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.message}</p>}
        {result?.challenge_completed && <p className="laboratory-completion">Reto completado · +{result.awarded_points} pts</p>}
      </form>
    </div>
    <footer className="laboratory-run-footer"><span>Al cerrar se desconecta el acceso; la evidencia dinámica se limpia automáticamente cuando corresponde.</span>
      <button type="button" className="table-action danger" disabled={closing || submitting} onClick={() => void close()}>{closing ? "Cerrando laboratorio…" : "Cerrar laboratorio"}</button>
    </footer>
  </article>;
}
