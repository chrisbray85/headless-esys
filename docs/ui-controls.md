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
| Button | LaunchButton | 651,422,49,54 | 675,449 | yes | orange ▶ on the 22.06 card — launches EsysUltra. **Do not click autonomously (Chris, 2 Sep 2026).** |
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
Values as set on Chris's install:

| Setting | Value | Control | AutomationId / Name | X,Y,W,H |
|---|---|---|---|---|
| close panel | — | Button | Name `X` | 1140,245,34,30 |
| PSDZ Location | `C:\Data` (the 322 GB full psdzdata extract) | Edit | `PsdzLocationTextBox` | 692,286,470,30 |
| Mode | `Car` | ComboBox | `Mode` | 692,350,152,31 |
| Memory (Java heap) | `2048` | ComboBox | `JavaHeap` | 851,350,151,31 |
| Language | `English` | ComboBox | `LanguageBox` | 1009,350,154,31 |
| Dark Mode | unchecked | CheckBox | `DarkModeCheckBox` / Name `Dark Mode` | 693,518,117,23 |

**KIS Exclusion** — 21 checkboxes, every one `IsChecked:True` = shown GREEN = series LOADED, i.e. NOT excluded (Chris confirmed 2 Sep 2026: "nothing is ticked to exclude, they are all green"). Untick = exclude. Grid laid out 58x30 starting at 692,415 (row pitch 30, column pitch 58; the CheckBox
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

## EsysUltra (`ESysUltra.exe`) — not yet probed

JavaFX+Swing under a C++/JVM shell. Expected near-empty in UIA; read path is
`screenshot()` + coordinate `click()`. Run `list_controls(app="EsysUltra")` once
it is up and append the result here.

## E-Sys (`javaw.exe` + `esysCore.jar`) — not yet probed

Java Swing. Same expectation as above.
