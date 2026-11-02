# Usage: python3 -I extract_prototype.py <downloaded assets dir> <out json>
# Parses JS object/array literals as data (no execution). Identifiers become "@ref:name".
import re, json, sys, os
class P:
    def __init__(s,t,i): s.t=t; s.i=i
    def ws(s):
        while s.t[s.i] in ' \n\t\r': s.i+=1
    def val(s):
        s.ws(); c=s.t[s.i]
        if c=='[':
            s.i+=1; a=[]
            while True:
                s.ws()
                if s.t[s.i]==']': s.i+=1; return a
                a.append(s.val()); s.ws()
                if s.t[s.i]==',': s.i+=1
        if c=='{':
            s.i+=1; o={}
            while True:
                s.ws()
                if s.t[s.i]=='}': s.i+=1; return o
                if s.t[s.i] in '`"\'': k=s.string()
                else:
                    m=re.compile(r'[\w$-]+').match(s.t,s.i); k=m.group(); s.i=m.end()
                s.ws()
                if s.t[s.i]==':': s.i+=1; o[k]=s.val()
                else: o[k]='@ref:'+k
                s.ws()
                if s.t[s.i]==',': s.i+=1
        if c in '`"\'': return s.string()
        if s.t.startswith('!0',s.i): s.i+=2; return True
        if s.t.startswith('!1',s.i): s.i+=2; return False
        m=re.compile(r'-?\d+(\.\d+)?').match(s.t,s.i)
        if m: s.i=m.end(); return float(m.group()) if '.' in m.group() else int(m.group())
        m=re.compile(r'[\w$.]+').match(s.t,s.i)
        if m:
            s.i=m.end(); name=m.group()
            # call expression like x(...) : capture raw
            if s.t[s.i]=='(':
                d=0; st=s.i
                while True:
                    ch=s.t[s.i]
                    if ch=='(':d+=1
                    elif ch==')':
                        d-=1
                        if d==0: s.i+=1; break
                    s.i+=1
                return '@call:'+name+s.t[st:s.i]
            if name in('null','void'): return None
            return '@ref:'+name
        raise ValueError('unexpected %r at %d'%(s.t[s.i:s.i+40],s.i))
    def string(s):
        q=s.t[s.i]; s.i+=1; out=[]
        while True:
            c=s.t[s.i]
            if c=='\\':
                n=s.t[s.i+1]; out.append({'n':'\n','t':'\t'}.get(n,n)); s.i+=2; continue
            if q=='`' and c=='$' and s.t[s.i+1]=='{':
                d=0
                while True:
                    ch=s.t[s.i]; out.append(ch)
                    if ch=='{': d+=1
                    elif ch=='}':
                        d-=1
                        if d==0: s.i+=1; break
                    s.i+=1
                continue
            if c==q: s.i+=1; return ''.join(out)
            out.append(c); s.i+=1
targets={'index-CXmOnMtK.js':['Mv','Fv','zv','py','gy'],'catalog-D69irPY0.js':['e','t','n','r','i','a','o'],
 'framework-B4NjXYcr.js':['e'],'library-Djy-QzUH.js':['e','t','n'],'program-pillar-map-B_EGlQHZ.js':['f'],'_id-DPkfbzwm.js':['_','g'],'research-cx6C9b35.js':['n']}
d=sys.argv[1]; res={}
for f,names in targets.items():
    t=open(os.path.join(d,f)).read()
    for n in names:
        m=re.search(r'[,; (]'+re.escape(n)+r'=(\[\{|\{")',t)
        if not m: print('miss',f,n); continue
        try: v=P(t,m.start(1)).val(); res[f.split('-')[0]+'.'+n]=v; print(f,n,len(v),json.dumps(v)[:150])
        except Exception as e: print('fail',f,n,e)
json.dump(res,open(sys.argv[2],'w'),indent=1)
