/* 果采报价台 — 界面逻辑，复用 window.QuoteCompare 比较口径 */
(function () {
  "use strict";

  // 与 samples/s05-mixed.csv 保持一致的模拟示例（内嵌以便 file:// 直接打开）
  const SAMPLE_CSV = [
    "supplier,product,grade,spec,unit,unit_price,currency,note",
    "示例供应商A,富士苹果,一级,净重明确按公斤报价,kg,8.0,CNY,模拟-可比较",
    "示例供应商B,富士苹果,一级,净重明确按公斤报价,kg,7.5,CNY,模拟-可比较",
    "示例供应商A,蜜桔,一级,盒装未标明净重,box,25.0,CNY,模拟-待核对",
    "示例供应商B,蜜桔,一级,盒装未标明净重,box,22.0,CNY,模拟-待核对",
    "示例供应商A,香蕉,一级,把装,kg,6.0,CNY,模拟-不同等级",
    "示例供应商B,香蕉,二级,把装,kg,5.0,CNY,模拟-不同等级",
  ].join("\n");

  const TEMPLATE_CSV = [
    "supplier,product,grade,spec,unit,unit_price,currency,note",
    "示例供应商A,富士苹果,一级,净重明确按公斤报价,kg,8.0,CNY,可比较",
    "示例供应商B,蜜桔,一级,盒装未标明净重,box,25.0,CNY,箱价待核对",
  ].join("\n");

  const STATUS_LABEL = {
    comparable: "比较",
    pending: "待核对",
    incomparable: "无可比对象",
    comparable_candidate: "比较",
  };

  const SOURCE_LABEL = {
    sample: "模拟示例",
    import: "导入文件",
    paste: "粘贴数据",
  };

  const els = {
    loadSample: document.getElementById("loadSample"),
    csvInput: document.getElementById("csvInput"),
    compareBtn: document.getElementById("compareBtn"),
    csvFile: document.getElementById("csvFile"),
    searchInput: document.getElementById("searchInput"),
    statusFilter: document.getElementById("statusFilter"),
    clearFilters: document.getElementById("clearFilters"),
    exportAll: document.getElementById("exportAll"),
    exportPending: document.getElementById("exportPending"),
    templateBtn: document.getElementById("templateBtn"),
    resultTable: document.getElementById("resultTable"),
    resultBody: document.getElementById("resultBody"),
    counts: document.getElementById("counts"),
    feedback: document.getElementById("feedback"),
    samplePreview: document.getElementById("samplePreview"),
    sampleLabel: document.getElementById("sampleLabel"),
    notice: document.getElementById("notice"),
    sourceBadge: document.getElementById("sourceBadge"),
  };

  let currentResult = null;

  function setSource(source, detail) {
    if (els.sourceBadge) {
      els.sourceBadge.textContent =
        SOURCE_LABEL[source] + (detail ? "（" + detail + "）" : "");
    }
    if (els.samplePreview) {
      els.samplePreview.hidden = source !== "sample";
    }
    if (els.sampleLabel) {
      els.sampleLabel.hidden = source !== "sample";
    }
  }

  function setFeedback(message, ok) {
    els.feedback.textContent = message;
    els.feedback.className = "feedback " + (ok ? "ok" : "err");
  }

  function clearResults() {
    currentResult = null;
    els.resultBody.textContent = "";
    els.counts.textContent = "";
  }

  function td(tr, text, className) {
    const cell = document.createElement("td");
    cell.textContent = text === null || text === undefined ? "" : String(text);
    if (className) cell.className = className;
    tr.appendChild(cell);
    return cell;
  }

  function render() {
    els.resultBody.textContent = "";
    if (!currentResult) {
      els.counts.textContent = "";
      return;
    }
    const keyword = els.searchInput.value.trim().toLowerCase();
    const status = els.statusFilter.value;

    const visible = currentResult.rows.filter(function (row) {
      if (status && row.status !== status) return false;
      if (!keyword) return true;
      return (
        String(row.supplier).toLowerCase().indexOf(keyword) >= 0 ||
        String(row.product).toLowerCase().indexOf(keyword) >= 0
      );
    });

    const groupMin = new Map();
    currentResult.rows.forEach(function (row) {
      if (row.status === "comparable" && row.group_id !== null) {
        const prev = groupMin.get(row.group_id);
        if (prev === undefined || row.unit_price < prev) {
          groupMin.set(row.group_id, row.unit_price);
        }
      }
    });

    visible.forEach(function (row) {
      const tr = document.createElement("tr");
      td(tr, row.supplier);
      td(tr, row.product);
      td(tr, row.grade);
      td(tr, row.spec);
      td(tr, row.unit);

      const priceText =
        row.unit_price_raw !== undefined && row.unit_price_raw !== ""
          ? String(row.unit_price_raw)
          : row.unit_price === null
            ? ""
            : String(row.unit_price);
      td(tr, priceText, "price-cell");
      td(tr, row.currency);

      const statusCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge badge-" + row.status;
      badge.textContent = STATUS_LABEL[row.status] || row.status;
      statusCell.appendChild(badge);
      tr.appendChild(statusCell);

      const cmpCell = document.createElement("td");
      const chip = document.createElement("span");
      if (row.status === "comparable") {
        const min = groupMin.get(row.group_id);
        if (row.is_lowest_in_group) {
          chip.className = "chip chip-low";
          chip.textContent = "同口径最低价 " + String(row.unit_price_raw);
        } else {
          chip.className = "chip chip-none";
          chip.textContent = "最低价 " + String(min) + "（本行 " + String(row.unit_price_raw) + "）";
        }
      } else if (row.status === "incomparable") {
        chip.className = "chip chip-none";
        chip.textContent = "无可比对象";
      } else {
        chip.className = "chip chip-na";
        chip.textContent = "不参与比较";
      }
      cmpCell.appendChild(chip);
      tr.appendChild(cmpCell);

      td(tr, row.reason);
      td(tr, row.note);

      els.resultBody.appendChild(tr);
    });

    const rows = currentResult.rows;
    els.counts.textContent =
      "共 " +
      rows.length +
      " 行 · 比较 " +
      currentResult.comparable.length +
      " · 待核对 " +
      currentResult.pending.length +
      " · 无可比对象 " +
      currentResult.incomparable.length +
      (visible.length !== rows.length ? " · 当前显示 " + visible.length + " 行（筛选不影响导出）" : "");
  }

  function runComparison(text, source, detail) {
    try {
      const rows = window.QuoteCompare.parseCsv(text);
      currentResult = window.QuoteCompare.classify(rows);
      setSource(source, detail);
      render();
      const sourceNote =
        source === "sample"
          ? "（模拟数据仅用于演示）"
          : "（来源：" + SOURCE_LABEL[source] + "）";
      setFeedback("比较完成，共 " + currentResult.rows.length + " 行结果" + sourceNote + "。", true);
    } catch (err) {
      clearResults();
      render();
      setFeedback("CSV 解析失败：" + (err && err.message ? err.message : String(err)) + "。已清空旧结果，请修正后重试。", false);
    }
  }

  function resetFilters() {
    els.searchInput.value = "";
    els.statusFilter.value = "";
  }

  function loadSample() {
    resetFilters();
    els.csvInput.value = SAMPLE_CSV;
    els.samplePreview.textContent = SAMPLE_CSV;
    runComparison(SAMPLE_CSV, "sample");
    setFeedback("已载入模拟示例（6 行，非真实供应商报价）。", true);
  }

  function download(filename, text) {
    const blob = new Blob(["\uFEFF" + text], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function exportAll() {
    if (!currentResult) {
      setFeedback("暂无结果可导出，请先载入示例或比较 CSV。", false);
      return;
    }
    download("果采报价台-全部结果.csv", window.QuoteCompare.toCsv(currentResult.rows));
    setFeedback("已导出全部结果 CSV（含全部输入行，UTF-8 BOM）。", true);
  }

  function exportPending() {
    if (!currentResult) {
      setFeedback("暂无结果可导出，请先载入示例或比较 CSV。", false);
      return;
    }
    const rows = currentResult.rows.filter(function (row) {
      return row.status === "pending" || row.status === "incomparable";
    });
    download("果采报价台-需核对报价.csv", window.QuoteCompare.toCsv(rows));
    setFeedback("已导出需核对报价 CSV（待核对 + 无可比对象，共 " + rows.length + " 行）。", true);
  }

  function onFileChange(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function () {
      els.csvInput.value = String(reader.result || "");
      runComparison(els.csvInput.value, "import", file.name);
      setFeedback("已导入文件 " + file.name + " 并完成比较（来源：导入文件，非模拟示例）。", true);
    };
    reader.onerror = function () {
      clearResults();
      render();
      setFeedback("文件读取失败，请确认为 UTF-8 编码 CSV。", false);
    };
    reader.readAsText(file, "utf-8");
    event.target.value = "";
  }

  els.loadSample.addEventListener("click", loadSample);
  els.compareBtn.addEventListener("click", function () {
    const text = els.csvInput.value.trim();
    if (!text) {
      clearResults();
      render();
      setFeedback("请先粘贴 CSV 文本或选择文件，或点击「载入模拟示例」。", false);
      return;
    }
    runComparison(text, "paste");
    setFeedback("已按粘贴数据完成比较（来源：粘贴数据，非模拟示例）。", true);
  });
  els.csvFile.addEventListener("change", onFileChange);
  els.searchInput.addEventListener("input", render);
  els.statusFilter.addEventListener("change", render);
  els.clearFilters.addEventListener("click", function () {
    resetFilters();
    render();
  });
  els.exportAll.addEventListener("click", exportAll);
  els.exportPending.addEventListener("click", exportPending);
  els.templateBtn.addEventListener("click", function () {
    download("果采报价台-CSV模板.csv", TEMPLATE_CSV);
    setFeedback("已下载 CSV 模板（UTF-8 BOM，八列）。", true);
  });

  // 启动时载入模拟示例
  loadSample();
})();
