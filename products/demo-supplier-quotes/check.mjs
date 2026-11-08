#!/usr/bin/env node
/**
 * Deterministic acceptance for P0 samples against compare.js.
 * Exit 0 only when S01/S02/S03/S05 expectations hold.
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const QuoteCompare = require("./compare.js");

const samplesDir = path.resolve(
  __dirname,
  "../../engagements/demo-supplier-quotes/samples"
);

function load(name) {
  return QuoteCompare.parseCsv(
    fs.readFileSync(path.join(samplesDir, name), "utf8")
  );
}

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

function run() {
  // S01
  {
    const result = QuoteCompare.classify(load("s01-same-basis.csv"));
    assert(result.comparable.length === 2, "S01: expect 2 comparable rows");
    assert(result.pending.length === 0, "S01: no pending");
    const b = result.comparable.find((r) => r.supplier.includes("B"));
    const a = result.comparable.find((r) => r.supplier.includes("A"));
    assert(b && a, "S01: suppliers A/B present");
    assert(b.unit_price < a.unit_price, "S01: B cheaper than A");
    assert(b.is_lowest_in_group && !a.is_lowest_in_group, "S01: B lowest in group");
  }

  // S02
  {
    const result = QuoteCompare.classify(load("s02-missing-net-weight.csv"));
    assert(result.comparable.length === 0, "S02: no comparable");
    assert(result.pending.length === 2, "S02: both pending");
    assert(
      !result.rows.some((r) => r.is_lowest_in_group),
      "S02: must not pick lowest by box price"
    );
  }

  // S03
  {
    const result = QuoteCompare.classify(load("s03-different-grade.csv"));
    assert(result.comparable.length === 0, "S03: grades differ, not one comparable group");
    assert(
      result.incomparable.length === 2,
      "S03: each grade stays separate single-quote rows"
    );
    assert(
      !result.rows.some((r) => r.is_lowest_in_group),
      "S03: no cross-grade lowest price"
    );
  }

  // S05
  {
    const result = QuoteCompare.classify(load("s05-mixed.csv"));
    assert(result.comparable.length === 2, "S05: apple comparable");
    assert(result.pending.length === 2, "S05: mandarin pending");
    assert(result.incomparable.length === 2, "S05: banana grades separate");
    assert(result.rows.length === 6, "S05: no silent drop");
    const pendingText = QuoteCompare.toCsv(result.pending);
    assert(pendingText.includes("status"), "modification: export includes status");
    assert(pendingText.includes("pending"), "modification: pending export works");
  }

  if (process.argv.includes("--support-regression")) {
    const sample = fs.readFileSync(path.join(samplesDir, "s01-same-basis.csv"), "utf8");
    const input = sample.replace(",unit_price,", ",unit_price ,");
    assert(input !== sample, "support fixture: expected original price header");
    const result = QuoteCompare.classify(QuoteCompare.parseCsv(input));
    assert(result.comparable.length === 2 && result.pending.length === 0, "support fixture: both rows comparable");
    const [a, b] = result.comparable;
    assert(a.unit_price === 8 && b.unit_price === 7.5, "support fixture: preserve both prices");
    assert(!a.is_lowest_in_group && b.is_lowest_in_group, "support fixture: only B is lowest");
    const boundaryFailures = [];
    for (const [label, header, error] of [
      ["missing price header", "price", /缺少列: unit_price/],
      ["non-ASCII space", "unit_price\u00a0", /缺少列: unit_price/],
      ["normalized price collision", "unit_price ,unit_price", /冲突|重复/],
    ]) {
      let message = "";
      try {
        QuoteCompare.parseCsv(sample.replace(",unit_price,", "," + header + ","));
      } catch (err) {
        message = err.message;
      }
      if (!error.test(message)) boundaryFailures.push(label);
    }
    const duplicateNote = sample.replace(",currency,note", ",currency,note,note");
    assert(duplicateNote !== sample, "support fixture: expected original note header");
    try {
      const duplicateResult = QuoteCompare.classify(QuoteCompare.parseCsv(duplicateNote));
      if (duplicateResult.comparable.length !== 2) boundaryFailures.push("unrelated duplicate header");
    } catch {
      boundaryFailures.push("unrelated duplicate header");
    }
    assert(!boundaryFailures.length, "support fixture: " + boundaryFailures.join(", "));
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        product: "demo-supplier-quotes",
        version: "v1.1",
        checked: ["S01", "S02", "S03", "S05"],
        modification: "pending-only CSV export",
      },
      null,
      2
    )
  );
}

try {
  run();
} catch (err) {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
}
