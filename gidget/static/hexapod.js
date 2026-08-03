const statusEl = document.getElementById("hexapodStatus");
const connectedEl = document.getElementById("hexapodConnected");
const modeEl = document.getElementById("hexapodMode");
const gaitEl = document.getElementById("hexapodGait");
const voltageEl = document.getElementById("hexapodVoltage");
const currentEl = document.getElementById("hexapodCurrent");
const metaEl = document.getElementById("hexapodMeta");
const jsonEl = document.getElementById("hexapodJson");

const modeSelect = document.getElementById("modeSelect");
const gaitSelect = document.getElementById("gaitSelect");
const fastToggle = document.getElementById("fastToggle");
const rotateLeftBtn = document.getElementById("rotateLeftBtn");
const rotateRightBtn = document.getElementById("rotateRightBtn");

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


// ---- Command heartbeat ----
//
// Runs continuously, not just while the joystick is being dragged, so a
// mode like "calibrate_90" stays active as long as it's selected - the
// controller's staleness/deadman timeout (0.5s) needs fresh commands on a
// steady cadence regardless of what's driving them.

async function sendCommand() {
    const body = {
        mode: modeSelect.value,
        gait: gaitSelect.value,
        speed: fastToggle.checked ? 1.0 : 0.5,
        x: stickX,
        y: stickY,
        r: rotateValue,
        manual_channels: manualChannels,
        source: "web-joystick",
    };

    try {
        await fetch("/hexapod/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
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
        return;
    }

    // Auto-scale mm -> px from the furthest toe/mount point, with padding.
    let maxExtent = 50;
    legs.forEach((leg) => {
        maxExtent = Math.max(maxExtent, Math.abs(leg.mount_x), Math.abs(leg.mount_y), Math.abs(leg.toe_x), Math.abs(leg.toe_y));
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

    // Each leg: mount point -> toe position.
    legs.forEach((leg) => {
        const [mx, my] = toScreen(leg.mount_x, leg.mount_y);
        const [tx, ty] = toScreen(leg.toe_x, leg.toe_y);

        legCtx.strokeStyle = "#80c7ff";
        legCtx.lineWidth = 2;
        legCtx.beginPath();
        legCtx.moveTo(mx, my);
        legCtx.lineTo(tx, ty);
        legCtx.stroke();

        legCtx.beginPath();
        legCtx.arc(mx, my, 4, 0, Math.PI * 2);
        legCtx.fillStyle = "#666";
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

        legCtx.fillStyle = "#777";
        legCtx.font = "11px monospace";
        legCtx.textAlign = "center";
        legCtx.fillText(String(leg.index), tx, ty - 10);
    });

    // Forward-direction marker.
    legCtx.fillStyle = "#555";
    legCtx.font = "12px monospace";
    legCtx.textAlign = "center";
    legCtx.fillText("FWD ↑", cx, 20);
}


// ---- State poll ----

async function refreshState() {
    try {
        const res = await fetch("/hexapod/api/state", { cache: "no-store" });

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const state = await res.json();
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

        drawLegs(legs);

        metaEl.textContent = `${legs.length} legs reporting | malformed serial lines: ${fmt(state.malformed_lines, "")}`;
        jsonEl.textContent = JSON.stringify(state, null, 2);
    } catch (err) {
        statusEl.textContent = "error";
        statusEl.classList.add("bad");
        metaEl.textContent = "Hexapod error: " + err;
    }
}

refreshState();
setInterval(refreshState, STATE_POLL_MS);
window.addEventListener("resize", () => refreshState());
