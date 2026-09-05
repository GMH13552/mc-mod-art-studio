#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 16x16 水晶法杖结构：棕色细柄 + 顶部独立水晶簇（非实心三角）。"""
import sys
from PIL import Image

def main(path: str) -> int:
    im = Image.open(path).convert('RGBA')
    px = im.load()
    opaque = sum(1 for r, g, b, a in im.getdata() if a > 0)
    brown = 0
    teal = 0
    top_teal: set[tuple[int, int]] = set()
    for y in range(16):
        for x in range(16):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if r > g + 20 and r > b + 20:
                brown += 1
            elif g >= r and g >= b and (g > 40 or b > 40):
                teal += 1
                if y <= 9:
                    top_teal.add((x, y))
    # 顶部水晶连通块（4邻域）
    seen = set()
    comps = []
    for p in top_teal:
        if p in seen:
            continue
        stack = [p]
        seen.add(p)
        n = 0
        while stack:
            x, y = stack.pop()
            n += 1
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                q = (x+dx, y+dy)
                if q in top_teal and q not in seen:
                    seen.add(q)
                    stack.append(q)
        comps.append(n)
    comps.sort(reverse=True)
    # 下半部（y>=10）每行不透明宽度
    widths = []
    for y in range(10, 16):
        w = sum(1 for x in range(16) if px[x, y][3] > 0)
        widths.append(w)
    max_lower = max(widths) if widths else 0

    print("opaque pixels :", opaque)
    print("brown handle  :", brown)
    print("teal crystal  :", teal)
    print("top components:", comps)
    print("handle row widths (y10-15):", widths, "max=", max_lower)

    ok = True
    if opaque < 20:
        print("FAIL: too few opaque pixels"); ok = False
    if brown < 6:
        print("FAIL: no clear brown handle"); ok = False
    if teal < 8:
        print("FAIL: no clear teal crystal cluster"); ok = False
    if len([c for c in comps if c >= 2]) < 2:
        print("FAIL: crystal cluster not separated into >=2 pieces"); ok = False
    if max_lower > 4:
        print("FAIL: lower body too thick (looks like wedge), max row=%d" % max_lower); ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
