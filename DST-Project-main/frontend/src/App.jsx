import { useState, useEffect, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:5000/api";

function App() {
  const [activeTab, setActiveTab] = useState("todo");
  const [state, setState] = useState(null);
  const stateRef = useRef(null);
  
  // Timezone and reminder settings (local state for inputs)
  const [selectedTz, setSelectedTz] = useState("America/New_York");
  const [reminderTime, setReminderTime] = useState("08:00");
  
  // New To-Do Input
  const [todoText, setTodoText] = useState("");
  
  // Emulator Custom Time Input
  const [customTime, setCustomTime] = useState("");
  const [timezones, setTimezones] = useState([]);

  const applyState = (nextState) => {
    if (!nextState) return;
    stateRef.current = nextState;
    setState(nextState);
  };

  // Fetch initial state & timezones
  useEffect(() => {
    fetchTimezones();
    fetchState();
  }, []);

  // Sync state values to form inputs when state is loaded
  useEffect(() => {
    if (state) {
      setSelectedTz(state.timezone);
      setReminderTime(state.reminder_time);
    }
  }, [state?.timezone, state?.reminder_time]);

  // Realtime mode only: refresh clock without wiping emulator session memory
  useEffect(() => {
    const pollInterval = setInterval(() => {
      if (stateRef.current?.mode === "realtime") {
        refreshState();
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, []);

  const buildClientSnapshot = () => {
    const current = stateRef.current;
    if (!current) return null;
    return {
      timezone: current.timezone,
      reminder_time: current.reminder_time,
      todos: current.todos,
      mode: current.mode,
      emulator_time: current.emulator_time,
      last_triggered_date: current.last_triggered_date,
      trigger_logs: current.trigger_logs,
    };
  };

  const apiPost = async (path, body = {}) => {
    const snapshot = buildClientSnapshot();
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...body,
        ...(snapshot ? { client_snapshot: snapshot } : {}),
      }),
    });
    return res.json();
  };

  const fetchTimezones = async () => {
    try {
      const res = await fetch(`${API_BASE}/timezones`);
      const data = await res.json();
      setTimezones(data);
    } catch (e) {
      console.error("Failed to fetch timezones", e);
    }
  };

  const fetchState = async () => {
    try {
      const res = await fetch(`${API_BASE}/state`);
      const data = await res.json();
      applyState(data);
    } catch (e) {
      console.error("Failed to fetch application state", e);
    }
  };

  const refreshState = async () => {
    try {
      const data = await apiPost("/state");
      applyState(data);
    } catch (e) {
      console.error("Failed to refresh application state", e);
    }
  };

  const saveConfig = async (tz = selectedTz, time = reminderTime) => {
    try {
      const data = await apiPost("/config", { timezone: tz, reminder_time: time });
      applyState(data);
    } catch (e) {
      console.error("Failed to save config", e);
    }
  };

  const handleAddTodo = async (e) => {
    e.preventDefault();
    if (!todoText.trim()) return;
    try {
      const data = await apiPost("/todos", { text: todoText });
      applyState(data);
      setTodoText("");
    } catch (e) {
      console.error("Failed to add todo", e);
    }
  };

  const handleToggleTodo = async (id) => {
    try {
      const data = await apiPost("/todos/toggle", { id });
      applyState(data);
    } catch (e) {
      console.error("Failed to toggle todo", e);
    }
  };

  const handleDeleteTodo = async (id) => {
    try {
      const data = await apiPost("/todos/delete", { id });
      applyState(data);
    } catch (e) {
      console.error("Failed to delete todo", e);
    }
  };

  const handleTick = async (secondsVal) => {
    try {
      const data = await apiPost("/emulator/tick", { seconds: secondsVal });
      if (data.state) {
        applyState(data.state);
      }
      if (data.triggered) {
        // Only fire native browser alert dialog as requested
        alert(data.alert);
      }
    } catch (e) {
      console.error("Failed to tick clock", e);
    }
  };

  const resetLogs = async () => {
    try {
      const data = await apiPost("/emulator/set", { reset_logs: true });
      applyState(data);
    } catch (e) {
      console.error("Failed to reset logs", e);
    }
  };

  // Preset scenarios handlers
  const loadSpringForwardPreset = async () => {
    try {
      const data = await apiPost("/emulator/set", {
        mode: "emulator",
        custom_local_time: "2026-03-08 01:58:00",
      });
      applyState(data);
    } catch (e) {
      console.error("Failed to load Spring Forward preset", e);
    }
  };

  const loadFallBackPreset = async () => {
    try {
      const data = await apiPost("/emulator/set", {
        mode: "emulator",
        custom_local_time: "2026-11-01 01:28:00 EDT",
      });
      applyState(data);
    } catch (e) {
      console.error("Failed to load Fall Back preset", e);
    }
  };

  const handleSetCustomTime = async () => {
    try {
      if (!customTime) return;
      const parts = customTime.trim().split(/\s+/);
      if (parts.length < 2 || parts.length > 3) {
        throw new Error("Format: YYYY-MM-DD HH:MM:SS [EST/EDT]");
      }

      const data = await apiPost("/emulator/set", {
        custom_local_time: customTime.trim(),
      });

      if (data.error) {
        throw new Error(data.error);
      }

      applyState(data);
    } catch (e) {
      alert(
        e.message ||
          "Please enter a valid format: YYYY-MM-DD HH:MM:SS (e.g. 2026-03-08 01:58:00)"
      );
    }
  };

  if (!state) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <div className="time-text">Loading application...</div>
      </div>
    );
  }

  const formatOffset = (offsetStr) => {
    if (!offsetStr) return "";
    const hours = offsetStr.slice(0, 3);
    const mins = offsetStr.slice(3);
    return `UTC${hours}:${mins}`;
  };

  return (
    <div className="app-container">
      <header>
        <div className="brand">
          <h1>DST To-Do List</h1>
        </div>
        <div className="tabs">
          <button 
            className={`tab-btn ${activeTab === "todo" ? "active" : ""}`}
            onClick={() => setActiveTab("todo")}
          >
            📋 To-Do & Clock
          </button>
          <button 
            className={`tab-btn ${activeTab === "emulator" ? "active" : ""}`}
            onClick={() => setActiveTab("emulator")}
          >
            🧪 DST Emulator
          </button>
        </div>
      </header>

      <main className="dashboard-grid">
        {/* LEFT COLUMN */}
        {activeTab === "todo" ? (
          <div className="card">
            <h2>📋 Daily To-Do List</h2>
            
            <form onSubmit={handleAddTodo} className="todo-input-row">
              <input
                type="text"
                placeholder="What do you need to do every day?"
                value={todoText}
                onChange={(e) => setTodoText(e.target.value)}
                maxLength={100}
              />
              <button type="submit" className="btn">Add Item</button>
            </form>

            <div className="todo-list">
              {state.todos.length === 0 ? (
                <div className="empty-state">
                  No items in your daily list. Add some above!
                </div>
              ) : (
                state.todos.map((todo) => (
                  <div key={todo.id} className={`todo-item ${todo.completed ? "completed" : ""}`}>
                    <div className="todo-item-left" onClick={() => handleToggleTodo(todo.id)}>
                      <div className="todo-checkbox">
                        {todo.completed && <span style={{ color: "white", fontSize: "0.8rem" }}>✓</span>}
                      </div>
                      <span className="todo-text">{todo.text}</span>
                    </div>
                    <button className="delete-btn" onClick={() => handleDeleteTodo(todo.id)}>
                      🗑️
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <div className="card">
            <div>
              <h2>🧪 Scenario Presets</h2>
              <div className="scenario-presets">
                <div className="preset-card" onClick={loadSpringForwardPreset}>
                  <div>
                    <div className="preset-title">🌸 Spring Forward</div>
                  </div>
                  <div style={{ marginTop: "0.75rem", alignSelf: "flex-end" }}>
                    <span className="btn btn-secondary" style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}>Load Scenario</span>
                  </div>
                </div>

                <div className="preset-card" onClick={loadFallBackPreset}>
                  <div>
                    <div className="preset-title">🍁 Fall Back</div>
                  </div>
                  <div style={{ marginTop: "0.75rem", alignSelf: "flex-end" }}>
                    <span className="btn btn-secondary" style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}>Load Scenario</span>
                  </div>
                </div>
              </div>

              <h2>⚙️ Emulator Controls</h2>
                
                <div className="form-group">
                  <label>Manually Set Date & Time (Local)</label>
                  <div className="todo-input-row">
                    <input 
                      type="text" 
                      placeholder="e.g. 2026-11-01 01:29:55 EST"
                      value={customTime}
                      onChange={(e) => setCustomTime(e.target.value)}
                    />
                    <button
                      className="btn btn-secondary"
                      onClick={handleSetCustomTime}
                    >
                      Set
                    </button>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginTop: "-1rem", marginBottom: "1rem" }}>
                    Enter date in YYYY-MM-DD HH:MM:SS format
                  </span>
                </div>



                <div className="form-group">
                  <label>Manual Steps</label>
                  <div className="control-grid">
                    <button className="btn btn-secondary" onClick={() => handleTick(1)}>+1 Sec</button>
                    <button className="btn btn-secondary" onClick={() => handleTick(60)}>+1 Min</button>
                    <button className="btn btn-secondary" onClick={() => handleTick(300)}>+5 Min</button>
                    <button className="btn btn-secondary" onClick={() => handleTick(3600)}>+1 Hour</button>
                    <button className="btn btn-secondary" onClick={() => handleTick(86400)}>+1 Day</button>
                  </div>
                </div>
              </div>
            </div>
          )}

        {/* RIGHT COLUMN (ALWAYS DISPLAY CLOCK & SETTINGS) */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Clock Card */}
          <div className="card clock-display">
            <div className="time-text">{state.local_time_display.split(" ")[1]} {state.local_time_display.split(" ")[2]}</div>
            <div className="date-text">{state.local_time_display.split(" ")[0]}</div>
            <div className={`timezone-pill ${state.timezone_abbr.includes("D") ? "dst-active" : ""}`}>
              🌍 {state.timezone_abbr} ({formatOffset(state.utc_offset)})
            </div>
          </div>

          {/* Time & Alert Configuration */}
          <div className="card">
            <h2>⚙️ Time Settings</h2>
            
            <div className="form-group">
              <label>Select US Timezone</label>
              <select 
                value={selectedTz} 
                onChange={(e) => {
                  setSelectedTz(e.target.value);
                  saveConfig(e.target.value, reminderTime);
                }}
              >
                {timezones.map((tz) => (
                  <option key={tz.id} value={tz.id}>
                    {tz.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Daily Reminder Time</label>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input 
                  type="time" 
                  value={reminderTime} 
                  onChange={(e) => setReminderTime(e.target.value)}
                />
                <button 
                  className="btn btn-secondary"
                  onClick={() => saveConfig(selectedTz, reminderTime)}
                >
                  Save
                </button>
              </div>
            </div>

          </div>

          {/* Log Card */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ margin: 0 }}>📜 Trigger Log</h2>
              <button 
                className="btn btn-secondary" 
                style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem", marginLeft: "auto" }}
                onClick={resetLogs}
              >
                Clear Logs
              </button>
            </div>
            <div className="log-panel">
              {state.trigger_logs.length === 0 ? (
                <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center", padding: "1rem 0" }}>
                  No triggers recorded.
                </div>
              ) : (
                state.trigger_logs.slice().reverse().map((log, index) => (
                  <div key={index} className="log-entry">
                    <div className="log-meta">System: {log.local_time}</div>
                    <div className="log-msg triggered">{log.message}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
