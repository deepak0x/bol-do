"use client";

import { useEffect, useRef, useState } from "react";

type Tone = "polite" | "firm" | "neutral";
type Lang = "hinglish" | "english";

type TranscriptLine = {
  role: "agent" | "callee" | "system";
  text: string;
  ts: number;
};

const PRESETS: { label: string; task: string; tone: Tone }[] = [
  {
    label: "Book a restaurant",
    task: "Book a table for 4 at 8 PM tonight. Window seat if possible. My name is Deepak.",
    tone: "polite",
  },
  {
    label: "Complain about delayed order",
    task:
      "Follow up on order #A1289 that was supposed to be delivered 2 days ago. Ask when it will arrive. Be firm but civil.",
    tone: "firm",
  },
  {
    label: "Clinic appointment enquiry",
    task: "Ask if Dr. Sharma is available for an appointment tomorrow afternoon for a routine check-up.",
    tone: "neutral",
  },
];

const SERVER = process.env.NEXT_PUBLIC_SERVER_URL ?? "http://localhost:7860";

export function CallConsole() {
  const [toNumber, setToNumber] = useState("+917678124123");
  const [task, setTask] = useState(PRESETS[0].task);
  const [tone, setTone] = useState<Tone>(PRESETS[0].tone);
  const [language, setLanguage] = useState<Lang>("hinglish");
  const [userName, setUserName] = useState("Deepak");
  const [scheduledFor, setScheduledFor] = useState("");
  const [callSid, setCallSid] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "queued" | "live" | "ended" | "error" | "scheduled">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [injectText, setInjectText] = useState("");
  const [injecting, setInjecting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [transcript]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  async function placeCall() {
    setErrorMsg(null);
    setTranscript([]);
    const scheduling = scheduledFor.trim().length > 0;
    setStatus(scheduling ? "scheduled" : "queued");
    try {
      const body: Record<string, unknown> = {
        to_number: toNumber.trim(),
        task: task.trim(),
        tone,
        language,
        user_name: userName.trim() || "the user",
      };
      if (scheduling) {
        // datetime-local gives "YYYY-MM-DDTHH:MM" with no TZ — backend assumes IST.
        body.scheduled_for = scheduledFor;
      }
      const res = await fetch(`${SERVER}/dialout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      const data: { call_sid: string; status: string } = await res.json();
      setCallSid(data.call_sid);
      if (scheduling) {
        // No live transcript for scheduled calls; just confirm and clear.
        setStatus("scheduled");
      } else {
        subscribeTranscript(data.call_sid);
        setStatus("live");
      }
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function subscribeTranscript(sid: string) {
    const wsUrl = SERVER.replace(/^http/, "ws") + `/transcript/${sid}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        const line = JSON.parse(ev.data) as TranscriptLine;
        setTranscript((prev) => [...prev, line]);
        if (line.role === "system" && line.text === "call ended") {
          setStatus("ended");
        }
      } catch {
        /* ignore */
      }
    };
    ws.onerror = () => {
      setErrorMsg("Lost transcript connection");
    };
  }

  function applyPreset(p: (typeof PRESETS)[number]) {
    setTask(p.task);
    setTone(p.tone);
  }

  async function sendInject() {
    const msg = injectText.trim();
    if (!msg || !callSid || injecting) return;
    setInjecting(true);
    try {
      const res = await fetch(`${SERVER}/inject/${callSid}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      if (!res.ok) throw new Error(await res.text());
      setInjectText("");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setInjecting(false);
    }
  }

  const disabled = status === "queued" || status === "live";

  return (
    <section className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-8">
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Your name</span>
            <input
              type="text"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Call number</span>
            <input
              type="tel"
              placeholder="+919876543210"
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm font-mono outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
        </div>

        <label className="mt-4 flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">What should Bol Do do?</span>
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={7}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="mr-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">Tone:</span>
          {(["polite", "neutral", "firm"] as Tone[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTone(t)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                tone === t
                  ? "border-black bg-black text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-black"
                  : "border-zinc-300 bg-white text-zinc-700 hover:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="mr-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">Language:</span>
          {(["hinglish", "english"] as Lang[]).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLanguage(l)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                language === l
                  ? "border-black bg-black text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-black"
                  : "border-zinc-300 bg-white text-zinc-700 hover:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
              }`}
            >
              {l}
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <span className="mr-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">Presets:</span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => applyPreset(p)}
              className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300"
            >
              {p.label}
            </button>
          ))}
        </div>

        <label className="mt-4 flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            Schedule for later (optional · IST)
          </span>
          <input
            type="datetime-local"
            value={scheduledFor}
            onChange={(e) => setScheduledFor(e.target.value)}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <div className="mt-6 flex items-center justify-between">
          <div className="text-xs text-zinc-500">
            {status === "idle" && "Ready"}
            {status === "queued" && "Queuing call…"}
            {status === "scheduled" && "Call scheduled — see Dashboard"}
            {status === "live" && callSid && `Live · ${callSid.slice(0, 10)}…`}
            {status === "ended" && "Call ended"}
            {status === "error" && (errorMsg ?? "Error")}
          </div>
          <button
            type="button"
            onClick={placeCall}
            disabled={disabled || !toNumber || task.trim().length < 4}
            className="rounded-full bg-black px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400 dark:bg-zinc-100 dark:text-black dark:hover:bg-zinc-300"
          >
            {disabled
              ? scheduledFor
                ? "Scheduling…"
                : "Calling…"
              : scheduledFor
                ? "Schedule call"
                : "Place call"}
          </button>
        </div>
      </div>

      <div className="flex flex-col rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">Live transcript</h2>
          {status === "live" && (
            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
              live
            </span>
          )}
        </div>
        <div
          ref={scrollerRef}
          className="min-h-64 flex-1 overflow-y-auto rounded-lg bg-zinc-50 p-4 text-sm leading-relaxed dark:bg-zinc-900"
        >
          {transcript.length === 0 ? (
            <p className="text-zinc-400">No transcript yet. Place a call to see it stream here.</p>
          ) : (
            transcript.map((line, i) => <TranscriptRow key={i} line={line} />)
          )}
        </div>
        {status === "live" && callSid && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={injectText}
              onChange={(e) => setInjectText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendInject();
                }
              }}
              disabled={injecting}
              placeholder="Type as the callee (Enter to send)…"
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-black disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <button
              type="button"
              onClick={sendInject}
              disabled={injecting || !injectText.trim()}
              className="rounded-lg bg-black px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400 dark:bg-zinc-100 dark:text-black dark:hover:bg-zinc-300"
            >
              {injecting ? "…" : "Send"}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function TranscriptRow({ line }: { line: TranscriptLine }) {
  if (line.role === "system") {
    return (
      <div className="my-2 text-center text-xs uppercase tracking-wide text-zinc-400">
        — {line.text} · {formatTs(line.ts)} —
      </div>
    );
  }
  const isAgent = line.role === "agent";
  return (
    <div className={`my-1.5 flex ${isAgent ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-3 py-2 ${
          isAgent
            ? "bg-white text-zinc-900 ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-zinc-700"
            : "bg-black text-white dark:bg-zinc-100 dark:text-black"
        }`}
      >
        <div className="mb-0.5 flex items-center justify-between gap-3 text-[10px] uppercase tracking-wide opacity-60">
          <span>{isAgent ? "Bol Do" : "Callee"}</span>
          <span className="font-mono normal-case">{formatTs(line.ts)}</span>
        </div>
        <div>{line.text}</div>
      </div>
    </div>
  );
}
