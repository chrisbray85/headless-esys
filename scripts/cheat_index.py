#!/usr/bin/env python3
"""Build cheatsheets/INDEX.md from the community cheat-sheet XMLs in cheatsheets/.

Usage: python scripts/cheat_index.py            (writes cheatsheets/INDEX.md)
       python scripts/cheat_index.py S18A       (filter to one series, prints to stdout)

Each XML is the E-Sys Launcher / EsysUltra "FDL cheat" format:
  <cafd id=".." name="ECU" author=".." series="S18A,..."><code description=".."><function comment="PROP">value</function>..
"""
import re, sys, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent / "cheatsheets"
CAFD = re.compile(r'<cafd\s+([^>]*)>(.*?)</cafd>', re.S)
ATTR = re.compile(r'(\w+)="([^"]*)"')
CODE = re.compile(r'<code\s+description="([^"]*)">(.*?)</code>', re.S)
FUNC = re.compile(r'<function([^>]*)>([^<]*)</function>')


def entries(only_series=None):
    for xml in sorted(ROOT.glob("*.xml")):
        text = xml.read_text(encoding="utf-8", errors="ignore")
        for m in CAFD.finditer(text):
            a = dict(ATTR.findall(m.group(1)))
            series = a.get("series", "")
            if only_series and only_series not in series:
                continue
            for c in CODE.finditer(m.group(2)):
                props = []
                for fa, val in FUNC.findall(c.group(2)):
                    cm = re.search(r'comment="([^"]*)"', fa)
                    props.append(f"{(cm.group(1) if cm else '?').split(' (')[0]} = {val.strip()}")
                yield dict(series=series, ecu=a.get("name", "?"), cafd=a.get("id", "?"),
                           desc=c.group(1).strip(), props="; ".join(props),
                           author=a.get("author", xml.stem), file=xml.name)


def table(rows):
    out = ["| Series | ECU | CAFD | Cheat | Properties | Author / file |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['series']} | {r['ecu']} | {r['cafd']} | {r['desc'].replace('|', '/')} | "
                   f"`{r['props'].replace('|', '/')}` | {r['author']} / {r['file']} |")
    return "\n".join(out)


def main():
    if len(sys.argv) > 1:
        print(table(list(entries(sys.argv[1]))))
        return
    rows = list(entries())
    by_series = collections.defaultdict(list)
    for r in rows:
        for s in [x.strip() for x in r["series"].split(",") if x.strip()]:
            by_series[s].append(r)
    md = ["# Cheat-sheet index", "",
          f"Generated from {len(list(ROOT.glob('*.xml')))} XML files, {len(rows)} entries. "
          "Regenerate with `python scripts/cheat_index.py`. Series codes: S18A = G20/G21 "
          "3-series, F001/F010 = F01/F10, etc. Always Review before Apply - a property may not "
          "exist in your car's CAFD version.", ""]
    for s in sorted(by_series):
        md += [f"## {s}", "", table(by_series[s]), ""]
    (ROOT / "INDEX.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {ROOT/'INDEX.md'}: {len(rows)} entries, {len(by_series)} series")


if __name__ == "__main__":
    main()
