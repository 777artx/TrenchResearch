// GMGN collector: runs fetch() inside a headless Chromium page so Cloudflare lets
// the requests through. Usage: node collect.js jobs.json out.jsonl
// jobs: [{id, path, params:{...}, pages, cursor_key, stop_ts}]
// Each response is appended to out.jsonl as {id, url, status, fetched_at, body}.
const fs = require('fs');
const { chromium } = require('playwright');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36';
const PAUSE_MS = 1100; // polite: under one request per second

(async () => {
  const [jobsFile, outFile] = process.argv.slice(2);
  const jobs = JSON.parse(fs.readFileSync(jobsFile, 'utf8'));
  const out = fs.openSync(outFile, 'a');
  const browser = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined });
  const page = await browser.newPage({ userAgent: UA });
  let base = null;
  page.on('request', r => {
    if (base) return;
    const u = new URL(r.url());
    if (u.hostname === 'gmgn.ai' && u.searchParams.get('device_id')) {
      base = {};
      for (const k of ['device_id', 'tab_id', 'fp_did', 'client_id', 'from_app', 'app_ver',
                       'tz_name', 'tz_offset', 'app_lang', 'os']) base[k] = u.searchParams.get(k) || '';
    }
  });
  await page.goto('https://gmgn.ai/?chain=sol', { waitUntil: 'domcontentloaded', timeout: 60000 });
  for (let i = 0; i < 30 && !base; i++) await page.waitForTimeout(1000);
  if (!base) { console.error('FATAL: could not obtain GMGN session parameters'); process.exit(2); }

  let fails = 0;
  for (const job of jobs) {
    let cursor = null;
    for (let p = 0; p < (job.pages || 1); p++) {
      const u = new URL('https://gmgn.ai' + job.path);
      for (const [k, v] of Object.entries({ ...base, ...(job.params || {}) })) u.searchParams.set(k, v);
      if (cursor) u.searchParams.set('cursor', cursor);
      const res = await page.evaluate(async (x) => {
        try { const r = await fetch(x); return { status: r.status, text: await r.text() }; }
        catch (e) { return { status: 0, text: String(e) }; }
      }, u.toString());
      let body = null; try { body = JSON.parse(res.text); } catch (e) {}
      fs.writeSync(out, JSON.stringify({ id: job.id, url: u.pathname + u.search.replace(/device_id=[^&]+/, 'device_id=x'),
        status: res.status, fetched_at: new Date().toISOString(), body: body ?? res.text.slice(0, 500) }) + '\n');
      await page.waitForTimeout(PAUSE_MS);
      if (res.status !== 200 || !body) { fails++; if (fails > 20) { console.error('FATAL: too many failures'); process.exit(3); } break; }
      const d = body.data || {};
      const items = d.history || d.list || [];
      cursor = d.next || null;
      if (!cursor || !items.length) break;
      if (job.stop_ts && items[items.length - 1].timestamp && items[items.length - 1].timestamp <= job.stop_ts) break;
    }
  }
  fs.closeSync(out);
  await browser.close();
})();
