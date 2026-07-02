{% extends "base.html" %}

{% set active_page = "users" %}

{% block content %}
<section class="page-wrap">
    <div class="card">
        <h2>Change My Password</h2>

        {% if message %}
            <div class="success">{{ message }}</div>
        {% endif %}

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <form method="post">
            <input type="hidden" name="action" value="change_own_password">

            <label>New password</label>
            <input name="password" type="password" required>

            <label>Confirm password</label>
            <input name="confirm" type="password" required>

            <button type="submit">Change Password</button>
        </form>
    </div>

    {% if current_user.role == "admin" %}
    <div class="card">
        <h2>Add User</h2>

        <form method="post">
            <input type="hidden" name="action" value="add_user">

            <label>Username</label>
            <input name="username" required>

            <label>Password</label>
            <input name="password" type="password" required>

            <label>Role</label>
            <select name="role">
                <option value="user">user</option>
                <option value="admin">admin</option>
            </select>

            <button type="submit">Add User</button>
        </form>
    </div>

    <div class="card">
        <h2>Users</h2>

        <table>
            <thead>
                <tr>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Enabled</th>
                    <th>Must Change Password</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ user.username }}</td>
                    <td>{{ user.role }}</td>
                    <td>{{ user.enabled }}</td>
                    <td>{{ user.must_change_password }}</td>
                    <td>
                        {% if user.username != current_user.username %}
                            {% if user.enabled %}
                            <form method="post" class="inline-form">
                                <input type="hidden" name="action" value="disable_user">
                                <input type="hidden" name="username" value="{{ user.username }}">
                                <button type="submit">Disable</button>
                            </form>
                            {% else %}
                            <form method="post" class="inline-form">
                                <input type="hidden" name="action" value="enable_user">
                                <input type="hidden" name="username" value="{{ user.username }}">
                                <button type="submit">Enable</button>
                            </form>
                            {% endif %}
                        {% else %}
                            Current user
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
</section>
{% endblock %}
