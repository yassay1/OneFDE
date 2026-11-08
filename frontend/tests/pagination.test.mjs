import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

async function pagination(api) {
  const source = await readFile(new URL('../src/api/pagination.ts', import.meta.url), 'utf8');
  const context = vm.createContext({ document: { hidden: false }, Set, Error, encodeURIComponent });
  const dependency = new vm.SyntheticModule(['api'], function () { this.setExport('api', api); }, { context });
  const module = new vm.SourceTextModule(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText, { context });
  await module.link(() => dependency); await module.evaluate();
  return module.namespace;
}

test('keyset reads beyond the first page and encodes cursor, preserving abort signal', async () => {
  const signal = new AbortController().signal; const calls = [];
  const { readPages } = await pagination(async (url, options) => {
    calls.push(url); assert.equal(options.signal, signal);
    return calls.length === 1 ? { items: ['first'], next_cursor: 'a+/=' } : { items: ['last'], next_cursor: null };
  });
  const result = await readPages('/objects?owner=fde', signal);
  assert.deepEqual(Array.from(result.items), ['first', 'last']);
  assert.equal(calls[1], '/objects?owner=fde&limit=100&cursor=a%2B%2F%3D');
});

test('repeated keyset cursor fails instead of hanging or pretending complete', async () => {
  const { readPages } = await pagination(async () => ({ items: [], next_cursor: 'stuck' }));
  await assert.rejects(readPages('/objects'), /分页游标未推进/);
});

test('sequence reread refreshes already-seen input status after adoption', async () => {
  let adopted = false;
  const { readSequence } = await pagination(async url => url.endsWith('after_sequence=0')
    ? { items: [{ id: 'input-1', status: adopted ? 'applied' : 'pending' }], last_sequence: 1, has_more: true }
    : { items: [{ id: 'input-2', status: 'rejected' }], last_sequence: 2, has_more: false });
  assert.equal((await readSequence('/inputs')).items[0].status, 'pending');
  adopted = true;
  const result = await readSequence('/inputs');
  assert.equal(result.items[0].status, 'applied'); assert.equal(result.items.length, 2);
});

test('sequence watermarks must advance when more records are promised', async () => {
  const { readSequence } = await pagination(async () => ({ items: [], last_sequence: 0, has_more: true }));
  await assert.rejects(readSequence('/events'), /事件水位未推进/);
});

test('a failed later page rejects the whole read rather than showing partial success', async () => {
  let calls = 0;
  const { readPages } = await pagination(async () => {
    if (++calls === 2) throw new Error('503');
    return { items: ['partial'], next_cursor: 'second' };
  });
  await assert.rejects(readPages('/objects'), /503/);
});
