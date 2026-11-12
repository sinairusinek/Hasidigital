import json,re,sys,html,difflib,collections
import xml.etree.ElementTree as ET
S=sys.argv[1]; XML=sys.argv[2]
NS={'t':'http://www.tei-c.org/ns/1.0'}
def clean(s):
    s=html.unescape(re.sub(r'<[^>]+>',' ',s))
    s=re.sub(r'[֑-ׇ]','',s)
    s=s.replace('״','"').replace('׳',"'").replace('–','-')
    return s
def toks(s):
    s=re.sub(r'[^א-ת"\' ]',' ',clean(s))
    return [w.strip('"\'') for w in s.split() if w.strip('"\'')]
# ours
root=ET.parse(XML).getroot()
ours=[]
for d in root.iter('{http://www.tei-c.org/ns/1.0}div'):
    if d.get('type')!='story': continue
    for sp in d.iter('{http://www.tei-c.org/ns/1.0}span'): sp.text=''
    for h in d.iter('{http://www.tei-c.org/ns/1.0}head'): h.text=''
    txt=' '.join(ET.tostring(p,encoding='unicode',method='text') for p in d.findall('.//t:p',NS))
    ours.append((d.get('{http://www.w3.org/XML/1998/namespace}id'),toks(txt)))
# sefaria
v=json.load(open(f'{S}/shivhei_v3.json'))['versions'][0]['text']
sef=[(f'Shivchei HaBesht {i+1}',toks(' '.join(st))) for i,st in enumerate(v)]
def shingles(t,k=3): return {' '.join(t[i:i+k]) for i in range(len(t)-k+1)}
sefsh=[shingles(t) for _,t in sef]
rows=[];agg=collections.Counter();tot=0;ops_all=[]
for oid,ot in ours:
    osh=shingles(ot)
    best=max(range(len(sef)),key=lambda j:len(osh&sefsh[j]))
    ov=len(osh&sefsh[best])/max(1,len(osh))
    st=sef[best][1]
    sm=difflib.SequenceMatcher(None,ot,st,autojunk=False)
    eq=sum(b-a for tag,a,b,c,d in sm.get_opcodes() if tag=='equal')
    diffs=[(tag,' '.join(ot[a:b]),' '.join(st[c:d])) for tag,a,b,c,d in sm.get_opcodes() if tag!='equal']
    for tag,a,b in diffs:
        if tag=='replace' and len(a.split())==1 and len(b.split())==1: ops_all.append((oid,a,b))
    rows.append((oid,len(ot),sef[best][0],len(st),round(ov,3),round(eq/max(1,len(ot)),4),len(diffs)))
    tot+=len(ot); agg['eq']+=eq; agg['diffs']+=len(diffs)
json.dump({'rows':rows,'subs':ops_all},open(f'{S}/align.json','w'),ensure_ascii=False)
print('our words',tot,'sefaria words',sum(len(t) for _,t in sef),'identical-word share %.4f'%(agg['eq']/tot),'diff spans',agg['diffs'])
mapped=collections.Counter(r[2] for r in rows)
print('sefaria stories hit by >1 of ours:',[(k,c) for k,c in mapped.items() if c>1][:20])
print('sefaria stories unmatched:',[s for s,_ in sef if s not in mapped])
print('low-overlap ours:',[r for r in rows if r[4]<0.5])
print('one-word substitutions',len(ops_all))
