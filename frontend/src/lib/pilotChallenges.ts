import type { Challenge } from "../models";

type ChallengeDraft = Omit<Challenge, "id" | "completed" | "flag_count" | "flags">;

/** Borradores de práctica: no se publican ni asignan sin aceptación física. */
export const BEGINNER_CHALLENGE_DRAFTS: ReadonlyArray<{
  challenge: ChallengeDraft;
  flag: { label: string; mode: "dynamic"; template: string; flag_order: number; is_active: true };
}> = [
  {
    challenge: {
      code: "CTF-LNX-02",
      name: "Explora la carpeta de práctica",
      description: "Practica navegación y lectura de archivos en la máquina Linux asignada.",
      instructions: "Inicia el laboratorio y abre SSH de la VM víctima. Comprueba dónde estás con pwd, lista /opt/ctf y lee el archivo flag.txt. Copia la evidencia con el botón del reto, envíala y cierra el laboratorio. Trabaja solo en la VM asignada.",
      difficulty: "Básico",
      category: "MISC",
      scenario: "LINUX-BASICO",
      mitre_technique: "T1083 — File and Directory Discovery",
      asset_references: ["LAB-LNXVICT"],
      points: 100,
      is_published: false,
    },
    flag: { label: "Evidencia dinámica de archivos", mode: "dynamic", template: "FLAG{ctf-lnx-02_{{USER}}_{{RUN_ID}}_{{RAND}}}", flag_order: 1, is_active: true },
  },
  {
    challenge: {
      code: "CTF-LNX-03",
      name: "Reconoce el servicio SSH",
      description: "Observa el servicio SSH de la máquina Linux y encuentra la evidencia de la corrida.",
      instructions: "Inicia el laboratorio y abre SSH de la VM víctima. Ejecuta ss -ltn para identificar el puerto SSH local. Después localiza la evidencia de práctica en /opt/ctf/flag.txt, cópiala, envíala y cierra el laboratorio. La flag valida el hallazgo; la plataforma no califica los comandos ejecutados.",
      difficulty: "Básico",
      category: "MISC",
      scenario: "SSH-BASICO",
      mitre_technique: "T1046 — Network Service Scanning",
      asset_references: ["LAB-LNXVICT"],
      points: 100,
      is_published: false,
    },
    flag: { label: "Evidencia dinámica de SSH", mode: "dynamic", template: "FLAG{ctf-lnx-03_{{USER}}_{{RUN_ID}}_{{RAND}}}", flag_order: 1, is_active: true },
  },
  {
    challenge: {
      code: "ESC-01-RECON",
      name: "Reconocimiento Kali → Linux",
      description: "Desde la VM Kali identifica un servicio didáctico de la víctima Linux y recupera la evidencia dinámica de esta corrida.",
      instructions: "Este reto requiere que el instructor haya instalado y verificado el servicio didáctico de evidencia en la VM víctima. Inicia el laboratorio, abre la conexión de Kali atacante (.134) y examina solo 192.168.146.137:18081. Un escaneo acotado puede usar nmap -sT -Pn -p 22,18081 192.168.146.137. Recupera la evidencia de http://192.168.146.137:18081/evidence, cópiala, envíala y cierra el laboratorio. No explores otras IP ni puertos.",
      difficulty: "Básico",
      category: "MISC",
      scenario: "ESC-01-RECON",
      mitre_technique: "T1046 — Network Service Scanning",
      asset_references: ["LAB-LNXVICT", "LAB-KALI"],
      points: 100,
      is_published: false,
    },
    flag: { label: "Evidencia dinámica de reconocimiento", mode: "dynamic", template: "FLAG{esc-01_{{USER}}_{{RUN_ID}}_{{RAND}}}", flag_order: 1, is_active: true },
  },
];

export const PILOT_PUBLISHED_CODES = ["LAB-01"] as const;

/** Solo el seed antiguo exacto puede actualizarse automáticamente sin pisar un reto editado. */
export function isLegacyReconDraft(challenge: Challenge): boolean {
  return challenge.code === "ESC-01-RECON" && !challenge.is_published &&
    challenge.scenario === "ESC-01-RECON" &&
    challenge.asset_references.length === 2 &&
    challenge.asset_references[0] === "LAB-LNXVICT" &&
    challenge.asset_references[1] === "192.168.146.137" &&
    challenge.flags?.length === 1 && challenge.flags[0].mode === "dynamic" &&
    challenge.flags[0].template === "FLAG{esc-01_{{USER}}_{{RUN_ID}}_{{RAND}}}";
}

export function legacyPublishedCodes(challenges: ReadonlyArray<Pick<Challenge, "code" | "is_published">>): string[] {
  const keep = new Set<string>(PILOT_PUBLISHED_CODES);
  return challenges.filter((challenge) => challenge.is_published && !keep.has(challenge.code)).map((challenge) => challenge.code);
}
