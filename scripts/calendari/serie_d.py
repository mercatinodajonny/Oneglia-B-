import pdfplumber,re,sys
MESI={'GEN':1,'FEB':2,'MAR':3,'APR':4,'MAG':5,'GIU':6,'LUG':7,'AGO':8,'SET':9,'OTT':10,'NOV':11,'DIC':12}
def parse(fn):
  pg=pdfplumber.open(fn).pages[0];ws=[w for w in pg.extract_words(x_tolerance=1.5,y_tolerance=2) if w['x0']>95]
  L=[]
  for w in sorted(ws,key=lambda w:w['top']):
    if L and w['top']-L[-1][2]<=3: L[-1][1].append(w);L[-1][2]=w['top']
    else: L.append([w['top'],[w],w['top']])
  L=[(a,b) for a,b,c in L]
  G={};heads=[]
  for top,l in L:
    l.sort(key=lambda w:w['x0']);txt=[w['text'] for w in l]
    if 'Giornata' in txt:
      heads=[]
      for i,w in enumerate(l):
        if w['text']=='Giornata' and i+1<len(l) and l[i+1]['text'].isdigit():
          n=int(l[i+1]['text']);c=(w['x0']+l[i+1]['x1'])/2;heads.append((c,n));G[n]={'n':n,'a':None,'r':None,'p':[]}
      continue
    if not heads: continue
    # assign words to nearest header column
    cols={}
    for w in l:
      cx=(w['x0']+w['x1'])/2;c,n=min(heads,key=lambda h:abs(h[0]-cx));cols.setdefault(n,[]).append(w['text'])
    for n,t in cols.items():
      s=' '.join(t)
      if s.startswith('AND.'):
        m=re.findall(r'(\d{2}) ([A-Z]{3}) (\d{4})',s)
        if len(m)>=1: G[n]['a']=f"{m[0][2]}-{MESI[m[0][1]]:02d}-{m[0][0]}"
        if len(m)>=2: G[n]['r']=f"{m[1][2]}-{MESI[m[1][1]]:02d}-{m[1][0]}"
      elif ' vs ' in s:
        h,a=s.split(' vs ',1);G[n]['p'].append([h.strip(),a.strip()])
  return [{'g':[G[k] for k in sorted(G)]}]
if __name__=='__main__':
  g=parse(sys.argv[1])[0]['g'];print(len(g),[len(x['p']) for x in g],g[0],g[-1]['a'],g[-1]['r'])
