#!/usr/bin/env python3
"""
Hexapod inverse kinematics and gait state machines.

Pure math - no serial, no Flask, no hardware imports. Ported from the
reference Hexapod.ino sketch (Arduino Mega + PS2 gamepad + Servo library),
adapted to run on the Pi instead of the Servo 2040 so the per-leg X/Y/Z
computed every frame can be reused directly for the web UI's leg visualizer.

Leg numbering (0-5) matches the reference sketch's leg1..leg6. Geometry and
home/body offsets are ported as final values - confirmed correct for this
chassis, not placeholders.

Per-servo calibration trim and the channel map are NOT ported from the
reference sketch, and deliberately do not live in this file. Trim (how far
a channel's true physical center sits from a literal 90 deg command) and
channel assignment (which of the 18 channels drives which leg/joint) are
facts about this specific robot's individual servos and wiring - they were
wrongly treated as portable constants early in this project, which is why
servos looked "calibrated" but weren't truly centered. Both now live in
hexapod_calibration.py as persisted, hand-edited config; this module stays
pure geometry with zero hardware/config-file knowledge, as the module
summary above promises.
"""

import math
from dataclasses import dataclass, field


LEG_COUNT = 6
CHANNEL_COUNT = 18
JOINTS = ("coxa", "femur", "tibia")

# Leg segment lengths, mm.
COXA_LENGTH = 51.0
FEMUR_LENGTH = 65.0
TIBIA_LENGTH = 121.0

# Coxa-to-toe home positions, mm, indexed by leg number 0-5.
HOME_X = (82.0, 0.0, -82.0, -82.0, 0.0, 82.0)
HOME_Y = (82.0, 116.0, 82.0, -82.0, -116.0, -82.0)
HOME_Z = (-80.0, -80.0, -80.0, -80.0, -80.0, -80.0)

# Body center-to-coxa servo distances, mm.
BODY_X = (110.4, 0.0, -110.4, -110.4, 0.0, 110.4)
BODY_Y = (58.4, 90.8, 58.4, -58.4, -90.8, -58.4)
BODY_Z = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

FRAME_TIME_MS = 20.0

# Commanded X/Y/R deadband below which a gait stops advancing once it
# returns to its resting tick, matching the reference sketch's threshold.
COMMAND_DEADBAND = 15.0

# Per-gait initial case assignment (leg 0-5) and the case each leg advances
# to once its current phase completes. Ported directly from the sketch's
# tripod_case/wave_case/ripple_case/tetrapod_case arrays and switch blocks.
GAIT_INITIAL_CASE = {
    "tripod": [1, 2, 1, 2, 1, 2],
    "wave": [1, 2, 3, 4, 5, 6],
    "ripple": [2, 6, 4, 1, 3, 5],
    "tetrapod": [1, 3, 2, 1, 2, 3],
}

WAVE_NEXT_CASE = {1: 6, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
RIPPLE_NEXT_CASE = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 1}
TETRAPOD_NEXT_CASE = {1: 2, 2: 3, 3: 1}

GAIT_NAMES = ("tripod", "wave", "ripple", "tetrapod")


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _solve_leg(x, y, z):
    """
    Shared trig core for leg_ik() and leg_joint_positions() - both derive
    from the exact same 2-link (femur/tibia) planar solve within the
    vertical plane defined by the coxa's horizontal bearing, so the
    visualizer's drawn joint positions can never drift out of sync with
    the angles actually being commanded to the servos (they're computed
    from the literal same intermediate values, not a separately-derived
    inverse that could disagree).

    Returns None if unreachable (mirrors leg_ik's silent-skip contract).
    """
    l0 = math.sqrt((x * x) + (y * y)) - COXA_LENGTH
    l3 = math.sqrt((l0 * l0) + (z * z))

    if not (TIBIA_LENGTH - FEMUR_LENGTH < l3 < TIBIA_LENGTH + FEMUR_LENGTH):
        return None

    phi_tibia = math.acos(
        ((FEMUR_LENGTH ** 2) + (TIBIA_LENGTH ** 2) - (l3 ** 2))
        / (2 * FEMUR_LENGTH * TIBIA_LENGTH)
    )
    gamma_femur = math.atan2(z, l0)
    phi_femur = math.acos(
        ((FEMUR_LENGTH ** 2) + (l3 ** 2) - (TIBIA_LENGTH ** 2))
        / (2 * FEMUR_LENGTH * l3)
    )
    # Coxa's horizontal bearing toward the toe - x is forward, y is right,
    # matching atan2(x, y) elsewhere in this module (0 deg = +Y/right,
    # 90 deg = +X/forward).
    theta_h = math.atan2(x, y)

    return {
        "gamma_femur": gamma_femur,
        "phi_femur": phi_femur,
        "phi_tibia": phi_tibia,
        "theta_h": theta_h,
    }


def leg_ik(leg_number, x, y, z):
    """
    Solve one leg's coxa/femur/tibia angles (degrees) for a target
    coxa-to-toe position (x, y, z), mm.

    Returns None if the target is out of reach (matches the reference
    sketch's silent skip - caller should hold the leg's previous angles).
    """
    solved = _solve_leg(x, y, z)
    if solved is None:
        return None

    theta_tibia = clamp(math.degrees(solved["phi_tibia"]) - 23.0, 0.0, 180.0)
    theta_femur = clamp(
        math.degrees(solved["phi_femur"] + solved["gamma_femur"]) + 14.0 + 90.0, 0.0, 180.0
    )

    theta_coxa = math.degrees(solved["theta_h"])
    theta_coxa = _apply_coxa_mount_offset(leg_number, theta_coxa)
    theta_coxa = clamp(theta_coxa, 0.0, 180.0)

    return theta_coxa, theta_femur, theta_tibia


def leg_joint_positions(x, y, z):
    """
    Coxa-relative (femur_pivot_xyz, tibia_pivot_xyz) for the same target
    leg_ik() would solve - the "knee" and "hip" points a visualizer needs
    to draw three real segments (coxa/femur/tibia) instead of one straight
    mount-to-toe line. Derived from the exact same _solve_leg() trig
    leg_ik() uses, so these positions are always geometrically consistent
    with the angles actually being commanded.

    Never raises: falls back to points along the direct mount-to-toe line
    if the target is unreachable, since a slightly-approximate diagram
    beats a frozen or crashed one - unlike leg_ik(), nothing here gets
    sent to a servo.
    """
    solved = _solve_leg(x, y, z)

    if solved is None:
        frac_femur = FEMUR_LENGTH / (FEMUR_LENGTH + TIBIA_LENGTH)
        femur_pivot = (0.0, 0.0, 0.0)
        tibia_pivot = (x * frac_femur, y * frac_femur, z * frac_femur)
        return femur_pivot, tibia_pivot

    theta_h = solved["theta_h"]
    femur_pivot = (
        COXA_LENGTH * math.sin(theta_h),
        COXA_LENGTH * math.cos(theta_h),
        0.0,
    )

    # Femur's actual elevation above the horizontal (theta_h) plane - the
    # same phi_femur + gamma_femur term leg_ik() converts into a servo
    # angle via its +14+90 offset; here it's used directly as a geometric
    # angle instead.
    femur_elevation = solved["gamma_femur"] + solved["phi_femur"]
    horiz_extra = FEMUR_LENGTH * math.cos(femur_elevation)
    vertical_extra = FEMUR_LENGTH * math.sin(femur_elevation)

    tibia_pivot = (
        femur_pivot[0] + horiz_extra * math.sin(theta_h),
        femur_pivot[1] + horiz_extra * math.cos(theta_h),
        femur_pivot[2] + vertical_extra,
    )

    return femur_pivot, tibia_pivot


def _apply_coxa_mount_offset(leg_number, theta_coxa):
    """
    Per-leg coxa mounting compensation, ported from the sketch's leg_IK
    switch/case. Legs 3-5 need the wraparound branch because atan2 can flip
    sign right where their mounting offset would otherwise straddle it.
    """
    if leg_number == 0:
        return theta_coxa + 45.0
    if leg_number == 1:
        return theta_coxa + 90.0
    if leg_number == 2:
        return theta_coxa + 135.0
    if leg_number == 3:
        return theta_coxa + 225.0 if theta_coxa < 0 else theta_coxa - 135.0
    if leg_number == 4:
        return theta_coxa + 270.0 if theta_coxa < 0 else theta_coxa - 90.0
    if leg_number == 5:
        return theta_coxa + 315.0 if theta_coxa < 0 else theta_coxa - 45.0
    raise ValueError(f"invalid leg_number {leg_number}")


def set_all_90():
    """
    Every joint at a literal 90 degrees - no trim. This is the mechanical
    horn-alignment reference position: with every channel commanded to the
    same raw value, a horn that isn't visually centered gets loosened and
    re-seated against this known-good reference, not electronically
    compensated for. Software trim (hexapod_calibration.py) covers the
    residual few-degree slop left over after that, applied later at the
    channel-output boundary - see apply_trim().
    """
    return {leg: (90.0, 90.0, 90.0) for leg in range(LEG_COUNT)}


def home_leg_xyz():
    return {leg: (HOME_X[leg], HOME_Y[leg], HOME_Z[leg]) for leg in range(LEG_COUNT)}


@dataclass
class GaitState:
    """
    Mutable walking state for one active gait. Reset whenever the gait
    selection changes (see reset_gait_state) - the reference sketch lets
    per-gait case arrays persist silently across mode switches, which this
    port deliberately avoids for predictability.
    """
    gait: str = "tripod"
    tick: int = 0
    case: list = field(default_factory=lambda: list(GAIT_INITIAL_CASE["tripod"]))
    leg_xyz: dict = field(default_factory=home_leg_xyz)
    step_height_multiplier: float = 1.0


def reset_gait_state(state: GaitState, gait: str):
    if gait not in GAIT_INITIAL_CASE:
        raise ValueError(f"unknown gait {gait!r}")

    state.gait = gait
    state.tick = 0
    state.case = list(GAIT_INITIAL_CASE[gait])
    state.leg_xyz = home_leg_xyz()


def compute_strides(commanded_x, commanded_y, commanded_r, fast):
    stride_x = 90 * commanded_x / 127
    stride_y = 90 * commanded_y / 127
    stride_r = 35 * commanded_r / 127
    sin_rot_z = math.sin(math.radians(stride_r))
    cos_rot_z = math.cos(math.radians(stride_r))
    duration_ms = 1080 if fast else 3240
    return stride_x, stride_y, sin_rot_z, cos_rot_z, duration_ms


def compute_amplitudes(leg_number, stride_x, stride_y, sin_rot_z, cos_rot_z, step_height_multiplier):
    total_x = HOME_X[leg_number] + BODY_X[leg_number]
    total_y = HOME_Y[leg_number] + BODY_Y[leg_number]

    rot_offset_x = (total_y * sin_rot_z) + (total_x * cos_rot_z) - total_x
    rot_offset_y = (total_y * cos_rot_z) - (total_x * sin_rot_z) - total_y

    amplitude_x = clamp((stride_x + rot_offset_x) / 2.0, -50, 50)
    amplitude_y = clamp((stride_y + rot_offset_y) / 2.0, -50, 50)

    if abs(stride_x + rot_offset_x) > abs(stride_y + rot_offset_y):
        amplitude_z = step_height_multiplier * (stride_x + rot_offset_x) / 4.0
    else:
        amplitude_z = step_height_multiplier * (stride_y + rot_offset_y) / 4.0

    return amplitude_x, amplitude_y, amplitude_z


def _in_deadband(commanded_x, commanded_y, commanded_r):
    return (
        abs(commanded_x) <= COMMAND_DEADBAND
        and abs(commanded_y) <= COMMAND_DEADBAND
        and abs(commanded_r) <= COMMAND_DEADBAND
    )


def _advance_tick(state, num_ticks):
    state.tick = state.tick + 1 if state.tick < num_ticks - 1 else 0


def tripod_gait_step(state, commanded_x, commanded_y, commanded_r, fast):
    if _in_deadband(commanded_x, commanded_y, commanded_r) and state.tick == 0:
        return

    stride_x, stride_y, sin_rot_z, cos_rot_z, duration_ms = compute_strides(
        commanded_x, commanded_y, commanded_r, fast
    )
    num_ticks = max(1, round(duration_ms / FRAME_TIME_MS / 2.0))

    for leg in range(LEG_COUNT):
        amp_x, amp_y, amp_z = compute_amplitudes(
            leg, stride_x, stride_y, sin_rot_z, cos_rot_z, state.step_height_multiplier
        )
        home_x, home_y, home_z = HOME_X[leg], HOME_Y[leg], HOME_Z[leg]
        phase = math.pi * state.tick / num_ticks

        if state.case[leg] == 1:
            x = home_x - (amp_x * math.cos(phase))
            y = home_y - (amp_y * math.cos(phase))
            z = home_z + (abs(amp_z) * math.sin(phase))
            if state.tick >= num_ticks - 1:
                state.case[leg] = 2
        else:
            x = home_x + (amp_x * math.cos(phase))
            y = home_y + (amp_y * math.cos(phase))
            z = home_z
            if state.tick >= num_ticks - 1:
                state.case[leg] = 1

        state.leg_xyz[leg] = (x, y, z)

    _advance_tick(state, num_ticks)


def wave_gait_step(state, commanded_x, commanded_y, commanded_r, fast):
    if _in_deadband(commanded_x, commanded_y, commanded_r) and state.tick == 0:
        return

    stride_x, stride_y, sin_rot_z, cos_rot_z, duration_ms = compute_strides(
        commanded_x, commanded_y, commanded_r, fast
    )
    num_ticks = max(1, round(duration_ms / FRAME_TIME_MS / 6.0))

    for leg in range(LEG_COUNT):
        amp_x, amp_y, amp_z = compute_amplitudes(
            leg, stride_x, stride_y, sin_rot_z, cos_rot_z, state.step_height_multiplier
        )
        home_x, home_y, home_z = HOME_X[leg], HOME_Y[leg], HOME_Z[leg]
        cur_x, cur_y, _cur_z = state.leg_xyz[leg]
        case = state.case[leg]

        if case == 1:
            phase = math.pi * state.tick / num_ticks
            x = home_x - (amp_x * math.cos(phase))
            y = home_y - (amp_y * math.cos(phase))
            z = home_z + (abs(amp_z) * math.sin(phase))
        else:
            x = cur_x - (amp_x / num_ticks / 2.5)
            y = cur_y - (amp_y / num_ticks / 2.5)
            z = home_z

        if state.tick >= num_ticks - 1:
            state.case[leg] = WAVE_NEXT_CASE[case]

        state.leg_xyz[leg] = (x, y, z)

    _advance_tick(state, num_ticks)


def ripple_gait_step(state, commanded_x, commanded_y, commanded_r, fast):
    if _in_deadband(commanded_x, commanded_y, commanded_r) and state.tick == 0:
        return

    stride_x, stride_y, sin_rot_z, cos_rot_z, duration_ms = compute_strides(
        commanded_x, commanded_y, commanded_r, fast
    )
    num_ticks = max(1, round(duration_ms / FRAME_TIME_MS / 6.0))

    for leg in range(LEG_COUNT):
        amp_x, amp_y, amp_z = compute_amplitudes(
            leg, stride_x, stride_y, sin_rot_z, cos_rot_z, state.step_height_multiplier
        )
        home_x, home_y, home_z = HOME_X[leg], HOME_Y[leg], HOME_Z[leg]
        cur_x, cur_y, _cur_z = state.leg_xyz[leg]
        case = state.case[leg]

        if case == 1:
            phase = math.pi * state.tick / (num_ticks * 2)
            x = home_x - (amp_x * math.cos(phase))
            y = home_y - (amp_y * math.cos(phase))
            z = home_z + (abs(amp_z) * math.sin(phase))
        elif case == 2:
            phase = math.pi * (num_ticks + state.tick) / (num_ticks * 2)
            x = home_x - (amp_x * math.cos(phase))
            y = home_y - (amp_y * math.cos(phase))
            z = home_z + (abs(amp_z) * math.sin(phase))
        else:
            x = cur_x - (amp_x / num_ticks / 2.0)
            y = cur_y - (amp_y / num_ticks / 2.0)
            z = home_z

        if state.tick >= num_ticks - 1:
            state.case[leg] = RIPPLE_NEXT_CASE[case]

        state.leg_xyz[leg] = (x, y, z)

    _advance_tick(state, num_ticks)


def tetrapod_gait_step(state, commanded_x, commanded_y, commanded_r, fast):
    if _in_deadband(commanded_x, commanded_y, commanded_r) and state.tick == 0:
        return

    stride_x, stride_y, sin_rot_z, cos_rot_z, duration_ms = compute_strides(
        commanded_x, commanded_y, commanded_r, fast
    )
    num_ticks = max(1, round(duration_ms / FRAME_TIME_MS / 3.0))

    for leg in range(LEG_COUNT):
        amp_x, amp_y, amp_z = compute_amplitudes(
            leg, stride_x, stride_y, sin_rot_z, cos_rot_z, state.step_height_multiplier
        )
        home_x, home_y, home_z = HOME_X[leg], HOME_Y[leg], HOME_Z[leg]
        cur_x, cur_y, _cur_z = state.leg_xyz[leg]
        case = state.case[leg]

        if case == 1:
            phase = math.pi * state.tick / num_ticks
            x = home_x - (amp_x * math.cos(phase))
            y = home_y - (amp_y * math.cos(phase))
            z = home_z + (abs(amp_z) * math.sin(phase))
        else:
            x = cur_x - (amp_x / num_ticks)
            y = cur_y - (amp_y / num_ticks)
            z = home_z

        if state.tick >= num_ticks - 1:
            state.case[leg] = TETRAPOD_NEXT_CASE[case]

        state.leg_xyz[leg] = (x, y, z)

    _advance_tick(state, num_ticks)


GAIT_STEP_FUNCTIONS = {
    "tripod": tripod_gait_step,
    "wave": wave_gait_step,
    "ripple": ripple_gait_step,
    "tetrapod": tetrapod_gait_step,
}


def step_gait(state: GaitState, commanded_x, commanded_y, commanded_r, fast):
    """Advance state.gait by one frame. Mutates and returns state.leg_xyz."""
    GAIT_STEP_FUNCTIONS[state.gait](state, commanded_x, commanded_y, commanded_r, fast)
    return state.leg_xyz


def leg_angles_for_frame(leg_xyz, previous_angles=None):
    """
    Run leg_ik for every leg. Legs whose target is unreachable keep their
    previous angles (matches the reference sketch's silent-skip behavior)
    or fall back to set_all_90() if no previous angles are known yet.
    """
    previous_angles = previous_angles or set_all_90()
    angles = {}

    for leg in range(LEG_COUNT):
        x, y, z = leg_xyz[leg]
        result = leg_ik(leg, x, y, z)
        angles[leg] = result if result is not None else previous_angles[leg]

    return angles


def angles_to_channels(angles, channel_map_by_leg):
    """
    Map {leg: (coxa, femur, tibia)} to a flat 18-element channel array,
    using the wiring map ({leg: {joint: channel}}) supplied by the caller -
    see hexapod_calibration.channel_map_by_leg(). No module-level default:
    the channel map is a hardware fact about this specific robot's wiring,
    discovered by hand, not something this pure-math module should guess at.

    Missing leg/joint entries are skipped, not raised on - that channel
    just keeps the safe 90 default below. hexapod_calibration.py's
    set_channel_map_entry() is written to never produce a map with a gap,
    but this is the layer that has to actually hold if it ever does: an
    IndexError/KeyError here used to take down the whole controller tick
    loop, which looked like "lost connection to the board" from the web UI
    with no obvious link back to whatever calibration edit caused it.
    """
    channels = [90.0] * CHANNEL_COUNT

    for leg, (coxa, femur, tibia) in angles.items():
        mapping = channel_map_by_leg.get(leg, {})
        for joint, value in zip(JOINTS, (coxa, femur, tibia)):
            channel = mapping.get(joint)
            if channel is not None and 0 <= channel < CHANNEL_COUNT:
                channels[channel] = value

    return channels


def apply_trim(channels, trim_deg_by_channel):
    """
    Adds each channel's calibration trim (a few degrees at most - the
    residual gap between a servo's true physical center and a literal 90
    deg command) and clamps to the servo's valid range. Applied once, at
    the very end, after angles_to_channels - trim is a hardware fact about
    one physical channel, not something IK/gait math should know about.
    """
    return [
        clamp(channels[ch] + trim_deg_by_channel.get(ch, 0.0), 0.0, 180.0)
        for ch in range(len(channels))
    ]


if __name__ == "__main__":
    # Quick standalone smoke check - no hardware/Pi/config file required.
    # Uses a local sequential channel map purely for this check, so this
    # module stays fully independent of hexapod_calibration.py's persisted
    # config, matching the "pure math" guarantee in the module docstring.
    demo_channel_map = {
        leg: {"coxa": leg * 3, "femur": leg * 3 + 1, "tibia": leg * 3 + 2}
        for leg in range(LEG_COUNT)
    }

    for gait_name in GAIT_NAMES:
        state = GaitState()
        reset_gait_state(state, gait_name)

        for _ in range(50):
            leg_xyz = step_gait(state, commanded_x=80, commanded_y=0, commanded_r=0, fast=True)

        angles = leg_angles_for_frame(leg_xyz)
        channels = angles_to_channels(angles, demo_channel_map)
        assert len(channels) == CHANNEL_COUNT
        femur_pivot, tibia_pivot = leg_joint_positions(*leg_xyz[0])
        print(f"{gait_name}: leg0 xyz={leg_xyz[0]} angles={angles[0]} "
              f"femur_pivot={femur_pivot} tibia_pivot={tibia_pivot}")

    print("set_all_90:", set_all_90()[0])
    print("angles_to_channels demo:", angles_to_channels(set_all_90(), demo_channel_map)[:3])
    print("apply_trim demo:", apply_trim([90.0] * CHANNEL_COUNT, {0: 3.5, 4: -2.0}))

    # angles_to_channels must survive a gap (e.g. mid-reassignment in the
    # Channel Mapping UI) instead of raising - see the KeyError bug this
    # was written to fix.
    incomplete_map = {leg: {} for leg in range(LEG_COUNT)}
    incomplete_map[0] = {"coxa": 0}  # femur/tibia missing entirely
    gapped = angles_to_channels(set_all_90(), incomplete_map)
    assert len(gapped) == CHANNEL_COUNT
    print("angles_to_channels survives a gap:", gapped[:3])

    print("OK")
