const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../investicni_pristrojova_deska.html'),'utf8');
const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
let now=Date.parse('2026-11-03T16:00:00Z');
class Clock extends Date { constructor(...args){super(...(args.length?args:[now]));} static now(){return now;} }
const els={},timers=[],events={},cache={};
const context=vm.createContext({Date:Clock,Intl,URL,AbortController,console,
 document:{hidden:false,getElementById:id=>els[id]??=( {value:'',textContent:'',innerHTML:'',showModal(){},close(){}} ),querySelectorAll:()=>[],addEventListener:(name,f)=>events[name]=f},
 localStorage:{getItem:k=>cache[k]||null,setItem:(k,v)=>cache[k]=v},
 setInterval:(f,ms)=>timers.push({f,ms}),setTimeout,clearTimeout,
 fetch:async()=>{throw Error('offline');}
});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
const quote=(time='2026-11-03T15:45:00Z',value=21)=>({series_id:'VIX',symbol:'^VIX',value,date:time.slice(0,10),frequency:'intraday',quote_time:time,fetch_status:'ok'});
const parse=d=>{context.input=d;return run('parseVix(input)')};
(async()=>{
 await new Promise(r=>setTimeout(r,20));
 assert.equal(parse(quote()).quoteTime,'2026-11-03T15:45:00.000Z');
 for(const d of [quote('2026-11-03T17:00:00Z'),quote('garbage'),quote('2026-11-03T15:45:00Z',null),{...quote(),symbol:'VIXY'},{...quote(),quote_time:'2026-11-03T15:45:00'}])assert.throws(()=>parse(d));
 context.v=parse(quote());assert.equal(run('riskStale(v)'),false);
 now+=46*60000;assert.equal(run('riskStale(v)'),true);assert.match(run('riskStatus(v)'),/ZASTARALÁ/);
 now=Date.parse('2026-11-03T16:00:00Z');
 let live=quote(),daily={series_id:'VIXCLS',value:19,date:'2026-11-02'};
 context.fetch=async url=>({ok:true,json:async()=>String(url).includes('vix_intraday')?live:daily});
 run('delete state.risk');await run('loadRisk()');assert.equal(run('state.risk.value'),21);assert.match(run('displayDate(state.risk)'),/Yahoo/);
 live=quote('2026-11-03T15:50:00Z',22);await run('loadRisk()');assert.equal(run('state.risk.value'),22);
 live=quote('2026-11-03T15:30:00Z',18);await run('loadRisk()');assert.equal(run('state.risk.value'),22);
 context.fetch=async()=>{throw Error('offline')};await run('loadRisk()');assert.equal(run('state.risk.value'),22);assert.match(run('errors.risk'),/není dostupný/);
 run('delete state.risk;restoreRisk()');assert.equal(run('state.risk.value'),22);
 run('delete state.risk');context.fetch=async url=>{if(String(url).includes('vix_intraday'))throw Error('HTTP 429');return {ok:true,json:async()=>daily}};
 await run('loadRisk()');assert.equal(run('state.risk.value'),19);assert.match(run('riskStatus(state.risk)'),/denní fallback/);
 assert.equal(run('stale(state.risk)'),true);
 run("detail('risk')");assert.match(els.dSource.innerHTML,/fred.stlouisfed.org/);
 assert.ok(timers.some(t=>t.ms===60000));assert.ok(timers.some(t=>t.ms===15000));assert.ok(events.visibilitychange);
 run('delete state.risk');context.fetch=async()=>{throw Error('offline')};await run('loadRisk()');assert.equal(run('state.risk'),undefined);
 console.log('PASS: timestamp validation, stale transition, quote updates, regression, outage retention, persistent cache, daily fallback, source dialog, timers, no-data');
})().catch(e=>{console.error(e);process.exitCode=1});
