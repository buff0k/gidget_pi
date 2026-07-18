const statusEl = document.getElementById("imuStatus");
const tiltCanvas = document.getElementById("tiltCanvas");
const tiltCtx = tiltCanvas.getContext("2d");
const chartCanvas = document.getElementById("imuChart");
const chartCtx = chartCanvas.getContext("2d");

function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
}

function fmtNum(value, decimals, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return Number(value).toFixed(decimals) + suffix;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
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

function drawTilt(pitch, roll) {
    const w = tiltCanvas.width;
    const h = tiltCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(w, h) * 0.34;
    const safePitch = Number(pitch || 0);
    const safeRoll = Number(roll || 0);

    tiltCtx.clearRect(0, 0, w, h);
    tiltCtx.fillStyle = "#050505";
    tiltCtx.fillRect(0, 0, w, h);

    tiltCtx.strokeStyle = "#333";
    tiltCtx.lineWidth = 1;
    tiltCtx.beginPath();
    tiltCtx.arc(cx, cy, radius, 0, Math.PI * 2);
    tiltCtx.stroke();

    tiltCtx.strokeStyle = "#222";
    tiltCtx.beginPath();
    tiltCtx.moveTo(cx - radius, cy);
    tiltCtx.lineTo(cx + radius, cy);
    tiltCtx.moveTo(cx, cy - radius);
    tiltCtx.lineTo(cx, cy + radius);
    tiltCtx.stroke();

    const dotX = cx + Math.max(-radius, Math.min(radius, (safeRoll / 45) * radius));
    const dotY = cy + Math.max(-radius, Math.min(radius, (safePitch / 45) * radius));

    tiltCtx.strokeStyle = "#aaa";
    tiltCtx.lineWidth = 2;
    tiltCtx.beginPath();
    tiltCtx.moveTo(cx, cy);
    tiltCtx.lineTo(dotX, dotY);
    tiltCtx.stroke();

    tiltCtx.fillStyle = "#ddd";
    tiltCtx.beginPath();
    tiltCtx.arc(dotX, dotY, 8, 0, Math.PI * 2);
    tiltCtx.fill();

    tiltCtx.fillStyle = "#aaa";
    tiltCtx.font = "13px monospace";
    tiltCtx.fillText("Tilt bubble", 14, 20);
    tiltCtx.fillText(`pitch ${fmtNum(safePitch, 1, "°")}`, 14, h - 32);
    tiltCtx.fillText(`roll ${fmtNum(safeRoll, 1, "°")}`, 14, h - 14);
}

function drawHistory(history) {
    const width = chartCanvas.width;
    const height = chartCanvas.height;
    const padLeft = 52;
    const padRight = 18;
    const padTop = 20;
    const padBottom = 34;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;

    chartCtx.clearRect(0, 0, width, height);
    chartCtx.fillStyle = "#050505";
    chartCtx.fillRect(0, 0, width, height);
    chartCtx.strokeStyle = "#333";
    chartCtx.strokeRect(padLeft, padTop, plotWidth, plotHeight);

    chartCtx.fillStyle = "#aaa";
    chartCtx.font = "12px monospace";
    chartCtx.fillText("Accel g / gyro", 8, 16);
    chartCtx.fillText("time →", width - 78, height - 12);

    if (!history || !history.length) {
        chartCtx.fillStyle = "#777";
        chartCtx.font = "16px monospace";
        chartCtx.fillText("Waiting for IMU samples...", padLeft + 20, padTop + 50);
        return;
    }

    const recent = history.slice(-120);
    const n = recent.length;

    function drawSeries(key, scale, offset, dashed) {
        chartCtx.strokeStyle = dashed ? "#777" : "#ddd";
        chartCtx.lineWidth = dashed ? 1 : 2;
        chartCtx.setLineDash(dashed ? [5, 5] : []);
        chartCtx.beginPath();

        recent.forEach((point, index) => {
            const value = Number(point[key] || 0);
            const x = padLeft + (n <= 1 ? 0 : (index / (n - 1)) * plotWidth);
            const y = padTop + plotHeight - Math.max(0, Math.min(plotHeight, ((value - offset) / scale) * plotHeight));
            if (index === 0) chartCtx.moveTo(x, y);
            else chartCtx.lineTo(x, y);
        });
        chartCtx.stroke();
        chartCtx.setLineDash([]);
    }

    drawSeries("accel_g", 2, 0, false);
    drawSeries("gyro_dps", 500, 0, true);

    chartCtx.fillStyle = "#ddd";
    chartCtx.fillText("solid: accel magnitude g", padLeft + 10, height - 18);
    chartCtx.fillStyle = "#999";
    chartCtx.fillText("dash: gyro magnitude °/s", padLeft + 210, height - 18);
}

async function refreshImu() {
    try {
        const res = await fetch("/imu/api/state");

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const imu = await res.json();
        const accel = imu.acceleration || {};
        const gyro = imu.gyro || {};
        const orientation = imu.orientation || {};
        const history = imu.history || [];

        document.getElementById("topStatus").textContent =
            `IMU ${imu.ok === true ? "ok" : "n/a"} | accel ${fmtNum(accel.magnitude_g, 3, " g")} | gyro ${fmtNum(gyro.magnitude_dps, 1, " °/s")}`;

        setStatus(imu.ok, imu.error);
        setText("imuSensor", fmt(imu.sensor));
        setText("imuAddress", fmt(imu.address_hint));
        setText("imuTemperature", fmtNum(imu.temperature_c, 1, " °C"));
        setText("accelMagnitude", `${fmtNum(accel.magnitude_mps2, 2, " m/s²")} / ${fmtNum(accel.magnitude_g, 3, " g")}`);
        setText("gyroMagnitude", fmtNum(gyro.magnitude_dps, 2, " °/s"));
        setText("pitch", fmtNum(orientation.pitch_deg, 1, "°"));
        setText("roll", fmtNum(orientation.roll_deg, 1, "°"));
        setText("imuTimestamp", fmt(imu.timestamp));
        setText("accelRaw", JSON.stringify(accel, null, 2));
        setText("gyroRaw", JSON.stringify(gyro, null, 2));
        setText("imuJson", JSON.stringify(imu, null, 2));

        drawTilt(orientation.pitch_deg, orientation.roll_deg);
        drawHistory(history);
        setText("imuMeta", `Showing ${history.length} samples | orientation source: ${fmt(orientation.source)}`);
    } catch (err) {
        statusEl.textContent = "error";
        statusEl.classList.add("bad");
        setText("imuMeta", "IMU error: " + err);
    }
}

refreshImu();
setInterval(refreshImu, 250);
