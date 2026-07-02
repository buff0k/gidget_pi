{% extends "base.html" %}

{% set active_page = "config" %}

{% block content %}
<section class="page-wrap">
    <div class="card">
        <h2>WiFi Configuration</h2>

        <div class="warning">
            WiFi changes can disconnect this web session if Gidget switches networks.
            Add profiles safely first, then connect manually only when ready.
        </div>

        <div id="configMessage" class="status-box"></div>
    </div>

    <div class="card">
        <h2>Current WiFi</h2>

        <div class="grid">
            <div class="metric">
                <div class="label">Device</div>
                <div id="currentDevice" class="value">n/a</div>
            </div>

            <div class="metric">
                <div class="label">State</div>
                <div id="currentState" class="value">n/a</div>
            </div>

            <div class="metric">
                <div class="label">Connection</div>
                <div id="currentConnection" class="value">n/a</div>
            </div>

            <div class="metric">
                <div class="label">Active Connections</div>
                <div id="activeConnections" class="value">n/a</div>
            </div>
        </div>

        <div class="row" style="margin-top: 1rem;">
            <button id="refreshCurrentBtn">Refresh Current WiFi</button>
        </div>
    </div>

    <div class="card">
        <h2>Add Saved WiFi Profile</h2>

        <p class="muted">
            This saves a WiFi profile without connecting immediately. Use this to preload site networks.
        </p>

        <form id="addProfileForm">
            <label>SSID</label>
            <input name="ssid" required>

            <label>Profile name optional</label>
            <input name="profile_name" placeholder="Leave blank to use SSID">

            <label>Password optional</label>
            <input name="password" type="password" autocomplete="new-password">

            <label>Autoconnect priority</label>
            <input name="priority" type="number" value="0">

            <label class="checkbox-label">
                <input name="autoconnect" type="checkbox" checked>
                Enable autoconnect
            </label>

            <label class="checkbox-label">
                <input name="hidden" type="checkbox">
                Hidden network
            </label>

            <button type="submit">Save Profile Only</button>
        </form>
    </div>

    <div class="card">
        <h2>Available Networks</h2>

        <p class="muted">
            Scanning should not intentionally disconnect the current WiFi, but it may briefly increase latency.
        </p>

        <div class="row">
            <button id="scanWifiBtn">Scan WiFi</button>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>In Use</th>
                        <th>SSID</th>
                        <th>Signal</th>
                        <th>Security</th>
                        <th>Channel</th>
                        <th>Rate</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="wifiScanBody">
                    <tr>
                        <td colspan="7">No scan yet.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <h2>Saved WiFi Profiles</h2>

        <div class="row">
            <button id="refreshSavedBtn">Refresh Saved Profiles</button>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Profile</th>
                        <th>Autoconnect</th>
                        <th>Priority</th>
                        <th>UUID</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="savedProfilesBody">
                    <tr>
                        <td colspan="5">Loading...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>
{% endblock %}

{% block scripts %}
<script src="/static/config.js"></script>
{% endblock %}
