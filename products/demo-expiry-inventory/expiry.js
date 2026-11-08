(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.Expiry = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const HEADER = ['商品', '批次', '到期日', '数量'];
  const STATUS_LABELS = {
    expired: '已过期',
    today: '今日到期',
    soon: '临期',
    later: '其余',
    review: '待核对',
  };
  const EXPORT_STATUSES = ['expired', 'today', 'soon'];

  function parseCsv(text) {
    const src = String(text).replace(/^\ufeff/, '');
    const records = [];
    let fields = [];
    let field = '';
    let inQuotes = false;
    let line = 1;
    let recordLine = 1;
    let i = 0;
    while (i < src.length) {
      const ch = src[i];
      if (inQuotes) {
        if (ch === '"') {
          if (src[i + 1] === '"') {
            field += '"';
            i += 2;
            continue;
          }
          inQuotes = false;
          i += 1;
          continue;
        }
        if (ch === '\n') line += 1;
        field += ch;
        i += 1;
        continue;
      }
      if (ch === '"') {
        inQuotes = true;
        i += 1;
        continue;
      }
      if (ch === ',') {
        fields.push(field);
        field = '';
        i += 1;
        continue;
      }
      if (ch === '\r' || ch === '\n') {
        fields.push(field);
        records.push({ fields, line: recordLine });
        fields = [];
        field = '';
        if (ch === '\r' && src[i + 1] === '\n') i += 1;
        i += 1;
        line += 1;
        recordLine = line;
        continue;
      }
      field += ch;
      i += 1;
    }
    if (inQuotes) throw new Error('CSV 引号未闭合');
    if (field !== '' || fields.length > 0) {
      fields.push(field);
      records.push({ fields, line: recordLine });
    }
    return records;
  }

  function parseDate(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    if (mo < 1 || mo > 12 || d < 1) return null;
    const daysInMonth = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    if (d > daysInMonth) return null;
    return Date.UTC(y, mo - 1, d);
  }

  const DAY = 86400000;

  function analyzeInventory(text, asOf) {
    const base = parseDate(String(asOf == null ? '' : asOf).trim());
    if (base === null) throw new Error('基准日无效，需为 YYYY-MM-DD');
    const records = parseCsv(text);
    if (records.length === 0) throw new Error('CSV 为空');
    const header = records[0].fields.map((f) => f.trim());
    if (header.length !== HEADER.length || HEADER.some((h, idx) => header[idx] !== h)) {
      throw new Error('CSV 表头必须为 商品,批次,到期日,数量');
    }
    const rows = [];
    for (let r = 1; r < records.length; r += 1) {
      const rec = records[r];
      const f = rec.fields;
      if (f.length === 1 && f[0].trim() === '') continue;
      const product = f[0] == null ? '' : f[0];
      const batch = f[1] == null ? '' : f[1];
      const expires = f[2] == null ? '' : f[2];
      const quantity = f[3] == null ? '' : f[3];
      const date = expires.trim() === '' ? null : parseDate(expires.trim());
      let status;
      if (date === null) {
        status = 'review';
      } else {
        const diff = Math.round((date - base) / DAY);
        if (diff < 0) status = 'expired';
        else if (diff === 0) status = 'today';
        else if (diff <= 3) status = 'soon';
        else status = 'later';
      }
      rows.push({ product, batch, expires, quantity, status, sourceLine: rec.line });
    }
    return rows;
  }

  function csvField(value) {
    const s = value == null ? '' : String(value);
    if (/[",\r\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function exportInventory(rows) {
    const lines = [HEADER.concat('状态').map(csvField).join(',')];
    for (const row of rows || []) {
      if (!EXPORT_STATUSES.includes(row.status)) continue;
      lines.push(
        [row.product, row.batch, row.expires, row.quantity, STATUS_LABELS[row.status]]
          .map(csvField)
          .join(',')
      );
    }
    return '\ufeff' + lines.join('\r\n') + '\r\n';
  }

  return { analyzeInventory, exportInventory, STATUS_LABELS };
});
