"""Revisione dei tasti di Golazo: apre le schermate principali, tocca ogni pulsante visibile
e segnala errori JavaScript e pulsanti che non fanno niente.
Uso: python3 -m http.server 8765 (nella cartella dell'app) e poi python3 scripts/audit_tasti.py
"""
import asyncio,sys,json
import urllib.request,gzip
UA="Mozilla/5.0"
async def espn_route(route):
    u=route.request.url
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Encoding":"gzip"}),timeout=40);b=r.read()
        if b[:2]==b"\x1f\x8b":b=gzip.decompress(b)
        await route.fulfill(status=200,body=b,headers={"content-type":"application/json","access-control-allow-origin":"*"})
    except Exception as e:
        await route.fulfill(status=500,body=str(e))

from playwright.async_api import async_playwright
SETUP={
 "home_vuota":"localStorage.removeItem('fc_pref');pubGo('partite')",
 "home_pref":"(()=>{const f=n=>(PUB.camp.find(c=>JSON.stringify(c.dati||{}).includes('\"'+n+'\"'))||{}).id;localStorage.setItem('fc_pref',JSON.stringify({sq:['Juventus','Andora'].map(n=>({n,c:f(n)})),camp:['serie-a']}));PUB.favIdx=0;pubGo('partite')})()",
 "campionati":"PUB.sez='dil';pubGo('home')",
 "cerca":"PUB.q='';pubGo('cerca')",
 "cerca_q":"PUB.q='sanrem';pubGo('cerca')",
 "camp_serieA":"PUB.vista='home';PUB.id='serie-a';PUB.sq=null;PUB.tab='cl';pubRender()",
 "camp_serieC_ris":"PUB.vista='home';PUB.id='serie-c-a';PUB.sq=null;PUB.tab='ris';pubRender()",
 "squadra_juve":"PUB.vista='home';PUB.id='serie-a';PUB.sq='Juventus';pubRender()",
 "squadra_andora":"PUB.vista='home';PUB.id=PUB.camp.find(c=>JSON.stringify(c.dati).includes('\"Andora\"')).id;PUB.sq='Andora';pubRender()",
 "entra":"PUB.chi='gio';pubGo('entra')",
 "login_soc":"PUB.chi='soc';PUB.lm='up';pubGo('login')",
}
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path="/usr/bin/google-chrome");pg=await b.new_page(viewport={"width":390,"height":844})
        errs=[];pg.on("pageerror",lambda e:errs.append(str(e)));pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss()))
        await pg.route("https://site.api.espn.com/**",espn_route)
        await pg.goto("http://localhost:8765/?audit=1");await pg.evaluate("sessionStorage.setItem('gz_splash','1')");await pg.reload();await pg.wait_for_timeout(4000)
        report=[]
        for name,js in SETUP.items():
            await pg.evaluate(js);await pg.wait_for_timeout(1500)
            state=await pg.evaluate("JSON.stringify({vista:PUB.vista,id:PUB.id,sq:PUB.sq,tab:PUB.tab,tt:PUB.tt,match:PUB.match,sez:PUB.sez,q:PUB.q,chi:PUB.chi,lm:PUB.lm,favIdx:PUB.favIdx})")
            n=await pg.evaluate("[...document.querySelectorAll('#pub [onclick], #pub label:has(input[type=file])')].filter(e=>e.offsetParent!==null).length")
            for i in range(min(n,70)):
                await pg.evaluate(f"Object.assign(PUB,JSON.parse({json.dumps(state)}));pubRender()");await pg.wait_for_timeout(120)
                info=await pg.evaluate(f"""(()=>{{const L=[...document.querySelectorAll('#pub [onclick], #pub label:has(input[type=file])')].filter(e=>e.offsetParent!==null);const e=L[{i}];if(!e)return null;return {{t:(e.innerText||e.getAttribute('aria-label')||e.className||'').trim().slice(0,40).replace(/\\n/g,' '),file:!!e.querySelector('input[type=file]')}}}})()""")
                if not info or info["file"]:continue
                before=await pg.evaluate("document.getElementById('pub').innerHTML.length+'|'+JSON.stringify({v:PUB.vista,i:PUB.id,s:PUB.sq,t:PUB.tab,tt:PUB.tt,m:PUB.match,z:PUB.sez})+'|'+document.getElementById('pub').scrollTop")
                e0=len(errs)
                try:
                    await pg.evaluate(f"(()=>{{const L=[...document.querySelectorAll('#pub [onclick]')].filter(e=>e.offsetParent!==null);L[{i}].click()}})()")
                except Exception as ex: errs.append(str(ex))
                await pg.wait_for_timeout(450)
                after=await pg.evaluate("document.getElementById('pub').innerHTML.length+'|'+JSON.stringify({v:PUB.vista,i:PUB.id,s:PUB.sq,t:PUB.tab,tt:PUB.tt,m:PUB.match,z:PUB.sez})+'|'+document.getElementById('pub').scrollTop")
                toast=await pg.evaluate("(()=>{const t=document.querySelector('.toast,#toast');return t?t.innerText:''})()")
                report.append(("_tot",name,info["t"],before==after));
                if len(errs)>e0: report.append((name,info["t"],"ERRORE",errs[-1][:120]))
                elif before==after and not toast: report.append((name,info["t"],"nessun effetto",""))
        import collections
        tot=[r for r in report if r[0]=="_tot"];print("cliccati",len(tot),collections.Counter(r[1] for r in tot));print([r for r in tot if r[3]][:20])
        for r in report:
            if r[0]!="_tot":print(r)
        print("errori totali",len(errs));await b.close()
if __name__=="__main__":asyncio.run(main())
