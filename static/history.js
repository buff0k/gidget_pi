let historyMap = L.map("historyMap").setView([0, 0], 2);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
}).addTo(historyMap);

let historyLiveMarker = null;
let replayMarker = null;
let trackLine = null;
let trackPoints = [];

let trackDates = [];
let loadedDates = new Set();

let replayIndex = 0;
let liveMode = true;
let playTimer = null;
let historyCentered = false;

const topStatusEl = document.getElementById("topStatus");
const pointInfoEl = document.getElementById("pointInfo");
const loadStatusEl = document.getElementById("historyLoadStatus");
const sliderEl = document.getElementById("replaySlider");

const dateSelectEl = document.getElementById("dateSelect");
const liveBtn = document.getElementById("liveBtn");
const backBtn = document.getElementById("backBtn");
const playBtn = document.getElementById("playBtn");
const forwardBtn = document.getElementById("forwardBtn");
const loadSelectedDateBtn = document.getElementById("loadSelectedDateBtn");
const loadAllDatesBtn = document.getElementById("loadAllDatesBtn");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");


function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
}


function setLoadStatus(message) {
    loadStatusEl.textContent = message;
}


function updateDateSelect() {
    if (!trackDates.length) {
        dateSelectEl.innerHTML = `<option value="">No track files</option>`;
        return;
    }

    dateSelectEl.innerHTML = trackDates.map((item, index) => {
        const loaded = loadedDates.has(item.date) ? "loaded" : "not loaded";
        return `<option value="${item.date}" ${index === 0 ? "selected" : ""}>${item.date} (${loaded})</option>`;
    }).join("");
}


function sortTrackPoints() {
    trackPoints.sort((a, b) => {
        const at = a.timestamp || "";
        const bt = b.timestamp || "";
        return at.localeCompare(bt);
    });
}


function dedupeTrackPoints(points) {
    const seen = new Set();
    const output = [];

    for (const point of points) {
        const key = `${point._date || ""}:${point._line || ""}:${point.timestamp || ""}:${point.lat}:${point.lon}`;

        if (seen.has(key)) {
            continue;
        }

        seen.add(key);
        output.push(point);
    }

    return output;
}


function updatePointInfo(point) {
    if (!point) {
        pointInfoEl.textContent = "No track point selected.";
        return;
    }

    pointInfoEl.textContent =
        `${point.timestamp} | ` +
        `Date ${fmt(point._date)} | ` +
        `Lat ${Number(point.lat).toFixed(6)} | Lon ${Number(point.lon).toFixed(6)} | ` +
        `Speed ${fmt(point.speed_kmh, " km/h")} | Course ${fmt(point.course_deg, "°")} | ` +
        `Alt ${fmt(point.altitude_m, " m")} | Sats ${fmt(point.satellites)}`;
}


function setReplayIndex(index) {
    if (!trackPoints.length) {
        updatePointInfo(null);
        return;
    }

    replayIndex = Math.max(0, Math.min(index, trackPoints.length - 1));
    sliderEl.value = replayIndex;

    const point = trackPoints[replayIndex];
    const latLng = [point.lat, point.lon];

    if (!replayMarker) {
        replayMarker = L.marker(latLng).addTo(historyMap);
    } else {
        replayMarker.setLatLng(latLng);
    }

    replayMarker.bindPopup("Replay point");
    updatePointInfo(point);

    if (!liveMode) {
        historyMap.panTo(latLng);
    }
}


function redrawTrack(keepView = true) {
    if (trackLine) {
        historyMap.removeLayer(trackLine);
        trackLine = null;
    }

    if (!trackPoints.length) {
        sliderEl.max = 0;
        sliderEl.value = 0;
        updatePointInfo(null);
        setLoadStatus("No track points loaded.");
        return;
    }

    const latLngs = trackPoints.map(p => [p.lat, p.lon]);
    trackLine = L.polyline(latLngs).addTo(historyMap);

    sliderEl.max = trackPoints.length - 1;

    if (liveMode) {
        replayIndex = trackPoints.length - 1;
        sliderEl.value = replayIndex;
    }

    setReplayIndex(replayIndex);

    if (!keepView || !historyCentered) {
        historyMap.fitBounds(trackLine.getBounds(), { padding: [30, 30] });
        historyCentered = true;
    }

    setLoadStatus(
        `Loaded ${trackPoints.length} points from ${loadedDates.size} day(s). ` +
        `Newest loaded date first; full history can load in background.`
    );
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

        topStatusEl.textContent =
            `${status.hostname} | ${status.ip} | ${wifi.ssid || "n/a"} ${wifi.signal || ""} | GPS ${gps.has_fix}`;

        if (gps.has_fix && gps.lat !== null && gps.lon !== null) {
            const latLng = [gps.lat, gps.lon];

            if (!historyLiveMarker) {
                historyLiveMarker = L.marker(latLng).addTo(historyMap);
            } else {
                historyLiveMarker.setLatLng(latLng);
            }

            historyLiveMarker.bindPopup("Live position");

            if (liveMode) {
                historyMap.panTo(latLng);
            }
        }
    } catch (err) {
        topStatusEl.textContent = "Status error: " + err;
    }
}


async function loadTrackDates() {
    setLoadStatus("Loading track dates...");

    const res = await fetch("/api/track/dates");

    if (res.status === 401) {
        window.location.href = "/auth/login";
        return;
    }

    const data = await res.json();
    trackDates = data.dates || [];

    updateDateSelect();

    if (!trackDates.length) {
        setLoadStatus("No track history files found.");
        return;
    }

    setLoadStatus(`Found ${trackDates.length} track date(s). Loading newest date...`);

    // Load newest date immediately.
    await loadTrackDate(trackDates[0].date, false);

    // Then background-load the rest, but allow the first render to complete.
    setTimeout(loadRemainingDatesInBackground, 500);
}


async function loadTrackDate(date, keepView = true) {
    if (!date) {
        return;
    }

    if (loadedDates.has(date)) {
        setLoadStatus(`${date} is already loaded.`);
        return;
    }

    setLoadStatus(`Loading ${date}...`);

    const res = await fetch(`/api/track/date/${encodeURIComponent(date)}`);

    if (res.status === 401) {
        window.location.href = "/auth/login";
        return;
    }

    const data = await res.json();
    const points = data.points || [];

    loadedDates.add(date);
    trackPoints = dedupeTrackPoints(trackPoints.concat(points));
    sortTrackPoints();
    updateDateSelect();

    if (liveMode && trackPoints.length) {
        replayIndex = trackPoints.length - 1;
    }

    redrawTrack(keepView);

    setLoadStatus(
        `Loaded ${points.length} point(s) from ${date}. ` +
        `Total loaded: ${trackPoints.length} point(s) from ${loadedDates.size} day(s).`
    );
}


async function loadRemainingDatesInBackground() {
    if (!trackDates.length) {
        return;
    }

    for (const item of trackDates.slice(1)) {
        if (loadedDates.has(item.date)) {
            continue;
        }

        setLoadStatus(
            `Background loading ${item.date}... ` +
            `${loadedDates.size}/${trackDates.length} day(s) loaded.`
        );

        await loadTrackDate(item.date, true);

        // Yield to the browser so the UI stays responsive.
        await new Promise(resolve => setTimeout(resolve, 250));
    }

    setLoadStatus(
        `Full history loaded: ${trackPoints.length} point(s) from ${loadedDates.size} day(s).`
    );
}


function clearLoadedHistory() {
    trackPoints = [];
    loadedDates = new Set();
    replayIndex = 0;
    liveMode = true;
    historyCentered = false;

    if (trackLine) {
        historyMap.removeLayer(trackLine);
        trackLine = null;
    }

    if (replayMarker) {
        historyMap.removeLayer(replayMarker);
        replayMarker = null;
    }

    updateDateSelect();
    redrawTrack(false);
    setLoadStatus("Cleared loaded history. Use Load Selected Date or Load Full History.");
}


function goLive() {
    liveMode = true;

    if (trackPoints.length) {
        setReplayIndex(trackPoints.length - 1);
    }

    if (historyLiveMarker) {
        historyMap.panTo(historyLiveMarker.getLatLng());
    }
}


function stepReplay(delta) {
    liveMode = false;
    setReplayIndex(replayIndex + delta);
}


function togglePlay() {
    liveMode = false;

    if (playTimer) {
        clearInterval(playTimer);
        playTimer = null;
        playBtn.textContent = "Play";
        return;
    }

    playBtn.textContent = "Pause";

    playTimer = setInterval(() => {
        if (!trackPoints.length) return;

        if (replayIndex >= trackPoints.length - 1) {
            setReplayIndex(0);
        } else {
            setReplayIndex(replayIndex + 1);
        }
    }, 500);
}


liveBtn.addEventListener("click", goLive);
backBtn.addEventListener("click", () => stepReplay(-1));
forwardBtn.addEventListener("click", () => stepReplay(1));
playBtn.addEventListener("click", togglePlay);

loadSelectedDateBtn.addEventListener("click", () => {
    loadTrackDate(dateSelectEl.value, false);
});

loadAllDatesBtn.addEventListener("click", () => {
    loadRemainingDatesInBackground();
});

clearHistoryBtn.addEventListener("click", clearLoadedHistory);

sliderEl.addEventListener("input", () => {
    liveMode = false;
    setReplayIndex(Number(sliderEl.value));
});


refreshStatus();
loadTrackDates();

setInterval(refreshStatus, 2000);
