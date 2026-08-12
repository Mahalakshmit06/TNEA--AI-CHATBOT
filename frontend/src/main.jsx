import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api";
const EMPTY_PROFILE = { name: "", cutoff: null, community: "", district: "", branch: "" };

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "The service could not complete that request.");
  }
  return response.json();
}

function useHashPage() {
  const read = () => {
    const value = window.location.hash.replace("#/", "");
    return ["chat", "calculator", "finder"].includes(value) ? value : "finder";
  };
  const [page, setPage] = useState(read);
  useEffect(() => {
    const handler = () => setPage(read());
    window.addEventListener("hashchange", handler);
    if (!window.location.hash) window.location.hash = "#/finder";
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  return page;
}

function navigate(page) {
  window.location.hash = `/${page}`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function App() {
  const page = useHashPage();
  const [meta, setMeta] = useState(null);
  const [apiError, setApiError] = useState("");

  useEffect(() => {
    api("/meta").then(setMeta).catch((error) => setApiError(error.message));
  }, []);

  return (
    <div className="app-shell">
      <Header page={page} />
      <main>
        <Hero meta={meta} />
        <PageTabs page={page} />
        {apiError && <div className="error-banner">{apiError} · Start the backend and refresh the page.</div>}
        <div className="page-wrap">
          {page === "chat" && <ChatPage />}
          {page === "calculator" && <CalculatorPage />}
          {page === "finder" && <FinderPage meta={meta} />}
        </div>
      </main>
      <Footer />
      <ScrollTop />
    </div>
  );
}

function Header({ page }) {
  return (
    <header className="topbar">
      <button className="brand" onClick={() => navigate("finder")} aria-label="Open College Finder">
        <span className="brand-mark">CA</span>
        <span><strong>Campus AI</strong><small>TNEA Counselling</small></span>
      </button>
      <nav className="desktop-nav" aria-label="Primary navigation">
        <button className={page === "finder" ? "nav-active" : ""} onClick={() => navigate("finder")}>College Finder</button>
        <button className={page === "calculator" ? "nav-active" : ""} onClick={() => navigate("calculator")}>Cutoff Calculator</button>
        <button className={page === "chat" ? "nav-active" : ""} onClick={() => navigate("chat")}>Campus AI</button>
      </nav>
    </header>
  );
}

function Hero({ meta }) {
  return (
    <section className="hero">
      <div className="hero-inner">
        <div className="eyebrow"><span className="dot" /> TNEA COUNSELLING · DATA-GROUNDED</div>
        <h1>Campus AI — TNEA Counselling<br className="desktop-only" /> Recommendation System</h1>
        <p>Find suitable college and branch options from the supplied counselling dataset, calculate your cutoff, and get step-by-step counselling guidance through one professional assistant.</p>
        <div className="stats">
          <Stat value={meta?.colleges ?? "—"} label="Colleges tracked" />
          <Stat value={meta?.records?.toLocaleString() ?? "—"} label="Branch listings" />
          <Stat value={meta?.districts?.length ?? "—"} label="Districts covered" />
        </div>
      </div>
    </section>
  );
}

function Stat({ value, label }) { return <div className="stat"><strong>{value}</strong><span>{label}</span></div>; }

function PageTabs({ page }) {
  const tabs = [["finder", "01", "College Finder"], ["calculator", "02", "Cutoff Calculator"], ["chat", "03", "Campus AI"]];
  return <div className="tabs-wrap"><div className="tabs">{tabs.map(([key, number, label]) => (
    <button key={key} className={`tab ${page === key ? "selected" : ""}`} onClick={() => navigate(key)}><span>{number}</span>{label}</button>
  ))}</div></div>;
}

function ChatPage() {
  const [profile, setProfile] = useState(() => JSON.parse(localStorage.getItem("campusProfile") || "null") || EMPTY_PROFILE);
  const [messages, setMessages] = useState(() => JSON.parse(localStorage.getItem("campusChat") || "null") || []);
  const [records, setRecords] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showScroll, setShowScroll] = useState(false);
  const messagesRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!messages.length) {
      setMessages([{ role: "assistant", text: "Hello! I’m Campus AI. Say Hi to begin." }]);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("campusChat", JSON.stringify(messages.slice(-80)));
    localStorage.setItem("campusProfile", JSON.stringify(profile));
  }, [messages, profile]);

  useEffect(() => {
    const box = messagesRef.current;
    if (!box) return;
    box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [messages, busy, records]);

  useEffect(() => {
    const box = messagesRef.current;
    if (!box) return;
    const onScroll = () => setShowScroll(box.scrollTop > 180);
    box.addEventListener("scroll", onScroll, { passive: true });
    return () => box.removeEventListener("scroll", onScroll);
  }, []);

  function add(role, value) { setMessages((current) => [...current, { role, text: value }]); }

  async function send(event) {
    event?.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setText("");
    setError("");
    add("user", value);
    setBusy(true);
    try {
      const data = await api("/chat", {
        method: "POST",
        body: JSON.stringify({
          name: profile.name || "",
          cutoff: profile.cutoff === null || profile.cutoff === "" ? null : Number(profile.cutoff),
          community: profile.community || null,
          district: profile.district || null,
          branch: profile.branch || null,
          message: value,
        }),
      });
      setProfile(data.profile || EMPTY_PROFILE);
      setRecords(data.records || []);
      add("assistant", data.reply);
    } catch (requestError) {
      setError(requestError.message);
      add("assistant", "I could not connect to the recommendation service. Please check that the backend is running and try again.");
    } finally {
      setBusy(false);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }

  function resetChat() {
    localStorage.removeItem("campusChat");
    localStorage.removeItem("campusProfile");
    setProfile(EMPTY_PROFILE);
    setMessages([{ role: "assistant", text: "Hello! I’m Campus AI. Say Hi to begin." }]);
    setRecords([]);
    setText("");
    setError("");
    setTimeout(() => inputRef.current?.focus(), 30);
  }

  function scrollMessagesToTop() {
    messagesRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  const ready = Boolean(profile.name && profile.cutoff !== null && profile.community && profile.district && profile.branch);
  const quick = [
    "Which colleges can I get with my cutoff?",
    "Which colleges offer CSE?",
    "Suggest colleges in Chennai.",
    "What documents are needed for counselling?",
  ];

  return (
    <section className="content-section">
      <div className="section-heading">
        <div><span className="section-kicker">03 · RECOMMENDATION ASSISTANT</span><h2>Talk to Campus AI</h2><p>Campus AI collects your profile one detail at a time, then recommends matching college-branch records and answers relevant counselling questions.</p></div>
        <button className="secondary-btn" onClick={resetChat}>New conversation</button>
      </div>

      <div className="chat-card">
        <div className="chat-header">
          <div className="assistant-avatar">CA</div>
          <div><strong>Campus AI Assistant</strong><span>{ready ? `Profile ready · ${profile.community} · ${profile.cutoff}` : "Profile setup · one question at a time"}</span></div>
          <div className="online-dot" title="Backend connection" />
        </div>

        <div className="chat-body">
          <div className="chat-profile" aria-label="Current recommendation profile">
            <ProfileChip label="Name" value={profile.name || "Waiting"} />
            <ProfileChip label="Cutoff" value={profile.cutoff ?? "Waiting"} />
            <ProfileChip label="Community" value={profile.community || "Waiting"} />
            <ProfileChip label="District" value={profile.district || "Waiting"} />
            <ProfileChip label="Branch" value={profile.branch || "Waiting"} />
          </div>

          <div className="messages-shell">
            <div ref={messagesRef} className="messages" aria-live="polite" aria-label="Campus AI conversation">
              {messages.map((message, index) => <ChatBubble key={`${index}-${message.role}`} role={message.role} text={message.text} />)}
              {busy && <div className="typing"><span /><span /><span /> Checking matching records…</div>}
            </div>
            {showScroll && <button className="chat-scroll-top" onClick={scrollMessagesToTop} aria-label="Scroll chat to top">↑</button>}
          </div>

          {records.length > 0 && <ResultsTable records={records} title="Matching college records" compact />}

          {ready && <div className="quick-prompts" aria-label="Suggested questions">
            {quick.map((question) => <button key={question} type="button" onClick={() => { setText(question); inputRef.current?.focus(); }}>{question}</button>)}
          </div>}

          {error && <div className="inline-error">{error}</div>}

          <form className="chat-input-row" onSubmit={send}>
            <input ref={inputRef} value={text} onChange={(event) => setText(event.target.value)} placeholder={ready ? "Ask about colleges, cutoff, branches or counselling…" : "Type your answer…"} aria-label="Chat message" autoComplete="off" enterKeyHint="send" />
            <button className="primary-btn" disabled={busy || !text.trim()}>{busy ? "Checking…" : "Send"}</button>
          </form>
          <p className="chat-note">Your conversation profile is stored locally and chat messages are also saved in the project database for profile continuity.</p>
        </div>
      </div>
    </section>
  );
}

function ProfileChip({ label, value }) { return <div className="profile-chip"><span>{label}</span><strong>{String(value)}</strong></div>; }

function ChatBubble({ role, text }) {
  return <div className={`bubble-row ${role === "user" ? "user-row" : ""}`}>{role !== "user" && <div className="mini-avatar">CA</div>}<div className={`bubble ${role}`}>{text}</div></div>;
}

function CalculatorPage() {
  const [marks, setMarks] = useState({ mathematics: "", physics: "", chemistry: "" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function calculate(event) {
    event.preventDefault(); setError(""); setResult(null);
    const values = Object.values(marks).map(Number);
    if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 100)) {
      setError("Enter valid marks from 0 to 100 for every subject."); return;
    }
    setBusy(true);
    try { setResult(await api("/calculate-cutoff", { method: "POST", body: JSON.stringify({ mathematics: values[0], physics: values[1], chemistry: values[2] }) })); }
    catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  }

  return <section className="content-section narrow">
    <div className="section-heading"><div><span className="section-kicker">02 · CUT-OFF CALCULATOR</span><h2>Calculate your cutoff</h2><p>Enter Mathematics, Physics and Chemistry marks to calculate your counselling cutoff.</p></div></div>
    <div className="calculator-card">
      <div className="formula-box"><span>Formula</span><strong>Mathematics + Physics / 2 + Chemistry / 2</strong><small>Maximum calculated cutoff: 200</small></div>
      <form className="mark-grid" onSubmit={calculate}>
        {[["mathematics", "Mathematics"], ["physics", "Physics"], ["chemistry", "Chemistry"]].map(([key, label]) => <label key={key}>{label} <span>/100</span><input type="number" min="0" max="100" step="0.01" value={marks[key]} placeholder="Enter marks" onChange={(event) => setMarks({ ...marks, [key]: event.target.value })} required /></label>)}
        {error && <div className="inline-error">{error}</div>}
        <button className="primary-btn large" disabled={busy}>{busy ? "Calculating…" : "Calculate cutoff"}</button>
      </form>
      {result && <div className="cutoff-result"><div><span>Your calculated cutoff</span><strong>{result.cutoff.toFixed(2)}</strong><small>/ 200</small></div><div className="result-meter"><span style={{ width: `${Math.min(result.cutoff / 200 * 100, 100)}%` }} /></div><p>Use this cutoff in <button onClick={() => navigate("finder")}>College Finder</button>.</p></div>}
    </div>
  </section>;
}

function FinderPage({ meta }) {
  const [form, setForm] = useState({ name: "", cutoff: "", community: "OC", district: "ALL", branch: "ALL" });
  const [records, setRecords] = useState([]); const [total, setTotal] = useState(0); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  async function search(event) {
    event?.preventDefault(); setError(""); setLoading(true);
    try { const data = await api("/recommend", { method: "POST", body: JSON.stringify({ ...form, cutoff: Number(form.cutoff), limit: 300 }) }); setRecords(data.records || []); setTotal(data.count || 0); localStorage.setItem("campusProfile", JSON.stringify(form)); }
    catch (requestError) { setError(requestError.message); setRecords([]); }
    finally { setLoading(false); }
  }
  function reset() { setForm({ name: "", cutoff: "", community: "OC", district: "ALL", branch: "ALL" }); setRecords([]); setTotal(0); setError(""); }
  return <section className="content-section">
    <div className="section-heading"><div><span className="section-kicker">01 · COLLEGE FINDER</span><h2>Find colleges that fit your profile</h2><p>Filter the supplied dataset by cutoff, community, district and branch.</p></div></div>
    <div className="finder-layout">
      <form className="finder-card" onSubmit={search}>
        <label>Your name<input value={form.name} placeholder="Enter your name" onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Your cutoff mark<input type="number" min="0" max="200" step="0.01" value={form.cutoff} placeholder="e.g. 180" onChange={(e) => setForm({ ...form, cutoff: e.target.value })} required /></label>
        <label>Community<select value={form.community} onChange={(e) => setForm({ ...form, community: e.target.value })}>{["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"].map((x) => <option key={x}>{x}</option>)}</select></label>
        <label>District<select value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })}><option value="ALL">All districts</option>{(meta?.districts || []).map((x) => <option key={x} value={x}>{titleDistrict(x)}</option>)}</select></label>
        <label>Branch<select value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })}><option value="ALL">All branches</option>{(meta?.branches || []).map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
        {error && <div className="inline-error">{error}</div>}
        <div className="form-actions"><button className="primary-btn large" disabled={loading}>{loading ? "Searching…" : "Search colleges"}</button><button type="button" className="secondary-btn" onClick={reset}>Reset filters</button></div>
      </form>
      <div className="results-card"><div className="results-head"><div><span className="section-kicker">RESULTS</span><h3>{loading ? "Checking records…" : `${total.toLocaleString()} matching records`}</h3></div>{records.length > 0 && <span className="result-count">Showing {records.length}</span>}</div>{loading ? <LoadingRows /> : records.length ? <ResultsTable records={records} /> : <div className="empty-state"><div className="empty-icon">⌕</div><h3>Ready for your search</h3><p>Enter your profile and search to see matching college and branch records.</p></div>}</div>
    </div>
  </section>;
}

function ResultsTable({ records, title, compact = false }) {
  return <div className={`table-wrap ${compact ? "compact-table" : ""}`}>{title && <div className="table-title">{title}</div>}<table><thead><tr><th>College</th><th>District</th><th>Branch</th><th>Closing cutoff</th><th>Margin</th><th>Fit</th></tr></thead><tbody>{records.map((record, index) => <tr key={`${record.college_code}-${record.branch_code}-${index}`}><td><div className="college-cell"><strong>{record.college_name}</strong><small>Code {record.college_code}</small></div></td><td>{titleDistrict(record.district)}</td><td>{record.branch}<small className="branch-code">{record.branch_code}</small></td><td><strong>{Number(record.closing_cutoff).toFixed(2)}</strong></td><td>{Number(record.margin) >= 0 ? "+" : ""}{Number(record.margin).toFixed(1)}</td><td><span className={`fit ${String(record.status).toLowerCase().replaceAll(" ", "-")}`}>{record.status}</span></td></tr>)}</tbody></table></div>;
}

function LoadingRows() { return <div className="loading-list">{Array.from({ length: 6 }).map((_, index) => <div className="skeleton" key={index}><span /><span /><span /></div>)}</div>; }
function titleDistrict(value) { return String(value || "").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase()); }
function ScrollTop() { const [visible, setVisible] = useState(false); useEffect(() => { const onScroll = () => setVisible(window.scrollY > 420); window.addEventListener("scroll", onScroll, { passive: true }); return () => window.removeEventListener("scroll", onScroll); }, []); return visible ? <button className="page-scroll-top" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="Scroll page to top">↑</button> : null; }
function Footer() { return <footer><p><strong>Campus AI</strong> · TNEA Counselling Recommendation System</p><p>College recommendations are generated from the supplied counselling dataset. Follow the official TNEA instructions for applicable counselling requirements.</p></footer>; }

createRoot(document.getElementById("root")).render(<App />);
