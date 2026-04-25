# How to Troubleshoot Dell Laptop Battery Issues

Source: https://www.dell.com/support/kbdoc/en-us/000123069/how-to-troubleshoot-dell-laptop-battery-issues
Dell KB article: 000123069 (How To)
Company: Dell

Applies to: Chromebook, G Series, Alienware, Dell Plus, Dell Pro, Dell Pro
Max, Dell Pro Plus, Dell Pro Premium, Inspiron, Latitude, Dell Pro Rugged,
Vostro, XPS, Legacy Laptop Models, Mobile Workstations, Dell Pro Max 16 XE
MC16250.

## Summary

A laptop battery provides power when the AC adapter is not connected.
Lithium-Ion (Li-ion) batteries are the most common type used in Dell laptops.
A laptop has two power sources: the AC adapter (charger) and the battery.
Battery-related issues can be caused by an aging battery, a battery reaching
end-of-life, the AC adapter not working correctly, and similar causes.

## Common battery symptoms

- The laptop battery does not hold a charge.
- The battery indicator LED does not glow, blinks in a specific pattern, or
  blinks constantly.
- The battery is not detected, not recognized, or not found.
- The battery charge is stuck at a certain percentage.
- The battery won't charge.

## Common AC-adapter symptoms (troubleshoot separately)

- The AC adapter or charger is not able to charge the battery.
- The AC adapter cannot turn on the laptop, or the LEDs on the laptop do
  not turn on.
- The AC adapter LED is off.
- AC adapter error messages such as "The AC adapter type cannot be
  determined." which prevents optimal computer performance.

## "Plugged in not charging" note

Some Dell laptops show "plugged in not charging" when you hover over the
battery icon, yet the battery charges outside Windows (BIOS or One-Time
Boot menu). Check whether your laptop has a hotkey (for example Fn+F2)
that disables battery charging; if so, use it to re-enable charging.

## Troubleshooting step 1 — Perform a hard reset

Performing a hard reset drains residual power that can cause problems.

### Nonremovable battery
- See Dell KB: "How to Reset Real Time Clock (RTC) to Recover Your Dell
  Laptop."
- On some Dell Latitude laptops, use "Forced ePSA to Recover from POST or
  Boot Failure on Dell Latitude PCs."

### Removable battery
1. Turn off the computer.
2. Disconnect the AC adapter and remove the battery.
3. Disconnect all USB devices, printers, webcams, and media cards
   (SD/xD).
4. Press and hold the power button for 15–20 seconds.
5. Reconnect the AC adapter and battery.
6. Turn on the computer.

## Step 2 — Verify AC-adapter functionality

Test with another known-good adapter and power cable.

1. Restart the computer.
2. Tap F2 at the Dell logo to enter BIOS/System Setup.
3. Check AC Adapter Type:
   - "None": verify the adapter is connected to laptop and outlet.
   - "Unknown": troubleshoot AC adapter issues (KB 000125125).
   - Recognized correctly: proceed to step 3.
4. Try another Dell AC adapter and power cable of the same wattage.

Dell offers an online AC-adapter hardware test; SupportAssist will run
it automatically when installed.

## Step 3 — Charge the battery in BIOS mode or with the laptop off

Operating-system settings (power management, device drivers) can impact
battery behavior. Charging outside the OS helps isolate hardware issues.

1. Turn off the computer.
2. Either (a) leave laptop off and charge for some time, or (b) restart
   and press F2 to enter BIOS, then let it charge there.
3. Verify the battery percentage increased.

## Step 4 — Run Dell hardware diagnostics

Use SupportAssist online battery diagnostics, or the built-in Pre-Boot
System Assessment:

1. Turn on the computer.
2. Tap F12 at the Dell logo until the One-Time Boot Menu appears.
3. Select Diagnostics and press Enter.
4. Follow on-screen prompts.
5. If the test fails, note the error code and validation code and contact
   Dell Technical Support.

## Step 5 — Check battery health status

Battery life depends mostly on charge/discharge cycles and the consumable
components inside a battery. It is normal for batteries to lose some
capacity and life over time — this is a characteristic of rechargeable
batteries and is not covered under warranty. See Dell KB: "How to Check
Battery Health Status on Dell Laptops" (KB 000124397) and "Swollen Battery
Information and Guidance" (KB 000128491).

## Step 6 — Update BIOS and Dell Quickset

Updating the BIOS helps the computer recognize the AC adapter correctly.

- Warning: Dell laptops must have a battery installed and connected to the
  AC adapter before updating BIOS. Some laptops require at least 10%
  battery charge.
- If the AC adapter type is not recognized, see "Forcing a BIOS Update
  Without the AC Adapter Attached on a Dell Laptop" (KB 000134938).
  Caution: updating BIOS from DOS when battery charge is under 10% can
  permanently damage the motherboard; proceed at your own risk.

Dell Quickset (on supported laptops) provides settings to disable/enable
battery charging, change Fn key behavior, and configure the wireless
shortcut. Install/update from Dell Drivers & Downloads under Application.

## Step 7 — Run the Windows troubleshooter

Windows 10 and 11 include a Hardware and Devices troubleshooter for power
issues.

1. Press Windows + R.
2. Type `Control` and press Enter.
3. In Control Panel search, type `Troubleshooter` and click Troubleshooting.
4. Under System and Security, click Power.

## Step 8 — Reinstall Microsoft ACPI battery driver

1. Press Windows + R.
2. Type `devmgmt.msc` and press Enter.
3. In Device Manager, expand Batteries.
4. Right-click Microsoft ACPI-Compliant Control Method Battery and click
   Uninstall.
5. Confirm the uninstall.
6. Restart the computer to reinstall the driver automatically.

## Step 9 — Check for battery recall

Some Dell batteries are subject to safety recalls.

1. Go to dellproduct.com.
2. Click Lookup.
3. Enter your Battery PPID and the security code.
4. Click Next to check. If affected, provide contact information for the
   replacement process.

You'll need your Dell laptop Service Tag or the battery PPID (serial
number) plus a shipping/service address.

## Step 10 — Replacement battery not recognized

Dell recommends using only Dell-sourced replacement batteries. If a
self-installed replacement is not recognized:

1. Turn the computer off.
2. Remove the AC adapter.
3. Remove the replacement battery.
4. Press and hold the power button for 20 seconds.
5. Reseat the battery cable and install the replacement battery.
6. Replace the bottom cover and attempt to power on.

If the replacement is still not recognized, reinstall the old battery (if
available) to verify the motherboard circuitry is still working. If the
battery was recently replaced under warranty, contact Dell Technical
Support.

## Further support

If none of these steps resolve the issue, contact Dell Technical Support at
dell.com/support/incidents-online/contactus/Dynamic. For consumers, the US
hardware warranty support line is 1-800-624-9896.
