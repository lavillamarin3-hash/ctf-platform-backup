import { useState } from 'react';
import type { Run } from '../../api';
import { GuacamoleTerminal } from './GuacamoleTerminal';

export function KaliPanel({run,command}:{run:Run;command?:string}) {
  const [message,setMessage]=useState('');
  if(run.target_vm_name!=='LAB-KALI') return <p role="status">Este reto necesita acceso a Kali. Solicita al instructor que habilite la máquina para continuar con las evidencias.</p>;
  return <section style={{margin:'1rem 0'}} aria-label="Máquina Kali del ejercicio">
    <h3>Trabaja en Kali · 192.168.146.134</h3>
    {command && <>
      <p>Copia el comando y pégalo en la terminal de Kali. Preparará los archivos en <code>~/ctf/corrida-{run.id}</code>. Después entra a esa carpeta con <code>cd ~/ctf/corrida-{run.id}</code>.</p>
      <button type="button" className="secondary-action" onClick={() => void navigator.clipboard.writeText(command).then(()=>setMessage('Comando copiado. Pégalo en la terminal Kali y pulsa Enter.')).catch(()=>setMessage('Selecciona el comando de abajo y cópialo con Ctrl+C.'))}>Copiar comando para preparar archivos</button>
      <details className="challenge-accordion"><summary>Ver comando de preparación</summary><textarea readOnly aria-label="Comando de preparación de archivos" value={command} style={{width:'100%',height:'6rem'}} /></details>
    </>}
    {message && <p role="status">{message}</p>}
    <p>La terminal usa tu cuenta de laboratorio. Si solicita acceso, introduce tu contraseña de la plataforma. Kali es compartida; utiliza la carpeta de tu corrida.</p>
    <GuacamoleTerminal runId={run.id} preferredProtocol="ssh" workspaceName="Kali" onClipboard={()=>{}} />
  </section>;
}
