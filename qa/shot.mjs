import { chromium } from 'playwright-core';
const [,, scheme, outPrefix, ...urls] = process.argv;
const exe='/home/cheycron/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome';
const b = await chromium.launch({executablePath:exe,args:['--no-sandbox']});
const ctx = await b.newContext({viewport:{width:1440,height:900},colorScheme:scheme,locale:'en-US'});
const p = await ctx.newPage();
await p.goto('http://127.0.0.1:3399/user/login');
await p.fill('#user_name','ada'); await p.fill('#password','Demo-pass-2026!'); await p.click('button.ui.primary.button');
await p.waitForLoadState('load'); await p.waitForTimeout(1200);
for (const u of urls){
  const [name,path]=u.split('=');
  await p.goto('http://127.0.0.1:3399'+path); await p.waitForLoadState('load'); await p.waitForTimeout(1500);
  await p.screenshot({path:`${outPrefix}-${name}.png`});
}
await b.close();
