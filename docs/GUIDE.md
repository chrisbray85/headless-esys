# Coding a BMW G20 with EsysUltra, driven by an AI agent

A hobbyist's guide, written from a real session: one evening, one 2018 G20 320d,
three ECUs coded and verified, plus a fault read. Everything here was learned the
hard way, so the gotchas are the valuable part. Nothing in this guide needs BMW
dealer access or online signing; it applies to cars still on pre-2021 software
(see "Secure coding" at the end for why that matters).

**Safety first.** Coding writes to the car's control units. A bad write can leave a
module uncoded until it is fixed. The rules that kept this session safe:

- Engine OFF, ignition ON for every read and write. Coding the engine ECU with the
  engine running resets the ECU and stalls it.
- Read before you write, and keep the read. EsysUltra's real-time backup does this
  for you (see below).
- Change one ECU at a time. Verify by reading it back before moving on.
- Never touch the car during a write. No doors, no buttons, no cable wiggling.
- Battery: a single coding takes seconds and is fine on a healthy battery. Flashing
  (software updates) needs a proper support charger and you sitting at the car.

## 1. Kit

| Item | Notes |
|---|---|
| Windows laptop at the car | Any modern Win 10/11 machine. Plug it into mains if you can. |
| ENET cable | OBD-to-RJ45. Plug into the OBD port under the dash and the laptop's Ethernet socket. The laptop takes a 169.254.x.x address by itself; the car answers on 169.254.x.x too. |
| EsysUltra + UltraAdmin | Commercial E-Sys front end. Licence is locked to the laptop's hardware. |
| psdzdata (full) | The BMW data set EsysUltra needs. Hundreds of GB for the full set with flash files. Set its path in UltraAdmin (PSDZ Location). |
| Cheat sheets | Community XML files with property names and values per car series. EsysUltra ships a set in its `CheatSheets` folder and shows them inside the FDL editor. |
| Remote control (optional) | This session drove the laptop from a Mac over Tailscale with the MCP server in this repo. Not required; everything below can be clicked by hand. |

## 2. UltraAdmin settings that matter

Open UltraAdmin, click the "•••" on the E-Sys card:

- **PSDZ Location**: your psdzdata folder.
- **Mode**: Car.
- **Memory**: the Java heap. The default 2048 hit its limit while loading data
  for a G20 with every series enabled. On a 16 GB laptop set **4096**.
- **KIS Exclusion**: the list of car series. Green = loaded. Leave your own series
  green (G20 = **S18A**); unticking the rest saves memory and start-up time.

Then the orange ▶ on the card launches EsysUltra. `ESysUltra.exe` will not run
on its own; it must be started from UltraAdmin.

**Gotcha: "ESysUltra.exe does not exist. Please re-install ESysUltra and add
C:\Windows\System32 to your anti-virus exclusions."** That message is misleading.
UltraAdmin looks for ESysUltra.exe in the folder it was started *from*. If you
launched UltraAdmin from a script or scheduled task, that folder is System32. Start
UltraAdmin from its own folder (or a shortcut whose "Start in" is
`C:\Program Files\ESysUltra`) and the error goes away.

Start-up takes a minute or two: splash, "Creating log file", "Loading KIS Data".

## 3. Connect and read the car

1. Ignition on, engine off. Wait ten seconds for the car's network to come up.
2. EsysUltra: **Connect** (toolbar plug icon). Pick your car/series and the ENET
   connection in the dialog.
3. **Expert Mode → Coding.**
4. Vehicle Order: **Read**. This is the FA, the car's option list.
5. SVT Actual: **Read (ECU)**. This lists every module and its software (CAFD =
   coding file, SWFL = software, BTLD = bootloader).

The status bar now shows the car's integration level (I-step), e.g.
`S18A-18-11-522` = November 2018 software, and the psdzdata target level.

### Read the faults while you are there

The toolbar's third EsysUltra icon (magnifier) opens a **DTC** window listing every
module. **Read** reads all faults. **Copy As File** saves them. Do not press
**Clear All** unless you mean it.

Reading faults in EsysUltra is a handy first look. ISTA is the tool for proper
diagnosis (test plans, actuator tests, service functions).

## 4. Backups: you already have them

EsysUltra writes everything it reads or writes to
`C:\Data\RealTimeBackup\<car>\<date>\`:

- `FA_MASTER\` and `SVT_MASTER\` — vehicle order and module list
- `DTC\` — fault reads
- `NCD\<ECU>\1_READ_<CAFD>.ncd` — a module's coding **before** you touched it
- `NCD\<ECU>\2_WRITE_<CAFD>.ncd` — what was written
- `NCD\<ECU>\3_READ_<CAFD>.ncd` — the verification read afterwards

Keep the whole folder somewhere else too (USB, cloud). The `1_READ` file is your
undo for each module.

## 5. Coding one module (the proven sequence)

1. In the SVT tree, click the module's **CAFD** row (the coding file).
2. **Read Coding Data** (Coding box, right). A report pops up: "0 Errors,
   readCPS o.k., …ncd generated". Close it. Your before-backup now exists.
3. Expand the CAFD (plus sign). A child row appears with the same CAFD name.
4. **Right-click the child row → Edit NCD.** The FDL editor opens.
5. In the editor, either:
   - **Cheat sheet route (fast):** press **Reload** in the right-hand pane, type in
     the pane's search box, click the entry, press **Review** to see current value →
     new value, close the review, press **Apply**. The log pane confirms
     `section > PROPERTY |> value … Done.` Repeat for each entry.
   - **Manual route:** type the property name in "Search for", press Search, expand
     the property, expand "Ausgelesen", right-click the value → Edit, choose the new
     value from the dropdown, Enter.
6. **Save** (toolbar disk icon). This only writes the file on the laptop.
7. Back to **Expert Mode → Coding.** The child row is still selected.
8. **Code NCD.** A progress window runs ("TAL execution finished … Finished",
   5 to 20 seconds), then a transaction report ("NCD Codieren … cdDeploy Finished").
   Close both.
9. **Verify:** select the CAFD parent row again, **Read Coding Data**, and compare
   `3_READ` with `2_WRITE` in the backup folder. Identical files = the car holds what
   you wrote.

### Gotchas in this sequence

- **A Review that shows nothing** means the cheat's property does not exist in your
  car's version of the coding file. Do not Apply; find the property another way or
  skip it.
- **The first read after a coding often times out** ("P2 timeout", "resource not
  available"). The module is resetting. The engine ECU answered after about 40
  seconds. The climate module needed ignition off, ten seconds, ignition on. Do not
  re-code; just wait and read again.
- **The head unit reboots** after coding: black screen for about a minute. Normal.
- **Every report window is modal.** Close it before clicking anything else.
- **Tree rows move** when you expand a node. Look again before clicking a row.
- **Read Coding Data is greyed** when the child row is selected. Select the parent
  CAFD row for reads, the child row for Edit NCD and Code NCD.

## 6. What was coded on a 2018 G20 320d (B47, ID7 head unit)

All verified by read-back. Property names are what you search for.

| Module | CAFD | Property | From → To | Effect |
|---|---|---|---|---|
| DME_BAC2 (engine) | 000029B7 | `TCM_MSA_MEMORY` | OFF (00) → ON (01) | Start/Stop button state survives an ignition cycle. Road-tested. |
| HU_MGU (head unit) | 00003E52 | `MACRO_CAM_LEGALDISCLAIMER` | ld_mit_timeout → kein_ld | No camera legal disclaimer |
| HU_MGU | 00003E52 | `LEGAL_DISCLAIMER_TIME` | → kein_ld | No disclaimer wait |
| HU_MGU | 00003E52 | `HUD_DISTANCE_INFO` | → aktiv | Distance info in the HUD |
| HU_MGU | 00003E52 | `5_FACH_TIPPBLINKEN` | → aktiv | 5-flash option appears in iDrive lighting settings |
| HU_MGU | 00003E52 | `PIM_DRIVING_TEXT_LENGTH` | → whole_text | Full SMS text while driving |
| HU_MGU | 00003E52 | `GLOBAL_CONF_SAILING`, `EFF_DYN_SAILING`, `SAILING_COUNTER` | nicht_aktiv → 01 | Sailing/coasting in Eco Pro |
| IHKA4 (climate) | 000051C9 | `LAENDERVARIANTE` | → 02 | "Colder A/C" pair |
| IHKA4 | 000051C9 | `TEMPERATUR_OFFSET` | → 06 | |

Already active from the factory on this car: `FH_KOMFORTSCHLIESSUNG_FB` (close windows
and sunroof from the key fob), in BDC_BODY3 CAFD 000044ED.

Not found in this car's coding files: `VAM_HORN_AT_SECURE` (horn on lock). The cheat
sheets list it under BDC_BODY3 CAFD 00007083, but the 031_020_109 version of that file
does not contain it.

Not possible on this car: anything needing the KAFAS front camera (Traffic Light
Assist, Speed Limit Assist display, lane change assist) because the car has no KAFAS
module in its SVT. Check your own SVT before chasing a cheat.

## 7. Reading the fault list

Fault codes from this car, with what they turned out to mean:

- `B7F89C` HU_MGU "No GPS reception over the last 40 km" together with `031786` ATM2
  "Functional limitation of Last State Call": the GPS signal path (shark-fin antenna →
  telematics box → head unit). A known G20 failure is the antenna seal letting water
  onto the telematics box. Hardware, not coding.
- `CD9767` / `CD9763` DME "axle speed message missing from DSC": appears when the
  car sits ignition-on with the engine off for a diagnostic session. Clear and ignore
  unless it returns while driving.
- `338100` DME "Bottom radiator blind: failure to detect closed limit position": the
  active grille shutter. Actuator test in ISTA.
- `031D18` RAM "bass speaker right: line disconnection" and `B7F500` "microphone
  driver not calibrated": wiring, and a calibration routine in ISTA.

## 8. Secure coding: read before updating software

From integration level **21-03** onward BMW signs coding files online. Once a module
(head unit, cluster, driver-assist modules first, most others by 2023) is on that
software, E-Sys/EsysUltra can no longer write its coding offline. Worse, an update
can delete a module's coding and then be unable to write it back. Signed files can
be bought per module from third-party services.

Practical consequences:

- A car on 2018 software keeps free coding. Nothing forces an update.
- If you want bug fixes, target the last open level (around 20-11) rather than the
  newest data, and dry-run the TAL calculation first to see what would flash.
- Selective flashing is possible (TAL filter): engine, gearbox, DSC and climate can
  go up without touching the head unit and cluster. Keep the entertainment modules
  together.
- Maps are separate from all this: a USB install plus an activation code tied to the
  VIN, not an E-Sys flash. Newer maps may need a minimum head-unit software level.

## 9. If you drive the laptop with the MCP server in this repo

Lessons that cost hours, all fixed in the code now:

- **Display scaling.** A 1920×1080 panel at 125% makes a DPI-unaware helper see
  1536×864: screenshots are a top-left crop (no taskbar = the tell) and every click
  lands 25% off. The helpers now call `SetProcessDPIAware()`.
- **Battery.** Windows scheduled tasks default to "don't start on batteries". Unplug
  the laptop at the car and every helper silently queues. `setup()` clears that flag.
- **Console flash.** A hidden PowerShell still flashes a console window, which steals
  focus and closes Java popup menus. Helpers run through `run-hidden.vbs`.
- **Java menus.** Clicking a popup item is unreliable; open the menu with a right-click
  and pick with the keyboard (`KEY {DOWN}{DOWN}{ENTER}`) in one `input_sequence`.
- **Flaky links.** If a click call errors, check the helper log before repeating it.
  The action may have been written but not triggered.
- The coordinate maps for UltraAdmin and EsysUltra windows are in
  [ui-controls.md](ui-controls.md).
