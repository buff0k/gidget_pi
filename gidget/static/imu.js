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
        status