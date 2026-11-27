import sys,json,glob,re,difflib
sys.path.insert(0,'/home/claude/scr');import leggi_calendario as cal2
camp=json.load(open('/home/claude/oneglia-b-/data/campionati.json'))['campionati']
import serie_d as seried_cal
STOP={'CALCIO','ASD','A','S','D','SSD','FC','F','C','US','USD','POL','POLISP','POLISPORTIVA','AC','ACD','SC','ASDC','SSDARL','ARL','1919','DI','DEL','THE','CLUB','SPORT','SPORTIVA','ASS','ASSOCIAZIONE'}
def norm(s):
  s=s.upper().replace('&',' ').replace('“','"').replace('”','"')
  s=re.sub(r"[^A-Z0-9' ]"," ",s);t=[x for x in s.split() if x not in STOP and not re.fullmatch(r'\d{2,4}',x)]
  return ' '.join(t)
def sc(a,b):
  na,nb=norm(a),norm(b)
  if not na or not nb: return 0
  r=difflib.SequenceMatcher(None,na,nb).ratio()
  ta,tb=set(na.split()),set(nb.split())
  if ta and tb and (ta<=tb or tb<=ta): r=max(r,0.85)
  return r
def teams_of(c):
  s=set(r['squadra'] for r in (c['dati'].get('classifica') or {}).get('righe',[]))
  if len(s)>=4: return sorted(s)
  for k in ('risultati','programma'):
    for m in c['dati'].get(k) or []: s.add(m['casa']);s.add(m['ospite'])
  return sorted(x for x in s if x)
def mapping(calteams,apptm):
  pairs=sorted(((sc(a,b),a,b) for a in calteams for b in apptm),reverse=True)
  M={};used=set()
  for s,a,b in pairs:
    if s<0.55: break
    if a in M or b in used: continue
    M[a]=b;used.add(b)
  for a in calteams:
    if a in M: continue
    s,b=max((sc(a,b),b) for b in apptm)
    if s>=0.6: M[a]=b
  return M
src=[]
for f in sorted(glob.glob('/tmp/cal/src/*.pdf')+glob.glob('/tmp/cal/src2/*.pdf')):
  if 'Open Day' in f: continue
  try:
    for gi in cal2.parse(f): src.append((f,gi['g']))
  except Exception as e: print('ERR',f,e)
for f in sorted(glob.glob('/tmp/cal/docx/*/*.docx')+glob.glob('/tmp/cal/docx2/*.docx')):
  for gi in cal2.parse_docx(f): src.append((f,gi['g']))
for gi in seried_cal.parse('/tmp/cal/sd/A.pdf'): src.append(('/tmp/cal/sd/Tabellone-Girone-A.pdf',gi['g']))
for f in sorted(glob.glob('/tmp/cal/ocr/*.pdf')):
  for gi in cal2.parse(f,ocr=True): src.append((f,gi['g']))
out={};rep=[]
for f,G in src:
  calteams=sorted(set(x for g in G for p in g['p'] for x in p))
  best=None
  for c in camp:
    apptm=teams_of(c)
    if len(apptm)<4: continue
    M=mapping(calteams,apptm)
    # verify with results
    res=[(m['giornata'],m['casa'],m['ospite']) for m in c['dati'].get('risultati') or [] if m.get('giornata')]
    cp={}
    for g in G:
      for h,a in g['p']: cp.setdefault(g['n'],[]).append((M.get(h),M.get(a)))
    ok=sum(1 for n,ca,os_ in res if any((x and sc(x,ca)>0.7) and (y and sc(y,os_)>0.7) for x,y in cp.get(n,[])))
    mv=set(M.values());res2=[r for r in res if r[1] in mv and r[2] in mv]
    score=len(set(M.values()))/max(len(apptm),1)
    key=(ok, score)
    if not best or key>best[0]: best=(key,c,M,len(res2) if len(teams_of(c))>len(calteams)+2 else len(res))
  (ok,score),c,M,nres=best
  napp=len(teams_of(c))
  # ensure c not taken by better
  rep.append((f.split('/')[-1][:45],c['id'],f'{ok}/{nres}',round(score,2),len(G),napp))
  if nres and ok/nres<0.7: continue
  if not nres and score<0.8: continue
  prev=out.get(c['id'])
  if prev and prev['_ok']>=ok: continue
  gi=[]
  for g in G:
    pp=[[M[h],M[a]] for h,a in g['p'] if h in M and a in M and M[h]!=M[a]]
    gi.append({'n':g['n'],'a':g['a'],'r':g['r'],'p':pp})
  import datetime as D
  for k in ('a','r'):
    if k=='a':
      for g in gi:
        if g['a'] and g['a']>='2027-01-01' and not g['r'] and g['n']<=3: g['r'],g['a']=g['a'],None
    ds=[D.date.fromisoformat(g[k]) if g[k] else None for g in gi]
    okv=[False]*len(ds)
    for i,d in enumerate(ds):
      if not d: continue
      prv=next((ds[j] for j in range(i-1,-1,-1) if ds[j]),None); nxt=next((ds[j] for j in range(i+1,len(ds)) if ds[j]),None)
      c1=prv and 5<=(d-prv).days<=7*(i-max(j for j in range(i) if ds[j]))+15 if prv else False
      c2=nxt and 5<=(nxt-d).days<=7*(min(j for j in range(i+1,len(ds)) if ds[j])-i)+15 if nxt else False
      okv[i]=bool(c1 or c2)
    if '/ocr/' in f:
      from collections import Counter
      wd=Counter(d.weekday() for d in ds if d).most_common(1)
      okv=[v and ds[i].weekday()==wd[0][0] for i,v in enumerate(okv)]
    for g,v in zip(gi,okv):
      if not v: g[k]=None
  out[c['id']]={'_ok':ok,'fonte':f.split('/')[-1],'giornate':gi}
for r in rep: print(*r)
for k,v in out.items(): v.pop('_ok')
json.dump(out,open('/tmp/cal/calendari.json','w'),ensure_ascii=False)
print(len(out),'campionati con calendario')
