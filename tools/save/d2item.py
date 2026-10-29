import csv
EXC = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "work", "mod", "data", "global", "excel") + "/"  # the built tables (tools/build.py)
def tsv(n): return list(csv.DictReader(open(EXC+n,newline='',encoding='utf-8',errors='replace'),delimiter='\t'))
ISC = {}
for r in tsv('itemstatcost.txt'):
    if r.get('*ID','').strip().isdigit():
        g=lambda k: int(r.get(k) or 0)
        ISC[int(r['*ID'])]=dict(name=r['Stat'],bits=g('Save Bits'),add=g('Save Add'),par=g('Save Param Bits'),
                                 enc=g('Encode'),
                                 nxt=None)
NAME2ID={v['name']:k for k,v in ISC.items()}
ARMOR={r['code'] for r in tsv('armor.txt')}
WEAP={r['code']:r for r in tsv('weapons.txt')}
MISC={r['code']:r for r in tsv('misc.txt')}
ALL={}
for f in ('armor.txt','weapons.txt','misc.txt'):
    for r in tsv(f): ALL[r['code']]=r
# D2R item code huffman tree
T=[[[[["w","u"],[["8",["y",["5",["j",[]]]]],"h"]],["s",[["2","n"],"x"]]],[[["c",["k","f"]],"b"],[["t","m"],["9","7"]]]],[" ",[[[["e","d"],"p"],["g",[[["z","q"],"3"],["v","6"]]]],[["r","l"],["a",[["1",["4","0"]],["i","o"]]]]]]]
CODES={}
def build(node,path):
    if isinstance(node,str): CODES[node]=path; return
    if node==[]: return
    build(node[0],path+[0]); build(node[1],path+[1])
build(T,[])

class R:
    def __init__(s,b,pos=0): s.b=b; s.p=pos
    def bit(s):
        v=(s.b[s.p>>3]>>(s.p&7))&1; s.p+=1; return v
    def n(s,k):
        v=0
        for i in range(k): v|=s.bit()<<i
        return v
    def huff(s):
        node=T
        while not isinstance(node,str): node=node[s.bit()]
        return node
class W:
    def __init__(s): s.bits=[]
    def n(s,v,k):
        for i in range(k): s.bits.append((v>>i)&1)
    def raw(s,lst): s.bits+=lst
    def bytes(s):
        b=s.bits+[0]*((-len(s.bits))%8)
        return bytes(sum(b[i+j]<<j for j in range(8)) for i in range(0,len(b),8))

def stackable(code): return ALL.get(code,{}).get('stackable','')=='1'
def read_props(r,out):
    while True:
        sid=r.n(16)  # D2R 3.3: 16-bit stat ids, list ends with 0xffff
        if sid==0xffff: return
        st=ISC[sid]
        par=r.n(st['par']) if st['par'] else None
        val=r.n(st['bits'])-st['add']
        out.append((sid,st['name'],par,val))
        # paired stats (min/max dmg etc.) per D2 rules
        for extra in {17:[18],48:[49],50:[51],52:[53],54:[55,56],57:[58,59]}.get(sid,[]):
            e=ISC[extra]; out.append((extra,e['name'],None,r.n(e['bits'])-e['add']))

def read_item(b,pos):
    r=R(b,pos); it={}
    it['flags']=r.n(32); f=it['flags']
    it['simple']=(f>>21)&1; it['socketed']=(f>>11)&1; it['ear']=(f>>16)&1; it['pers']=(f>>24)&1; it['rw']=(f>>26)&1
    it['b105']=r.n(8)  # D2R 3.3 (save v105): a byte before the version, 0x05 on every item seen
    it['ver']=r.n(3); it['loc']=r.n(3); it['eq']=r.n(4); it['x']=r.n(4); it['y']=r.n(4); it['page']=r.n(3)
    code=''.join(r.huff() for _ in range(4)); it['code']=code.strip()
    if it['simple']:
        # D2R 3.3 simple item: id flag + 128-bit id, then the 1-bit socket count
        it['guidflag']=r.bit()
        if it['guidflag']: it['guid']=r.n(128)
        it['socks_filled']=r.n(1)
    else:
        it['socks_filled']=r.n(3)
    if not it['simple']:
        it['id']=r.n(32); it['ilvl']=r.n(7); q=it['quality']=r.n(4)
        if r.bit(): it['pic']=r.n(3)
        if r.bit(): it['autoaffix']=r.n(16)  # D2R 3.3: 16 bits
        if q==1: it['lowq']=r.n(3)
        elif q==3: it['sup']=r.n(3)
        elif q==4: it['prefix']=r.n(11); it['suffix']=r.n(11)
        elif q==5: it['set']=r.n(12)
        elif q==7: it['unique']=r.n(12)
        elif q in (6,8):
            it['rare']=[r.n(8),r.n(8)]+[r.n(11) if r.bit() else None for _ in range(6)]
        if it['rw']: it['rwid']=r.n(12); r.n(4)
        if it['pers']:
            s=''
            while True:
                c=r.n(8)
                if c==0: break
                s+=chr(c)
            it['name']=s
        if it['code'] in ('tbk','ibk'): it['tome']=r.n(5)
        it['guidflag']=r.bit()
        if it['guidflag']: it['guid']=r.n(128)
        c=it['code']
        if c in ARMOR: it['def']=r.n(ISC[31]['bits'])-ISC[31]['add']
        if c in ARMOR or c in WEAP:
            it['maxdur']=r.n(ISC[73]['bits'])-ISC[73]['add']
            if it['maxdur']>0: it['dur']=r.n(ISC[72]['bits'])-ISC[72]['add']
        it['ts']=r.bit()  # D2R 3.3: after the defense/durability fields
        if stackable(c): it['qty']=r.n(9)
        if it['socketed']: it['socks']=r.n(4)
        if q==5: it['setmask']=r.n(5)
        props=[]; read_props(r,props); it['props']=props
    it['bits']=r.p-pos
    end=(r.p+7)//8*8
    return it,end
