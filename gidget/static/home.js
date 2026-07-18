let homeMap = L.map("homeMap").setView([0, 0], 2);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(homeMap);

let homeMarker = null;
let homeCentered = false;

function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
}

function fmtNum(value, decimals, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return Number(value).toFixed(decimals) + suffix;
}

function formatUptime(seconds) {
    if (seconds === null || seconds === undefined) return "n/a";

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);

    if (days) return `${days}d ${hours}h ${mins}m`;
    if (hours) return `${hours}h ${mins}m`;
    return `${mins}m`;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

function setFixClass(id, value) {
    const el = document.getElementById(id);
    if (!el) return;

    el.classList.remove("good", "bad", "warn");

    if (value === true || value === "true") {
        el.classList.add("good");
    } else if (value === false || value === "false") {
        el.classList.add("bad");
    } else {
        el.classList.add("warn");
    }
}

function renderEnvironment(environment) {
    const aht20 = environment.aht20 || {};
    const bmp280 = environment.bmp280 || {};

    if (environment.ok === true) {
        setText("envStatus", "ok");
        setFixClass("envStatus", true);
    } else if (environment.error) {
        setText("envStatus", environment.error);
        setFixClass("envStatus", false);
    } else {
        setText("envStatus", "n/a");
        setFixClass("envStatus", null);
    }

    setText("ahtTemp", fmtNum(aht20.temperature_c, 1, " °C"));
    setText("humidity", fmtNum(aht20.humidity_percent, 1, " %"));
    setText("bmpTemp", fmtNum(bmp280.temperature_c, 1, " °C"));
    setText("pressure", fmtNum(bmp280.pressure_hpa, 1, " hPa"));
    setText("envAltitude", fmtNum(bmp280.altitude_m, 1, " m"));
    setText("bmpAddress", fmt(bmp280.address));
    setText("envTimestamp", fmt(environment.timestamp));
}

async function refreshStatus() {
    try {
        const res = await fetch("/api/status");

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const status = await res.json();

        const gps = status.gps || {};
        const wifi = status.wifi || {};
        const load = status.load_average || {};
        const memory = status.memory || {};
        const storage = status.storage || {};
        const environment = status.environment || {};
        const constellations = gps.constellations || [];

        document.getElementById("topStatus").textContent =
            `${status.hostname} | ${status.ip} | ${wifi.ssid || "n/a"} ${wifi.signal || ""} | ` +
            `GPS ${gps.has_fix} | ENV ${environment.ok === true ? "ok" : "n/a"} | ` +
            `CPU ${fmt(status.cpu_temp_c, " °C")} | ` +
            `MEM ${fmt(memory.used_percent, "%")} | DISK ${fmt(storage.used_percent)}`;

        setText("gpsFix", gps.has_fix);
        setFixClass("gpsFix", gps.has_fix);

        setText("gpsSats", fmt(gps.satellites));
        setText("gpsConstellations", constellations.length ? constellations.join(", ") : "n/a");
        setText("gpsLat", fmtNum(gps.lat, 6));
        setText("gpsLon", fmtNum(gps.lon, 6));
        setText("gpsSpeed", fmt(gps.speed_kmh, " km/h"));
        setText("gpsCourse", fmt(gps.course_deg, "°"));
        setText("gpsAlt", fmt(gps.altitude_m, " m"));
        setText("gpsTime", fmt(gps.timestamp));

        renderEnvironment(environment);

        setText("hostname", status.hostname);
        setText("ip", status.ip);
        setText("ssid", wifi.ssid || "n/a");
        setText("signal", wifi.signal || "n/a");

        setText("cpuTemp", fmt(status.cpu_temp_c, " °C"));

        if (load.one_min !== null && load.one_min !== undefined) {
            setText("cpuLoad", `${load.one_min} / ${load.five_min} / ${load.fifteen_min}`);
        } else {
            setText("cpuLoad", "n/a");
        }

        if (memory.used_mb !== null && memory.used_mb !== undefined) {
            setText(
                "memoryUsage",
                `${memory.used_mb} / ${memory.total_mb} MB (${memory.used_percent}%)`
            );
        } else {
            setText("memoryUsage", "n/a");
        }

        if (storage.used !== null && storage.used !== undefined) {
            setText(
                "storageUsage",
                `${storage.used} / ${storage.total} (${storage.used_percent})`
            );
        } else {
            setText("storageUsage", "n/a");
        }

        setText("uptime", formatUptime(status.uptime_seconds));

        if (gps.has_fix && gps.lat !== null && gps.lon !== null) {
            const latLng = [gps.lat, gps.lon];

            if (!homeMarker) {
                homeMarker = L.marker(latLng).addTo(homeMap);
            } else {
                homeMarker.setLatLng(latLng);
            }

            homeMarker.bindPopup("Live position");

            if (!homeCentered) {
                homeMap.setView(latLng, 17);
                homeCentered = true;
            }
        }
    } catch (err) {
        document.getElementById("topStatus").textContent = "Status error: " + err;
    }
}

refreshStatus();
setInterval(refreshStatus, 2000);
