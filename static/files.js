let currentPath = "";
let parentPath = null;

const fileListBody = document.getElementById("fileListBody");
const currentPathEl = document.getElementById("currentPath");
const viewerTitleEl = document.getElementById("viewerTitle");
const viewerMetaEl = document.getElementById("viewerMeta");
const fileViewerEl = document.getElementById("fileViewer");
const filesMessageEl = document.getElementById("filesMessage");

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showMessage(message, kind = "success") {
    filesMessageEl.textContent = message || "";
    filesMessageEl.className = "status-box";

    if (kind === "error") {
        filesMessageEl.classList.add("error");
    } else if (kind === "warning") {
        filesMessageEl.classList.add("warning");
    } else {
        filesMessageEl.classList.add("success");
    }
}

function clearMessage() {
    filesMessageEl.textContent = "";
    filesMessageEl.className = "status-box";
}

function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return "";

    const units = ["B", "KB", "MB", "GB"];
    let value = Number(bytes);
    let index = 0;

    while (value >= 1024 && index < units.length - 1) {
        value = value / 1024;
        index += 1;
    }

    if (index === 0) {
        return `${value} ${units[index]}`;
    }

    return `${value.toFixed(1)} ${units[index]}`;
}

function formatDate(timestampSeconds) {
    if (!timestampSeconds) return "";

    const date = new Date(timestampSeconds * 1000);
    return date.toLocaleString();
}

function languageClass(fileType) {
    const type = String(fileType || "").toLowerCase();

    if (type.includes("python")) return "lang-python";
    if (type.includes("javascript")) return "lang-javascript";
    if (type.includes("css")) return "lang-css";
    if (type.includes("html")) return "lang-html";
    if (type.includes("json")) return "lang-json";
    if (type.includes("ini")) return "lang-ini";
    if (type.includes("bash")) return "lang-bash";

    return "lang-text";
}

async function apiGet(url) {
    const response = await fetch(url);

    if (response.status === 401) {
        window.location.href = "/auth/login";
        return null;
    }

    const data = await response.json();

    if (!response.ok || data.ok === false) {
        throw new Error(data.error || "Request failed");
    }

    return data;
}

async function loadDirectory(path = "") {
    clearMessage();

    fileListBody.innerHTML = `<tr><td colspan="5">Loading...</td></tr>`;

    try {
        const data = await apiGet(`/files/api/list?path=${encodeURIComponent(path)}`);
        if (!data) return;

        currentPath = data.path || "";
        parentPath = data.parent;

        currentPathEl.textContent = `/opt/gidget/${currentPath}`;
        document.getElementById("upBtn").disabled = parentPath === null;

        const entries = data.entries || [];

        if (!entries.length) {
            fileListBody.innerHTML = `<tr><td colspan="5">Directory is empty.</td></tr>`;
            return;
        }

        fileListBody.innerHTML = entries.map(entry => {
            const name = escapeHtml(entry.name);
            const pathEncoded = encodeURIComponent(entry.path);
            const type = escapeHtml(entry.type);
            const size = formatBytes(entry.size_bytes);
            const modified = formatDate(entry.modified);

            let actions = "";

            if (entry.type === "directory") {
                actions += `<button class="small-btn" onclick="loadDirectory('${pathEncoded}', true)">Open</button>`;
            }

            if (entry.type === "file" && entry.viewable) {
                actions += `<button class="small-btn" onclick="viewFile('${pathEncoded}')">View</button>`;
            }

            if (entry.type === "file" && entry.downloadable) {
                actions += `<a class="small-link" href="/files/download?path=${pathEncoded}">Download</a>`;
            }

            const icon = entry.type === "directory" ? "📁" : entry.type === "file" ? "📄" : "•";

            return `
                <tr>
                    <td>${icon} ${name}</td>
                    <td>${type}</td>
                    <td>${size}</td>
                    <td>${modified}</td>
                    <td>${actions}</td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        fileListBody.innerHTML = `<tr><td colspan="5">Error loading directory.</td></tr>`;
        showMessage("Directory error: " + err.message, "error");
    }
}

async function viewFile(encodedPath) {
    clearMessage();

    const path = decodeURIComponent(encodedPath);

    viewerTitleEl.textContent = "Loading...";
    viewerMetaEl.textContent = path;
    fileViewerEl.className = "file-viewer";
    fileViewerEl.innerHTML = "<code>Loading...</code>";

    try {
        const data = await apiGet(`/files/api/view?path=${encodeURIComponent(path)}`);
        if (!data) return;

        viewerTitleEl.textContent = data.name;
        viewerMetaEl.textContent =
            `${data.path} | ${formatBytes(data.size_bytes)} | ${data.line_count} line(s) | ${data.file_type}`;

        const lang = languageClass(data.file_type);
        fileViewerEl.className = `file-viewer ${lang}`;

        const lines = data.lines || [];

        fileViewerEl.innerHTML = lines.map((line, index) => {
            const lineNo = index + 1;
            return `<div class="code-line"><span class="line-no">${lineNo}</span><code>${escapeHtml(line)}</code></div>`;
        }).join("");
    } catch (err) {
        viewerTitleEl.textContent = "Viewer";
        viewerMetaEl.textContent = path;
        fileViewerEl.className = "file-viewer";
        fileViewerEl.innerHTML = `<code>${escapeHtml(err.message)}</code>`;
        showMessage("Viewer error: " + err.message, "error");
    }
}

document.getElementById("rootBtn").addEventListener("click", () => {
    loadDirectory("");
});

document.getElementById("upBtn").addEventListener("click", () => {
    if (parentPath !== null) {
        loadDirectory(parentPath);
    }
});

document.getElementById("refreshBtn").addEventListener("click", () => {
    loadDirectory(currentPath);
});

loadDirectory("");
