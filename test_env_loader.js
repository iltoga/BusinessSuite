import { dirname, resolve } from 'path';
function getEnvCandidates() {
  const c = [];
  let d = process.cwd();
  c.push(resolve(d, '.env'), resolve(d, '..', '.env'));
  
  if (typeof __dirname !== 'undefined') d = __dirname;
  else if (import.meta && import.meta.url) {
    // hack to get dir in test
    d = '/app/dist/business-suite-frontend/server';
  }
  
  while (true) {
    c.push(resolve(d, '.env'));
    const p = dirname(d);
    if (p === d) break;
    d = p;
  }
  return [...new Set(c)];
}
console.log(getEnvCandidates());
