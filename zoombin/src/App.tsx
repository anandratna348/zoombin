
import { useEffect, useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8765";

type Meeting = {
  id: string;
  title: string;
  created_at: string;
  ended_at: string | null;
};

type Transcript = {
  id: number;
  speaker: string;
  text: string;
  timestamp: string;
};

function App() {
  const [connected, setConnected] = useState(false);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [activeMeeting, setActiveMeeting] = useState<Meeting | null>(null);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [title, setTitle] = useState("AI Engineer Interview");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refreshMeetings() {
    try {
      const response = await fetch(`${API}/api/sessions`);
      if (!response.ok) throw new Error("Backend unavailable");
      setMeetings(await response.json());
      setConnected(true);
    } catch {
      setConnected(false);
    }
  }

  async function openMeeting(meeting: Meeting) {
    try {
      const response = await fetch(`${API}/api/sessions/${meeting.id}`);
      if (!response.ok) throw new Error("Could not open meeting");

      const data = await response.json();
      setActiveMeeting(meeting);
      setTranscripts(data.transcripts ?? []);
      setMessage("");
    } catch {
      setMessage("Cannot open meeting. Check that the backend is running.");
    }
  }

  async function startMeeting() {
    if (!title.trim() || busy) return;

    setBusy(true);
    setMessage("");

    try {
      const response = await fetch(`${API}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim() }),
      });

      if (!response.ok) throw new Error("Could not create meeting");

      const meeting: Meeting = await response.json();
      setActiveMeeting(meeting);
      setTranscripts([]);
      setConnected(true);
      await refreshMeetings();
    } catch {
      setMessage(
        "Backend not connected. Start FastAPI on port 8765 and try again."
      );
    } finally {
      setBusy(false);
    }
  }

  async function endMeeting() {
    if (!activeMeeting) return;

    try {
      const response = await fetch(
        `${API}/api/sessions/${activeMeeting.id}/end`,
        { method: "PATCH" }
      );

      if (!response.ok) throw new Error("Could not end meeting");

      setActiveMeeting(null);
      setTranscripts([]);
      await refreshMeetings();
    } catch {
      setMessage("Could not end the meeting. Check the backend.");
    }
  }

  async function exportTranscript(format: "markdown" | "txt" | "json") {
    if (!activeMeeting) return;

    try {
      const response = await fetch(
        `${API}/api/sessions/${activeMeeting.id}/export?format=${format}`
      );

      if (!response.ok) throw new Error("Export failed");

      const result = await response.json();
      const blob = new Blob(
        [typeof result.content === "string"
          ? result.content
          : JSON.stringify(result, null, 2)],
        { type: "text/plain;charset=utf-8" }
      );

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename ?? `zoombin.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setMessage("Transcript export failed.");
    }
  }

  useEffect(() => {
    void refreshMeetings();
  }, []);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Z</div>
          <div>
            <div className="brand-name">zoombin<span>.in</span></div>
            <div className="brand-caption">AI MEETING ASSISTANT</div>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <button className="nav-item active">
          <span>▦</span> Dashboard
        </button>
        <button
          className="nav-item"
          onClick={() => {
            setActiveMeeting(null);
            setTranscripts([]);
            setMessage("");
          }}
        >
          <span>◷</span> Meeting workspace
        </button>

        <div className="nav-label history-label">RECENT MEETINGS</div>
        <div className="meeting-list">
          {meetings.length === 0 && (
            <p className="empty-history">Your meetings will appear here.</p>
          )}

          {meetings.map((meeting) => (
            <button
              className={`history-item ${
                activeMeeting?.id === meeting.id ? "selected" : ""
              }`}
              key={meeting.id}
              onClick={() => void openMeeting(meeting)}
            >
              <span className="history-dot" />
              <span className="history-title">{meeting.title}</span>
            </button>
          ))}
        </div>

        <div className="sidebar-bottom">
          <div className="connection-row">
            <span className={`status-dot ${connected ? "online" : ""}`} />
            <span>{connected ? "Backend connected" : "Backend disconnected"}</span>
          </div>
          <div className="local-note">Your transcripts are stored locally.</div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div>
            <div className="breadcrumb">Workspace / <strong>Dashboard</strong></div>
          </div>
          <div className="topbar-right">
            <span className="local-badge"><span /> Local workspace</span>
            <div className="avatar">Z</div>
          </div>
        </header>

        <div className="page-content">
          <section className="welcome-row">
            <div>
              <div className="eyebrow">YOUR PERSONAL MEETING COPILOT</div>
              <h1>Meet smarter with <span>Zoombin.</span></h1>
              <p className="subtitle">
                Capture conversations, review transcripts, and prepare better answers.
              </p>
            </div>
            <div className="welcome-decoration">✳</div>
          </section>

          {message && (
            <div className="message-banner" role="status">
              {message}
              <button onClick={() => setMessage("")}>Dismiss</button>
            </div>
          )}

          <section className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon purple">◷</div>
              <div className="stat-label">TOTAL MEETINGS</div>
              <div className="stat-value">{meetings.length}</div>
              <div className="stat-foot">Saved on this device</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon green">▤</div>
              <div className="stat-label">TRANSCRIPT ENTRIES</div>
              <div className="stat-value">{transcripts.length}</div>
              <div className="stat-foot">In the selected meeting</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon blue">✧</div>
              <div className="stat-label">AI ASSISTANT</div>
              <div className="stat-value small-value">Coming next</div>
              <div className="stat-foot">Provider connection not configured</div>
            </div>
          </section>

          <section className="workspace-grid">
            <div className="panel meeting-panel">
              <div className="panel-heading">
                <div>
                  <div className="panel-kicker">GET STARTED</div>
                  <h2>{activeMeeting ? "Meeting workspace" : "Start a meeting"}</h2>
                </div>
                <span className="panel-icon">↗</span>
              </div>

              {activeMeeting ? (
                <>
                  <div className="active-meeting-card">
                    <div className="live-indicator"><span /> SESSION SELECTED</div>
                    <h3>{activeMeeting.title}</h3>
                    <p>Session data is saved to your local database.</p>
                  </div>

                  <div className="meeting-actions">
                    <button
                      className="primary-button"
                      onClick={() => void exportTranscript("markdown")}
                    >
                      Export transcript
                    </button>
                    <button className="secondary-button" onClick={() => void endMeeting()}>
                      End session
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="panel-description">
                    Create a session to organize your meeting transcript.
                  </p>
                  <label className="field-label" htmlFor="meeting-title">
                    MEETING NAME
                  </label>
                  <input
                    id="meeting-title"
                    className="text-input"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. AI Engineer Interview"
                    maxLength={200}
                  />
                  <button
                    className="primary-button full-button"
                    onClick={() => void startMeeting()}
                    disabled={busy || !title.trim()}
                  >
                    {busy ? "Creating session..." : "+  Create meeting session"}
                  </button>
                  <p className="privacy-note">
                    <span>♧</span> No audio is captured in this version.
                  </p>
                </>
              )}
            </div>

            <div className="panel transcript-panel">
              <div className="panel-heading">
                <div>
                  <div className="panel-kicker">MEETING NOTES</div>
                  <h2>Transcript</h2>
                </div>
                <span className="panel-icon">▤</span>
              </div>

              {!activeMeeting ? (
                <div className="empty-state">
                  <div className="empty-icon">▤</div>
                  <h3>Nothing here yet</h3>
                  <p>Create or select a meeting to view its transcript.</p>
                </div>
              ) : transcripts.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">◷</div>
                  <h3>Ready for your conversation</h3>
                  <p>Transcript entries will appear here when transcription is connected.</p>
                </div>
              ) : (
                <div className="transcript-list">
                  {transcripts.map((item) => (
                    <div className="transcript-entry" key={item.id}>
                      <div className="speaker">{item.speaker}</div>
                      <p>{item.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="panel ai-panel">
            <div className="ai-symbol">✧</div>
            <div className="ai-copy">
              <div className="panel-kicker">YOUR AI COPILOT</div>
              <h2>Thoughtful answers, when you need them.</h2>
              <p>
                AI-powered response suggestions will appear here after we connect
                your AI provider and transcription pipeline.
              </p>
            </div>
            <span className="coming-badge">COMING NEXT</span>
          </section>

          <footer className="footer">
            <span>ZOOMBIN.IN © 2026</span>
            <span>Built for more productive conversations.</span>
          </footer>
        </div>
      </section>
    </main>
  );
}

export default App;
