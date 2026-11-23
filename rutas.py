#!/usr/bin/env python3
"""Rutas de la Era Hiboria: calcula una ruta (tierra/mar, hasta 5 paradas) y dibuja un PNG.

Uso:
  python3 rutas.py HTML_RUTAS SALIDA.png ORIGEN DESTINO [--paradas "A,B"] [--evitar "Ghaza,Argos"] [--sin-mar] [--sin-red] [--embarque DIAS]
  python3 rutas.py HTML_RUTAS --lista        (lista de nombres validos)

HTML_RUTAS = rutas-hiboria.html del proyecto (lleva datos, mapa, red de ciudades y reglas incrustados).
Por defecto: red de ciudades vecinas (X=14 dias) y viaje por mar permitido. --sin-red = ruta directa hex a hex; --sin-mar = solo tierra.
Distancia estimada = hexagonos recorridos x 26 millas (hexagono de 30 millas vertice a vertice = 25,98 millas entre centros).
Por defecto se muestra en millas; con --km se convierte a kilometros (1 milla = 1,609344 km).
Modelo: 3 hex/dia en mar; tierra llanura 1 dia/hex, desierto/colinas/pantano/bosque/tundra 2, montana/jungla 3.
"""
import sys, re, json, io, base64, heapq, argparse, unicodedata
from PIL import Image, ImageDraw, ImageFont

NAMES = ['llanura', 'desierto', 'montaña', 'jungla', 'colinas', 'pantano', 'agua', 'bosque', 'tundra']
LC = [1, 2, 3, 3, 2, 2, 0, 2, 2]
SW = ['#d6c98a', '#e0b45c', '#6f6a66', '#1f6b33', '#a98650', '#5b8f86', '#6ccff5', '#78aa50', '#ecf2f6']


def load(path):
    s = open(path, encoding='utf8').read()
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', s, re.S)
    D = json.loads(m.group(1))
    m = re.search(r'data:image/jpeg;base64,([A-Za-z0-9+/=]+)', s)
    img = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert('RGB')
    me = re.search(r'<script id="edges" type="application/json">(.*?)</script>', s, re.S)
    mp = re.search(r'<script id="epaths" type="application/json">(.*?)</script>', s, re.S)
    E = json.loads(me.group(1)) if me and mp else None
    EP = json.loads(mp.group(1)) if me and mp else None
    return D, img, E, EP


def norm(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn').strip()


# ---------- geometria (cubo, flat-top odd-q) ----------
def cube(v, rows):
    c, r = divmod(v, rows)
    x = c; z = r - (c - (c & 1)) // 2
    return x, -x - z, z


def hdist(a, b, rows):
    A, B = cube(a, rows), cube(b, rows)
    return max(abs(A[0] - B[0]), abs(A[1] - B[1]), abs(A[2] - B[2]))


def hline(a, b, rows):
    A, B = cube(a, rows), cube(b, rows)
    n = max(abs(A[0] - B[0]), abs(A[1] - B[1]), abs(A[2] - B[2]))
    out = []
    for i in range(n + 1):
        t = i / n if n else 0
        f = [A[k] + (B[k] - A[k]) * t for k in range(3)]
        rx, ry, rz = round(f[0]), round(f[1]), round(f[2])
        dx, dy, dz = abs(rx - f[0]), abs(ry - f[1]), abs(rz - f[2])
        if dx > dy and dx > dz: rx = -ry - rz
        elif dy > dz: ry = -rx - rz
        else: rz = -rx - ry
        out.append(rx * rows + (rz + (rx - (rx & 1)) // 2))
    return out


class Net:
    def __init__(s, D, pf=1.0):
        s.pf = pf
        s.D = D; s.rows = D['rows']; s.cols = D['cols']
        s.N = s.rows * s.cols; s.K = len(D['nodes'])
        t = [int(ch, 36) for ch in D['terr']]
        s.t = t
        s.sea = [x >= 16 for x in t]
        s.cost = [LC[x & 15] * 3 * pf if (x & 15) != 6 else None for x in t]
        s.landNodes = {}; s.seaNodes = {}; s.bH = set(); s.bN = set(); s.shade = set()
        for k, n in enumerate(D['nodes']):
            if n[4] >= 0: s.landNodes.setdefault(n[4], []).append(k)
            for h in n[5]:
                s.seaNodes.setdefault(h, []).append((k, max(1, hdist(n[6], h, s.rows)) if n[6] >= 0 else 1))

    # ---- exclusiones ----
    PAL = [(110, 208, 245), (196, 223, 156), (250, 203, 223), (255, 251, 204), (195, 180, 139), (246, 150, 162), (246, 151, 121), (255, 255, 255)]

    def classes(s, img):
        """Color de relleno dominante de cada hexagono (indice de PAL, -1 si no se sabe)."""
        import numpy as np
        if hasattr(s, '_cls'): return s._cls
        a = np.asarray(img).astype(int); S = a.shape[1] / s.D['W']; R, h = s.D['R'], s.D['h']
        pal = np.array(Net.PAL); cls = []
        for v in range(s.N):
            c, r = divmod(v, s.rows)
            x, y = c * 1.5 * R * S, (r * h + (h / 2 if c % 2 else 0)) * S; rr = R * S * 0.75
            p = a[max(0, int(y - rr)):int(y + rr) + 1, max(0, int(x - rr)):int(x + rr) + 1].reshape(-1, 3)
            if len(p) == 0: cls.append(-1); continue
            d = np.abs(p[:, None, :] - pal[None]).max(2); m = d.argmin(1); ok = d.min(1) <= 26
            cls.append(int(np.bincount(m[ok], minlength=8).argmax()) if ok.sum() >= 3 else -1)
        s._cls = cls
        return cls

    def region(s, kingdom, img):
        """Hexagonos de tierra ininterrumpidos del mismo color que las ciudades del reino."""
        cls = s.classes(img); nodes = s.D['nodes']
        seeds = [n[4] for n in nodes if n[1] == kingdom and n[4] >= 0]
        votes = {}
        for sd in seeds:
            for v in [sd] + list(s.neigh(sd)):
                if cls[v] not in (-1, 0, 7): votes[cls[v]] = votes.get(cls[v], 0) + 1
        if not seeds or not votes: return set(seeds)
        c = max(votes, key=votes.get); seen = set(seeds); st = list(seeds)
        while st:
            u = st.pop()
            for v in s.neigh(u):
                if v in seen or s.sea[v]: continue
                if cls[v] == c or (cls[v] == -1 and sum(cls[w] == c for w in s.neigh(v)) >= 3):
                    seen.add(v); st.append(v)
        return seen

    def evitar(s, names, img, norm):
        """names: ciudades o paises. Devuelve descripcion de lo bloqueado."""
        nodes = s.D['nodes']; s.bH = set(); s.bN = set(); desc = []; s.shade = set()
        kings = sorted({n[1] for n in nodes})
        for q in names:
            qn = norm(q)
            kc = [k for k in kings if norm(k) == qn] or [k for k in kings if qn in norm(k)]
            cc = [i for i, n in enumerate(nodes) if norm(n[0]) == qn] or [i for i, n in enumerate(nodes) if qn in norm(n[0])]
            if len(kc) == 1 and (len(cc) != 1 or norm(kc[0]).startswith(qn)):
                reg = s.region(kc[0], img); s.bH |= reg; s.shade |= reg
                for i, n in enumerate(nodes):
                    if n[4] in reg or n[1] == kc[0]: s.bN.add(i)
                extra = sorted({n[1] for n in nodes if n[4] in reg and n[1] != kc[0]})
                desc.append(f"{kc[0].split(' (')[0]}: {len(reg)} hex. de tierra" + (f" (incluye ciudades de {', '.join(e.split(' (')[0] for e in extra)} por compartir color)" if extra else ''))
            elif len(cc) == 1:
                i = cc[0]; s.bN.add(i)
                if nodes[i][4] >= 0: s.bH.add(nodes[i][4])
                desc.append(nodes[i][0])
            else:
                sys.exit(f'--evitar: {q!r} no es una ciudad ni un pais unico ({[nodes[i][0] for i in cc][:5]} {kc[:3]})')
        return desc

    def neigh(s, v):
        rows, cols = s.rows, s.cols
        c, r = divmod(v, rows)
        d = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)] if c % 2 == 0 else \
            [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]
        for dc, dr in d:
            cc, rr = c + dc, r + dr
            if 0 <= cc < cols and 0 <= rr < rows: yield cc * rows + rr

    def acc(s, k, h):
        n = s.D['nodes'][k]
        return max(1, hdist(n[6], h, s.rows)) if n[6] >= 0 else 1

    def route(s, a, b, use_sea, extra_days, sea_only=False):
        N, K = s.N, s.K; extra = extra_days * 3; nodes = s.D['nodes']
        dist = {}; prev = {}; start = 2 * N + a
        dist[start] = 0; h = [(0, start)]; done = set()
        tg1, tg2 = 2 * N + b, 2 * N + K + b
        def relax(u, v, w):
            nd = dist[u] + w
            if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; heapq.heappush(h, (nd, v))
        while h:
            d, u = heapq.heappop(h)
            if u in done: continue
            done.add(u)
            if u == tg1 or u == tg2: break
            if u >= 2 * N + K:
                n = nodes[u - 2 * N - K]
                if n[4] >= 0: relax(u, n[4], 0)
            elif u >= 2 * N:
                n = nodes[u - 2 * N]
                if n[4] >= 0 and not sea_only: relax(u, n[4], 0)
                if use_sea:
                    for sh in n[5]: relax(u, N + sh, s.acc(u - 2 * N, sh) + extra)
            elif u < N:
                for v in s.neigh(u):
                    if s.cost[v] is not None and v not in s.bH: relax(u, v, s.cost[v])
                for k in s.landNodes.get(u, []):
                    if k not in s.bN: relax(u, 2 * N + k, 0)
            else:
                sh = u - N
                for v in s.neigh(sh):
                    if s.sea[v]: relax(u, N + v, 1)
                for k, c in s.seaNodes.get(sh, []):
                    if k not in s.bN: relax(u, 2 * N + K + k, c)
        tg = tg1 if dist.get(tg1, 1e18) <= dist.get(tg2, 1e18) else tg2
        if tg not in dist: return None
        path = []; v = tg
        while v is not None:
            path.append(v); v = prev.get(v)
        path.reverse()
        return dist[tg], path

    # ---- red de ciudades vecinas ----
    def net_init(s, E, EP):
        s.E = E; K = s.K
        s.LE = [(e[0], e[1], [e[2] * 3 * s.pf, e[3] * 3 * s.pf], EP[i]) for i, e in enumerate(E['land'])]
        s.ADJL = [[] for _ in range(K)]; s.ADJS = [[] for _ in range(K)]; s.BR = set()
        for i, e in enumerate(E['land']):
            s.ADJL[e[0]].append((e[1], i, 0)); s.ADJL[e[1]].append((e[0], i, 1))
            if len(e) > 4 and e[4]: s.BR.add((e[0], e[1])); s.BR.add((e[1], e[0]))
        for a, b, tab, tba in E['sea']:
            s.ADJS[a].append((b, tab)); s.ADJS[b].append((a, tba))
        s.cache = {}

    def landw(s, i, d):
        a, b, w, hx = s.LE[i]
        if not s.bH and not s.bN: return w[d]
        if a in s.bN or b in s.bN: return None
        if not any(h in s.bH for h in hx[d]): return w[d]
        if (i, d) not in s.cache:
            u, v = (b, a) if d else (a, b)
            r = s.route(u, v, False, 0)
            s.cache[(i, d)] = r[0] if r else None
        return s.cache[(i, d)]

    def netdj(s, a, b, use_sea, extra):
        K = s.K; dist = {a: 0}; prev = {}; pk = {}; done = set(); h = [(0, a)]
        while h:
            d, u = heapq.heappop(h)
            if u in done: continue
            done.add(u)
            if u == b: break
            for v, i, dr in s.ADJL[u]:
                if v in s.bN: continue
                w = s.landw(i, dr)
                if w is None: continue
                if d + w < dist.get(v, 1e18): dist[v] = d + w; prev[v] = u; pk[v] = 0; heapq.heappush(h, (d + w, v))
            if use_sea:
                for v, t in s.ADJS[u]:
                    if v in s.bN: continue
                    nd = d + t + extra * 3
                    if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; pk[v] = 1; heapq.heappush(h, (nd, v))
        return dist, prev, pk

    def netpath(s, a, t, res, extra):
        dist, prev, pk = res
        if t not in dist: return None
        seq = []; v = t
        while v is not None:
            seq.append(v); v = prev.get(v)
        seq.reverse(); path = [2 * s.N + a]
        for i in range(1, len(seq)):
            u, v = seq[i - 1], seq[i]
            r = s.route(u, v, True, extra, True) if pk[v] == 1 else s.route(u, v, False, 0)
            if not r: return None
            path += r[1][1:]
        return dist[t], path

    def netroute(s, a, b, use_sea, extra):
        return s.netpath(a, b, s.netdj(a, b, use_sea, extra), extra)

    def netnearest(s, a, b, use_sea, extra):
        res = s.netdj(a, -1, use_sea, extra); nb = s.D['nodes'][b]; best = -1; bd = 1e18
        for k in res[0]:
            if k in s.bN: continue
            n = s.D['nodes'][k]; d = ((n[2] - nb[2]) ** 2 + (n[3] - nb[3]) ** 2) ** .5
            if d < bd: bd = d; best = k
        if best < 0: return None
        return best, (None if best == a else s.netpath(a, best, res, extra))

    def legs(s, path, extra_days):
        N, K = s.N, s.K; nodes = s.D['nodes']
        nk = lambda v: v - 2 * N - K if v >= 2 * N + K else v - 2 * N
        out = []; start = nk(path[0]); seg = []
        for v in path[1:]:
            if v >= 2 * N:
                end = nk(v)
                if seg:
                    sea = seg[0] >= N
                    t = 0; counts = [0] * 9; acc = []; passed = []; hx = 0
                    if sea:
                        f0, l0 = seg[0] - N, seg[-1] - N
                        ca, cb = s.acc(start, f0), s.acc(end, l0)
                        t = ca + (len(seg) - 1) + cb + extra_days * 3
                        hx = ca + cb + len(seg) - 1
                        ps, pe = nodes[start][6], nodes[end][6]
                        if ps >= 0: acc += hline(ps, f0, s.rows)
                        if pe >= 0: acc += hline(l0, pe, s.rows)
                    else:
                        for j, hh in enumerate(seg):
                            if j > 0:
                                t += s.cost[hh]; counts[s.t[hh] & 15] += 1
                            if j > 0 and j < len(seg) - 1:
                                for k in s.landNodes.get(hh, []):
                                    if k not in (start, end): passed.append(nodes[k][0])
                    if sea or len(seg) > 1:
                        out.append(dict(sea=sea, a=start, b=end, hexes=hx if sea else len(seg) - 1, t=t,
                                        counts=counts, passed=passed, verts=seg, acc=acc))
                start = end; seg = []
            else:
                seg.append(v)
        return out


UNIT_KM = '--km' in sys.argv
if UNIT_KM:
    sys.argv.remove('--km')

def km(n):
    v = n * 15 * 3 ** .5 * (1.609344 if UNIT_KM else 1)
    return f'{round(v):,}'.replace(',', '.') + (' km' if UNIT_KM else ' mi')


def fmt(t):
    d = t / 3
    return (f'{d:.1f}'.rstrip('0').rstrip('.')).replace('.', ',')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html'); ap.add_argument('out', nargs='?'); ap.add_argument('origen', nargs='?'); ap.add_argument('destino', nargs='?')
    ap.add_argument('--paradas', default=''); ap.add_argument('--sin-mar', action='store_true'); ap.add_argument('--sin-red', action='store_true', help='ruta directa hex a hex en lugar de la red de ciudades vecinas')
    ap.add_argument('--embarque', type=float, default=0.0); ap.add_argument('--lista', action='store_true')
    ap.add_argument('--evitar', default='', help='ciudades o paises a evitar, separados por comas')
    ap.add_argument('--escala', type=float, default=1.0, help='escala del mapa (1 = 3850 px de ancho)')
    ap.add_argument('--ritmo', default='pie', help='ritmo en tierra: pie (26 mi/dia), caravana (18), ejercito (18), caballo (40) o un numero de millas/dia')
    a = ap.parse_args()
    D, img0, E, EP = load(a.html)
    nodes = D['nodes']
    if a.lista:
        for n in sorted(nodes, key=lambda n: norm(n[0])): print(f'{n[0]} | {n[1]}')
        return
    byname = {norm(n[0]): i for i, n in enumerate(nodes)}
    def find(q):
        q = norm(q)
        if q in byname: return byname[q]
        c = [i for k, i in byname.items() if q in k]
        if len(c) == 1: return c[0]
        sys.exit(f'Nombre no valido o ambiguo: {q!r} ({[nodes[i][0] for i in c][:6]})')
    pts = [find(a.origen)] + [find(x) for x in a.paradas.split(',') if x.strip()] + [find(a.destino)]
    if len(pts) > 7: sys.exit('Maximo 5 paradas')
    RITMOS = {'pie': 26, 'caravana': 18, 'ejercito': 18, 'ejército': 18, 'caballo': 40}
    try: mpd = RITMOS.get(norm(a.ritmo)) or float(a.ritmo)
    except ValueError: sys.exit(f'--ritmo no valido: {a.ritmo!r} (pie, caravana, ejercito, caballo o millas/dia)')
    if mpd <= 0: sys.exit('--ritmo debe ser positivo')
    PF = 26 / mpd
    P = Net(D, PF); use_sea = not a.sin_mar
    net_on = not a.sin_red
    if net_on and E is None:
        print('AVISO: el HTML no lleva la red de ciudades; uso ruta directa.', file=sys.stderr); net_on = False
    if net_on: P.net_init(E, EP)
    partial = None
    desc_ev = P.evitar([x for x in a.evitar.split(',') if x.strip()], img0, norm) if a.evitar.strip() else []
    for k in pts:
        if k in P.bN or (nodes[k][4] >= 0 and nodes[k][4] in P.bH):
            sys.exit(f'{nodes[k][0]} esta dentro de lo que quieres evitar')
    stages = []
    for i in range(len(pts) - 1):
        if pts[i] == pts[i + 1]: continue
        r = P.netroute(pts[i], pts[i + 1], use_sea, a.embarque) if net_on else P.route(pts[i], pts[i + 1], use_sea, a.embarque)
        to = pts[i + 1]
        if not r and net_on:
            q = P.netnearest(pts[i], pts[i + 1], use_sea, a.embarque)
            partial = (pts[i + 1], q[0] if q else pts[i], i < len(pts) - 2)
            if q and q[1]: stages.append((pts[i], q[0], q[1][0], q[1][1], P.legs(q[1][1], a.embarque)))
            break
        if not r: sys.exit(f'Sin ruta entre {nodes[pts[i]][0]} y {nodes[pts[i+1]][0]}' + ('' if use_sea else ' (prueba sin --sin-mar)'))
        stages.append((pts[i], pts[i + 1], r[0], r[1], P.legs(r[1], a.embarque)))
    if not stages: sys.exit('No se puede avanzar desde el origen hacia el destino con las exclusiones actuales.' if partial else 'Origen y destino son el mismo lugar.')
    tot = sum(s[2] for s in stages)

    # ---------- dibujo ----------
    S = a.escala
    img = img0.resize((round(D['W'] * a.escala), round(D['H'] * a.escala)))
    R, h = D['R'] * a.escala, D['h'] * a.escala
    cen = lambda v: ((v // D['rows']) * 1.5 * R, (v % D['rows']) * h + (h / 2 if (v // D['rows']) % 2 else 0))
    hexv = lambda v: [(cen(v)[0] + R * __import__('math').cos(__import__('math').pi / 3 * i),
                       cen(v)[1] + R * __import__('math').sin(__import__('math').pi / 3 * i)) for i in range(6)]
    over = Image.new('RGBA', img.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(over)
    allv = []
    for v in P.shade: dr.polygon(hexv(v), fill=(40, 40, 40, 70))
    def paint(v, sea):
        c = SW[6] if sea else SW[P.t[v] & 15]
        rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        pts_ = hexv(v)
        dr.polygon(pts_, fill=rgb + (215,))
        dr.line(pts_ + [pts_[0]], fill=(109, 40, 217, 255) if sea else (217, 45, 32, 255), width=3, joint='curve')
        allv.append(v)
    for _, _, _, path, legs in stages:
        for v in path:
            if v < 2 * P.N: paint(v % P.N, v >= P.N)
        for l in legs:
            for v in l['acc']: paint(v, True)
    img = Image.alpha_composite(img.convert('RGBA'), over).convert('RGB'); dr = ImageDraw.Draw(img)
    F = lambda sz, b=False: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if b else ''), sz)
    def dot(k, col, big=True, num=None):
        n = nodes[k]; x, y = n[2] * S, n[3] * S; r = 9 if big else 5
        dr.ellipse((x - r, y - r, x + r, y + r), fill=col, outline='white', width=3)
        if num: dr.text((x, y), num, fill='white', font=F(11, True), anchor='mm')
        dr.text((x + 12, y - 8), n[0], fill='#111', font=F(15, True), anchor='ls', stroke_width=3, stroke_fill='white')
    for s in stages:
        for l in s[4]:
            for nm in l['passed']: dot(byname[norm(nm)], '#444')
            if l['b'] != pts[-1]: dot(l['b'], '#6d28d9')
    for i, k in enumerate(pts[1:-1]): dot(k, '#b45309', num=str(i + 1))
    dot(pts[0], '#14733f', num='A'); dot(pts[-1], '#111', num='B')
    xs = [cen(v)[0] for v in allv]; ys = [cen(v)[1] for v in allv]
    m = 90
    box = (max(0, int(min(xs) - m)), max(0, int(min(ys) - m)), min(img.width, int(max(xs) + m)), min(img.height, int(max(ys) + m)))
    if box[2] - box[0] < 700: c = (box[0] + box[2]) // 2; box = (max(0, c - 350), box[1], min(img.width, c + 350), box[3])
    if box[3] - box[1] < 450: c = (box[1] + box[3]) // 2; box = (box[0], max(0, c - 225), box[2], min(img.height, c + 225))
    crop = img.crop(box)

    # ---------- panel de leyenda ----------
    th = [0] * 9; sh = 0; st = 0; emb = 0; tl = 0
    for s in stages:
        for l in s[4]:
            if l['sea']: sh += l['hexes']; st += l['t'] - a.embarque * 3; emb += a.embarque * 3
            else:
                tl += l['t']
                for i, n in enumerate(l['counts']): th[i] += n
    hl = sum(th)
    lines = [('t', f"{nodes[pts[0]][0]} → {nodes[pts[-1]][0]}"),
             ('b', f"{fmt(tot)} días  ·  ≈ {km(hl + sh)}" + (f"  ·  {len(pts)-2} parada(s)" if len(pts) > 2 else '')),
             ('s', f"Tierra {fmt(tl)} d ({km(hl)})  ·  Mar {fmt(st)} d ({km(sh)})" + (f"  ·  Embarque {fmt(emb)} d" if emb else ''))]
    lines.append(('s', ('Red de ciudades vecinas' if net_on else 'Ruta directa') + f"  ·  Ritmo en tierra: {mpd:g} {'km' if UNIT_KM else 'mi'}/día".replace(f'{mpd:g} km', f'{round(mpd * 1.609344)} km')))
    if desc_ev: lines.append(('s', 'Evitado: ' + '; '.join(desc_ev)))
    rows_t = []
    for i, n in enumerate(th):
        if n: rows_t.append((SW[i], NAMES[i].capitalize(), f'{n} hex. · {km(n)}', f'{fmt(n * LC[i] * 3 * PF)} d'))
    if sh: rows_t.append(('#6ccff5', 'Mar', f'{sh} hex. · {km(sh)}', f'{fmt(st)} d'))
    if emb: rows_t.append(('#999999', 'Embarque', '', f'{fmt(emb)} d'))
    steps = []
    multi = len(stages) > 1
    for si, s in enumerate(stages):
        if multi: steps.append(('h', f'Etapa {si+1}: {nodes[s[0]][0]} → {nodes[s[1]][0]}  ({fmt(s[2])} d)'))
        for l in s[4]:
            txt = f"{'Mar' if l['sea'] else 'Tierra'}: {nodes[l['a']][0]} → {nodes[l['b']][0]}  ·  {l['hexes']} hex. ({km(l['hexes'])})  ·  {fmt(l['t'])} d"
            steps.append(('l', txt))
    PW = 640; pad = 18; lh = 22
    import textwrap
    ev_lines = textwrap.wrap('Evitado: ' + '; '.join(desc_ev), 70) if desc_ev else []
    if partial:
        ev_lines += textwrap.wrap(f"SIN RUTA hasta {nodes[partial[0]][0]}: se llega hasta {nodes[partial[1]][0]}, la ciudad alcanzable mas cercana." + (' Paradas siguientes no calculadas.' if partial[2] else ''), 70)
    ph = pad * 2 + 34 + 30 + 24 + 26 + 18 * len(ev_lines) + (len(rows_t) + 2) * lh + 20 + len(steps) * lh + 10
    W = crop.width + PW; H = max(crop.height, ph)
    out = Image.new('RGB', (W, H), 'white'); out.paste(crop, (0, 0))
    d = ImageDraw.Draw(out); x = crop.width + pad; y = pad
    d.text((x, y), lines[0][1], fill='#111', font=F(19, True)); y += 34
    d.text((x, y), lines[1][1], fill='#b3261e', font=F(26, True)); y += 36
    d.text((x, y), lines[2][1], fill='#444', font=F(14)); y += 30
    for ln in ev_lines: d.text((x, y - 4), ln, fill='#7a130c', font=F(13)); y += 18
    if ev_lines: y += 10
    d.text((x, y), 'Días por tipo de terreno', fill='#111', font=F(15, True)); y += 26
    for col, nm, hx, dd in rows_t:
        d.rectangle((x, y + 3, x + 14, y + 17), fill=col, outline='#888'); d.text((x + 24, y), nm, fill='#222', font=F(14))
        d.text((x + 300, y), hx, fill='#222', font=F(14)); d.text((x + PW - 2 * pad, y), dd, fill='#222', font=F(14), anchor='ra'); y += lh
    d.line((x, y + 3, x + PW - 2 * pad, y + 3), fill='#aaa'); y += 8
    d.text((x + 24, y), 'Total', fill='#111', font=F(14, True)); d.text((x + 300, y), f'{hl + sh} hex. · {km(hl + sh)}', fill='#111', font=F(14, True)); d.text((x + PW - 2 * pad, y), f'{fmt(tot)} d', fill='#111', font=F(14, True), anchor='ra'); y += lh + 14
    for kind, txt in steps:
        if kind == 'h': d.text((x, y), txt, fill='#111', font=F(13, True))
        else:
            d.text((x, y), txt[:70], fill='#333', font=F(12))
        y += lh
    out.save(a.out)
    fin = nodes[stages[-1][1]][0]
    print(f'{fmt(tot)} dias, ~{km(hl + sh)}: {nodes[pts[0]][0]} -> {fin}  ({"red de ciudades" if net_on else "ruta directa"}; guardado en {a.out})')
    if partial: print(f'AVISO: no hay ruta hasta {nodes[partial[0]][0]}; se muestra hasta {fin}, la ciudad alcanzable mas cercana.')


main()
