/**
 * Deterministic quote comparison for P0 CSV rules (R01—R05).
 * No freight/MOQ/delivery; never auto-select a supplier.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.QuoteCompare = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const REQUIRED = [
    "supplier",
    "product",
    "grade",
    "spec",
    "unit",
    "unit_price",
    "currency",
    "note",
  ];

  function parseCsv(text) {
    const lines = String(text)
      .replace(/^\uFEFF/, "")
      .split(/\r?\n/)
      .filter((line) => line.trim().length > 0);
    if (lines.length < 2) {
      throw new Error("CSV 至少需要表头与一行数据");
    }
    const header = splitCsvLine(lines[0]);
    for (const name of REQUIRED) {
      if (!header.includes(name)) {
        throw new Error("缺少列: " + name);
      }
    }
    return lines.slice(1).map((line, index) => {
      const cells = splitCsvLine(line);
      const row = { _line: index + 2 };
      header.forEach((key, i) => {
        row[key] = cells[i] === undefined ? "" : cells[i];
      });
      return row;
    });
  }

  function splitCsvLine(line) {
    const out = [];
    let cur = "";
    let quoted = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else if (ch === '"') {
          quoted = false;
        } else {
          cur += ch;
        }
      } else if (ch === '"') {
        quoted = true;
      } else if (ch === ",") {
        out.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out;
  }

  function parsePrice(value) {
    if (value === null || value === undefined || String(value).trim() === "") {
      return { ok: false, reason: "unit_price 为空" };
    }
    const n = Number(String(value).trim());
    if (!Number.isFinite(n) || n < 0) {
      return { ok: false, reason: "unit_price 不是有效非负数字" };
    }
    return { ok: true, value: n };
  }

  function basisKey(row) {
    return [row.product, row.grade, row.spec, row.unit].join("\u0001");
  }

  function classify(rows) {
    const annotated = rows.map((row) => {
      const price = parsePrice(row.unit_price);
      const base = {
        supplier: row.supplier,
        product: row.product,
        grade: row.grade,
        spec: row.spec,
        unit: row.unit,
        unit_price_raw: row.unit_price,
        currency: row.currency || "",
        note: row.note || "",
        line: row._line,
      };
      if (!row.product || !row.grade || !row.spec || !row.unit || !row.supplier) {
        return {
          ...base,
          status: "pending",
          reason: "缺少商品/等级/规格/单位/供应商",
          group_id: null,
          unit_price: null,
          is_lowest_in_group: false,
        };
      }
      if (!price.ok) {
        return {
          ...base,
          status: "pending",
          reason: price.reason,
          group_id: null,
          unit_price: null,
          is_lowest_in_group: false,
        };
      }
      if (String(row.unit).trim() !== "kg") {
        return {
          ...base,
          status: "pending",
          reason: "P0 仅比较 unit=kg；当前单位无法在未确认换算表下比较",
          group_id: null,
          unit_price: price.value,
          is_lowest_in_group: false,
        };
      }
      if (String(row.currency || "CNY").trim() !== "CNY") {
        return {
          ...base,
          status: "pending",
          reason: "P0 不做汇率换算；非 CNY 待核对",
          group_id: null,
          unit_price: price.value,
          is_lowest_in_group: false,
        };
      }
      return {
        ...base,
        status: "comparable_candidate",
        reason: "",
        group_id: basisKey(row),
        unit_price: price.value,
        is_lowest_in_group: false,
      };
    });

    const groups = new Map();
    for (const item of annotated) {
      if (item.status !== "comparable_candidate") continue;
      if (!groups.has(item.group_id)) groups.set(item.group_id, []);
      groups.get(item.group_id).push(item);
    }

    const comparable = [];
    const pending = [];
    const singles = [];

    for (const item of annotated) {
      if (item.status === "pending") {
        pending.push(item);
        continue;
      }
      const peers = groups.get(item.group_id) || [];
      if (peers.length < 2) {
        item.status = "incomparable";
        item.reason = "同口径仅一家报价，无可比对象（不跨等级/规格合并）";
        item.is_lowest_in_group = false;
        singles.push(item);
        continue;
      }
      const min = Math.min(...peers.map((p) => p.unit_price));
      item.status = "comparable";
      item.reason = "同商品/等级/规格/单位(kg)可比较";
      item.is_lowest_in_group = item.unit_price === min;
      comparable.push(item);
    }

    return {
      rows: [...comparable, ...singles, ...pending],
      comparable,
      pending,
      incomparable: singles,
      limitations:
        "结果仅为约定口径下的单位报价比较；未计入运费、起订量、送货条件；不自动采购或选定供应商。",
    };
  }

  function toCsv(rows) {
    const cols = [
      "supplier",
      "product",
      "grade",
      "spec",
      "unit",
      "unit_price",
      "currency",
      "note",
      "status",
      "reason",
      "is_lowest_in_group",
    ];
    const escape = (v) => {
      const s = v === null || v === undefined ? "" : String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const lines = [cols.join(",")];
    for (const row of rows) {
      lines.push(
        cols
          .map((c) => {
            if (c === "unit_price") return escape(row.unit_price_raw ?? row.unit_price);
            if (c === "is_lowest_in_group") return escape(row.is_lowest_in_group);
            return escape(row[c]);
          })
          .join(",")
      );
    }
    return lines.join("\n") + "\n";
  }

  return { REQUIRED, parseCsv, classify, toCsv };
});
