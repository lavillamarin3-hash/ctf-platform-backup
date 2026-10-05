import assert from "node:assert/strict";
import { test } from "node:test";
import { BEGINNER_CHALLENGE_DRAFTS, isLegacyReconDraft, legacyPublishedCodes } from "../src/lib/pilotChallenges.ts";

test("legacy cleanup preserves LAB-01 and already inactive history", () => {
  assert.deepEqual(legacyPublishedCodes([
    { code: "LAB-01", is_published: true },
    { code: "OLD-01", is_published: true },
    { code: "OLD-02", is_published: false },
  ]), ["OLD-01"]);
});

test("beginner drafts are unpublished, dynamic, and target the confirmed victim", () => {
  assert.equal(BEGINNER_CHALLENGE_DRAFTS.length, 3);
  for (const item of BEGINNER_CHALLENGE_DRAFTS) {
    assert.equal(item.challenge.is_published, false);
    assert.equal(item.challenge.asset_references[0], "LAB-LNXVICT");
    assert.ok(item.challenge.asset_references.every((ref) => ["LAB-LNXVICT", "LAB-KALI"].includes(ref)));
    assert.equal(item.flag.mode, "dynamic");
    assert.equal(item.flag.flag_order, 1);
    assert.ok(item.flag.template.includes("{{USER}}"));
    assert.ok(item.flag.template.includes("{{RUN_ID}}"));
    assert.ok(item.flag.template.includes("{{RAND}}"));
  }
});

test("only the exact old reconnaissance seed may be upgraded without overwriting custom work", () => {
  const seed = {
    code: "ESC-01-RECON", is_published: false, scenario: "ESC-01-RECON",
    asset_references: ["LAB-LNXVICT", "192.168.146.137"],
    flags: [{ mode: "dynamic", template: "FLAG{esc-01_{{USER}}_{{RUN_ID}}_{{RAND}}}" }],
  };
  assert.equal(isLegacyReconDraft(seed), true);
  assert.equal(isLegacyReconDraft({ ...seed, is_published: true }), false);
  assert.equal(isLegacyReconDraft({ ...seed, asset_references: ["LAB-LNXVICT", "LAB-KALI"] }), false);
  assert.equal(isLegacyReconDraft({ ...seed, flags: [{ mode: "static" }] }), false);
});
