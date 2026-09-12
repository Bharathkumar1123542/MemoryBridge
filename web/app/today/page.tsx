"use client";
import { useEffect, useState, useRef, useCallback } from "react";

interface Step { step_number: number; text: string; }
interface Routine { id: string; title: string; steps: Step[]; }

type UIState = "loading" | "nothing" | "routine" | "done" | "help-confirm";

export default function TodayPage() {
  const [state, setState] = useState<UIState>("loading");
  const [routine, setRoutine] = useState<Routine | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [helpNote, setHelpNote] = useState("");
  const [helpSent, setHelpSent] = useState(false);
  const [helpLoading, setHelpLoading] = useState(false);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);

  async function load() {
    setState("loading");
    const res = await fetch("/api/today");
    if (!res.ok) { setState("nothing"); return; }
    const data = await res.json();
    if (data.routine) {
      setRoutine(data.routine);
      setState("routine");
    } else {
      setState("nothing");
    }
  }

  useEffect(() => { load(); }, []);

  // ----- Speech synthesis (browser Web Speech API) -----
  const speakSteps = useCallback(() => {
    if (!routine || speaking) return;
    window.speechSynthesis.cancel();
    setSpeaking(true);
    setCurrentStep(0);

    const steps = routine.steps;
    let idx = 0;

    function speakNext() {
      if (idx >= steps.length) {
        setSpeaking(false);
        setCurrentStep(-1);
        return;
      }
      const utt = new SpeechSynthesisUtterance(steps[idx].text);
      utt.rate = 0.88;
      utt.pitch = 1.05;
      utt.onend = () => {
        idx++;
        setCurrentStep(idx);
        setTimeout(speakNext, 600); // short pause between steps
      };
      utt.onerror = () => { setSpeaking(false); setCurrentStep(-1); };
      speechRef.current = utt;
      window.speechSynthesis.speak(utt);
    }

    speakNext();
  }, [routine, speaking]);

  function stopSpeaking() {
    window.speechSynthesis.cancel();
    setSpeaking(false);
    setCurrentStep(-1);
  }

  async function markDone() {
    if (!routine) return;
    stopSpeaking();
    const today = new Date().toISOString().slice(0, 10);
    await fetch(`/api/routines/${routine.id}/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ occurrence_date: today }),
    });
    setState("done");
  }

  async function sendHelp() {
    setHelpLoading(true);
    await fetch("/api/help", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        note: helpNote || null,
        routine_title: routine?.title ?? null,
      }),
    });
    setHelpSent(true);
    setHelpLoading(false);
  }

  // ---- Render ----

  if (state === "loading") {
    return (
      <div className="today-shell">
        <div className="spinner" style={{ width: 44, height: 44, borderWidth: 4 }} />
      </div>
    );
  }

  if (state === "help-confirm") {
    return (
      <div className="today-shell">
        <div className="today-card">
          {!helpSent ? (
            <>
              <div style={{ fontSize: "3rem", marginBottom: "0.75rem" }}>🆘</div>
              <h1 className="today-title" style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
                Need help?
              </h1>
              <p className="today-subtitle">
                Your caregiver will be notified right away.
              </p>
              <textarea
                className="form-textarea"
                placeholder="You can leave a note if you want to (optional)"
                value={helpNote}
                onChange={e => setHelpNote(e.target.value)}
                style={{ marginBottom: "1.25rem", fontSize: "1.1rem" }}
                aria-label="Optional help note"
              />
              <div className="today-actions">
                <button
                  id="send-help"
                  className="btn btn-xl btn-block"
                  style={{ background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#fff" }}
                  onClick={sendHelp}
                  disabled={helpLoading}
                >
                  {helpLoading ? <><span className="spinner" /> Sending…</> : "📣 Notify my caregiver"}
                </button>
                <button
                  className="btn btn-ghost btn-block"
                  onClick={() => setState(routine ? "routine" : "nothing")}
                >
                  Go back
                </button>
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: "3.5rem", marginBottom: "1rem" }}>✅</div>
              <h1 className="today-title" style={{ fontSize: "2rem" }}>All done!</h1>
              <p className="today-subtitle" style={{ marginBottom: "2rem" }}>
                Your caregiver has been notified in the app.
              </p>
              <button
                className="btn btn-primary btn-xl btn-block"
                onClick={() => { setHelpSent(false); setHelpNote(""); setState(routine ? "routine" : "nothing"); }}
              >
                Return to my routine
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  if (state === "done") {
    return (
      <div className="today-shell">
        <div className="today-card">
          <div style={{ fontSize: "4rem", marginBottom: "0.75rem" }}>🌟</div>
          <h1 className="today-title">Nice work!</h1>
          <p className="today-subtitle" style={{ marginBottom: "2rem" }}>
            You finished your routine for today. Well done!
          </p>
          <button className="btn btn-primary btn-xl btn-block" onClick={load}>
            Check again
          </button>
        </div>
        <button className="help-btn" onClick={() => setState("help-confirm")} aria-label="Help me">
          🆘 Help me
        </button>
      </div>
    );
  }

  if (state === "nothing" || !routine) {
    return (
      <div className="today-shell">
        <div className="today-card">
          <div style={{ fontSize: "3.5rem", marginBottom: "0.75rem" }}>☀️</div>
          <h1 className="today-title">Nothing to do right now.</h1>
          <p className="today-subtitle">Check back later — your caregiver will let you know.</p>
          <button className="btn btn-ghost btn-block mt-3" onClick={load}>Refresh</button>
        </div>
        <button className="help-btn" onClick={() => setState("help-confirm")} aria-label="Help me">
          🆘 Help me
        </button>
      </div>
    );
  }

  // ---- Active routine state ----
  return (
    <div className="today-shell" style={{ paddingBottom: "6rem" }}>
      <div className="today-card">
        <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.5rem" }}>
          Today&apos;s routine
        </p>
        <h1 className="today-title">{routine.title}</h1>

        {routine.steps.length > 0 && (
          <ul className="steps-list" role="list" aria-label="Routine steps">
            {routine.steps.map((s, i) => (
              <li
                key={s.step_number}
                className={`step-item${currentStep === i ? " speaking" : ""}`}
                aria-current={currentStep === i ? "step" : undefined}
              >
                <span className={`step-number${currentStep === i ? " active" : ""}`} aria-hidden="true">
                  {s.step_number}
                </span>
                <span style={{ fontSize: "clamp(1.05rem, 2.5vw, 1.2rem)", lineHeight: 1.55 }}>{s.text}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="today-actions">
          {!speaking ? (
            <button
              id="listen-btn"
              className="btn btn-primary btn-xl btn-block"
              onClick={speakSteps}
            >
              🔊 Listen to steps
            </button>
          ) : (
            <button
              id="stop-listen-btn"
              className="btn btn-ghost btn-xl btn-block"
              onClick={stopSpeaking}
            >
              ⏹ Stop
            </button>
          )}
          <button
            id="done-btn"
            className="btn btn-success btn-xl btn-block"
            onClick={markDone}
          >
            ✓ I&apos;m done!
          </button>
        </div>
      </div>

      <button
        id="help-btn"
        className="help-btn"
        onClick={() => setState("help-confirm")}
        aria-label="Help me — notify caregiver"
      >
        🆘 Help me
      </button>
    </div>
  );
}
