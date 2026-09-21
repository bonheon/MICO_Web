# -*- coding: utf-8 -*-
"""학습 코드 흐름 페이지(guide_code_flow.html) 레이아웃 점검.

노드·프레임 좌표를 손으로 적는 구조라, 노드를 추가하거나 옮기면
상자가 겹치거나 글자가 잘리는 것을 눈으로 놓치기 쉽다.
이 스크립트는 화면을 띄우지 않고 좌표만으로 아래를 검사한다.

  1. 글자 넘침   — 제목/부제 글자 폭이 상자 너비를 넘는가
  2. 상자 간격   — 겹치거나, 가로 40px·세로 30px 보다 가까운가
                   (노드 클릭 판정 영역이 ±12 라 26px 면 서로 닿는다)
  3. 프레임 여백 — for 루프 점선 박스의 상하좌우 여백이 24px 미만인가
  4. 프레임 라벨 — 박스 제목 글자가 안쪽 노드를 덮는가
  5. 엣지 라벨   — 화살표 라벨이 상자를 덮거나 상자 사이 간격보다 넓은가

실행:  python3 tools/flow_audit.py
반환:  문제가 하나라도 있으면 종료 코드 1
"""
import io
import re
import sys
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / 'setup_mico' / 'templates' / 'setup_mico' / 'guide_code_flow.html'

# 노드 본문 여백(좌 17 / 우 14) · 클릭 판정 여유(±12) 기준값
MIN_GAP_X = 40
MIN_GAP_Y = 30
MIN_FRAME_PAD = 24


def parse_nodes(block):
    out = []
    for m in re.finditer(
            r"\{ id:'(\w+)',\s*g:'(\w+)',\s*x:(-?\d+),\s*y:(-?\d+),"
            r"\s*w:(\d+),\s*h:(\d+),\s*t:'([^']*)',\s*s:'([^']*)'", block):
        out.append(dict(id=m.group(1), g=m.group(2), x=int(m.group(3)), y=int(m.group(4)),
                        w=int(m.group(5)), h=int(m.group(6)), t=m.group(7), s=m.group(8)))
    return out


def parse_frames(block):
    out = []
    for m in re.finditer(
            r"\{ x:(-?\d+),\s*y:(-?\d+),\s*w:(\d+),\s*h:(\d+),\s*\n?\s*"
            r"t:'([^']*)'(?:,\s*\n?\s*s:'([^']*)')?", block):
        out.append(dict(x=int(m.group(1)), y=int(m.group(2)), w=int(m.group(3)),
                        h=int(m.group(4)), t=m.group(5), s=m.group(6) or ''))
    return out


def parse_edges(block):
    return [(m.group(1), m.group(2), m.group(3) or '') for m in re.finditer(
        r"\{\s*a:'(\w+)',\s*b:'(\w+)'(?:,\s*r:'\w+')?(?:,\s*c:1)?(?:,\s*l:'([^']*)')?", block)]


def txtw(t, px):
    """대략적인 글자 폭. 한글은 px, 영문·숫자는 0.56배로 본다."""
    return sum(px if ord(ch) > 0x1100 else px * 0.56 for ch in t)


def audit(name, nodes, frames, edges):
    print('\n== %s ==' % name)
    byid = {n['id']: n for n in nodes}
    prob = []

    for n in nodes:
        avail = n['w'] - 17 - 14
        if txtw(n['t'], 16) > avail:
            prob.append('글자넘침 %s 제목 (%.0f > %d)' % (n['id'], txtw(n['t'], 16), avail))
        if txtw(n['s'], 12) > avail:
            prob.append('글자넘침 %s 부제 (%.0f > %d)' % (n['id'], txtw(n['s'], 12), avail))

    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            gx = max(a['x'] - (b['x'] + b['w']), b['x'] - (a['x'] + a['w']))
            gy = max(a['y'] - (b['y'] + b['h']), b['y'] - (a['y'] + a['h']))
            if gx < 0 and gy < 0:
                prob.append('노드겹침 %s ~ %s' % (a['id'], b['id']))
            elif gx < MIN_GAP_X and gy < 0:
                prob.append('가로간격 %s ~ %s = %d' % (a['id'], b['id'], gx))
            elif gy < MIN_GAP_Y and gx < 0:
                prob.append('세로간격 %s ~ %s = %d' % (a['id'], b['id'], gy))

    for k, f in enumerate(frames):
        inside = [n for n in nodes
                  if n['x'] >= f['x'] - 40 and n['x'] + n['w'] <= f['x'] + f['w'] + 40
                  and n['y'] >= f['y'] - 40 and n['y'] + n['h'] <= f['y'] + f['h'] + 40]
        if not inside:
            prob.append('프레임%d 안에 노드 없음' % k)
            continue
        l = min(n['x'] for n in inside) - f['x']
        r = (f['x'] + f['w']) - max(n['x'] + n['w'] for n in inside)
        t = min(n['y'] for n in inside) - f['y']
        b = (f['y'] + f['h']) - max(n['y'] + n['h'] for n in inside)
        print('   프레임%d "%s" 여백 L%d R%d T%d B%d  (노드 %d개)'
              % (k, f['t'][:26], l, r, t, b, len(inside)))
        for side, v in (('L', l), ('R', r), ('T', t), ('B', b)):
            if v < MIN_FRAME_PAD:
                prob.append('프레임%d 여백 %s=%d 부족' % (k, side, v))
        lw = max(txtw(f['t'], 13), txtw(f['s'], 11.5))
        band = 52 if f['s'] else 34          # 라벨이 두 줄이면 52, 한 줄이면 34
        for n in inside:
            if n['y'] < f['y'] + band and n['x'] < f['x'] + 18 + lw and n['x'] + n['w'] > f['x'] + 18:
                prob.append('프레임%d 라벨이 %s 와 겹침' % (k, n['id']))
        for k2, f2 in enumerate(frames[k + 1:], k + 1):
            lw2 = max(txtw(f2['t'], 13), txtw(f2['s'], 11.5))
            if abs(f['y'] - f2['y']) < 40 and not (
                    f['x'] + 18 + lw < f2['x'] + 18 or f2['x'] + 18 + lw2 < f['x'] + 18):
                prob.append('프레임%d·%d 라벨 겹침' % (k, k2))

    # 엣지 라벨 위치는 route() 와 같은 규칙으로 다시 계산한다
    for a, b, l in edges:
        if not l or a not in byid or b not in byid:
            continue
        A, B = byid[a], byid[b]
        ax, ay = A['x'] + A['w'], A['y'] + A['h'] / 2.0
        bx, by = B['x'], B['y'] + B['h'] / 2.0
        if bx >= ax - 2:
            lx, ly = (ax + bx) / 2.0, (ay + by) / 2.0 - 9
        else:
            lx = ((A['x'] + A['w'] / 2.0) + (B['x'] + B['w'] / 2.0)) / 2.0
            ly = ((A['y'] + A['h']) + B['y']) / 2.0 - 9
        w = txtw(l, 11) + 14
        x0, x1, y0, y1 = lx - w / 2, lx + w / 2, ly - 12, ly + 6
        for n in nodes:
            if x0 < n['x'] + n['w'] and x1 > n['x'] and y0 < n['y'] + n['h'] and y1 > n['y']:
                prob.append('엣지라벨 "%s" 가 %s 를 덮음' % (l, n['id']))
        if bx >= ax - 2 and w > (bx - ax) - 16:
            prob.append('엣지라벨 "%s" 폭 %.0f > 간격 %d (%s→%s)' % (l, w, bx - ax, a, b))

    for p in sorted(set(prob)):
        print('   ! ' + p)
    if not prob:
        print('   이상 없음')
    return prob


def main():
    if not HTML.exists():
        sys.exit('파일을 찾을 수 없음: %s' % HTML)
    src = io.open(HTML, encoding='utf-8').read()
    problems = []

    problems += audit('MAIN',
                      parse_nodes(re.search(r'var MAIN_NODES = \[(.*?)\n  \];', src, re.S).group(1)),
                      parse_frames(re.search(r'var MAIN_FRAMES = \[(.*?)\n  \];', src, re.S).group(1)),
                      parse_edges(re.search(r'var MAIN_EDGES = \[(.*?)\n  \];', src, re.S).group(1)))

    sub = src[src.index('  var SUBS = {'):src.index('  /* ── 렌더링 ──')]
    keys = list(re.finditer(r"\n  (\w+): \{\n", sub))
    for i, m in enumerate(keys):
        j = keys[i + 1].start() if i + 1 < len(keys) else len(sub)
        b = sub[m.start():j]
        nb = b[b.index('nodes: ['):b.index('edges: [')] if 'nodes: [' in b else ''
        fb = b[b.index('frames: ['):b.index('nodes: [')] if 'frames: [' in b else ''
        eb = b[b.index('edges: ['):b.index('    d: {')] if 'edges: [' in b else ''
        problems += audit(m.group(1), parse_nodes(nb), parse_frames(fb), parse_edges(eb))

    print('\n%s' % ('문제 %d건' % len(problems) if problems else '전체 이상 없음'))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
