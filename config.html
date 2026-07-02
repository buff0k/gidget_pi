const messageEl = document.getElementById("configMessage");

function showMessage(message, kind = "success") {
    messageEl.textContent = message || "";
    messageEl.className = "status-box";

    if (kind === "error") {
        messageEl.classList.add("error");
    } else if (kind === "warning") {
        messageEl.classList.add("warning");
    } else {
        messageEl.classList.add("success");
    }
}

function clearMessage() {
    messageEl.textContent = "";
    messageEl.className = "status-box";
}

async function apiGet(url) {
    const response = await fetch(url);

    if (response.status === 401) {
        window.location.href = "/auth/login";
        return null;
    }

    return await response.json();
}

async function apiPost(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    if (response.status === 401) {
        window.location.href = "/auth/login";
        return null;
    }

    const data = await response.json();

    if (!response.ok || !data.ok) {
        throw new Error(data.error || "Request failed");
    }

    return data;
}

function valueOrNA(value) {
    if (value === null || value === undefined || value === "") {
        return "n/a";
    }

    return value;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function loadCurrentWifi() {
    try {
        const data = await apiGet("/config/api/wifi/current");
        if (!data) return;

        const device = data.wifi_device || {};

        document.getElementById("currentDevice").textContent = valueOrNA(device.device);
        document.getElementById("currentState").textContent = valueOrNA(device.state);
        document.getElementById("currentConnection").textContent = valueOrNA(device.connection);

        const active = data.active_connections || [];

        if (active.length) {
            document.getElementById("activeConnections").textContent = active
                .map(item => `${item.name} (${item.device})`)
                .join(", ");
        } else {
            document.getElementById("activeConnections").textContent = "n/a";
        }
    } catch (err) {
        showMessage("Current WiFi error: " + err.message, "error");
    }
}

async function scanWifi() {
    const body = document.getElementById("wifiScanBody");
    body.innerHTML = `<tr><td colspan="7">Scanning...</td></tr>`;

    try {
        const data = await apiGet("/config/api/wifi/scan");
        if (!data) return;

        const networks = data.networks || [];

        if (!data.ok) {
            showMessage(data.error || "WiFi scan failed.", "error");
        } else if (!data.rescan_ok) {
            showMessage("WiFi listed, but rescan reported an issue: " + valueOrNA(data.error), "warning");
        } else {
            showMessage("WiFi scan complete.");
        }

        if (!networks.length) {
            body.innerHTML = `<tr><td colspan="7">No networks found.</td></tr>`;
            return;
        }

        body.innerHTML = networks.map(network => {
            const ssid = escapeHtml(network.ssid);
            const signal = escapeHtml(network.signal);
            const security = escapeHtml(network.security);
            const channel = escapeHtml(network.channel);
            const rate = escapeHtml(network.rate);
            const inUse = network.in_use ? "yes" : "";

            return `
                <tr>
                    <td>${inUse}</td>
                    <td>${ssid}</td>
                    <td>${signal}</td>
                    <td>${security}</td>
                    <td>${channel}</td>
                    <td>${rate}</td>
                    <td>
                        <button class="small-btn" onclick="prefillProfile('${encodeURIComponent(network.ssid)}')">
                            Use SSID
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        body.innerHTML = `<tr><td colspan="7">Scan error.</td></tr>`;
        showMessage("WiFi scan error: " + err.message, "error");
    }
}

function prefillProfile(encodedSsid) {
    const ssid = decodeURIComponent(encodedSsid);
    const form = document.getElementById("addProfileForm");

    if (ssid === "<hidden>") {
        form.ssid.value = "";
        form.hidden.checked = true;
    } else {
        form.ssid.value = ssid;
    }

    form.profile_name.value = "";
    form.password.focus();
}

async function loadSavedProfiles() {
    const body = document.getElementById("savedProfilesBody");
    body.innerHTML = `<tr><td colspan="5">Loading...</td></tr>`;

    try {
        const data = await apiGet("/config/api/wifi/saved");
        if (!data) return;

        const profiles = data.profiles || [];

        if (!data.ok) {
            body.innerHTML = `<tr><td colspan="5">Could not load saved profiles.</td></tr>`;
            showMessage(data.error || "Could not load saved profiles.", "error");
            return;
        }

        if (!profiles.length) {
            body.innerHTML = `<tr><td colspan="5">No saved WiFi profiles.</td></tr>`;
            return;
        }

        body.innerHTML = profiles.map(profile => {
            const name = escapeHtml(profile.name);
            const encodedName = encodeURIComponent(profile.name);
            const uuid = escapeHtml(profile.uuid);
            const autoconnect = escapeHtml(profile.autoconnect);
            const priority = escapeHtml(profile.priority);

            return `
                <tr>
                    <td>${name}</td>
                    <td>
                        <select id="autoconnect-${encodedName}">
                            <option value="yes" ${profile.autoconnect === "yes" ? "selected" : ""}>yes</option>
                            <option value="no" ${profile.autoconnect === "no" ? "selected" : ""}>no</option>
                        </select>
                    </td>
                    <td>
                        <input id="priority-${encodedName}" type="number" value="${priority || 0}">
                    </td>
                    <td class="small-text">${uuid}</td>
                    <td>
                        <button class="small-btn" onclick="connectProfile('${encodedName}')">Connect Now</button>
                        <button class="small-btn" onclick="saveAutoconnect('${encodedName}')">Save Auto</button>
                        <button class="small-btn danger-btn" onclick="deleteProfile('${encodedName}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        body.innerHTML = `<tr><td colspan="5">Saved profile error.</td></tr>`;
        showMessage("Saved profile error: " + err.message, "error");
    }
}

async function addProfile(event) {
    event.preventDefault();

    const form = event.target;

    const payload = {
        ssid: form.ssid.value,
        profile_name: form.profile_name.value,
        password: form.password.value,
        priority: form.priority.value,
        autoconnect: form.autoconnect.checked,
        hidden: form.hidden.checked,
    };

    try {
        const data = await apiPost("/config/api/wifi/add-profile", payload);
        showMessage(data.message || "Profile saved.");
        form.password.value = "";
        await loadSavedProfiles();
    } catch (err) {
        showMessage("Add profile error: " + err.message, "error");
    }
}

async function connectProfile(encodedName) {
    const name = decodeURIComponent(encodedName);

    const confirmed = confirm(
        `Connect to '${name}' now?\n\n` +
        "This may disconnect this web session if the Pi switches networks."
    );

    if (!confirmed) return;

    try {
        const data = await apiPost("/config/api/wifi/connect", {
            profile_name: name,
        });

        showMessage(data.message || `Connection command sent for '${name}'.`);
        setTimeout(loadCurrentWifi, 3000);
    } catch (err) {
        showMessage("Connect error: " + err.message, "error");
    }
}

async function deleteProfile(encodedName) {
    const name = decodeURIComponent(encodedName);

    const confirmValue = prompt(
        `Delete saved WiFi profile '${name}'?\n\n` +
        "Type DELETE to confirm."
    );

    if (confirmValue !== "DELETE") {
        showMessage("Delete cancelled.", "warning");
        return;
    }

    try {
        const data = await apiPost("/config/api/wifi/delete", {
            profile_name: name,
            confirm: "DELETE",
        });

        showMessage(data.message || `Deleted '${name}'.`);
        await loadSavedProfiles();
    } catch (err) {
        showMessage("Delete error: " + err.message, "error");
    }
}

async function saveAutoconnect(encodedName) {
    const name = decodeURIComponent(encodedName);

    const autoconnectEl = document.getElementById(`autoconnect-${encodedName}`);
    const priorityEl = document.getElementById(`priority-${encodedName}`);

    try {
        const data = await apiPost("/config/api/wifi/autoconnect", {
            profile_name: name,
            autoconnect: autoconnectEl.value === "yes",
            priority: priorityEl.value,
        });

        showMessage(data.message || `Updated '${name}'.`);
        await loadSavedProfiles();
    } catch (err) {
        showMessage("Autoconnect update error: " + err.message, "error");
    }
}

document.getElementById("refreshCurrentBtn").addEventListener("click", loadCurrentWifi);
document.getElementById("scanWifiBtn").addEventListener("click", scanWifi);
document.getElementById("refreshSavedBtn").addEventListener("click", loadSavedProfiles);
document.getElementById("addProfileForm").addEventListener("submit", addProfile);

loadCurrentWifi();
loadSavedProfiles();
