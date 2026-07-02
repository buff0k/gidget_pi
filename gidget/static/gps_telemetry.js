function fmt(value, suffix = "") {
    if (value === null || value === undefined || value === "") return "n/a";
    return value + suffix;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function setText(id, value) {
    document.getElementById(id).textContent = value;
}

function setFixClass(id, value) {
    const el = document.getElementById(id);
    el.classList.remove("good", "bad", "warn");

    if (value === true || value === "true") {
        el.classList.add("good");
    } else if (value === false || value === "false") {
        el.classList.add("bad");
    } else {
        el.classList.add("warn");
    }
}

function renderUsedSatellites(satellites) {
    const body = document.getElementById("usedSatellitesBody");

    if (!satellites || !satellites.length) {
        body.innerHTML = `<tr><td colspan="3">No satellites used in fix yet.</td></tr>`;
        return;
    }

    body.innerHTML = satellites.map(sat => `
        <tr>
            <td>${escapeHtml(sat.id)}</td>
            <td>${escapeHtml(sat.talker)}</td>
            <td>${escapeHtml(sat.constellation)}</td>
        </tr>
    `).join("");
}

function renderVisibleSatellites(satellites) {
    const body = document.getElementById("visibleSatellitesBody");

    if (!satellites || !satellites.length) {
        body.innerHTML = `<tr><td colspan="7">No visible satellites reported yet.</td></tr>`;
        return;
    }

    body.innerHTML = satellites.map(sat => `
        <tr>
            <td>${escapeHtml(sat.id)}</td>
            <td>${escapeHtml(sat.talker)}</td>
            <td>${escapeHtml(sat.constellation)}</td>
            <td>${escapeHtml(fmt(sat.elevation_deg, "°"))}</td>
            <td>${escapeHtml(fmt(sat.azimuth_deg, "°"))}</td>
            <td>${escapeHtml(fmt(sat.snr_db, " dB"))}</td>
            <td>${escapeHtml(sat.last_seen)}</td>
        </tr>
    `).join("");
}

function renderTerminal(tail, lastSentence) {
    const terminal = document.getElementById("gpsTerminal");

    if (tail && tail.length) {
        terminal.textContent = tail
            .map(item => `${item.timestamp}\n${item.sentence}`)
            .join("\n\n");
    } else {
        terminal.textContent = lastSentence || "Waiting for NMEA...";
    }

    terminal.scrollTop = terminal.scrollHeight;
}

async function refreshGpsTelemetry() {
    try {
        const res = await fetch("/api/status");

        if (res.status === 401) {
            window.location.href = "/auth/login";
            return;
        }

        const status = await res.json();
        const gps = status.gps || {};
        const gsa = gps.gsa || {};
        const constellations = gps.constellations || [];
        const used = gps.satellites_used || [];
        const visible = gps.satellites_visible || [];

        document.getElementById("topStatus").textContent =
            `${status.hostname} | GPS ${gps.has_fix} | ` +
            `Used ${used.length} | Visible ${visible.length} | ` +
            `Constellations ${constellations.length ? constellations.join(", ") : "n/a"}`;

        setText("fixStatus", gps.has_fix);
        setFixClass("fixStatus", gps.has_fix);

        setText("constellations", constellations.length ? constellations.join(", ") : "n/a");
        setText("satellitesUsedCount", used.length);
        setText("satellitesVisibleCount", visible.length);
        setText("pdop", fmt(gsa.pdop));
        setText("hdop", fmt(gsa.hdop));
        setText("vdop", fmt(gsa.vdop));
        setText("lastUpdate", fmt(gps.timestamp));

        renderUsedSatellites(used);
        renderVisibleSatellites(visible);
        renderTerminal(gps.nmea_tail || [], gps.last_sentence);
    } catch (err) {
        document.getElementById("topStatus").textContent = "GPS telemetry error: " + err;
    }
}

refreshGpsTelemetry();
setInterval(refreshGpsTelemetry, 2000);
