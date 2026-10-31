import functools, itertools, json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
from regal.espresso import _Cover

VARS = ['t0','t1','t2','t3','t4','CS_n','PEND','RD_n','WR_n','CPUCLK']
N = len(VARS)
SP = _Cover(N)

# K values nobody drives: the SIO GAL drives K 0-3, the address buffers 8-11
UNDRIVEN = [4, 5, 6, 7, 12, 13, 14, 15]

def paths(e):
    read = [(0,0),(0,1),(e['c1'],0),(e['c1'],1)]
    write = [(0,0),(0,1),(e['c1'],0),(e['c1'],1)]
    for a in e['A']:
        read += [(a,0),(a,1)]; write += [(a,0),(a,1)]
    for d in e['dummy']:
        read += [(d,0),(d,1)]
    for d in (e['dH'], e['dL']):
        write += [(d,0),(d,1)]
    l1,l2,l3,l4 = e['R']
    read += [(l1,0),(l2,0),(e['h8'],1),(l3,0),(l4,0),(e['h9'],1),(e['hr'],1)]
    write += [(e['hw'],1)]
    t = lambda s: [2*k+b for k,b in s]
    return t(read), t(write)

def valid(e):
    r, w = paths(e)
    return len(set(r)) == len(r) and len(set(w)) == len(w)

def build(e):
    read, write = paths(e)
    P = e['P']
    fr, fw = e['fr'], e['fw']
    rows = {}
    for v in itertools.product([0,1], repeat=N):
        t = sum(v[i] << i for i in range(5))
        cs, pend, rd, wr, ck = v[5:]
        m = None
        if cs:
            # Idle (t = 0), waiting for the end of the bus cycle, or power-up
            # (t = 31, PEND set)
            if t in {0, fr, fw} or (t == 31 and pend and rd and wr):
                nt = 0
                if t == fr and t and not rd: nt |= fr
                if t == fw and t and not wr: nt |= fw
                start = t == 0 and (not rd or not wr)
                m = dict(t=nt, cs=0 if start else 1, pend=pend, ck=1-ck)
        elif rd != wr:
            s = read if wr else write
            if t in s:
                j = s.index(t)
                if j + 1 < len(s):
                    m = dict(t=s[j+1], cs=0, pend=pend, ck=P[j])
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

# Waiting state after a read: K 4, which nobody drives, as the RAM keeps
# driving SIO for up to tDIS = 20 ns after CS rises. Waiting states only
# have one bit set, so that leaving them only clears bits.
FR = 8

# 8052 clock after each transaction state: phases of 2 to 4 master clocks,
# periods of at most 7 (the slow phase may follow one fast phase)
P = [0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0]

def random_enc(rng):
    c = rng.sample([1, 2, 3], 3)
    u = rng.sample(UNDRIVEN, 6)
    R = u[2:]
    e = dict(c1=c[0], dH=c[1], dL=c[2], A=rng.sample(range(8, 12), 4),
             dummy=u[:2], R=R, h8=rng.choice(R[:2]), h9=rng.choice(R[2:]),
             fr=FR, fw=1 << rng.randrange(5), P=P)
    e['hr'] = rng.choice([k for k in UNDRIVEN
                          if k not in (e['h8'], e['h9']) + tuple(e['dummy'])])
    e['hw'] = rng.choice(UNDRIVEN)
    return e

def mutate(e, rng):
    e = json.loads(json.dumps(e))
    k = rng.randrange(6)
    if k == 0:
        a, b = rng.sample(['c1', 'dH', 'dL'], 2); e[a], e[b] = e[b], e[a]
    elif k == 1:
        i, j = rng.sample(range(4), 2); e['A'][i], e['A'][j] = e['A'][j], e['A'][i]
    elif k == 2:
        u = rng.sample(UNDRIVEN, 6)
        e['dummy'], e['R'] = u[:2], u[2:]
        e['h8'] = rng.choice(e['R'][:2]); e['h9'] = rng.choice(e['R'][2:])
        e['hr'] = rng.choice([x for x in UNDRIVEN
                              if x not in (e['h8'], e['h9']) + tuple(e['dummy'])])
    elif k == 3:
        e['fw'] = 1 << rng.randrange(5)
    elif k == 4:
        e['hw'] = rng.choice(UNDRIVEN)
    else:
        e['hr'] = rng.choice([x for x in UNDRIVEN
                              if x not in (e['h8'], e['h9']) + tuple(e['dummy'])])
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
