"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const SERVER = process.env.NEXT_PUBLIC_SERVER_URL ?? "http://localhost:7860";

type Index = { chats: string[]; calls: string[] };
type Line = { role: "agent" | "callee" | "system"; text: string; ts: number };
type Scheduled = {
  id: string;
  scheduled_for: string;
  to_number: string;
  task: string;
  tone: string;
  user_name: string;
  status: "pending" | "fired" | "missed" | "cancelled";
  fired_at: string | null;
  call_sid: string | null;
};

type CallDetail = {
  meta: {
    call_sid: string;
    to_number?: string;
    from_number?: string;
    task?: string;
    tone?: string;
    user_name?: string;
  };
  transcript: Line[];
};

type ChatDetail = {
  task: string;
  tone: string;
  user_name: string;
  history: { role: "user" | "model"; content: string }[];
};

export default function DashboardPage() {
  const [tab, setTab] = useState<"calls" | "chats" | "scheduled">("calls");
  const [index, setIndex] = useState<Index>({ chats: [], calls: [] });
  const [scheduled, setScheduled] = useState<Scheduled[]>([]);
  const [open, setOpen] = useState<{ kind: "call" | "chat"; id: string } | null>(null);
  const [detail, setDetail] = useState<CallDetail | ChatDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([
        fetch(`${SERVER}/sessions`),
        fetch(`${SERVER}/scheduled`),
      ]);
      if (!r.ok) throw new Error(`${r.status}`);
      setIndex(await r.json());
      if (s.ok) setScheduled(await s.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  async function cancelScheduled(id: string) {
    try {
      await fetch(`${SERVER}/scheduled/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!open) {
      setDetail(null);
      return;
    }
    fetch(`${SERVER}/sessions/${open.kind}/${open.id}`)
      .then((r) => r.json())
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [open]);

  return (
    <div className="flex flex-col flex-1 items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-1 w-full max-w-7xl flex-col py-12 px-6 sm:py-16 sm:px-10">
        <header className="mb-8 flex items-start justify-between gap-6">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Bol Do · sessions</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
              Dashboard
            </h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              All calls and debug chats stored on the backend. Auto-refreshes every 5s.
            </p>
          </div>
          <Link
            href="/"
            className="shrink-0 rounded-full border border-zinc-300 px-4 py-1.5 text-xs font-medium text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-100"
          >
            ← New call
          </Link>
        </header>

        <div className="mb-4 flex gap-2">
          {(["calls", "chats", "scheduled"] as const).map((t) => {
            const count =
              t === "calls"
                ? index.calls.length
                : t === "chats"
                  ? index.chats.length
                  : scheduled.filter((s) => s.status === "pending").length;
            const label = t === "calls" ? "Calls" : t === "chats" ? "Chats" : "Scheduled";
            return (
              <button
                key={t}
                onClick={() => {
                  setTab(t);
                  setOpen(null);
                }}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                  tab === t
                    ? "bg-black text-white dark:bg-zinc-100 dark:text-black"
                    : "border border-zinc-300 text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300"
                }`}
              >
                {label} ({count})
              </button>
            );
          })}
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {error}
          </div>
        )}

        {tab === "scheduled" ? (
          <ScheduledList items={scheduled} onCancel={cancelScheduled} />
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {(tab === "calls" ? index.calls : index.chats).length === 0 && (
                  <li className="px-2 py-6 text-center text-sm text-zinc-400">
                    No {tab} yet.
                  </li>
                )}
                {(tab === "calls" ? index.calls : index.chats).map((id) => {
                  const active = open?.kind === (tab === "calls" ? "call" : "chat") && open?.id === id;
                  return (
                    <li key={id}>
                      <button
                        onClick={() =>
                          setOpen({ kind: tab === "calls" ? "call" : "chat", id })
                        }
                        className={`block w-full px-3 py-3 text-left font-mono text-sm transition-colors ${
                          active
                            ? "bg-zinc-100 text-black dark:bg-zinc-800 dark:text-zinc-100"
                            : "text-zinc-800 hover:bg-zinc-50 dark:text-zinc-200 dark:hover:bg-zinc-900"
                        }`}
                      >
                        {id}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              {!open && (
                <p className="text-sm text-zinc-400">Select a session to view its transcript.</p>
              )}
              {open && !detail && <p className="text-sm text-zinc-400">Loading…</p>}
              {open && detail && open.kind === "call" && (
                <CallView call={detail as CallDetail} />
              )}
              {open && detail && open.kind === "chat" && (
                <ChatView chat={detail as ChatDetail} />
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function ScheduledList({
  items,
  onCancel,
}: {
  items: Scheduled[];
  onCancel: (id: string) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-400 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        No scheduled calls yet.
      </div>
    );
  }
  const statusColor = (s: Scheduled["status"]) => {
    switch (s) {
      case "pending":
        return "text-amber-600 dark:text-amber-400";
      case "fired":
        return "text-emerald-600 dark:text-emerald-400";
      case "missed":
        return "text-red-600 dark:text-red-400";
      case "cancelled":
        return "text-zinc-500";
    }
  };
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {items.map((s) => (
          <li key={s.id} className="grid grid-cols-[1fr_auto] gap-4 px-2 py-3 text-sm">
            <div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-semibold uppercase tracking-wide ${statusColor(s.status)}`}>
                  {s.status}
                </span>
                <span className="font-mono text-xs text-zinc-500">{s.id}</span>
              </div>
              <div className="mt-1 text-zinc-800 dark:text-zinc-100">
                <span className="font-mono">{s.to_number}</span> · {s.tone} · scheduled{" "}
                <span className="font-mono">{s.scheduled_for}</span>
              </div>
              <div className="mt-1 text-zinc-600 dark:text-zinc-400">{s.task}</div>
              {s.fired_at && (
                <div className="mt-1 text-xs text-zinc-500">
                  fired at {s.fired_at}
                  {s.call_sid && (
                    <>
                      {" · "}
                      <span className="font-mono">{s.call_sid}</span>
                    </>
                  )}
                </div>
              )}
            </div>
            <div className="flex items-start">
              {s.status === "pending" && (
                <button
                  onClick={() => onCancel(s.id)}
                  className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-700 hover:border-red-500 hover:text-red-600 dark:border-zinc-700 dark:text-zinc-300"
                >
                  Cancel
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}


function CallView({ call }: { call: CallDetail }) {
  return (
    <div>
      <div className="mb-4 space-y-1 text-xs text-zinc-500">
        <div>
          <span className="font-semibold text-zinc-600 dark:text-zinc-300">To:</span>{" "}
          <span className="font-mono">{call.meta.to_number ?? "?"}</span>
        </div>
        <div>
          <span className="font-semibold text-zinc-600 dark:text-zinc-300">Task:</span>{" "}
          {call.meta.task ?? "?"}
        </div>
        <div>
          <span className="font-semibold text-zinc-600 dark:text-zinc-300">Tone:</span>{" "}
          {call.meta.tone ?? "?"}
        </div>
      </div>
      <div className="max-h-[60vh] overflow-y-auto rounded-lg bg-zinc-50 p-4 text-sm leading-relaxed dark:bg-zinc-900">
        {call.transcript.length === 0 ? (
          <p className="text-zinc-400">No transcript captured.</p>
        ) : (
          call.transcript.map((line, i) => (
            <div
              key={i}
              className={`my-1.5 flex ${
                line.role === "system"
                  ? "justify-center"
                  : line.role === "agent"
                    ? "justify-start"
                    : "justify-end"
              }`}
            >
              {line.role === "system" ? (
                <span className="text-xs uppercase tracking-wide text-zinc-400">
                  — {line.text} —
                </span>
              ) : (
                <div
                  className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                    line.role === "agent"
                      ? "bg-white text-zinc-900 ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-zinc-700"
                      : "bg-black text-white dark:bg-zinc-100 dark:text-black"
                  }`}
                >
                  <div className="mb-0.5 text-[10px] uppercase tracking-wide opacity-60">
                    {line.role === "agent" ? "Bol Do" : "Callee"}
                  </div>
                  <div>{line.text}</div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ChatView({ chat }: { chat: ChatDetail }) {
  return (
    <div>
      <div className="mb-4 space-y-1 text-xs text-zinc-500">
        <div>
          <span className="font-semibold text-zinc-600 dark:text-zinc-300">Task:</span>{" "}
          {chat.task}
        </div>
        <div>
          <span className="font-semibold text-zinc-600 dark:text-zinc-300">Tone:</span>{" "}
          {chat.tone}
        </div>
      </div>
      <div className="max-h-[60vh] overflow-y-auto rounded-lg bg-zinc-50 p-4 text-sm leading-relaxed dark:bg-zinc-900">
        {chat.history.length === 0 ? (
          <p className="text-zinc-400">No turns yet.</p>
        ) : (
          chat.history.map((line, i) => (
            <div
              key={i}
              className={`my-1.5 flex ${
                line.role === "model" ? "justify-start" : "justify-end"
              }`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                  line.role === "model"
                    ? "bg-white text-zinc-900 ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-zinc-700"
                    : "bg-black text-white dark:bg-zinc-100 dark:text-black"
                }`}
              >
                <div className="mb-0.5 text-[10px] uppercase tracking-wide opacity-60">
                  {line.role === "model" ? "Bol Do" : "You"}
                </div>
                <div>{line.content}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
