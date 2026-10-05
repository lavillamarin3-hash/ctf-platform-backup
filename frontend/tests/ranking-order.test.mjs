import assert from "node:assert/strict";
import { test } from "node:test";
import { topRankingRows } from "../src/lib/rankingOrder.ts";

test("respeta el desempate temporal y los puestos del servidor", () => {
  const rows = [
    { position: 3, username: "alice", total_points: 200, challenges_completed: 2 },
    { position: 2, username: "bob", total_points: 200, challenges_completed: 2 },
    { position: 4, username: "carol", total_points: 0, challenges_completed: 0 },
    { position: 1, username: "dave", total_points: 300, challenges_completed: 1 },
  ];
  const displayed = topRankingRows(rows);
  assert.deepEqual(displayed.map((row) => [row.position, row.username]), [
    [1, "dave"], [2, "bob"], [3, "alice"], [4, "carol"],
  ]);
  assert.deepEqual(rows.map((row) => row.username), ["alice", "bob", "carol", "dave"]);
});
