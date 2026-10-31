# Writes seq.v, sio.v and encoding.py for a state assignment found by
# search.py: python gen.py encoding.json ..
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from search import sizes, paths, VARS, N

NAMES = dict(t0='SCK', t1='K0', t2='K1', t3='K2', t4='K3')
OUTN = dict(t0='SCK', t1='K0', t2='K1', t3='K2', t4='K3', CS_n='CS_n', PEND='PEND', CPUCLK='CPUCLK')

def term(c):
    lits = []
    for i in range(N):
        b = (c >> (2 * i)) & 3
        name = NAMES.get(VARS[i], VARS[i])
        if b == 1: lits.append('!' + name)
        elif b == 2: lits.append(name)
    return ' & '.join(lits) or "1'b1"

def describe(e):
    read, write, init = paths(e)
    f = lambda s: ' '.join(str(x) for x in s)
    return read, write, init

def emit(e, outdir):
    cov = sizes(e, covers=True)
    read, write, init = paths(e)
    lines = []
    for name in ['t0', 't1', 't2', 't3', 't4', 'CS_n', 'PEND', 'CPUCLK']:
        n, c, inv = cov[name]
        body = '\n    | '.join('(' + term(x) + ')' for x in c) if c else "1'b0"
        lines.append('// {} product terms\nwire {}_next = {}({});'.format(
            n, OUTN[name], '!' if inv else '', body))
    eqs = '\n\n'.join(lines)
    st = lambda s: ', '.join(str(x) for x in s)
    v = open(os.path.join(HERE, 'seq_template.v')).read()
    v = v.replace('@READ@', st(read)).replace('@WRITE@', st(write)).replace('@INIT@', st(init))
    v = v.replace('@FR@', str(e['fr'])).replace('@FW@', str(e['fw'])).replace('@FI@', str(e['fi']))
    v = v.replace('@EQS@', eqs)
    for k in ['c1R', 'c1W', 'dH', 'dL']:
        v = v.replace('@%s@' % k, str(e[k]))
    v = v.replace('@A@', ', '.join(str(a) for a in e['A']))
    open(outdir + '/seq.v', 'w').write(v)

    eq = [0, 0, 1, 1, 1, 0, 0, 0]
    ones = sorted(k for i, k in enumerate(e['init']) if eq[i])
    s = open(os.path.join(HERE, 'sio_template.v')).read()
    s = s.replace('@EQIO@', ' || '.join('k == %d' % k for k in ones))
    for k in ['c1R', 'c1W', 'dH', 'dL']:
        s = s.replace('@%s@' % k, str(e[k]))
    open(outdir + '/sio.v', 'w').write(s)
    open(outdir + '/encoding.py', 'w').write(
        '# Nibble numbers (K) of A15-12, A11-8, A7-4 and A3-0: the 74AC138\n'
        '# output enabled for each K must enable that nibble\'s 74AC244 half\n'
        'ADDRESS_K = {}\n'.format(e['A']))

if __name__ == '__main__':
    e = json.load(open(sys.argv[1]))
    emit(e, sys.argv[2])
