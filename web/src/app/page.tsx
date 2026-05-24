import Link from "next/link";
import { CallConsole } from "./call-console";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-1 w-full max-w-7xl flex-col py-12 px-6 sm:py-20 sm:px-10">
        <header className="mb-10 flex items-start justify-between gap-6">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Bol Do · Silk 1 hackathon
            </div>
            <h1 className="mt-2 text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
              Type the call. I&apos;ll make it.
            </h1>
            <p className="mt-3 max-w-xl text-base leading-relaxed text-zinc-600 dark:text-zinc-400">
              Bol Do places real phone calls on your behalf and talks like a human in
              Hinglish. You watch the conversation live and get a summary at the end.
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Link
              href="/architecture"
              className="rounded-full border border-zinc-300 px-4 py-1.5 text-xs font-medium text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-100"
            >
              Architecture
            </Link>
            <Link
              href="/dashboard"
              className="rounded-full border border-zinc-300 px-4 py-1.5 text-xs font-medium text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-100"
            >
              Dashboard →
            </Link>
          </div>
        </header>
        <CallConsole />
      </main>
    </div>
  );
}
