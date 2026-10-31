import functools, itertools, json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
from regal.espresso import _Cover

VARS = ['t0','t1','t2','t3','t4','CS_n','PEND','RD_n','WR_n','RST','CPUCLK']
N = len(VARS)
SP = _Cover(N)

def paths(e):
    read = [(0,0),(0,1),(e['c1R'],0),(e['c1R'],1)]
    write = [(0,0),(0,1),(e['c1W'],0),(e['c1W'],1)]
    for a in e['A']:
        read += [(a,0),(a,1)]; write += [(a,0),(a,1)]
    for d in (e['dH'], e['dL']):
        read += [(d,0),(d,1)]; write += [(d,0),(d,1)]
    l1,l2,l3,l4 = e['R']
    read += [(l1,0),(l2,0),(e['h8'],1),(l3,0),(l4,0),(e['h9'],1),(e['hr'],1)]
    write += [(e['hw'],1)]
    init = []
    for k in e['init']:
        init += [(k,0),(k,1)]
    init += [(e['ih'],1)]
    t = lambda s: [2*k+b for k,b in s]
    return t(read), t(write), t(init)

def valid(e):
    r, w, i = paths(e)
    return len(set(r)) == len(r) and len(set(w)) == len(w) and len(set(i)) == len(i)

def build(e):
    read, write, init = paths(e)
    P = e['P']
    fr, fw, fi = e['fr'], e['fw'], e['fi']
    rows = {}
    for v in itertools.product([0,1], repeat=N):
        t = sum(v[i] << i for i in range(5))
        cs, pend, rd, wr, rst, ck = v[5:]
        m = None
        if cs:
            if pend:
                if t in (0, 31) and rd and wr:
                    m = dict(t=0, cs=0 if (t == 0 and not rst) else 1, pend=1, ck=1-ck)
            else:
                if t in {0, fr, fw, fi}:
                    nt = 0
                    if t == fr and t and not rd: nt = t
                    if t == fw and t and not wr: nt = t
                    start = t == 0 and (not rd or not wr)
                    m = dict(t=nt, cs=0 if start else 1, pend=0, ck=1-ck)
        elif pend:
            if t in init and rd and wr:
                j = init.index(t)
                if j + 1 < len(init):
                    m = dict(t=init[j+1], cs=0, pend=1, ck=1-ck)
                else:
                    m = dict(t=fi, cs=1, pend=0, ck=1-ck)
        elif rd != wr:
            s = read if wr else write
            if t in s:
                j = s.index(t)
                if j + 1 < len(s):
                    m = dict(t=s[j+1], cs=0, pend=0, ck=P[j])
                else:
                    m = dict(t=fr if wr else fw, cs=1, pend=0, ck=P[j])
        rows[v] = m
    return rows

def cube(v):
    return sum((2 if b else 1) << (2*i) for i, b in enumerate(v))

def minimize_dc(on, dc):
    if not on: return []
    onc = [cube(v) for v in on]
    off = SP.complement(SP.single_cube_containment(onc + [cube(v) for v in dc]))
    cov = SP.expand(onc, off)
    res = list(cov)
    for c in sorted(cov, key=lambda c: (SP.size(c), c)):
        rest = [d for d in res if d != c]
        if all(any(p & ~d == 0 for d in rest) for p in onc if p & ~c == 0):
            res = rest
    return res

OUTS = [('t%d' % i, (lambda i: lambda m: (m['t'] >> i) & 1)(i)) for i in range(5)] + \
       [('CS_n', lambda m: m['cs']), ('PEND', lambda m: m['pend']), ('CPUCLK', lambda m: m['ck'])]

def sizes(e, covers=False):
    rows = build(e)
    dc = [v for v, m in rows.items() if m is None]
    out = {}
    for name, f in OUTS:
        on = [v for v, m in rows.items() if m is not None and f(m)]
        off = [v for v, m in rows.items() if m is not None and not f(m)]
        a = minimize_dc(on, dc); b = minimize_dc(off, dc)
        out[name] = (len(a), a, False) if len(a) <= len(b) else (len(b), b, True)
    return out if covers else {k: v[0] for k, v in out.items()}

def cost(s):
    return sum(v + 100 * max(0, v - 8) for v in s.values())

PATTERNS = {
    '3333': [(i // 3) % 2 for i in range(23)],
    '3434': [0,0,0,1,1,1,1,0,0,0,1,1,1,1,0,0,0,1,1,1,1,0,0],
    '4343': [0,0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0,0,1,1,1,0,0],
}

def random_enc(rng):
    d = rng.sample(range(1, 8), 4)
    R = rng.sample(range(12, 16), 4)
    e = dict(c1R=d[0], c1W=d[1], dH=d[2], dL=d[3], A=rng.sample(range(8, 12), 4),
             R=R, h8=rng.choice(R[:2]), h9=rng.choice(R[2:]),
             init=[0] + rng.sample(range(1, 8), 7), ih=rng.randrange(8, 16),
             fr=1 << rng.randrange(5), fw=1 << rng.randrange(5),
             fi=rng.choice([0, 1, 2, 4, 8, 16]), Pn=rng.choice(list(PATTERNS)))
    e['hr'] = rng.choice([k for k in R if k not in (e['h8'], e['h9'])])
    e['hw'] = rng.randrange(16)
    e['P'] = PATTERNS[e['Pn']]
    return e

def mutate(e, rng):
    e = json.loads(json.dumps(e))
    k = rng.randrange(9)
    if k == 0:
        keys = ['c1R', 'c1W', 'dH', 'dL']
        a = rng.choice(keys)
        used = {e[x] for x in keys}
        free = [x for x in range(1, 8) if x not in used]
        if free and rng.random() < 0.5:
            e[a] = rng.choice(free)
        else:
            b = rng.choice(keys); e[a], e[b] = e[b], e[a]
    elif k == 1:
        i, j = rng.sample(range(4), 2); e['A'][i], e['A'][j] = e['A'][j], e['A'][i]
    elif k == 2:
        R = rng.sample(range(12, 16), 4); e['R'] = R
        e['h8'] = rng.choice(R[:2]); e['h9'] = rng.choice(R[2:])
        e['hr'] = rng.choice([x for x in R if x not in (e['h8'], e['h9'])])
    elif k == 3:
        i, j = rng.sample(range(1, 8), 2); e['init'][i], e['init'][j] = e['init'][j], e['init'][i]
    elif k == 4:
        e['ih'] = rng.randrange(8, 16)
    elif k == 5:
        e['fr'] = 1 << rng.randrange(5); e['fw'] = 1 << rng.randrange(5)
    elif k == 6:
        e['fi'] = rng.choice([0, 1, 2, 4, 8, 16])
    elif k == 7:
        e['hw'] = rng.randrange(16)
    else:
        e['Pn'] = rng.choice(list(PATTERNS)); e['P'] = PATTERNS[e['Pn']]
    return e

if __name__ == '__main__':
    seed = int(sys.argv[1]); iters = int(sys.argv[2])
    rng = random.Random(seed)
    e = random_enc(rng)
    while not valid(e): e = random_enc(rng)
    s = sizes(e); c = cost(s)
    best = (c, e, s)
    import math
    for it in range(iters):
        T = 30 * (1 - it / iters) + 0.5
        n = mutate(e, rng)
        if not valid(n): continue
        ns = sizes(n); nc = cost(ns)
        if nc <= c or rng.random() < math.exp((c - nc) / T):
            e, s, c = n, ns, nc
            if c < best[0]:
                best = (c, e, s)
    print(json.dumps(dict(cost=best[0], sizes=best[2], enc=best[1])))
