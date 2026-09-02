# BMW diagnostic glossary (German and BMW terms you will meet)

ISTA and the underlying BMW data speak German and acronyms. This is what they mean.
Coding-specific rows are kept because ISTA shows the same names in its vehicle
tree and reports; this project does not itself do coding.

| Term | Meaning |
|---|---|
| **FA** (Fahrzeugauftrag) | Vehicle order: the car's option list and build data. "Read FA" reads it from the car. |
| **VO** | Vehicle order, same thing in English. "VO coding" = adding or removing an option code and re-coding the affected modules. |
| **SVT** (Softwareverbauungstabelle) | The list of every module (ECU) in the car with its software, bootloader and coding file versions. "Read SVT (ECU)" asks each module. |
| **ECU / Steuergerät** | A control unit. Names like DME_BAC2 (engine), HU_MGU (head unit), IHKA4 (climate), BDC_BODY3 (body controller), DKOMBI4 (cluster), ATM2 (telematics). |
| **CAFD** (Codierdatei) | A module's coding file, the *description* of what can be set. Identified by an id like `CAFD_000029B7_000_023_086`. |
| **NCD** | The *values* actually coded into a module for that CAFD. What "Read Coding Data" reads and "Code NCD" writes. Stored as `.ncd` files. |
| **FDL** (Funktionsdatenliste) | Function data: the individual properties inside an NCD. "FDL coding" = changing single properties. "Edit NCD" opens the FDL editor. |
| **Kommentar** | Comment. The German description of a property, e.g. `Status MSAFahrerwunsch entspricht mit KL15 ein dem Status vor der letzten KL15Deaktivierung` = "Start/Stop driver setting at ignition-on matches the state before the last ignition-off". |
| **Ausgelesen** | "Read out": the value currently in the car. Expand it to see the value and its raw bytes. |
| **Werte** | Values. `Werte=01` is the raw byte. Named values sit next to it (`ON`, `aktiv`). |
| **aktiv / nicht_aktiv** | Active / not active. The commonest pair of values. |
| **kein_ld** | "No legal disclaimer" (kein = none, LD = legal disclaimer). |
| **ld_mit_timeout** | Legal disclaimer with a timeout (goes away by itself). |
| **KL15 / KL30 / KLR** | Klemme = terminal. KL15 = ignition on, KL30 = permanent power, KLR = accessory. "KL15 off/on" = ignition cycle. |
| **MSA** (Motor-Start-Stopp-Automatik) | Auto Start/Stop. |
| **TCM** | In DME properties, the coding block for transmission/vehicle functions; `TCM_MSA_MEMORY` is the Start/Stop memory. |
| **I-Step** (Integrationsstufe) | Integration level: the car's overall software version, e.g. `S18A-18-11-522` = G20 platform, November 2018. "I-Step shipm." = what the car has, "I-Step target" = what your data could flash. |
| **psdzdata** | BMW's data set (coding descriptions and, in the "full" version, flash files). Set its folder in UltraAdmin. |
| **KIS** | The knowledge base EsysUltra loads per series to explain properties and support the SVT/cheat features. "KIS Exclusion" unticks series you don't need. |
| **TAL** (Transaktionsliste) | The transaction list: the plan of what will be coded or flashed. "TAL execution finished" = the write ran. "TAL-Calculating" prepares a flash. |
| **cdDeploy** | The coding-deploy step inside a TAL. "cdDeploy Finished" = the coding was written. |
| **CPS / readCPS** | Coding parameter set. "readCPS o.k." = the module's coding was read successfully. |
| **RDBI** | ReadDataByIdentifier, the diagnostic service used to read. "P2 timeout on Service RDBI_CPS" = the module didn't answer in time (usual right after a coding). |
| **VCM** | Vehicle Configuration Management: the gateway's stored copy of FA/SVT. "Read (VCM)" reads the stored copy; "Read (ECU)" asks every module. |
| **HWEL / BTLD / SWFL / SWFK / HWAP / NAVD / ENTD** | Row types in the SVT: hardware, bootloader, software, software (K), hardware option, navigation data, entertainment data. Coding only touches CAFD/NCD rows. |
| **FSC** (Freischaltcode) | Activation code for paid features and map updates, tied to the VIN. |
| **SFA** | Secure Feature Activation: the newer, online-only version of FSC. |
| **Secure Coding / NCD 2.0** | From software level 21-03, coding files are signed online by BMW; offline E-Sys cannot write them. See the guide before updating software. |
| **Anflash** | Flashing a module's software (not coding). |
| **DTC** | Diagnostic trouble code, a fault. EsysUltra's DTC window reads them from every module. |
| **Codierdaten** | "Coding data", the label on CAFD rows in the SVT. |
| **Codierbeschreibungsdatei** | "Coding description file", another label for a CAFD. |
