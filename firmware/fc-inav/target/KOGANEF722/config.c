/*
 * KOGANE F722 — iNAV custom target default config (SKELETON)
 *
 * targetConfiguration() runs once to seed sane defaults so a freshly-flashed board
 * boots close to flyable. Anything here can still be overridden from the CLI
 * (see fc-inav/config/kogane-fc.diff). Reconcile setting names with your iNAV version.
 */
#include "platform.h"
#include "config/config_master.h"
#include "fc/config.h"

void targetConfiguration(void)
{
    // TODO(kogane): set defaults matching kogane-fc.diff, e.g.:
    //   motorConfigMutable()->motorPwmProtocol = PWM_TYPE_DSHOT300;
    //   rxConfigMutable()->receiverType = RX_TYPE_SERIAL;
    //   rxConfigMutable()->serialrx_provider = SERIALRX_CRSF;
    //   batteryMetersConfigMutable()->voltage.scale = 1100;
    //   rangefinderConfigMutable()->rangefinder_hardware = RANGEFINDER_VL53L1X;
    //   blackboxConfigMutable()->device = BLACKBOX_DEVICE_SDCARD;
    // Names differ across iNAV majors — verify against your checked-out release.
}
