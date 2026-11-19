const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36' });
  const want = {}; 
  p.on('request', r => { const u = r.url(); for (const k of ['token_trades_v2', 'token_holders/', 'rank/sol/wallets/7d']) if (u.includes(k) && !want[k]) want[k] = u; });
  const tok = 'ELR9i6Z7uhtZMWqkySYNnDhviSuSMA7nnyZ1BocKkEK';
  await p.goto(`https://gmgn.ai/sol/token/${tok}`, { waitUntil: 'domcontentloaded', timeout: 45000 }); await p.waitForTimeout(10000);
  await p.goto('https://gmgn.ai/trade?chain=sol', { waitUntil: 'domcontentloaded', timeout: 45000 }); await p.waitForTimeout(8000);
  for (const [k, u] of Object.entries(want)) {
    const q = new URL(u); console.log('\n==', k, '\n  path', q.pathname, '\n  params', [...q.searchParams.keys()].join(','));
    const j = await p.evaluate(async (x) => (await fetch(x)).json(), u);
    const d = j.data || j; const arr = d.history || d.list || d.rank || d.holders || (Array.isArray(d) ? d : null);
    console.log('  top keys', Object.keys(d).slice(0, 12).join(','), '| next', d.next || '');
    if (arr && arr[0]) console.log('  n', arr.length, '| item keys', Object.keys(arr[0]).slice(0, 40).join(','));
    fs.writeFileSync(`/tmp/claude-0/-home-user/adf5c9f9-ecf8-51a7-afb6-987c64621ba8/scratchpad/scrape/${k.replace(/\W/g,'_')}.json`, JSON.stringify(j));
    if (k === 'token_trades_v2' && d.next) {               // page back to test history depth
      let next = d.next, oldest = arr[arr.length-1].timestamp, pages = 1;
      for (let i = 0; i < 15 && next; i++) {
        const nu = new URL(u); nu.searchParams.set('cursor', next);
        const jj = await p.evaluate(async (x) => (await fetch(x)).json(), nu.toString());
        const h = (jj.data||{}).history || []; if (!h.length) break; oldest = h[h.length-1].timestamp; next = jj.data.next; pages++;
        await p.waitForTimeout(800);
      }
      console.log('  paging:', pages, 'pages, oldest trade', new Date(oldest*1000).toISOString());
    }
  }
  await b.close();
})();
