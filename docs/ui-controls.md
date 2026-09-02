# UI control inventory — garage laptop apps

Captured via `list_controls(app=...)` (UIAutomation). Coordinates are physical
screen pixels in the 1920x1080 capture: `X,Y,W,H` = top-left + size; centre =
(X+W/2, Y+H/2). UIA coords and capture pixels match 1:1.

**DPI lesson (fixed 2 Sep 2026 18:13):** the panel is 1920x1080 at 125% scaling.
A DPI-unaware PowerShell saw 1536x864, so `grab.ps1` captured only the top-left
crop (no taskbar in the frame = the tell) and `input.ps1` normalised clicks
against the wrong size, landing 1.25x too far right/down in empty space. Both
scripts now call `SetProcessDPIAware()` first. First successful injected click:
`CLICK 429 401 screen=1920x1080` opened the About page.
Re-run `list_controls` after any window move/resize — positions shift, names don't.

## UltraAdmin (`UltraAdmin.exe`, `C:\Program Files\ESysUltra\`) — 2 Sep 2026, home tab

WPF app (ListBoxItems are `System.Windows.Controls.ListBoxItem`), so UIA works.
`Name` is empty on every button; identify by `AutomationId`. `click_control()`
matches on Name only, so for these use coordinate `click()` at the centre.

| ControlType | AutomationId | X,Y,W,H | Centre | Enabled | What it is |
|---|---|---|---|---|---|
| Button | ESettings | 649,236,45,36 | 671,254 | yes | "•••" on the 22.06 card — E-Sys profile settings |
| Button | LaunchButton | 651,422,49,54 | 675,449 | yes | orange ▶ on the 22.06 card — launches EsysUltra. **Do not click autonomously — the owner decides when EsysUltra launches.** |
| Button | Shortcut | 601,424,52,49 | 627,448 | yes | ↗ on the 22.06 card — create desktop shortcut |
| ListItem | Main | 410,221,38,72 | 429,257 | yes | left rail: home |
| ListItem | Global | 410,292,38,73 | 429,328 | yes | left rail: globe (global settings) |
| ListItem | About | 410,365,38,72 | 429,401 | yes | left rail: ? (about/license) |
| Button | UpdateButton | 1225,183,56,37 | 1253,201 | yes | title bar ⤓ (check for update) |
| Button | RotatingButton | 1282,183,56,37 | 1310,201 | yes | title bar ⟳ (refresh) |
| Button | PART_MinimizeButton | 1339,183,56,37 | 1367,201 | yes | title bar minimise |
| Button | PART_MaximizeRestoreButton | 1396,183,56,37 | 1424,201 | **no** | title bar maximise (disabled — fixed-size window) |
| Button | PART_CloseButton | 1453,183,56,37 | 1481,201 | yes | title bar close |

Status bar text: `ESysUltra - Licensed to [ <licence id> ] - [ <owner> ]`.
Install dir contents: `CheatSheets/`, `Config/`, `extLib/`, `Logs/`, `Resources/`,
`ESysUltra.exe` (33 MB), `UltraAdmin.exe` (12.8 MB).

Observed 2 Sep 2026 18:03: `click(675,449)` was injected (`sent=3`) but nothing
happened — explained by the DPI bug above (it physically landed at ~844,561, empty
window body). Not a launch failure.

### About page (rail `?`, centre 429,401)
`Version 1.0.0.37` · `Integrated PSdZ 4.60.30` · links esysultra.com/changelog,
esysultra.com/manual. Rail `Main` (429,257) returns to the launcher card.

### E-Sys profile settings panel (opened via `ESettings` "•••") — 2 Sep 2026 18:08

Overlays the home tab; all home-tab controls above stay present underneath.
Values as set on the reference install:

| Setting | Value | Control | AutomationId / Name | X,Y,W,H |
|---|---|---|---|---|
| close panel | — | Button | Name `X` | 1140,245,34,30 |
| PSDZ Location | `C:\Data` (the 322 GB full psdzdata extract) | Edit | `PsdzLocationTextBox` | 692,286,470,30 |
| Mode | `Car` | ComboBox | `Mode` | 692,350,152,31 |
| Memory (Java heap) | `2048` | ComboBox | `JavaHeap` | 851,350,151,31 |
| Language | `English` | ComboBox | `LanguageBox` | 1009,350,154,31 |
| Dark Mode | unchecked | CheckBox | `DarkModeCheckBox` / Name `Dark Mode` | 693,518,117,23 |

**KIS Exclusion** — 21 checkboxes, every one `IsChecked:True` = shown GREEN = series LOADED, i.e. NOT excluded (confirmed by the owner: "nothing is ticked to exclude, they are all green"). Untick = exclude. Grid laid out 58x30 starting at 692,415 (row pitch 30, column pitch 58; the CheckBox
itself is 38x20 at +10,+5). Named by the chassis/series code:

| Row (y) | Codes left→right (x = 702, 760, 818, 876, 934, 992, 1050, 1108) |
|---|---|
| 420 | F001 F010 F020 F025 F056 G045 G070 I001 |
| 450 | I020 J001 K001 KE01 KS01 NA05 RR21 S15A |
| 480 | S15C S18A U006 X001 XS01 |

**KIS Exclusion semantics (confirmed via esysultra.com changelog, 2 Sep 2026):**
excluded series are NOT loaded — v1.0.0.11 "SVT Description (KIS Feature) will
honor the 'Exclude KIS' set in UltraAdmin". Current state: nothing excluded, all
21 green. **S18A = G20 — keep it green.** Unticking the others would save heap /
startup time but is optional.
`ULSettings.json` `ShownKISWarning: true` means EsysUltra has already shown its
KIS warning once.

**Java heap:** 2048 is only the vendor default (changelog v1.0.0.7 / v1.0.0.20).
Laptop has 15.7 GB RAM (Lenovo 20S1SCAS01, 64-bit) → 4096 is the sensible value
with the full 322 GB psdzdata; leaves plenty for ISTA/Windows.

Global.json (`C:\Program Files\ESysUltra\Config\`): BackupPath `C:\Data\Backup`,
DisableCache/DisableCheatSheets/DisableKeybinds/DisableSVTDescription false,
ReserveIcomOnConnect + ReleaseIcomOnDisconnect true, DiscoverIcomAutomatically
false, DisableRealTimeBackup false, MinimizeToTray false. 23 community cheat
sheets already installed in `CheatSheets\` (incl. siegester.xml = G20).

## Launching EsysUltra headlessly — what actually works (2 Sep 2026 18:16)

**UltraAdmin resolves `ESysUltra.exe` relative to its CURRENT WORKING DIRECTORY.**
A scheduled task starts in `C:\Windows\System32`, so an UltraAdmin launched by a
task with a bare `start "" "...\UltraAdmin.exe"` throws *"ESysUltra.exe does not
exist. Please re-install ESysUltra and add the following folder to the exclusion
list of your anti-virus: C:\Windows\System32"* when ▶ is pressed. Not an AV
problem (`C:\Program Files\ESysUltra\*` is already excluded).

Fix: `C:\ista-mcp\openadmin.cmd` = `start "" /d "C:\Program Files\ESysUltra"
"C:\Program Files\ESysUltra\UltraAdmin.exe"`, run via scheduled task **OpenAdmin**
(`/it`, your Windows user). Then `click(675,449)` on ▶. `ESysUltra.exe` starts as a child of
UltraAdmin (won't run standalone — the `OpenUltra` task that launches it directly is
useless; still points at openultra.cmd). Startup: splash → "Creating log file" →
"Loading KIS Data" (~1.6 GB working set, 1–2 min with all 21 series loaded).
UltraAdmin exits once EsysUltra is up.

Gotchas: `schtasks /change /tr` on an interactive task prints nothing and does NOT
apply (needs the password) — create a new task instead. `timeout /t` fails over SSH
("Input redirection is not supported") — use `powershell Start-Sleep`.

## EsysUltra (`ESysUltra.exe`) — Java, UIA-blind (confirmed)

JavaFX+Swing under a C++/JVM shell. `list_controls(app="ESysUltra")` → **0 controls**
(probed during startup 2 Sep 2026). Read path is `screenshot()` + coordinate `click()`.

### EsysUltra 22.06 main window, MAXIMISED (1920x1080) — coordinate map, 2 Sep 2026

Title bar: `E-SysUltra 22.06 (64bit) [<licence>]`; maximise/restore 1830,14; close 1888,14
(pre-maximise window: maximise button was at 902,19).
Menu: File 19,41 · Options 72,41 · Extras 134,41 · Help 185,41.
Toolbar (y=80), Coding/Comfort views: back 22 · forward 59 · connect 106 (shows a red
X once connected) · disconnect 150 · log 195 · help 246 · EsysUltra extras: 296 =
**NCD Compare** (WinMerge diff dialog, close X at 1214,139) · 344 = **SVT-ToolBox** (SVT to CAFD / FDL Extractor; close X at 1619,18) · 392 =
**DTC reader** (dialog "DTC": Read 447,185 (read-only) · **Clear All 533,185 (WRITE —
never autonomous)** · Copy As Text 645,185 · Copy As File 775,185 · Timeout 1460,185 ·
ECU list with tick boxes x=438 from y=255 step ~31 · close X 1482,146).
G20 320d ECUs seen: ACSM5[01] ATM2[61] BDC_BODY3[40] BDC_GW3[10] DKOMBI4[60]
**DME_BAC2[12]** (engine — Start/Stop memory lives here) DSC_BRS[29] DSC_VIP_IB4[39]
EGS7[18] FLM2[44] FLM2[43] FZD2[56] GWS2[5E] HKFM2[0D] HU_MGU[63] ICAM4[06] IHKA4[78]
RAM[37] SCR2[0B] USS[2C] (+1 below the fold).
(Data Handling start view had a longer toolbar: open 238 · save 280 · save-as 320 ·
help 372 · extras 422/470/518.) Menus: Extras = Convert OrderXML↔FA only; Options =
Customize…, Settings…. Comfort Mode rail (x=113): TAL-Calculating 175 · FSC 245 ·
Certificate Management 313 · SFA 380 · KDS 448 · Anflash 516; Expert Mode 844.
Connected status bar: I-step shipm/target, series, VIN, "Http-Server: RUNNING".
Left rail, x=113: Comfort Mode 130 · Expert Mode 161 · Editors & Viewers 192 ·
Data Handling 224 · (section icons below, e.g. PDX-Charger 113,268) ·
External Applications 937 · Personal view 969.
Status bar y=1006: "Logged in" 1146 · "SWL-Sec: CERTIFICATE" 1277 · "Role: Expert" 1444.
First-start dialog: "Information ... WAVE-11 ... registry-wave11.bat" — OK at 959,657
(window not yet maximised). Just dismiss it.

Expert Mode rail (after clicking Expert Mode 113,161), icons at x=103:
TAL-Processing 205 · VCM 272 · Coding 340 · Coding-Verification 407 ·
NCD preparation 475 · FSC Extended 542 · TSL-Update 610 · NAV/ENT-Update 677 ·
OBD-CVN 745 · Certificate Management Extended 812 (list scrolls; scrollbar x=209).
WRITE-to-car modules (human-confirmed only): TAL-Processing, VCM, Coding (Code FDL /
Code buttons), FSC Extended, TSL/NAV updates. Read-only within Coding: Connect,
Read FA, Read SVT, Read Coding Data, open FDL editor.

Coding view (Expert Mode → Coding 103,340), maximised. Toolbar changes: connect 106,80
· disconnect 150,80 (greyed until connected).
- Vehicle Order box: Read 281,167 · Load 356,167 · Save 431,167 · Edit 503,167. FA tree
  renders under it (left pane 240–735 x 185–375); Vehicle Profile pane 750–1905.
- SVT pane 240–1090 x 415–960 (legend: Actual red / Target red / Identical / HW diff / NCD).
- SVT Actual: Read (VCM) 1188,475 · Read (ECU) 1327,475 · Load 1462,475 · Save 1583,475
  · Edit 1706,475 · Close 1826,475.
- SVT Target / KIS: I-Step (shipm.) 1365,571 · I-Step (target) 1365,600 · Calculate 1183,629
  · Calculation Strategy radios 1533,591 / 1533,620 / 1712,591 / 1712,620.
  Target Read (VCM) 1184,714 · Load 1305,714 · Save 1425,714 · Edit 1543,714 · Close 1662,714
  · HW-IDs from SVTactual 1237,751 · Detect CAF for SWE 1444,751.
- Coding box: **Code 1175,826 (WRITE)** · Read Coding Data 1309,826 (read) ·
  **Code NCD 1455,826 (WRITE)** · **Code Default Values 1241,864 (WRITE)** ·
  Read CPS 1441,864 (read) · Parallel TAL-Execution checkbox 1137,899.
- SVT filter: All 1160,969 · SVT Reset 1256,969.
Flow for a read: Connect (106,80) → pick target/ENET in dialog → Vehicle Order Read
(281,167) → SVT Actual Read (ECU) (1327,475) → select ECU CAFD in SVT tree → Read
Coding Data (1309,826) → right-click CAFD → Edit FDL.

### FDL editor ("Edit NCD" on the NCD child node under a CAFD), maximised
Open it with `input_sequence(["RCLICK <ncd-row x y>", "KEY {DOWN}{DOWN}{ENTER}"])` —
context menu on the NCD row = Delete · **Edit NCD** (2nd) · Code NCD (WRITE) · Code ·
Read Coding Data · Read Serial Number · Read ECU INFO · Reboot ECU · Expand · Collapse.
Mouse-clicking a Java popup item is unreliable; keyboard pick is.
Editor: File Name 1100,135 (C:\Data\CAF\<CAFD>.ncd) · **Search for** field 484,186 ·
Search button 655,186 · Filter ticks: Default Values 730,192 · Parameter 850,192 ·
Activation Condition 948,192. Tree pane 240–1215 x 230–880 (root CAF [ECU] → Header,
Daten → 3010 BSR_BEREICH / 3020 BSU_BEREICH / 3030 TL_ID / 3031 CAF_ID / 3032 SIGNATURE).
Right pane = EsysUltra **Cheat Sheet Maker** (search 1445,657 · Series/Author filters ·
Review 1318,864 · **Apply 1572,864** (edits the FDL locally, not the car) · Reload 1826,864).
"Values from ECU" strip at y=909. Toolbar gains open 238 · **save 280** · save-as 320.
Left rail = Editors & Viewers list (FA/TAL/TALFILTER/SVT/SWESEQ/FSC/FDL/Anflash editors,
CAF/Log viewers). Coding after edit: save (280,80) → back to Expert Mode → Coding →
select CAFD → **Code FDL / "Code" (WRITE, human-confirmed)**.

### Proven FDL coding workflow (2 Sep 2026, TCM_MSA_MEMORY on DME_BAC2)
1. Expert Mode → Coding → Read FA (281,167) → SVT Read (ECU) (1327,475).
2. Scroll SVT to the ECU, click its CAFD row, **Read Coding Data** (1309,826) → report "0 Errors" (Close 1134,788). RealTimeBackup gets `NCD\<ECU>\1_READ_<CAFD>.ncd` = the before-backup.
3. Expand CAFD (+), select the NCD child row → `input_sequence(["RCLICK x y","KEY {DOWN}{DOWN}{ENTER}"])` = Edit NCD → FDL editor.
4. Search for property (484,186 / 655,186) → expand it → expand "Ausgelesen" → RCLICK the value row → `KEY {DOWN}{ENTER}` (Edit) → inline combo → `KEY {DOWN}{ENTER}` to pick next value → Save (280,80).
5. Expert Mode → Coding; NCD row still selected → **Code NCD (1455,826) — WRITE, human go only** → progress window "TAL execution finished" (Close 970,464) → Transaktions-Report "NCD Codieren … cdDeploy Finished" (Close 1134,788). ~15 s. RealTimeBackup gets `2_WRITE_<CAFD>.ncd`.
6. Verify: Read Coding Data again → `3_READ_<CAFD>.ncd`; compare to 2_WRITE. Use `-LiteralPath` — the ECU folder name contains `[12]`.
Gotchas: **SVT tree rows shift down 20 px for every node you expand** — re-screenshot
before clicking a CAFD row after any expand (read the wrong CAFD once, 2 Sep). Cheat
Sheet pane: after opening a new CAFD in the editor the list is empty until **Reload**
(1826,864); an entry whose property doesn't exist in that CAFD version gives an EMPTY
Review — don't Apply blind. Keep each `run()` helper sequence under ~45 s of sleeps
(the tool times out at 60 s and you lose the result, not the actions). Every E-Sys report is MODAL — a click aimed elsewhere hits it. Java popup items: pick by keyboard. Engine OFF, ignition ON.

### Cheat-sheet coding path (fastest, proven on HU_MGU + IHKA4, 2 Sep 2026)
In the FDL editor: tick **Auto Fetch** (1804,240) once, else **Reload** (1826,864) → cheat search field 1445,657 (`TYPE ^a<word>`) →
list rows start y=268, pitch 22 → click row → **Review** (1318,864; review window close
X 1546,286; EMPTY review = property not in this CAFD version, do NOT apply) → **Apply**
(1572,864; first time shows an info popup, OK 1571,594; tick "Disable disclaimer" 1523,240)
→ log pane (y≈692+) prints `section > PROPERTY |> value … Done.` → Save (280,80) →
Expert Mode (113,161) → Coding (103,340) → NCD child row still selected → Code NCD.
Post-coding verify read may time out (P2/T2) — DME ok after ~40 s, IHKA4 needed an
ignition off/on. ECU folder names contain `[nn]` → always `-LiteralPath`.

## E-Sys (`javaw.exe` + `esysCore.jar`) — not yet probed

Java Swing. Same expectation as above.
