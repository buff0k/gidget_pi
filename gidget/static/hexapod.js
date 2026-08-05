const statusEl = document.getElementById("hexapodStatus");
const connectedEl = document.getElementById("hexapodConnected");
const modeEl = document.getElementById("hexapodMode");
const gaitEl = document.getElementById("hexapodGait");
const voltageEl = document.getElementById("hexapodVoltage");
const currentEl = document.getElementById("hexapodCurrent");
const metaEl = document.getElementById("hexapodMeta");
const jsonEl = document.getElementById("hexapodJson");
const copyStateBtn = document.getElementById("copyStateBtn");
const freezeStateBtn = document.getElementById("freezeStateBtn");
const copyStateStatus = document.getElementById("copyStateStatus");

const modeSelect = document.getElementById("modeSelect");
const gaitSelect = document.getElementById("gaitSelect");
const fastToggle = document.getElementById("fastToggle");
const rotateLeftBtn = document.getElementById("rotateLeftBtn");
const rotateRightBtn = document.getElementById("rotateRightBtn");

// Some browsers restore <select> state across a reload even without the
// page asking for it. Every fresh load must start in Idle regardless of
// whatever the form last showed - relying on the browser to "just default
// to the first option" isn't guaranteed.
modeSelect.value = "idle";

const joystickCanvas = document.getElementById("joystickCanvas");
const joystickCtx = joystickCanvas.getContext("2d");

const legCanvas = document.getElementById("legCanvas");
const legCtx = legCanvas.getContext("2d");

const channelGrid = document.getElementById("channelGrid");

const JOY_RADIUS = (joystickCanvas.width / 2) - 18;
const HEARTBEAT_MS = 200;
const STATE_POLL_MS = 300;
const ROTATE_MAGNITUDE = 90;
const CHANNEL_COUNT = 18;

let stickX = 0;   // -127..127, forward/back
let stickY = 0;   // -127..127, left/right
let stickActive = false;
let rotateValue = 0; // -127..127, held while a rotate button is pressed
let manualChannels = new Array(CHANNEL_COUNT).fill(90);


function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
}

function fmtNum(value, decimals, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    const num = Number(value);
    if (Number.isNaN(num)) return "n/a";
    return num.toFixed(decimals) + suffix;
}

function setText(el, value) {
    el.textContent = value;
}

function setStatus(ok, error) {
    statusEl.classList.remove("good", "bad", "warn");

    if (ok === true) {
        statusEl.classList.add("good");
        statusEl.textContent = "ok";
    } else if (error) {
        statusEl.classList.add("bad");
        statusEl.textContent = error;
    } else {
        statusEl.classList.add("warn");
        statusEl.textContent = "n/a";
    }
}


// ---- Joystick (touch + mouse via Pointer Events) ----

function drawJoystick() {
    const w = joystickCanvas.width;
    const h = joystickCanvas.height;
    const cx = w / 2;
    const cy = h / 2;

    joystickCtx.clearRect(0, 0, w, h);

    joystickCtx.strokeStyle = "#333";
    joystickCtx.lineWidth = 1;
    joystickCtx.beginPath();
    joystickCtx.arc(cx, cy, JOY_RADIUS, 0, Math.PI * 2);
    joystickCtx.stroke();

    joystickCtx.beginPath();
    joystickCtx.moveTo(cx - JOY_RADIUS, cy);
    joystickCtx.lineTo(cx + JOY_RADIUS, cy);
    joystickCtx.moveTo(cx, cy - JOY_RADIUS);
    joystickCtx.lineTo(cx, cy + JOY_RADIUS);
    joystickCtx.stroke();

    joystickCtx.fillStyle = "#777";
    joystickCtx.font = "11px monospace";
    joystickCtx.textAlign = "center";
    joystickCtx.fillText("FWD", cx, cy - JOY_RADIUS - 6);

    const thumbX = cx + (stickY / 127) * JOY_RADIUS;
    const thumbY = cy - (stickX / 127) * JOY_RADIUS;

    joystickCtx.beginPath();
    joystickCtx.arc(thumbX, thumbY, 16, 0, Math.PI * 2);
    joystickCtx.fillStyle = stickActive ? "#80c7ff" : "#555";
    joystickCtx.fill();
}

function updateStickFromEvent(evt) {
    const rect = joystickCanvas.getBoundingClientRect();
    const scaleX = joystickCanvas.width / rect.width;
    const scaleY = joystickCanvas.height / rect.height;
    const px = (evt.clientX - rect.left) * scaleX;
    const py = (evt.clientY - rect.top) * scaleY;

    const cx = joystickCanvas.width / 2;
    const cy = joystickCanvas.height / 2;

    let dx = px - cx;
    let dy = py - cy;
    const dist = Math.hypot(dx, dy);

    if (dist > JOY_RADIUS) {
        dx = (dx / dist) * JOY_RADIUS;
        dy = (dy / dist) * JOY_RADIUS;
    }

    stickY = Math.round((dx / JOY_RADIUS) * 127);
    stickX = Math.round((-dy / JOY_RADIUS) * 127);

    drawJoystick();
}

function resetStick() {
    stickX = 0;
    stickY = 0;
    stickActive = false;
    drawJoystick();
}

joystickCanvas.addEventListener("pointerdown", (evt) => {
    stickActive = true;
    joystickCanvas.setPointerCapture(evt.pointerId);
    updateStickFromEvent(evt);
});

joystickCanvas.addEventListener("pointermove", (evt) => {
    if (!stickActive) return;
    updateStickFromEvent(evt);
});

joystickCanvas.addEventListener("pointerup", resetStick);
joystickCanvas.addEventListener("pointercancel", resetStick);

drawJoystick();


// ---- Rotate hold-buttons ----

function bindHoldButton(button, onPress, onRelease) {
    button.addEventListener("pointerdown", (evt) => {
        button.setPointerCapture(evt.pointerId);
        onPress();
    });
    button.addEventListener("pointerup", onRelease);
    button.addEventListener("pointercancel", onRelease);
    button.addEventListener("pointerleave", onRelease);
}

bindHoldButton(rotateLeftBtn, () => { rotateValue = -ROTATE_MAGNITUDE; }, () => { rotateValue = 0; });
bindHoldButton(rotateRightBtn, () => { rotateValue = ROTATE_MAGNITUDE; }, () => { rotateValue = 0; });


// ---- Manual channel sliders ----
//
// Raw per-channel control, bypassing gait/IK entirely - only takes effect
// on the controller while Mode is "manual" (see hexapod_controller.py),
// but the sliders themselves are always live so switching into Manual mode
// doesn't require re-touching every channel.

function buildChannelGrid() {
    for (let i = 0; i < CHANNEL_COUNT; i++) {
        const wrap = document.createElement("div");
        wrap.className = "channel-control";

        const label = document.createElement("div");
        label.className = "channel-control-label";

        const nameSpan = document.createElement("span");
        nameSpan.textContent = `Ch ${i}`;

        const valueSpan = document.createElement("span");
        valueSpan.id = `channelValue${i}`;
        valueSpan.textContent = "90°";

        label.appendChild(nameSpan);
        label.appendChild(valueSpan);

        const slider = document.createElement("input");
        slider.type = "range";
        slider.min = "0";
        slider.max = "180";
        slider.step = "1";
        slider.value = "90";
        slider.id = `channelSlider${i}`;

        slider.addEventListener("input", () => {
            manualChannels[i] = Number(slider.value);
            valueSpan.textContent = `${slider.value}°`;
        });

        wrap.appendChild(label);
        wrap.appendChild(slider);
        channelGrid.appendChild(wrap);
    }
}

buildChannelGrid();

// Keeps the sliders honest against what the hardware is actually doing,
// not just whatever this page happened to load with. Only syncs while
// Manual isn't the active mode - once you're in Manual and dragging a
// slider, incoming state polls must not fight your input. This also means
// switching into Manual always starts from the real current position
// (read from hexapod_state.json) instead of silently resetting every
// channel to 90 and causing an uncommanded movement - which is exactly
// what a page reload used to do.
function syncManualChannelsFromState(channels) {
    if (modeSelect.value === "manual") return;
    if (!Array.isArray(channels) || channels.length !== CHANNEL_COUNT) return;

    for (let i = 0; i < CHANNEL_COUNT; i++) {
        const value = Math.round(Number(channels[i]));
        if (Number.isNaN(value)) continue;

        manualChannels[i] = value;

        const slider = document.getElementById(`channelSlider${i}`);
        const valueSpan = document.getElementById(`channelValue${i}`);
        if (slider) slider.value = String(value);
        if (valueSpan) valueSpan.textContent = `${value}°`;
    }
}


// ---- Calibration & Channel Mapping ----
//
// Both panels write straight to hexapod_calibration.json via small REST
// endpoints (not the command relay) - hexapod_controller.py picks up
// changes within ~1s (see CalibrationCache in hexapod_controller.py). The
// Channel Mapping panel's "test" jog is the one exception: it borrows the
// existing Manual-mode command path to move exactly one channel briefly,
// rather than adding a second live-command mechanism.

const calibChannelSelect = document.getElementById("calibChannelSelect");
const calibTrimValue = document.getElementById("calibTrimValue");
const calibStatus = document.getElementById("calibStatus");
const trimTableBody = document.getElementById("trimTableBody");
const mapTableBody = document.getElementById("mapTableBody");
const mapStatus = document.getElementById("mapStatus");
const mapIssues = document.getElementById("mapIssues");
const mapResetBtn = document.getElementById("mapResetBtn");

const LEG_COUNT = 6;
const JOINT_NAMES = ["coxa", "femur", "tibia"];

let lastCalibration = { channel_map: {}, trim_deg: {} };
// {channel, offset} while a row's Test button is held - read by
// buildManualChannelsForSend() in the heartbeat below.
let testChannelOverride = null;
let modeBeforeTest = null;
// Only sync the mapping table's leg/joint <select> values to the server's
// current assignment once, on the first successful fetch - after that they
// are pure input for the next Assign click. Otherwise a background poll
// mid-edit would silently snap a dropdown back under the operator's hand.
let mapRowsSynced = false;

function jointLabel(joint) {
    if (!joint) return "n/a";
    return joint.charAt(0).toUpperCase() + joint.slice(1);
}

function populateChannelSelect(select) {
    for (let i = 0; i < CHANNEL_COUNT; i++) {
        const opt = document.createElement("option");
        opt.value = String(i);
        opt.textContent = `Channel ${i}`;
        select.appendChild(opt);
    }
}

populateChannelSelect(calibChannelSelect);

// ---- Calibration: single-channel nudge + all-channel trim summary ----

function renderCalibDisplay() {
    const trim = (lastCalibration.trim_deg || {})[calibChannelSelect.value];
    calibTrimValue.textContent = trim === undefined ? "n/a" : `${Number(trim).toFixed(1)}°`;
}

function renderTrimTable() {
    const trimDeg = lastCalibration.trim_deg || {};
    trimTableBody.innerHTML = "";

    for (let row = 0; row < CHANNEL_COUNT / 3; row++) {
        const tr = document.createElement("tr");

        for (let col = 0; col < 3; col++) {
            const ch = row * 3 + col;
            const chTd = document.createElement("td");
            chTd.textContent = String(ch);

            const trimTd = document.createElement("td");
            const trim = trimDeg[String(ch)];
            trimTd.className = "assigned-badge";
            trimTd.textContent = trim === undefined ? "n/a" : `${Number(trim).toFixed(1)}°`;

            tr.appendChild(chTd);
            tr.appendChild(trimTd);
        }

        trimTableBody.appendChild(tr);
    }
}

calibChannelSelect.addEventListener("change", renderCalibDisplay);

async function nudgeTrim(delta) {
    const channel = Number(calibChannelSelect.value);

    try {
        const res = await fetch("/hexapod/api/calibration/trim", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel, delta, session_id: window.GIDGET_SESSION_ID }),
        });
        const body = await res.json();

        if (!res.ok) {
            calibStatus.textContent = body.error || "Save failed";
            return;
        }

        lastCalibration = body.calibration;
        renderCalibDisplay();
        renderTrimTable();
        calibStatus.textContent = "Saved";
        setTimeout(() => { calibStatus.textContent = ""; }, 1500);
    } catch (e) {
        calibStatus.textContent = "Save failed - offline?";
    }
}

document.getElementById("calibNudgeMinus5").addEventListener("click", () => nudgeTrim(-5));
document.getElementById("calibNudgeMinus1").addEventListener("click", () => nudgeTrim(-1));
document.getElementById("calibNudgePlus1").addEventListener("click", () => nudgeTrim(1));
document.getElementById("calibNudgePlus5").addEventListener("click", () => nudgeTrim(5));

// ---- Channel Mapping: all 18 channels in one table ----

// Borrows Manual mode to move exactly one channel a bounded amount away
// from its current position and back, so the operator can watch which
// physical joint responds.
//
// Two things had to be fixed here beyond the basic press/release: (1) the
// heartbeat only fires every HEARTBEAT_MS (200ms) - a quick tap could start
// AND end entirely between two ticks, so the override was never actually
// sent at all. Fixed by calling sendCommand() immediately on press and on
// release instead of only relying on the timer. (2) even with an immediate
// send, a fast tap barely moves the servo before reverting it - fixed with
// a minimum hold duration, so release only takes effect once at least
// MIN_TEST_HOLD_MS has passed since the press (a genuinely long hold is
// unaffected - it already exceeds that by the time you let go).
const MIN_TEST_HOLD_MS = 350;
let testHoldTimer = null;
let testStartedAt = 0;

function startChannelTest(channel) {
    if (testHoldTimer) {
        clearTimeout(testHoldTimer);
        testHoldTimer = null;
    }
    // If a previous test's minimum-hold timer hasn't fired yet, keep the
    // ORIGINAL pre-test mode rather than capturing "manual" as it.
    if (modeBeforeTest === null) {
        modeBeforeTest = modeSelect.value;
    }
    modeSelect.value = "manual";
    testChannelOverride = { channel, offset: 25 };
    testStartedAt = Date.now();
    sendCommand();
}

function finishChannelTest() {
    testChannelOverride = null;
    if (modeBeforeTest !== null) {
        modeSelect.value = modeBeforeTest;
        modeBeforeTest = null;
    }
    sendCommand();
}

function stopChannelTest() {
    const remaining = MIN_TEST_HOLD_MS - (Date.now() - testStartedAt);

    if (remaining <= 0) {
        finishChannelTest();
    } else {
        testHoldTimer = setTimeout(() => {
            testHoldTimer = null;
            finishChannelTest();
        }, remaining);
    }
}

async function assignChannel(channel) {
    const legSelect = document.getElementById(`mapLeg${channel}`);
    const jointSelect = document.getElementById(`mapJoint${channel}`);
    const leg = Number(legSelect.value);
    const joint = jointSelect.value;

    try {
        const res = await fetch("/hexapod/api/calibration/channel_map", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel, leg, joint, session_id: window.GIDGET_SESSION_ID }),
        });
        const body = await res.json();

        if (!res.ok) {
            mapStatus.textContent = body.error || "Assign failed";
            return;
        }

        // A collision swap (see hexapod_calibration.py) may have moved a
        // DIFFERENT channel too - re-render every row's badge, not just
        // this one, from the server's actual resulting state.
        lastCalibration = body.calibration;
        renderMapTable();
        renderMapIssues();
        mapStatus.textContent = `Assigned channel ${channel}`;
        setTimeout(() => { mapStatus.textContent = ""; }, 2000);
    } catch (e) {
        mapStatus.textContent = "Assign failed - offline?";
    }
}

function buildMapTableSkeleton() {
    for (let ch = 0; ch < CHANNEL_COUNT; ch++) {
        const tr = document.createElement("tr");

        const chTd = document.createElement("td");
        chTd.textContent = String(ch);

        const assignedTd = document.createElement("td");
        assignedTd.id = `mapAssigned${ch}`;
        assignedTd.className = "assigned-badge";
        assignedTd.textContent = "n/a";

        const testTd = document.createElement("td");
        const testBtn = document.createElement("button");
        testBtn.type = "button";
        testBtn.textContent = "Test";
        bindHoldButton(testBtn, () => startChannelTest(ch), stopChannelTest);
        testTd.appendChild(testBtn);

        const legTd = document.createElement("td");
        const legSelect = document.createElement("select");
        legSelect.id = `mapLeg${ch}`;
        for (let leg = 0; leg < LEG_COUNT; leg++) {
            const opt = document.createElement("option");
            opt.value = String(leg);
            opt.textContent = `Leg ${leg}`;
            legSelect.appendChild(opt);
        }
        legTd.appendChild(legSelect);

        const jointTd = document.createElement("td");
        const jointSelect = document.createElement("select");
        jointSelect.id = `mapJoint${ch}`;
        JOINT_NAMES.forEach((joint) => {
            const opt = document.createElement("option");
            opt.value = joint;
            opt.textContent = jointLabel(joint);
            jointSelect.appendChild(opt);
        });
        jointTd.appendChild(jointSelect);

        const assignTd = document.createElement("td");
        const assignBtn = document.createElement("button");
        assignBtn.type = "button";
        assignBtn.textContent = "Assign";
        assignBtn.addEventListener("click", () => assignChannel(ch));
        assignTd.appendChild(assignBtn);

        tr.appendChild(chTd);
        tr.appendChild(assignedTd);
        tr.appendChild(testTd);
        tr.appendChild(legTd);
        tr.appendChild(jointTd);
        tr.appendChild(assignTd);
        mapTableBody.appendChild(tr);
    }
}

function renderMapTable() {
    const channelMap = lastCalibration.channel_map || {};

    for (let ch = 0; ch < CHANNEL_COUNT; ch++) {
        const entry = channelMap[String(ch)];
        const badge = document.getElementById(`mapAssigned${ch}`);
        if (badge) {
            badge.textContent = entry ? `L${entry.leg} ${jointLabel(entry.joint)}` : "unassigned";
        }

        if (!mapRowsSynced && entry) {
            const legSelect = document.getElementById(`mapLeg${ch}`);
            const jointSelect = document.getElementById(`mapJoint${ch}`);
            if (legSelect) legSelect.value = String(entry.leg);
            if (jointSelect) jointSelect.value = entry.joint;
        }
    }

    mapRowsSynced = true;
}

// Surfaces gaps/duplicates the server finds in the raw stored map (see
// hexapod_calibration.channel_map_issues) - the swap-on-assign logic
// should keep new edits from ever producing one, but this is what makes
// leftover corruption (from before that fix existed, or a hand-edited
// file) visible instead of silently patched over by the "missing channel
// stays at safe neutral" fallback in hexapod_kinematics.angles_to_channels.
function renderMapIssues() {
    const issues = lastCalibration.issues || [];

    if (!issues.length) {
        mapIssues.style.display = "none";
        mapIssues.innerHTML = "";
        return;
    }

    mapIssues.style.display = "block";
    const items = issues.map((issue) => `<li>${issue}</li>`).join("");
    mapIssues.innerHTML = `<strong>Channel map has ${issues.length} problem(s):</strong><ul>${items}</ul>`;
}

mapResetBtn.addEventListener("click", async () => {
    if (!window.confirm("Reset the channel map to the default sequential assignment? Trim values are kept.")) {
        return;
    }

    try {
        const res = await fetch("/hexapod/api/calibration/reset_channel_map", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: window.GIDGET_SESSION_ID }),
        });
        const body = await res.json();

        if (!res.ok) {
            mapStatus.textContent = body.error || "Reset failed";
            return;
        }

        lastCalibration = body.calibration;
        mapRowsSynced = false;
        renderMapTable();
        renderMapIssues();
        mapStatus.textContent = "Channel map reset";
        setTimeout(() => { mapStatus.textContent = ""; }, 2000);
    } catch (e) {
        mapStatus.textContent = "Reset failed - offline?";
    }
});

buildMapTableSkeleton();

async function fetchCalibration() {
    try {
        const res = await fetch("/hexapod/api/calibration", { cache: "no-store" });
        if (!res.ok) return;
        lastCalibration = await res.json();
        renderCalibDisplay();
        renderTrimTable();
        renderMapTable();
        renderMapIssues();
    } catch (e) {
        // Best-effort - the next poll retries.
    }
}

fetchCalibration();
setInterval(fetchCalibration, STATE_POLL_MS);


// ---- Command heartbeat ----
//
// Runs continuously, not just while the joystick is being dragged, so a
// mode like "calibrate_90" stays active as long as it's selected - the
// controller's staleness/deadman timeout (0.5s) needs fresh commands on a
// steady cadence regardless of what's driving them.

let sessionSuperseded = false;

// While the Channel Mapping panel's test button is held, sends a copy of
// manualChannels with just the tested channel offset - never mutates
// manualChannels itself, so the Manual panel's sliders aren't disturbed by
// a test jog.
function buildManualChannelsForSend() {
    if (!testChannelOverride) return manualChannels;

    const copy = manualChannels.slice();
    const idx = testChannelOverride.channel;
    const base = copy[idx];
    let target = base + testChannelOverride.offset;
    if (target > 180) target = base - testChannelOverride.offset;
    target = Math.max(0, Math.min(180, target));
    copy[idx] = target;
    return copy;
}

async function sendCommand() {
    if (sessionSuperseded) return;

    const body = {
        mode: modeSelect.value,
        gait: gaitSelect.value,
        speed: fastToggle.checked ? 1.0 : 0.5,
        x: stickX,
        y: stickY,
        r: rotateValue,
        manual_channels: buildManualChannelsForSend(),
        session_id: window.GIDGET_SESSION_ID,
        source: "web-joystick",
    };

    try {
        const res = await fetch("/hexapod/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (res.status === 409) {
            // Another tab/reload has taken over command authority - stop
            // hammering a rejected session and make it obvious why the
            // controls have gone dead, rather than failing silently.
            sessionSuperseded = true;
            setStatus(false, "Another tab has taken control - reload this page");
        }
    } catch (e) {
        // Best-effort - the next heartbeat tick will retry, and the
        // controller's staleness timeout covers a dropped connection.
    }
}

setInterval(sendCommand, HEARTBEAT_MS);


// ---- Leg visualizer ----

function resizeCanvasForDisplay(canvas) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width));
    const height = Math.max(280, Math.floor(rect.height || 420));

    if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
    }
}

function drawLegs(legs) {
    resizeCanvasForDisplay(legCanvas);

    const width = legCanvas.width;
    const height = legCanvas.height;
    const cx = width / 2;
    const cy = height / 2;

    legCtx.clearRect(0, 0, width, height);
    legCtx.fillStyle = "#050505";
    legCtx.fillRect(0, 0, width, height);

    if (!legs || !legs.length) {
        legCtx.fillStyle = "#777";
        legCtx.font = "16px monospace";
        legCtx.textAlign = "left";
        legCtx.fillText("Waiting for hexapod state...", 20, cy);
        return [];
    }

    // Auto-scale mm -> px from the furthest point of any leg, with padding.
    // Includes the knee/hip pivots, not just mount/toe - a bent leg's knee
    // can swing wider than a straight line from mount to toe would suggest.
    let maxExtent = 50;
    legs.forEach((leg) => {
        [leg.mount_x, leg.femur_pivot_x, leg.tibia_pivot_x, leg.toe_x].forEach((v) => {
            maxExtent = Math.max(maxExtent, Math.abs(v));
        });
        [leg.mount_y, leg.femur_pivot_y, leg.tibia_pivot_y, leg.toe_y].forEach((v) => {
            maxExtent = Math.max(maxExtent, Math.abs(v));
        });
    });
    const padding = 60;
    const scale = (Math.min(width, height) / 2 - padding) / maxExtent;

    function toScreen(x, y) {
        // Body X is forward, Y is right - screen X follows Y (right),
        // screen Y follows -X (forward is up on screen).
        return [cx + (y * scale), cy - (x * scale)];
    }

    // Body outline through the 6 mount points, in leg order.
    legCtx.strokeStyle = "#444";
    legCtx.lineWidth = 2;
    legCtx.beginPath();
    legs.forEach((leg, index) => {
        const [px, py] = toScreen(leg.mount_x, leg.mount_y);
        if (index === 0) legCtx.moveTo(px, py);
        else legCtx.lineTo(px, py);
    });
    legCtx.closePath();
    legCtx.stroke();

    // Each leg drawn as three real segments (coxa/femur/tibia), not one
    // straight mount-to-toe line - the old single-line abstraction is
    // exactly why "which segment is which joint" was impossible to tell
    // at a glance. Each segment gets its own color plus a channel-number
    // label, using the same channel map the controller actually commands
    // (leg.channels), so the diagram and the hardware can never disagree
    // about which channel drives what.
    const JOINT_STYLE = {
        coxa: { color: "#ff9f4d", short: "C" },
        femur: { color: "#80c7ff", short: "F" },
        tibia: { color: "#8dffb0", short: "T" },
    };

    function drawSegment(x1, y1, x2, y2, joint, channel) {
        const style = JOINT_STYLE[joint];
        legCtx.strokeStyle = style.color;
        legCtx.lineWidth = 3;
        legCtx.beginPath();
        legCtx.moveTo(x1, y1);
        legCtx.lineTo(x2, y2);
        legCtx.stroke();

        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        const label = channel === undefined || channel === null
            ? `${style.short}?`
            : `${style.short}${channel}`;

        legCtx.fillStyle = style.color;
        legCtx.font = "9px monospace";
        legCtx.textAlign = "center";
        legCtx.fillText(label, midX, midY - 4);
    }

    const unreachableLegs = [];

    legs.forEach((leg) => {
        const [mx, my] = toScreen(leg.mount_x, leg.mount_y);
        const [fx, fy] = toScreen(leg.femur_pivot_x, leg.femur_pivot_y);
        const [kx, ky] = toScreen(leg.tibia_pivot_x, leg.tibia_pivot_y);
        const [tx, ty] = toScreen(leg.toe_x, leg.toe_y);
        const chans = leg.channels || {};

        drawSegment(mx, my, fx, fy, "coxa", chans.coxa);
        drawSegment(fx, fy, kx, ky, "femur", chans.femur);
        drawSegment(kx, ky, tx, ty, "tibia", chans.tibia);

        // leg.reachable is false only in "walk", when this tick's target
        // was out of physical reach and the angles being sent are a stale
        // hold-over, not a live solve - see leg_angles_for_frame() in
        // hexapod_kinematics.py. A ring around the toe makes "this leg has
        // silently stopped moving" visible instead of indistinguishable
        // from normal stillness.
        if (leg.reachable === false) {
            unreachableLegs.push(leg.index);
            legCtx.beginPath();
            legCtx.arc(tx, ty, 12, 0, Math.PI * 2);
            legCtx.strokeStyle = "#ff4444";
            legCtx.lineWidth = 2;
            legCtx.setLineDash([3, 3]);
            legCtx.stroke();
            legCtx.setLineDash([]);
        }

        legCtx.beginPath();
        legCtx.arc(mx, my, 4, 0, Math.PI * 2);
        legCtx.fillStyle = "#666";
        legCtx.fill();

        // Knee (femur/tibia joint) - small dot so the bend is visible even
        // when the two segments are nearly in line.
        legCtx.beginPath();
        legCtx.arc(kx, ky, 3, 0, Math.PI * 2);
        legCtx.fillStyle = "#999";
        legCtx.fill();

        // Toe height (Z) hinted by dot size - smaller/dimmer means the
        // foot is lifted higher off the ground. Home Z is -80mm for every
        // leg, and lifting a foot moves Z toward 0 (less negative).
        const lifted = Math.max(0, leg.z + 80);
        const radius = Math.max(3, 7 - (lifted / 15));
        legCtx.beginPath();
        legCtx.arc(tx, ty, radius, 0, Math.PI * 2);
        legCtx.fillStyle = lifted > 5 ? "#ffd36e" : "#80ff9f";
        legCtx.fill();

        legCtx.fillStyle = "#ccc";
        legCtx.font = "bold 11px monospace";
        legCtx.textAlign = "center";
        legCtx.fillText(`L${leg.index}`, mx, my - 12);
    });

    // Forward-direction marker.
    legCtx.fillStyle = "#555";
    legCtx.font = "12px monospace";
    legCtx.textAlign = "center";
    legCtx.fillText("FWD ↑", cx, 20);

    return unreachableLegs;
}


// ---- State poll ----

let lastState = {};
let frozen = false;

async function copyStateText() {
    const text = JSON.stringify(lastState, null, 2);

    try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) {
            throw new Error("Clipboard API unavailable");
        }
        await navigator.clipboard.writeText(text);
        copyStateStatus.textContent = "Copied";
        setTimeout(() => { copyStateStatus.textContent = ""; }, 2000);
    } catch (e) {
        // navigator.clipboard is often restricted to HTTPS/localhost - on a
        // plain http://gidget.local connection it may not exist at all.
        // Fall back to selecting the text so Ctrl-C / long-press-copy works.
        const range = document.createRange();
        range.selectNodeContents(jsonEl);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        copyStateStatus.textContent = "Auto-copy unavailable here - text selected, press Ctrl-C";
    }
}

copyStateBtn.addEventListener("click", copyStateText);

freezeStateBtn.addEventListener("click", () => {
    frozen = !frozen;
    freezeStateBtn.textContent = frozen ? "Resume updates" : "Freeze updates";
});

async function refreshState() {
    if (frozen) return;

    try {
        const res = await fetch("/hexapod/api/state", { cache: "no-store" });

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const state = await res.json();
        lastState = state;
        const telemetry = state.telemetry || {};
        const legs = state.legs || [];

        document.getElementById("topStatus").textContent =
            `Hexapod ${state.ok === true ? "ok" : "n/a"} | ${fmt(state.mode)} | ${fmt(state.gait)}`;

        setStatus(state.ok, state.error);
        setText(connectedEl, state.connected ? "connected" : "no telemetry");
        connectedEl.classList.remove("good", "bad", "warn");
        connectedEl.classList.add(state.connected ? "good" : "warn");

        setText(modeEl, fmt(state.mode));
        setText(gaitEl, fmt(state.gait));
        setText(voltageEl, fmtNum(telemetry.voltage_v, 2, " V"));
        setText(currentEl, fmtNum(telemetry.current_a, 2, " A"));

        syncManualChannelsFromState(state.channels);

        const unreachableLegs = drawLegs(legs);
        const unreachableNote = unreachableLegs.length
            ? ` | UNREACHABLE (dashed red ring, frozen angles): leg ${unreachableLegs.join(", leg ")}`
            : "";

        metaEl.textContent = `${legs.length} legs reporting | malformed serial lines: ${fmt(state.malformed_lines, "")}${unreachableNote}`;
        jsonEl.textContent = JSON.stringify(state, null, 2);
    } catch (err) {
        statusEl.textContent = "error";
        statusEl.classList.add("bad");
        metaEl.textContent = "Hexapod error: " + err;
    }
}

refreshState();
setInterval(refreshState, STATE_POLL_MS);
window.addEventListener("resize", () => { if (!frozen) refreshState(); });
