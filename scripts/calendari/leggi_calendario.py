import re,sys,json,subprocess,os,tempfile
MESI={'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12}
def words_pdf(fn):
  import pdfplumber
  out=[]
  with pdfplumber.open(fn) as pdf:
    for pi,pg in enumerate(pdf.pages):
      for w in pg.extract_words(keep_blank_chars=False,use_text_flow=False,x_tolerance=1.5):
        out.append(dict(t=w['text'],x0=w['x0'],x1=w['x1'],y=pi*10000+w['top'],h=w['bottom']-w['top']))
  return out
def words_ocr(fn,dpi=250):
  d=tempfile.mkdtemp();subprocess.run(['pdftoppm','-r',str(dpi),'-png',fn,d+'/p'],check=True)
  out=[]
  for pi,f in enumerate(sorted(os.listdir(d))):
    tsv=subprocess.run(['tesseract',d+'/'+f,'-','--psm','6','-l','ita','tsv'],capture_output=True).stdout.decode('utf8','ignore')
    for l in tsv.splitlines()[1:]:
      c=l.split('\t')
      if len(c)<12 or not c[11].strip(): continue
      x,y,w,h=map(int,c[6:10]);out.append(dict(t=c[11].strip(),x0=x,x1=x+w,y=pi*100000+y,h=h))
  return out
def lines_of(ws,tol):
  ws=sorted(ws,key=lambda w:(w['y'],w['x0']));L=[]
  for w in ws:
    if L and abs(w['y']-L[-1][0])<=tol: L[-1][1].append(w)
    else: L.append([w['y'],[w]])
  return [(y,sorted(l,key=lambda w:w['x0'])) for y,l in L]
def dt(s,anno=None):
  s=s.upper().replace('O','0') if False else s
  m=re.search(r'(\d{1,2})\s*[/ .]?\s*(GEN|FEB|MAR|APR|MAG|GIU|LUG|AGO|SET|OTT|NOV|DIC)[A-Z]*\.?\s*(\d{2,4})?',s.upper())
  if not m: return None
  d,mo,y=int(m.group(1)),MESI[m.group(2).lower()],m.group(3)
  yy=2026 if mo>=7 else 2027
  if d<1 or d>31: return None
  return f"{yy}-{mo:02d}-{d:02d}"
def parse(fn,ocr=False):
  ws=words_ocr(fn) if ocr else words_pdf(fn)
  hmed=sorted(w['h'] for w in ws)[len(ws)//2] if ws else 10
  L=lines_of(ws,hmed*0.6)
  M=[]
  for y,l in L:
    if M and any(re.fullmatch(r'(?i)giornata',w['t']) for w in l) and any(re.fullmatch(r'(?i)giornata',w['t']) for w in M[-1][1]) and abs(y-M[-1][0])<hmed*1.5:
      M[-1]=(M[-1][0],sorted(M[-1][1]+l,key=lambda w:w['x0']))
    else: M.append((y,l))
  L=M
  gironi=[];cur=None;i=0
  while i<len(L):
    y,l=L[i]
    hs=[k for k,w in enumerate(l) if re.fullmatch(r'(?i)giornata',w['t'])]
    if hs:
      cols=[]
      for k in hs:
        g=l[k];num=None
        if k>0 and re.match(r'^\d+',l[k-1]['t']) and l[k-1]['x1']>g['x0']-hmed*2: num=int(re.match(r'\d+',l[k-1]['t']).group()); x0=l[k-1]['x0']
        else:
          x0=g['x0']
          if k+1<len(l) and re.fullmatch(r'[\dDOIl]{1,2}',l[k+1]['t']): 
            t=l[k+1]['t'].replace('D','0').replace('O','0').replace('I','1').replace('l','1')
            num=int(t) if t.isdigit() else None
        cols.append(dict(num=num,c=(x0+g['x1'])/2))
      if cur is None or (cols[0]['num']==1 and cur['g']): cur={'g':[]};gironi.append(cur)
      bounds=[]
      for j,c in enumerate(cols):
        lo=(cols[j-1]['c']+c['c'])/2 if j>0 else -1e9
        hi=(cols[j+1]['c']+c['c'])/2 if j+1<len(cols) else 1e9
        if j==0 and len(cols)>1: lo=c['c']-(hi-c['c'])
        if j==len(cols)-1 and len(cols)>1: hi=c['c']+(c['c']-lo)
        seq=c['num'] if c['num'] and c['num']==len(cur['g'])+1 else len(cur['g'])+1
        G={'n':seq,'num_pdf':c['num'],'a':None,'r':None,'p':[],'lo':lo,'hi':hi}
        cur['g'].append(G);bounds.append(G)
      i+=1;first=True
      while i<len(L):
        y2,l2=L[i]
        if any(re.fullmatch(r'(?i)giornata',w['t']) for w in l2): break
        txt=' '.join(w['t'] for w in l2)
        if re.search(r'(?i)stagione|calendario|delegazione|girone\s|comitato',txt) and not first: 
          i+=1;continue
        for G in bounds:
          ww=[w for w in l2 if G['lo']<= (w['x0']+w['x1'])/2 < G['hi']]
          ww=[w for w in ww if re.search(r'[A-Za-z0-9]',w['t']) and not re.fullmatch(r'[-=x:.,;_—–»«*ÈèÙùòàì”"“\'’|]+',w['t'])]
          if not ww: continue
          s=' '.join(w['t'] for w in ww)
          ds=re.findall(r'\d{1,2}\s*[/ .]?\s*(?:GEN|FEB|MAR|APR|MAG|GIU|LUG|AGO|SET|OTT|NOV|DIC)[A-Z]*\.?(?:\s*\d{2,4})?',s.upper())
          if ds and len(ds)>=1 and not G['p']:
            if G['a'] is None: G['a']=dt(ds[0]); G['r']=dt(ds[1]) if len(ds)>1 else None
            continue
          if re.search(r'(?i)riposa',s): continue
          # split at largest gap
          if len(ww)<2: continue
          gaps=[(ww[k+1]['x0']-ww[k]['x1'],k) for k in range(len(ww)-1)]
          g,k=max(gaps)
          if g<hmed*0.9: continue
          h=' '.join(w['t'] for w in ww[:k+1]);a=' '.join(w['t'] for w in ww[k+1:])
          G['p'].append([h,a])
        first=False;i+=1
      continue
    i+=1
  for gi in gironi:
    for G in gi['g']: G.pop('lo');G.pop('hi')
  return gironi
if __name__=='__main__':
  ocr='--ocr' in sys.argv
  for fn in [a for a in sys.argv[1:] if not a.startswith('--')]:
    gs=parse(fn,ocr)
    for gi in gs:
      g=gi['g'];teams=set(x for G in g for p in G['p'] for x in p)
      print(fn.split('/')[-1][:50],'giornate',len(g),'squadre',len(teams),'partite/g',[len(G['p']) for G in g],'date',[G['a'] for G in g][:3],[G['num_pdf'] for G in g][:15])

def parse_docx(fn):
  import docx
  d=docx.Document(fn);G=[]
  for t in d.tables:
    if len(t.columns)!=2 or len(t.rows)<3: continue
    h=t.rows[0].cells[0].text
    m=re.search(r'(\d+)\s*[aª°^]?\s*Giornata',h,re.I)
    if not m: continue
    ds=re.findall(r'\d{1,2}\s*[/ .]?\s*(?:Gen|Feb|Mar|Apr|Mag|Giu|Lug|Ago|Set|Ott|Nov|Dic)[a-z]*\.?(?:\s*\d{2,4})?',h,re.I)
    g={'n':int(m.group(1)),'num_pdf':int(m.group(1)),'a':dt(ds[0]) if ds else None,'r':dt(ds[1]) if len(ds)>1 else None,'p':[]}
    for r in t.rows[1:]:
      a,b=[c.text.strip() for c in r.cells]
      if a and b and not re.search(r'(?i)riposa',a+b): g['p'].append([a,b])
    G.append(g)
  return [{'g':G}]
