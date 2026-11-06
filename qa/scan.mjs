import { chromium } from 'playwright-core';
import fs from 'fs';
const exe='/home/cheycron/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome';
const [,, scheme, themeCss, outJson] = process.argv; // scheme for emulation; themeCss path for palette
const b = await chromium.launch({executablePath:exe,args:['--no-sandbox']});
const ctx = await b.newContext({viewport:{width:1440,height:900},colorScheme:scheme,locale:'en-US'});
const p = await ctx.newPage();
await p.goto('http://127.0.0.1:3399/user/login');
await p.fill('#user_name','ada'); await p.fill('#password','Demo-pass-2026!'); await p.click('button.ui.primary.button');
await p.waitForLoadState('load'); await p.waitForTimeout(800);
const pages={repo:'/aurora/ledger',diff:'/aurora/ledger/pulls/1/files',issues:'/aurora/ledger/issues',pr:'/aurora/ledger/pulls/1',issue:'/aurora/ledger/issues/9',settings:'/user/settings/appearance',profile:'/ada',newissue:'/aurora/ledger/issues/new',file:'/aurora/ledger/src/branch/main/ledger/core.py',commits:'/aurora/ledger/commits/branch/main',branches:'/aurora/ledger/branches',explore:'/explore/repos',merged:'/aurora/ledger/pulls/10',labels:'/aurora/ledger/labels'};
const res={};
for (const [k,u] of Object.entries(pages)){
  await p.goto('http://127.0.0.1:3399'+u); await p.waitForLoadState('load'); await p.waitForTimeout(1000);
  res[k]=await p.evaluate(()=>{
    const out={}; const root=getComputedStyle(document.documentElement);
    const props=['color','backgroundColor','borderTopColor','borderRightColor','borderBottomColor','borderLeftColor','outlineColor','fill','stroke'];
    for (const el of document.querySelectorAll('body *')){
      const r=el.getBoundingClientRect(); if(!r.width||!r.height) continue;
      const cs=getComputedStyle(el);
      for (const pr of props){
        const v=cs[pr]; if(!v||v==='none'||v==='rgba(0, 0, 0, 0)') continue;
        if(pr.startsWith('border')&&(cs[pr.replace('Color','Style')]==='none'||parseFloat(cs[pr.replace('Color','Width')])===0)) continue;
        if(pr==='outlineColor'&&(cs.outlineStyle==='none')) continue;
        const key=pr+'|'+v; const o=out[key]||(out[key]={n:0,ex:[]}); o.n++;
        if(o.ex.length<3){o.ex.push((el.tagName.toLowerCase()+(el.className&&typeof el.className==='string'?'.'+el.className.trim().split(/\s+/).slice(0,3).join('.'):'')).slice(0,80));}
      }
    }
    return {out, body:root.getPropertyValue('--color-body'), scheme:root.colorScheme, dark:root.getPropertyValue('--is-dark-theme'), theme:document.documentElement.getAttribute('data-theme')||document.body.className.slice(0,40)};
  });
}
// theme options
await p.goto('http://127.0.0.1:3399/user/settings/appearance'); await p.waitForTimeout(800);
res.options=await p.evaluate(()=>[...document.querySelectorAll('.theme-list option, select[name=theme] option, [data-theme-name], .ui.dropdown [data-value]')].map(e=>e.textContent.trim()+'='+(e.value||e.dataset.value||'')).slice(0,20));
fs.writeFileSync(outJson,JSON.stringify(res));
await b.close();
