# FC power-path review before first flight

Reviewed 2026-10-17 against `pcb/FC/FC.kicad_pcb`, `power.kicad_sch`, and
`jlcpcb/production_files/BOM-FC.csv`. This is a targeted netlist/rating review,
not a completed PCB design certification. Installed component markings and
any repair changes still require physical confirmation.

## Existing protection is present

| Device | Saved PCB connection/function | Finding |
|---|---|---|
| F1, BSMD2920L-1000-16V | J1 +BATT -> VSYS | Existing resettable fuse, not missing |
| D4, SMAJ18A | VSYS to GND | Existing TVS transient protection, not a battery ADC divider |
| U7, LMR51430 | VSYS -> switching stage -> +5V | 4.5-36 V rated regulator with internal protection |
| U6, LMR51430 | Net-(D2-C) -> switching stage -> +3.3V | Same regulator type |
| D1/D2, RB088LAM-40TR | VBUS -> respective diode-OR nodes | Existing USB supply paths |
| Q1, DMG3415U | G=VBUS, S=Net-(D1-C), D=+5V | Part of the 5 V/USB supply selection |
| Q2, DMG3415U | G=VBUS, S=Net-(D2-C), D=VSYS | Battery-side supply selection feeding U6 |

ESC motor power comes directly from the battery. The FC F1 is downstream in
the FC branch; it does not interrupt the ESC's direct motor-power supply.
R7/R10 and R8/R9 set regulator output voltages. They do not connect pack
voltage to the STM32 battery ADC, which remains unconnected on PC0.

## Confirmed design-rating concerns

### 1. F1 is specified at 16 V maximum

The exact part named in the PCB and BOM has a listed 10 A hold current,
20 A trip current and 16 V maximum rating. A conventional full 4S LiPo is
16.8 V. The user's GNB11004S120AHV is a 4S LiHV pack: using the manufacturer's
4.35 V/cell HV charge limit gives 17.4 V. Confirm the physical pack label and
charger instructions before setting any charging mode.

Thus the specified F1 is not within its voltage rating over the intended full
pack range. Its existence does not resolve that rating mismatch. If the actual
installed F1 differs, check that part's data instead. A replacement must be
chosen for voltage, normal load, trip behavior, fault current and footprint;
do not simply fit another 16 V part or bypass it with a wire.

### 2. Q2 can exceed its gate-to-source limit

Diodes Incorporated rates DMG3415U at VDS=-20 V and VGS=+/-8 V maximum.
The saved PCB connects Q2's gate directly to VBUS while its source is the
battery-fed input node of U6. The source can rise toward pack voltage through
Q2's body diode and conducting channel.

With VBUS near 5 V and source near 14.8 V, the estimated VGS is about -9.8 V
(or still beyond -8 V with a modest body-diode drop). At 17.4 V it can approach
-12.4 V. These are calculated circuit conditions, not measured Q2 voltages.
With USB absent the VBUS/gate behavior also needs deliberate control; it must
not be assumed safe because the board happens to boot.

No external Q2 gate clamp is connected to that gate net in the saved PCB.
D4 protects VSYS against transients; it does not clamp Q2's gate-source
difference to 8 V. A polyfuse also does not enforce a MOSFET gate-voltage limit.

Select and verify a specific power-selection repair (appropriate device and
gate protection, or a correctly designed diode-OR alternative) before more
battery-powered tests. Do not improvise a drain-source bridge: reverse power
flow and USB backfeeding must remain controlled. This repair is not designed,
built, or approved by a passing bench test yet. No exact replacement part is
being recommended for purchase until the repair topology is settled.

## Immediate operating boundary

- Keep the FC USB-only while these battery-path issues are unresolved.
- The standalone voltage divider can be measured from the battery while
  disconnected from both FC and ESC electronics.
- Preserve existing protections. Do not add a second polyfuse by assumption.
- A current-limited supply or fast smoke stopper is optional bench equipment
  for first power-up after rework; it does not correct the voltage-rating issues.
- Verify existing bypass/bulk capacitor values and ratings against the actual
  assembled board. Several exported BOM entries reuse LCSC IDs across different
  value comments, so the export alone is not proof of what was populated.

## What this review has not established

No claim is made that F1/Q2 are damaged, that the present assembled board is
identical to the files, or that all other components/PCB layout are qualified
for motor transients. After any repair, verify rails, source selection,
temperature and resets under intended loads, including battery-only startup.
Motor switching/noise and mechanical repair durability remain separate checks.

## Sources

- [DMG3415U manufacturer datasheet](https://www.diodes.com/datasheet/download/DMG3415U.pdf)
- [BHFUSE series datasheet, including the 1000-16V row](https://datasheet.lcsc.com/lcsc/2504250935_BHFUSE-BSMD2920L-700-24V_C48579159.pdf)
- [Exact F1 supplier specification](https://jlcpcb.com/partdetail/BHFUSE-BSMD2920L_100016V/C46597958)
- [LMR51430 manufacturer datasheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf)
- [GNB battery model selected by the user](https://rotorvillage.ca/gnb-1100mah-4s-120c-hv-lipo-xt60/)
- [GNB manufacturer: HV chemistry uses 4.35 V charge voltage](https://www.gaoneng.shop/collections/fpv-battery)
