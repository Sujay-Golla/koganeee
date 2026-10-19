from kogane_base.protocol import (
    DroneState, DS_F_FC_LINK_UP, DS_F_YAW_VALID, DS_F_BATT_VALID, DS_F_LINKQ_VALID,
)
from verify_wifi import describe_state


def test_monitor_honors_validity_flags():
    state = DroneState(0, 0, 0, 1234, 4980, 0, 80)
    line = describe_state(state)
    assert "FC=DOWN" in line
    assert "yaw=unknown" in line
    assert "battery=unknown" in line
    assert "wifi_q=unknown" in line


def test_monitor_displays_forwarded_fc_values():
    flags = DS_F_FC_LINK_UP | DS_F_YAW_VALID | DS_F_BATT_VALID | DS_F_LINKQ_VALID
    line = describe_state(DroneState(0, 0, 0, -1234, 4980, flags, 80))
    assert "FC=UP DISARMED" in line
    assert "yaw=-12.34 deg" in line
    assert "battery=4.980 V" in line
    assert "wifi_q=80" in line
