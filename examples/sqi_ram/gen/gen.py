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

def emit(e, outdir):
    cov = sizes(e, covers=True)
    read, write = paths(e)
    lines = []
    for name in ['t0', 't1', 't2', 't3', 't4', 'CS_n', 'PEND', 'CPUCLK']:
        n, c, inv = cov[name]
        body = '\n    | '.join('(' + term(x) + ')' for x in c) if c else "1'b0"
        lines.append('// {} product terms\nwire {}_next = {}({});'.format(
            n, OUTN[name], '!' if inv else '', body))
    eqs = '\n\n'.join(lines)
    st = lambda s: ', '.join(str(x) for x in s)
    v = open(os.path.join(HERE, 'seq_template.v')).read()
    v = v.replace('@READ@', st(read)).replace('@WRITE@', st(write))
    v = v.replace('@FR@', str(e['fr'])).replace('@FW@', str(e['fw']))
    v = v.replace('@EQS@', eqs)
    for k in ['c1', 'dH', 'dL']:
        v = v.replace('@%s@' % k, str(e[k]))
    v = v.replace('@DUMMY@', ' and '.join(str(d) for d in e['dummy']))
    v = v.replace('@A@', ', '.join(str(a) for a in e['A']))
    open(outdir + '/seq.v', 'w').write(v)

    s = open(os.path.join(HERE, 'sio_template.v')).read()
    for k in ['c1', 'dH', 'dL']:
        s = s.replace('@%s@' % k, str(e[k]))
    open(outdir + '/sio.v', 'w').write(s)
    open(outdir + '/encoding.py', 'w').write(
        '# Nibble numbers (K) of A15-12, A11-8, A7-4 and A3-0: the 74AC138\n'
        '# output enabled for each K must enable that nibble\'s 74AC244 half\n'
        'ADDRESS_K = {}\n'.format(e['A']))

if __name__ == '__main__':
    e = json.load(open(sys.argv[1]))
    emit(e, sys.argv[2])
