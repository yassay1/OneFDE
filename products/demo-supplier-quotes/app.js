/* global QuoteCompare */
(function () {
  const fileInput = document.getElementById("file");
  const runBtn = document.getElementById("run");
  const exportAll = document.getElementById("export-all");
  const exportPending = document.getElementById("export-pending");
  const tableBody = document.querySelector("#result tbody");
  const summary = document.getElementById("summary");
  const limitations = document.getElementById("limitations");
  const versionLabel = document.getElementById("version");

  let last = null;

  versionLabel.textContent = "v1.1（同 Task 修改：待核对单独导出）";

  function render(result) {
    last = result;
    tableBody.innerHTML = "";
    for (const row of result.rows) {
      const tr = document.createElement("tr");
      tr.className = row.status;
      tr.innerHTML = [
        row.supplier,
        row.product,
        row.grade,
        row.spec,
        row.unit,
        row.unit_price_raw,
        row.status,
        row.reason,
        row.is_lowest_in_group ? "是（组内）" : "",
      ]
        .map((c) => "<td>" + escapeHtml(c) + "</td>")
        .join("");
      tableBody.appendChild(tr);
    }
    summary.textContent =
      "可比较 " +
      result.comparable.length +
      " 行 · 待核对 " +
      result.pending.length +
      " 行 · 同口径单家 " +
      result.incomparable.length +
      " 行";
    limitations.textContent = result.limitations;
    exportAll.disabled = false;
    exportPending.disabled = result.pending.length === 0;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function download(name, text) {
    const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }

  runBtn.addEventListener("click", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      summary.textContent = "请先选择 CSV 文件";
      return;
    }
    try {
      const text = await file.text();
      const rows = QuoteCompare.parseCsv(text);
      render(QuoteCompare.classify(rows));
    } catch (err) {
      summary.textContent = String(err.message || err);
      tableBody.innerHTML = "";
      last = null;
      exportAll.disabled = true;
      exportPending.disabled = true;
    }
  });

  exportAll.addEventListener("click", () => {
    if (!last) return;
    download("quote-result.csv", QuoteCompare.toCsv(last.rows));
  });

  exportPending.addEventListener("click", () => {
    if (!last || !last.pending.length) return;
    download("quote-pending.csv", QuoteCompare.toCsv(last.pending));
  });
})();
