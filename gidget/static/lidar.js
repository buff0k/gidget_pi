const statusEl = document.getElementById("lidarStatus");
const sensorEl = document.getElementById("lidarSensor");
const addressEl = document.getElementById("lidarAddress");
const distanceEl = document.getElementById("lidarDistance");
const timestampEl = document.getElementById("lidarTimestamp");
const metaEl = document.getElementById("lidarMeta");
const jsonEl = document.getElementById("lidarJson");
const canvas = document.getElementById("lidarCanvas");
const ctx = canvas.getContext("2d");

function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
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

function drawLidar(points, maxDisplayMm) {
    const width = canvas.width;
    const height = canvas.height;
    const padLeft = 58;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 42;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;
    const maxMm = maxDisplayMm || 4000;

    ctx.clearRect(0, 0, width, height);

    ctx.fillStyle = "#050505";
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "#333";
    ctx.lineWidth = 1;
    ctx.strokeRect(padLeft, padTop, plotWidth, plotHeight);

    ctx.fillStyle = "#aaa";
    ctx.font = "12px monospace";
    ctx.fillText("Distance mm", 8, 16);
    ctx.fillText("time →", width - 78, height - 12);

    for (let i = 0; i <= 4; i++) {
        const y = padTop + (plotHeight * i / 4);
        const distance = Math.round(maxMm - (maxMm * i / 4));

        ctx.strokeStyle = "#1f1f1f";
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(width - padRight, y);
        ctx.stroke();

        ctx.fillStyle = "#777";
        ctx.fillText(String(distance), 10, y + 4);
    }

    if (!points || !points.length) {
        ctx.fillStyle = "#777";
        ctx.font = "16px monospace";
        ctx.fillText("Waiting for LIDAR samples...", padLeft + 20, padTop + 50);
        return;
    }

    const recent = points.slice(-180);
    const n = recent.length;

    ctx.strokeStyle = "#aaa";
    ctx.lineWidth = 2;
    ctx.beginPath();

    recent.forEach((point, index) => {
        const distance = Math.max(0, Math.min(maxMm, Number(point.distance_mm || 0)));
        const x = padLeft + (n <= 1 ? 0 : (index / (n - 1)) * plotWidth);
        const y = padTop + plotHeight - ((distance / maxMm) * plotHeight);

        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    ctx.stroke();

    recent.forEach((point, index) => {
        const distance = Math.max(0, Math.min(maxMm, Number(point.distance_mm || 0)));
        const x = padLeft + (n <= 1 ? 0 : (index / (n - 1)) * plotWidth);
        const y = padTop + plotHeight - ((distance / maxMm) * plotHeight);

        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fillStyle = "#ddd";
        ctx.fill();
    });

    const latest = recent[recent.length - 1];
    metaEl.textContent = `Showing ${recent.length} samples | latest ${fmt(latest.distance_mm, " mm")} | display max ${maxMm} mm`;
}

async function refreshLidar() {
    try {
        const res = await fetch("/api/status");

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const status = await res.json();
        const lidar = status.lidar || {};
        const points = lidar.points || [];

        document.getElementById("topStatus").textContent =
            `${status.hostname} | LIDAR ${lidar.ok === true ? "ok" : "n/a"} | ${fmt(lidar.distance_mm, " mm")}`;

        setStatus(lidar.ok, lidar.error);
        setText(sensorEl, fmt(lidar.sensor));
        setText(addressEl, fmt(lidar.address));
        setText(distanceEl, fmt(lidar.distance_mm, " mm"));
        setText(timestampEl, fmt(lidar.timestamp));

        drawLidar(points, lidar.max_display_mm);
        jsonEl.textContent = JSON.stringify(lidar, null, 2);
    } catch (err) {
        statusEl.textContent = "error";
        statusEl.classList.add("bad");
        metaEl.textContent = "LIDAR error: " + err;
    }
}

refreshLidar();
setInterval(refreshLidar, 500);
