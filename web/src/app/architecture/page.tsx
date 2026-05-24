import Link from "next/link";

export default function ArchitecturePage() {
  return (
    <div className="flex flex-col flex-1 items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-1 w-full max-w-7xl flex-col py-12 px-6 sm:py-16 sm:px-10">
        <header className="mb-8 flex items-start justify-between gap-6">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Bol Do · how it works
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
              Architecture
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
              You type a task. Bol Do dials a real phone, has a Hinglish conversation, and emails
              you the summary. Here is what happens behind the scenes.
            </p>
          </div>
          <Link
            href="/"
            className="shrink-0 rounded-full border border-zinc-300 px-4 py-1.5 text-xs font-medium text-zinc-700 hover:border-black dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-100"
          >
            ← New call
          </Link>
        </header>

        {/* Visual diagram */}
        <ArchitectureDiagram />
      </main>
    </div>
  );
}

/* ---------- inline SVG diagram ---------- */

function ArchitectureDiagram() {
  // Clip-art / hand-drawn style — black borders, drop shadows, bright fills.
  // Always rendered on a white background regardless of dark mode.
  return (
    <div className="overflow-x-auto rounded-2xl border border-zinc-300 bg-white p-6 shadow-sm">
      <svg
        viewBox="0 0 1100 720"
        xmlns="http://www.w3.org/2000/svg"
        className="mx-auto block h-auto w-full max-w-[1100px]"
        fontFamily="sans-serif"
      >
        <defs>
          <filter id="shadow" x="-15%" y="-15%" width="130%" height="130%">
            <feDropShadow dx="3" dy="3" stdDeviation="2" floodOpacity="0.35" />
          </filter>
          <marker
            id="arrowK"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#000" />
          </marker>
        </defs>

        {/* Dashed system boundary */}
        <rect
          x={80}
          y={40}
          width={1000}
          height={530}
          rx={6}
          fill="none"
          stroke="#888"
          strokeDasharray="6 4"
          strokeWidth={1.4}
        />

        {/* USER stick figure (outside boundary, left) */}
        <Stick x={20} y={170} label="USER" />

        {/* Inside system: row 1 — Browser → Frontend → Backend */}
        <ClipBox x={110} y={170} w={130} h={70} fill="#E53935" textFill="#fff" lines={["BROWSER"]} />
        <ClipBox x={290} y={170} w={170} h={70} fill="#F4A98C" lines={["FRONTEND", "(NEXT.JS)"]} />
        <ClipBox x={520} y={210} w={210} h={90} fill="#FFE825" lines={["BACKEND", "(FASTAPI + PIPECAT)"]} bold />

        {/* DATABASE cylinder — sessions */}
        <Cylinder cx={620} cy={90} rx={110} h={55} fill="#C97B95" lines={["SESSIONS / TRANSCRIPTS"]} />

        {/* SERVER RACK with 3 nodes — in-call AI pipeline */}
        <Rack x={800} y={70} w={250} h={300}>
          <RackNode y={90} label="DEEPGRAM (STT)" />
          <RackNode y={170} label="GEMINI (LLM)" />
          <RackNode y={250} label="SILK 1 (TTS)" />
        </Rack>

        {/* TWILIO — orange box, off to the right side under rack */}
        <ClipBox x={830} y={400} w={170} h={70} fill="#FB8C00" textFill="#fff" lines={["TWILIO"]} />

        {/* CALLEE stick figure (outside boundary, right) */}
        <Stick x={1050} y={400} label="CALLEE" mirror />

        {/* Bottom row — Side effects */}
        <ClipBox x={300} y={460} w={200} h={80} fill="#B7C8B5" lines={["GMAIL SMTP", "(EMAIL REPORT)"]} />
        <ClipBox x={560} y={460} w={200} h={80} fill="#B7C8B5" lines={["SCHEDULER", "(QUEUED CALLS)"]} />

        {/* Arrows */}
        {/* USER → BROWSER */}
        <SvgArrow d={`M 90 195 L 110 195`} />
        {/* BROWSER → FRONTEND */}
        <SvgArrow d={`M 240 205 L 290 205`} />
        {/* FRONTEND ↔ BACKEND */}
        <SvgArrow d={`M 460 195 L 520 240`} label="POST /dialout" labelOffset={[-90, -8]} />
        <SvgArrow d={`M 520 270 L 460 220`} label="WS /transcript" labelOffset={[-100, 14]} />
        {/* BACKEND → DATABASE (up) */}
        <SvgArrow d={`M 625 210 L 620 140`} label="save" labelOffset={[8, -10]} />
        {/* BACKEND → RACK (right) — for AI services */}
        <SvgArrow d={`M 730 240 L 800 240`} label="STT / LLM / TTS" labelOffset={[-25, -8]} />
        {/* BACKEND → TWILIO (down-right) */}
        <SvgArrow d={`M 700 290 Q 800 360 830 430`} label="dial · audio WS" labelOffset={[-30, -15]} />
        {/* TWILIO → CALLEE (right) */}
        <SvgArrow d={`M 1000 435 L 1050 435`} label="voice" labelOffset={[-20, -6]} />
        {/* CALLEE → TWILIO (back) */}
        <SvgArrow d={`M 1050 460 L 1000 460`} />
        {/* BACKEND → GMAIL (down-left) */}
        <SvgArrow d={`M 560 300 Q 480 370 400 460`} label="on end" labelOffset={[-20, -10]} />
        {/* BACKEND → SCHEDULER (down) */}
        <SvgArrow d={`M 680 300 Q 670 380 660 460`} label="fires" labelOffset={[8, -10]} />

        {/* Title at bottom */}
        <text
          x={550}
          y={650}
          textAnchor="middle"
          fontSize={18}
          fill="#1976D2"
          fontStyle="italic"
        >
          BOL DO · ARCHITECTURE DIAGRAM
        </text>
      </svg>
    </div>
  );
}

/* ---- clip-art primitives ---- */

function ClipBox({
  x,
  y,
  w,
  h,
  fill,
  textFill = "#000",
  lines,
  bold,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
  textFill?: string;
  lines: string[];
  bold?: boolean;
}) {
  const lh = 14;
  const startY = y + h / 2 - ((lines.length - 1) * lh) / 2 + 4;
  return (
    <g filter="url(#shadow)">
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        fill={fill}
        stroke="#000"
        strokeWidth={1.5}
        rx={3}
      />
      {lines.map((ln, i) => (
        <text
          key={i}
          x={x + w / 2}
          y={startY + i * lh}
          textAnchor="middle"
          fontSize={12}
          fontWeight={bold ? 700 : 600}
          fill={textFill}
        >
          {ln}
        </text>
      ))}
    </g>
  );
}

function Cylinder({
  cx,
  cy,
  rx,
  h,
  fill,
  lines,
}: {
  cx: number;
  cy: number;
  rx: number;
  h: number;
  fill: string;
  lines: string[];
}) {
  const top = cy - h / 2;
  const bot = cy + h / 2;
  return (
    <g filter="url(#shadow)">
      {/* body */}
      <path
        d={`M ${cx - rx} ${top} L ${cx - rx} ${bot} A ${rx} 10 0 0 0 ${cx + rx} ${bot} L ${cx + rx} ${top}`}
        fill={fill}
        stroke="#000"
        strokeWidth={1.5}
      />
      {/* top ellipse */}
      <ellipse cx={cx} cy={top} rx={rx} ry={10} fill={fill} stroke="#000" strokeWidth={1.5} />
      {lines.map((ln, i) => (
        <text
          key={i}
          x={cx}
          y={cy + i * 14}
          textAnchor="middle"
          fontSize={12}
          fontWeight={600}
          fill="#fff"
        >
          {ln}
        </text>
      ))}
    </g>
  );
}

function Rack({
  x,
  y,
  w,
  h,
  children,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  children: React.ReactNode;
}) {
  return (
    <g filter="url(#shadow)">
      <rect x={x} y={y} width={w} height={h} fill="#F0F0F0" stroke="#000" strokeWidth={1.5} rx={4} />
      <g transform={`translate(${x}, ${y})`}>{children}</g>
    </g>
  );
}

function RackNode({ y, label }: { y: number; label: string }) {
  // Drawn relative to the rack origin
  return (
    <g>
      <rect x={25} y={y} width={200} height={60} fill="#fff" stroke="#000" strokeWidth={1.5} rx={2} />
      {/* power LED */}
      <circle cx={210} cy={y + 12} r={3} fill="#4CAF50" stroke="#000" strokeWidth={0.5} />
      <text x={125} y={y + 36} textAnchor="middle" fontSize={12} fontWeight={600}>
        {label}
      </text>
    </g>
  );
}

function Stick({ x, y, label, mirror }: { x: number; y: number; label?: string; mirror?: boolean }) {
  const dir = mirror ? -1 : 1;
  return (
    <g stroke="#000" strokeWidth={1.6} fill="none">
      {/* head */}
      <circle cx={x} cy={y} r={10} />
      {/* body */}
      <line x1={x} y1={y + 10} x2={x} y2={y + 50} />
      {/* arms */}
      <line x1={x} y1={y + 20} x2={x - 14 * dir} y2={y + 35} />
      <line x1={x} y1={y + 20} x2={x + 14 * dir} y2={y + 35} />
      {/* legs */}
      <line x1={x} y1={y + 50} x2={x - 12} y2={y + 75} />
      <line x1={x} y1={y + 50} x2={x + 12} y2={y + 75} />
      {label && (
        <text
          x={x}
          y={y + 95}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill="#000"
          stroke="none"
        >
          {label}
        </text>
      )}
    </g>
  );
}

function SvgArrow({
  d,
  label,
  labelOffset = [0, 0],
}: {
  d: string;
  label?: string;
  labelOffset?: [number, number];
}) {
  // Crude midpoint estimate for label placement: pull the second L/Q xy.
  // Caller passes the offset to nudge.
  const mid = parseMid(d);
  return (
    <g>
      <path d={d} fill="none" stroke="#000" strokeWidth={1.5} markerEnd="url(#arrowK)" />
      {label && mid && (
        <text
          x={mid[0] + labelOffset[0]}
          y={mid[1] + labelOffset[1]}
          fontSize={10}
          fill="#333"
          fontStyle="italic"
        >
          {label}
        </text>
      )}
    </g>
  );
}

function parseMid(d: string): [number, number] | null {
  // Pull all numbers and average x's and y's. Cheap but works for short paths.
  const nums = d.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
  if (nums.length < 4) return null;
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < nums.length - 1; i += 2) {
    xs.push(nums[i]);
    ys.push(nums[i + 1]);
  }
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
  const my = ys.reduce((a, b) => a + b, 0) / ys.length;
  return [mx, my];
}

