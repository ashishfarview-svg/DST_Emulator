import os
import json
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Prefer /tmp on Vercel (project dir is read-only); fall back to local file for dev.
STORAGE_FILE = (
    "/tmp/dst_storage.json"
    if os.environ.get("VERCEL")
    else os.path.join(os.path.dirname(__file__), "storage.json")
)

# Source of truth in memory — required for serverless where file writes can fail
# or different instances do not share disk.
STORAGE_STATE = {
    "timezone": "America/New_York",
    "reminder_time": "08:00",
    "todos": [],
}

# In-memory emulator and temporary session states (reset on server restart, which is fine)
EMULATOR_STATE = {
    "mode": "emulator",  # "realtime" or "emulator"
    "emulator_time": datetime.now(ZoneInfo("UTC")).isoformat(),  # UTC ISO string
    "last_triggered_date": None,  # date string YYYY-MM-DD
    "trigger_logs": []  # list of trigger events
}

# Supported US Timezones
US_TIMEZONES = [
    {"id": "America/New_York", "name": "Eastern Time (EST/EDT)"},
    {"id": "America/Chicago", "name": "Central Time (CST/CDT)"},
    {"id": "America/Denver", "name": "Mountain Time (MST/MDT)"},
    {"id": "America/Los_Angeles", "name": "Pacific Time (PST/PDT)"},
    {"id": "America/Phoenix", "name": "Arizona (MST, no DST)"},
    {"id": "America/Anchorage", "name": "Alaska Time (AKST/AKDT)"},
    {"id": "America/Adak", "name": "Hawaii-Aleutian Time with DST (HDT/HST)"},
    {"id": "Pacific/Honolulu", "name": "Hawaii Time (HST, no DST)"}
]

def load_storage():
    """Return the live in-memory store (optionally hydrated once from disk)."""
    global STORAGE_STATE
    if STORAGE_STATE.get("_hydrated"):
        return {k: v for k, v in STORAGE_STATE.items() if k != "_hydrated"}

    default_state = {
        "timezone": "America/New_York",
        "reminder_time": "08:00",
        "todos": [],
    }
    loaded = default_state
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r") as f:
                loaded = json.load(f)
        except Exception:
            loaded = default_state

    STORAGE_STATE = {**loaded, "_hydrated": True}
    return {k: v for k, v in STORAGE_STATE.items() if k != "_hydrated"}

def save_storage(data):
    """Update memory first, then best-effort persist to disk."""
    global STORAGE_STATE
    STORAGE_STATE = {**data, "_hydrated": True}
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving storage: {e}")


def apply_client_snapshot(req):
    """
    Restore session from the browser. Required on Vercel because each
    serverless invocation can be a fresh process with empty memory.
    """
    if not req:
        return
    snap = req.get("client_snapshot")
    if not isinstance(snap, dict):
        return

    global STORAGE_STATE, EMULATOR_STATE
    STORAGE_STATE = {
        "timezone": snap.get("timezone") or "America/New_York",
        "reminder_time": snap.get("reminder_time") or "08:00",
        "todos": snap.get("todos") if isinstance(snap.get("todos"), list) else [],
        "_hydrated": True,
    }
    if snap.get("mode") in ("emulator", "realtime"):
        EMULATOR_STATE["mode"] = snap["mode"]
    if snap.get("emulator_time"):
        EMULATOR_STATE["emulator_time"] = snap["emulator_time"]
    if "last_triggered_date" in snap:
        EMULATOR_STATE["last_triggered_date"] = snap.get("last_triggered_date")
    if "trigger_logs" in snap and isinstance(snap.get("trigger_logs"), list):
        EMULATOR_STATE["trigger_logs"] = snap["trigger_logs"]


def build_state():
    data = load_storage()
    curr_utc = get_current_time_utc()
    tz = ZoneInfo(data["timezone"])
    local_dt = curr_utc.astimezone(tz)
    return {
        "timezone": data["timezone"],
        "reminder_time": data["reminder_time"],
        "todos": data["todos"],
        "mode": EMULATOR_STATE["mode"],
        "emulator_time": EMULATOR_STATE["emulator_time"],
        "last_triggered_date": EMULATOR_STATE["last_triggered_date"],
        "trigger_logs": EMULATOR_STATE["trigger_logs"],
        "current_time_utc": curr_utc.isoformat(),
        "local_time": local_dt.isoformat(),
        "local_time_display": local_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
        "timezone_abbr": local_dt.tzname(),
        "utc_offset": local_dt.strftime("%z"),
    }


def get_current_time_utc():
    if EMULATOR_STATE["mode"] == "realtime":
        return datetime.now(ZoneInfo("UTC"))
    else:
        return datetime.fromisoformat(EMULATOR_STATE["emulator_time"].replace("Z", "+00:00"))

def check_reminder(prev_utc, curr_utc, timezone_str, reminder_time_str, last_triggered):
    """
    Checks if the daily reminder was crossed as the clock ticked from prev_utc to curr_utc.
    Returns: (triggered_boolean, triggered_date_str, alert_message)
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        return False, last_triggered, None

    try:
        r_hour, r_min = map(int, reminder_time_str.split(':'))
        r_time = time(r_hour, r_min)
    except Exception:
        return False, last_triggered, None

    # Convert UTC datetimes to local time
    prev_local = prev_utc.astimezone(tz)
    curr_local = curr_utc.astimezone(tz)

    d_start = prev_local.date()
    d_end = curr_local.date()

    curr_d = d_start
    while curr_d <= d_end:
        curr_d_str = curr_d.isoformat()
        
        # If already triggered for this calendar day, skip checking
        if last_triggered == curr_d_str:
            curr_d += timedelta(days=1)
            continue

        is_crossed = False
        is_adjusted = False

        if curr_d == d_start and curr_d == d_end:
            # Same-day tick
            if prev_local.time() < r_time and curr_local.time() >= r_time:
                is_crossed = True
                
                # Check for skipped time (Spring Forward gap)
                # If we create nominal local datetime for r_time on this day,
                # convert it to UTC, and convert it back, does the time shift?
                # For example, on March 8, 2026, 02:30 AM America/New_York shifts to 03:30 AM.
                try:
                    nominal_dt = datetime.combine(curr_d, r_time).replace(tzinfo=tz)
                    utc_dt = nominal_dt.astimezone(ZoneInfo("UTC"))
                    back_dt = utc_dt.astimezone(tz)
                    if back_dt.time() != nominal_dt.time():
                        is_adjusted = True
                except Exception:
                    pass
        elif curr_d == d_start:
            # Multi-day tick, first day portion
            if prev_local.time() < r_time:
                is_crossed = True
        elif curr_d == d_end:
            # Multi-day tick, final day portion
            if curr_local.time() >= r_time:
                is_crossed = True
                # Check for gap
                try:
                    nominal_dt = datetime.combine(curr_d, r_time).replace(tzinfo=tz)
                    utc_dt = nominal_dt.astimezone(ZoneInfo("UTC"))
                    back_dt = utc_dt.astimezone(tz)
                    if back_dt.time() != nominal_dt.time():
                        is_adjusted = True
                except Exception:
                    pass
        else:
            # Full intermediate day crossed
            is_crossed = True

        if is_crossed:
            tz_name = curr_local.tzname()
            # If adjusted, we notify that it ran immediately at the transition time (curr_local)
            if is_adjusted:
                msg = (f"Reminder for {reminder_time_str} triggered at {curr_local.strftime('%I:%M:%S %p')} ({tz_name}) "
                       f"with Spring Forward adjustment (local time {reminder_time_str} was skipped)." )
            else:
                msg = f"Reminder triggered for {curr_d_str} at {curr_local.strftime('%I:%M:%S %p')} ({tz_name})."
            
            return True, curr_d_str, msg

        curr_d += timedelta(days=1)

    return False, last_triggered, None


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "DST Reminder API is running"})


@app.route("/api/timezones", methods=["GET"])
def get_timezones():
    return jsonify(US_TIMEZONES)


@app.route("/api/state", methods=["GET", "POST"])
def get_state():
    if request.method == "POST":
        apply_client_snapshot(request.json)
    return jsonify(build_state())


@app.route("/api/config", methods=["POST"])
def update_config():
    req = request.json or {}
    apply_client_snapshot(req)
    data = load_storage()

    if "timezone" in req:
        data["timezone"] = req["timezone"]
    if "reminder_time" in req:
        data["reminder_time"] = req["reminder_time"]

    save_storage(data)

    # Reset triggered date when config changes so they can test immediately
    EMULATOR_STATE["last_triggered_date"] = None

    return jsonify(build_state())


@app.route("/api/todos", methods=["POST"])
def add_todo():
    req = request.json or {}
    apply_client_snapshot(req)
    data = load_storage()

    new_todo = {
        "id": (max([t.get("id", 0) for t in data["todos"]] + [0]) + 1),
        "text": req.get("text", "").strip(),
        "completed": False
    }
    if new_todo["text"]:
        data["todos"].append(new_todo)
        save_storage(data)

    return jsonify(build_state())


@app.route("/api/todos/toggle", methods=["POST"])
def toggle_todo():
    req = request.json or {}
    apply_client_snapshot(req)
    data = load_storage()
    todo_id = req.get("id")

    for todo in data["todos"]:
        if todo["id"] == todo_id:
            todo["completed"] = not todo["completed"]
            break

    save_storage(data)
    return jsonify(build_state())


@app.route("/api/todos/delete", methods=["POST"])
def delete_todo():
    req = request.json or {}
    apply_client_snapshot(req)
    data = load_storage()
    todo_id = req.get("id")

    data["todos"] = [t for t in data["todos"] if t["id"] != todo_id]
    save_storage(data)
    return jsonify(build_state())


@app.route("/api/emulator/set", methods=["POST"])
def set_emulator():
    req = request.json or {}
    apply_client_snapshot(req)
    if "mode" in req:
        EMULATOR_STATE["mode"] = req["mode"]
    if "emulator_time" in req:
        # Expecting ISO format string
        EMULATOR_STATE["emulator_time"] = req["emulator_time"]
    # Allow presets/UI to update reminder in the same request as the clock jump
    if "reminder_time" in req or "timezone" in req:
        data = load_storage()
        if "reminder_time" in req:
            data["reminder_time"] = req["reminder_time"]
        if "timezone" in req:
            data["timezone"] = req["timezone"]
        save_storage(data)
        EMULATOR_STATE["last_triggered_date"] = None
    if "custom_local_time" in req:
        try:
            data = load_storage()
            tz = ZoneInfo(data["timezone"])

            time_str = req["custom_local_time"].strip()
            suffix = ""
            parts = time_str.split()
            if len(parts) == 3:
                suffix = parts[2].upper()
                time_str = f"{parts[0]} {parts[1]}"

            naive_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

            fold = 0
            # If standard time suffix is typed, resolve to the EST/Standard occurrence
            if suffix in ["EST", "CST", "MST", "PST", "AKST", "HAST"]:
                fold = 1

            local_dt = naive_dt.replace(tzinfo=tz, fold=fold)
            utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
            EMULATOR_STATE["emulator_time"] = utc_dt.isoformat()
        except Exception as e:
            return jsonify({"error": f"Invalid custom time: {str(e)}"}), 400
    if "reset_logs" in req and req["reset_logs"]:
        EMULATOR_STATE["trigger_logs"] = []
        EMULATOR_STATE["last_triggered_date"] = None

    return jsonify(build_state())


@app.route("/api/emulator/tick", methods=["POST"])
def tick_emulator():
    req = request.json or {}
    apply_client_snapshot(req)
    seconds = int(req.get("seconds", 60))

    if EMULATOR_STATE["mode"] != "emulator":
        return jsonify({"error": "Cannot tick clock when in realtime mode"}), 400

    data = load_storage()
    prev_utc = get_current_time_utc()

    # Tick the clock
    curr_utc = prev_utc + timedelta(seconds=seconds)
    EMULATOR_STATE["emulator_time"] = curr_utc.isoformat()

    # Check for alarm trigger (only if tasks are present in the list)
    triggered = False
    new_date = EMULATOR_STATE["last_triggered_date"]
    msg = ""

    if len(data.get("todos", [])) > 0:
        triggered, new_date, msg = check_reminder(
            prev_utc,
            curr_utc,
            data["timezone"],
            data["reminder_time"],
            EMULATOR_STATE["last_triggered_date"]
        )

    alert = None
    if triggered:
        EMULATOR_STATE["last_triggered_date"] = new_date

        # Strike off daily tasks when the reminder fires
        for todo in data.get("todos", []):
            todo["completed"] = True
        save_storage(data)

        log_entry = {
            "timestamp": curr_utc.isoformat(),
            "message": msg,
            "local_time": curr_utc.astimezone(ZoneInfo(data["timezone"])).strftime("%Y-%m-%d %I:%M:%S %p")
        }
        EMULATOR_STATE["trigger_logs"].append(log_entry)
        alert = msg

    return jsonify({
        "state": build_state(),
        "triggered": triggered,
        "alert": alert
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)
