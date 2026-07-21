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


async function drawOverlay() {
    const data = await loadSensors();

    ctx.clearRect(0, 0, canvas.width, canvas.height);

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
