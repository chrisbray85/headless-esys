# Cheat sheets

Community-written FDL "cheat" files for BMW F- and G-series coding, in the format
E-Sys Launcher and EsysUltra load directly. Each `<cafd>` entry names the ECU, the
coding file (CAFD id), the car series it applies to, and the author.

**Credit:** every entry carries its author's name inside the XML (Almaretto, Botho,
Bundang_Thunder, jokinawa, siegester, stanleyy, ekfxisid, otakar, packetpilot,
pmooiweer, ruben_17non, SergAA, TMD29, aboulfad, aknight720, dmnc02, Kip_M3,
PerryGunn, simpaty, tutuianu_daniel and others). They were shared publicly on the
Bimmerpost and Bimmerfest E-Sys coding threads for exactly this use. This folder just
keeps them together and indexed; nothing here is ours except `INDEX.md`. If you are an
author and want a change, open an issue.

G20-specific notes were learned from siegester03's guide,
<https://github.com/siegester03/bmw-g-series-coding>, and the G20 Bimmerpost coding
thread. Read that guide for what does and does not work on a G20.

## Use

- **In EsysUltra:** copy the `.xml` files into `C:\Program Files\ESysUltra\CheatSheets\`.
  In the FDL editor press **Reload** in the cheat pane, search, select, **Review**,
  then **Apply**. EsysUltra ships most of these already.
- **In E-Sys Launcher Pro:** same files, its own cheat folder.
- **By hand:** look the property up in [INDEX.md](INDEX.md) and edit it in the FDL
  editor.

## Rules

1. **Review before Apply.** A cheat written for one CAFD version may name a property
   that does not exist in yours; the review then shows nothing and you skip it.
2. **Series matters.** `S18A` = G20/G21. An F-series entry with the same property name
   is not proof it works on a G-series car.
3. **Some cheats need hardware or an I-step you may not have** (front camera, HUD,
   2020+ software). Check your SVT first.
4. **Back up first.** EsysUltra's real-time backup keeps the before/after files; keep a
   copy elsewhere.

See [../docs/GUIDE.md](../docs/GUIDE.md) for the full coding sequence and what was
verified on a real G20.
