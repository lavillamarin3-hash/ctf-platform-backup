export type TerminalProtocol = "ssh" | "rdp";
export type TerminalTarget = "victim" | "attacker";

type RawOptions = { protocols?: readonly string[]; attacker_protocols?: readonly string[] };

const supported = (values: readonly string[] = []): TerminalProtocol[] =>
  (["ssh", "rdp"] as const).filter((value) => values.includes(value));

/** ESC-01 solo puede abrir Kali; la VM víctima es el objetivo, no una terminal del alumno. */
export function selectTerminalConnection(options: RawOptions, preferred: string | null | undefined, attackerOnly: boolean) {
  const victimProtocols = supported(options.protocols);
  const attackerProtocols = supported(options.attacker_protocols);
  const target: TerminalTarget = attackerOnly || attackerProtocols.length > 0 ? "attacker" : "victim";
  const available = target === "attacker" ? attackerProtocols : victimProtocols;
  const protocol = available.includes(preferred as TerminalProtocol)
    ? preferred as TerminalProtocol
    : available[0] ?? null;
  return { victimProtocols, attackerProtocols, target, protocol };
}
