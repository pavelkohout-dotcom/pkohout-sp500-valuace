const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.join(__dirname,'..'),data=JSON.parse(fs.readFileSync(path.join(root,'data/earnings_reactions.json')));
const html=fs.readFileSync(path.join(root,'investicni_pristrojova_deska.html'),'utf8');
const els={},events={};
class Clock extends Date {constructor(...a){super(...(a.length?a:['2026-11-03T23:59:00Z']));}static now(){return Date.parse('2026-11-03T23:59:00Z');}}
const ctx=vm.createContext({Date:Clock,Intl,URL,AbortController,console,setTimeout,clearTimeout,setInterval(){},localStorage:{getItem(){return null},setItem(){}},document:{hidden:false,getElementById:id=>els[id]??={hidden:false,innerHTML:'',value:'',textContent:'',showModal(){},close(){}},querySelectorAll:()=>[],addEventListener:(n,f)=>events[n]=f},fetch:async()=>{throw Error('offline')}});
vm.runInContext(html.match(/<script>\s*([\s\S]*?)<\/script>/)[1],ctx);
const run=s=>vm.runInContext(s,ctx);
(async()=>{
 await new Promise(r=>setTimeout(r,20));ctx.input=data;
 assert.equal(run('parseReactions(input).counts.declined'),data.counts.declined);
 run("state.profit.quarter=input.quarter;detail('profit')");
 assert.equal(els.earningsReactions.hidden,false);assert.match(els.earningsReactions.innerHTML,new RegExp('Seznam beatů s poklesem \\('+data.counts.declined+'\\)'));assert.match(els.earningsReactions.innerHTML,/dostupný vzorek/);
 run("detail('risk')");assert.equal(els.earningsReactions.hidden,true);
 ctx.input=structuredClone(data);ctx.input.counts.declined++;assert.throws(()=>run('parseReactions(input)'));
 ctx.input=structuredClone(data);ctx.input.events.push(ctx.input.events[0]);assert.throws(()=>run('parseReactions(input)'));
 ctx.input=structuredClone(data);const row=ctx.input.events.find(r=>r.status==='measured');row.change_pct=999;assert.throws(()=>run('parseReactions(input)'));
 run("state.profit.quarter='2027-Q1';detail('profit')");assert.match(els.earningsReactions.innerHTML,/jiné sezoně/);assert.doesNotMatch(els.earningsReactions.innerHTML,/reaction-count/);
 await new Promise(r=>setTimeout(r,20));run("state.profit.quarter=reactionData.quarter");await run('loadReactions(true)');assert.equal(run('reactionData.counts.declined'),data.counts.declined);assert.match(els.earningsReactions.innerHTML,/Obnova se nezdařila/);
 assert.equal(run("htmlText('<img src=x>')"),'&lt;img src=x&gt;');
 console.log('PASS: live snapshot integrity, counters/list, coverage label, dialog switching, invalid counts/prices/duplicates, season mismatch, outage retention, escaping');
})().catch(e=>{console.error(e);process.exitCode=1});
