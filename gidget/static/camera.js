const canvas = document.getElementById("cameraOverlay");
const image = document.getElementById("cameraFeed");
const ctx = canvas.getContext("2d");


function resizeCanvas() {
    // Use the rendered box size (not naturalWidth/Height) so the canvas
    // coordinate space matches the CSS pixels we draw text at.
    const width = image.clientWidth;
    const height = image.clientHeight;

    if (width && height && (canvas.width !== width || canvas.height !== height)) {
        canvas.width = width;
        canvas.height = height;
    }
}


// MJPEG (multipart/x-mixed-replace) streams don't reliably fire `load`
// per frame across browsers, so don't rely on image.onload alone. Poll
// the rendered size on an interval as well - cheap, and guarantees the
// canvas tracks the image even before the first frame arrives.
image.addEventListener("load", resizeCanvas);
window.addEventListener("resize", resizeCanvas);
setInterval(resizeCanvas, 500);
resizeCanvas();


async function fetchJson(url) {
    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) return {};
        return await res.json();
    } catch (e) {
        return {};
    }
}


async function loadSensors() {
    const [lidar, imu, status] = await Promise.all([
        fetchJson("/lidar/api/state"),
        fetchJson("/imu/api/state"),
        fetchJson("/api/status"),
    ]);

    return {
        lidar,
        imu,
        env: status.environment || {},
        gps: status.gps || {},
    };
}


function fmt(value, decimals, unit) {
    if (value === null || value === undefined) return "n/a";
    const num = Number(value);
    if (Number.isNaN(num)) return "n/a";
    return num.toFixed(decimals) + (unit || "");
}


function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}


// Fighter-jet-style HUD attitude ladder: a horizon line + pitch rungs that
// rotate/translate with the airframe, plus a fixed reference symbol at
// screen center representing the vehicle itself.
function drawFalseHorizon(pitch, roll) {
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const pxPerDeg = canvas.height / 60;
    const pitchOffset = clamp(Number(pitch) || 0, -30, 30) * pxPerDeg;
    const rollRad = (Number(roll) || 0) * (Math.PI / 180);
    const halfWidth = canvas.width * 0.32;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-rollRad);
    ctx.translate(0, pitchOffset);

    ctx.strokeStyle = "#39ff6a";
    ctx.fillStyle = "#39ff6a";
    ctx.lineWidth = 2;
    ctx.shadowColor = "rgba(0,0,0,0.85)";
    ctx.shadowBlur = 4;
    ctx.font = "11px monospace";
    ctx.textAlign = "center";

    // Horizon line, split with a gap in the middle like a real ADI/HUD.
    ctx.beginPath();
    ctx.moveTo(-halfWidth, 0);
    ctx.lineTo(-halfWidth * 0.2, 0);
    ctx.moveTo(halfWidth * 0.2, 0);
    ctx.lineTo(halfWidth, 0);
    ctx.stroke();

    // Pitch ladder rungs above/below the horizon.
    [15, 30].forEach((deg) => {
        const rungWidth = halfWidth * 0.45;

        [1, -1].forEach((sign) => {
            const y = -sign * deg * pxPerDeg;

            ctx.beginPath();
            ctx.moveTo(-rungWidth, y);
            ctx.lineTo(rungWidth, y);
            ctx.stroke();

            ctx.fillText(String(sign * deg), 0, y - 6);
        });
    });

    ctx.restore();

    // Fixed vehicle reference (wings + dot), drawn unrotated at screen center.
    ctx.strokeStyle = "#ffcc33";
    ctx.fillStyle = "#ffcc33";
    ctx.lineWidth = 3;
    ctx.shadowColor = "rgba(0,0,0,0.85)";
    ctx.shadowBlur = 4;

    ctx.beginPath();
    ctx.moveTo(cx - 42, cy);
    ctx.lineTo(cx - 14, cy);
    ctx.moveTo(cx + 14, cy);
    ctx.lineTo(cx + 42, cy);
    ctx.moveTo(cx, cy - 8);
    ctx.lineTo(cx, cy - 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();

    // Bank angle readout at the top.
    ctx.font = "13px monospace";
    ctx.textAlign = "left";
    ctx.fillText(`BANK ${fmt(roll, 1, "deg")}`, cx - 40, 20);
}


async function drawOverlay() {
    const data = await loadSensors();

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (document.getElementById("falseHorizonToggle").checked) {
        const orientation = data.imu.orientation || {};
        drawFalseHorizon(orientation.pitch_deg, orientation.roll_deg);
    }

    ctx.font = "20px monospace";
    ctx.textBaseline = "top";
    ctx.shadowColor = "rgba(0,0,0,0.85)";
    ctx.shadowBlur = 4;
    ctx.fillStyle = "#80ff9f";

    let y = 16;
    const lineHeight = 26;

    function line(text) {
        ctx.fillText(text, 16, y);
        y += lineHeight;
    }

    if (document.getElementById("lidarToggle").checked) {
        line("RANGE: " + fmt(data.lidar.distance_cm, 1, " cm"));
    }

    if (document.getElementById("imuToggle").checked) {
        const orientation = data.imu.orientation || {};
        line(
            "PITCH: " + fmt(orientation.pitch_deg, 1, "deg") +
            "  ROLL: " + fmt(orientation.roll_deg, 1, "deg")
        );
    }

    if (document.getElementById("environmentToggle").checked) {
        const aht20 = data.env.aht20 || {};
        line(
            "TEMP: " + fmt(aht20.temperature_c, 1, "C") +
            "  HUM: " + fmt(aht20.humidity_percent, 0, "%")
        );
    }

    if (document.getElementById("gpsToggle").checked) {
        const gps = data.gps || {};
        if (gps.has_fix) {
            line(
                "GPS: " + fmt(gps.lat, 5) + ", " + fmt(gps.lon, 5) +
                "  " + fmt(gps.speed_kmh, 1, " km/h")
            );
        } else {
            line("GPS: no fix");
        }
    }
}


setInterval(drawOverlay, 500);
drawOverlay();
