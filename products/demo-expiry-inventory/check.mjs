import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const {analyzeInventory,exportInventory}=createRequire(import.meta.url)('./expiry.js');
const csv=readFileSync(new URL('./inventory.csv',import.meta.url),'utf8');
const items=analyzeInventory(csv,'2026-01-30');
assert.deepEqual(items.map(r=>[r.product,r.batch,r.expires,r.quantity,r.status,r.sourceLine]),[
  ['酸奶','Y1','2026-01-29','2','expired',2],
  ['酸奶','Y2','2026-01-30','3','today',3],
  ['面包','B1','2026-01-31','1','soon',4],
  ['奶酪','C1','2026-02-02','5','soon',5],
  ['果汁','J1','2026-02-03','4','later',6],
  ['牛奶','M1','2026-02-30','6','review',7],
  ['豆乳','S1','','7','review',8],
  ['果酱,原味','G1','2026-02-01','8','soon',9],
]);
assert.equal(analyzeInventory(csv.replace('2026-01-30,3','2026/01/30,3'),'2026-01-30')[1].status,'review');
assert.deepEqual(analyzeInventory('\ufeff'+csv.replaceAll('\n','\r\n'),'2026-01-30'),items);
assert.throws(()=>analyzeInventory(csv,'2026-02-30'));
assert.throws(()=>analyzeInventory(csv.replace('到期日','日期'),'2026-01-30'));
assert.deepEqual(exportInventory(items).replace(/^\ufeff/,'').trimEnd().split(/\r?\n/),[
  '商品,批次,到期日,数量,状态',
  '酸奶,Y1,2026-01-29,2,已过期',
  '酸奶,Y2,2026-01-30,3,今日到期',
  '面包,B1,2026-01-31,1,临期',
  '奶酪,C1,2026-02-02,5,临期',
  '"果酱,原味",G1,2026-02-01,8,临期',
]);
console.log('PASS: 8 batches, month boundary, invalid/missing/slash dates, BOM and CRLF, quoted CSV and 5 export rows');
