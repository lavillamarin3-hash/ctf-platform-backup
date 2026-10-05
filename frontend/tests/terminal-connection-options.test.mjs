import assert from "node:assert/strict";
import { test } from "node:test";
import { selectTerminalConnection } from "../src/lib/terminalConnectionOptions.ts";

test("ESC-01 abre Kali aunque la víctima no ofrezca protocolos", () => {
  const result = selectTerminalConnection({ protocols: [], attacker_protocols: ["rdp", "ssh"] }, "ssh", true);
  assert.equal(result.target, "attacker");
  assert.equal(result.protocol, "ssh");
  assert.deepEqual(result.victimProtocols, []);
  assert.deepEqual(result.attackerProtocols, ["ssh", "rdp"]);
});

test("ESC-01 no recae en la víctima cuando Kali no está disponible", () => {
  const result = selectTerminalConnection({ protocols: ["ssh"], attacker_protocols: [] }, "ssh", true);
  assert.equal(result.target, "attacker");
  assert.equal(result.protocol, null);
});

test("LAB-01 mantiene su protocolo de la víctima", () => {
  const result = selectTerminalConnection({ protocols: ["rdp", "ssh"], attacker_protocols: [] }, "rdp", false);
  assert.equal(result.target, "victim");
  assert.equal(result.protocol, "rdp");
});
