import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { NetworkData, NetworkNode } from "../api/types";

// Identity is carried by shape + text label + legend; colour is a secondary cue.
const TYPE_STYLE: Record<NetworkNode["type"], { color: string; shape: "circle" | "square" | "diamond" | "triangle"; label: string }> = {
  biomarker: { color: "#12305a", shape: "circle", label: "Biomarker" },
  cancer: { color: "#e34948", shape: "square", label: "Cancer" },
  gene: { color: "#2a78d6", shape: "circle", label: "Gene" },
  protein: { color: "#1baf7a", shape: "diamond", label: "Protein" },
  pathway: { color: "#6250d6", shape: "triangle", label: "Pathway" },
  publication: { color: "#898781", shape: "square", label: "Publication" },
  variant: { color: "#eb6834", shape: "diamond", label: "Variant" },
};

export function routeFor(n: NetworkNode): string {
  switch (n.type) {
    case "biomarker": return `/biomarkers/${n.entity_id}`;
    case "cancer": return `/cancers/${n.entity_id}`;
    case "gene": return `/genes/${n.entity_id}`;
    case "protein": return `/proteins/${n.entity_id}`;
    case "pathway": return `/pathways/${n.entity_id}`;
    case "variant": return `/variants/${n.entity_id}`;
    case "publication": return `/publications?q=${encodeURIComponent(n.label.replace("PMID ", ""))}`;
  }
}

interface Pos { x: number; y: number }

/** Deterministic force-directed layout (no randomness: same data -> same picture). */
export function layout(data: NetworkData, width: number, height: number): Record<string, Pos> {
  const n = data.nodes.length;
  const pos: Record<string, Pos> = {};
  data.nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(n, 1);
    const r = i === 0 ? 0 : Math.min(width, height) * 0.35;
    pos[node.id] = { x: width / 2 + r * Math.cos(angle), y: height / 2 + r * Math.sin(angle) };
  });
  const k = Math.sqrt((width * height) / Math.max(n, 1)) * 0.75;
  for (let iter = 0; iter < 300; iter++) {
    const disp: Record<string, Pos> = {};
    for (const a of data.nodes) disp[a.id] = { x: 0, y: 0 };
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = pos[data.nodes[i].id], b = pos[data.nodes[j].id];
        let dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (k * k) / d;
        dx /= d; dy /= d;
        disp[data.nodes[i].id].x += dx * f; disp[data.nodes[i].id].y += dy * f;
        disp[data.nodes[j].id].x -= dx * f; disp[data.nodes[j].id].y -= dy * f;
      }
    }
    for (const e of data.edges) {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = (d * d) / k;
      disp[e.source].x -= (dx / d) * f; disp[e.source].y -= (dy / d) * f;
      disp[e.target].x += (dx / d) * f; disp[e.target].y += (dy / d) * f;
    }
    const temp = 40 * (1 - iter / 300) + 1;
    data.nodes.forEach((node, i) => {
      if (i === 0) return; // keep the focus entity centred
      const d = disp[node.id];
      const len = Math.max(Math.hypot(d.x, d.y), 0.01);
      const p = pos[node.id];
      p.x = Math.min(width - 60, Math.max(60, p.x + (d.x / len) * Math.min(len, temp)));
      p.y = Math.min(height - 24, Math.max(24, p.y + (d.y / len) * Math.min(len, temp)));
    });
  }
  return pos;
}

function Shape({ shape, color, size, focus }: { shape: string; color: string; size: number; focus: boolean }) {
  const stroke = { stroke: "#ffffff", strokeWidth: 2 };
  const ring = focus ? <circle r={size + 4} fill="none" stroke={color} strokeWidth={2} /> : null;
  if (shape === "square") return <>{ring}<rect x={-size} y={-size} width={size * 2} height={size * 2} rx={2} fill={color} {...stroke} /></>;
  if (shape === "diamond") return <>{ring}<polygon points={`0,${-size - 2} ${size + 2},0 0,${size + 2} ${-size - 2},0`} fill={color} {...stroke} /></>;
  if (shape === "triangle") return <>{ring}<polygon points={`0,${-size - 2} ${size + 2},${size} ${-size - 2},${size}`} fill={color} {...stroke} /></>;
  return <>{ring}<circle r={size} fill={color} {...stroke} /></>;
}

export function NetworkGraph({ data, height = 460 }: { data: NetworkData; height?: number }) {
  const width = 900;
  const navigate = useNavigate();
  const [hover, setHover] = useState<string | null>(null);
  const pos = useMemo(() => layout(data, width, height), [data, height]);
  const neighbours = useMemo(() => {
    if (!hover) return null;
    const s = new Set([hover]);
    data.edges.forEach((e) => { if (e.source === hover) s.add(e.target); if (e.target === hover) s.add(e.source); });
    return s;
  }, [hover, data.edges]);
  const types = Array.from(new Set(data.nodes.map((n) => n.type)));

  return (
    <div>
      <ul className="mb-2 flex flex-wrap gap-3 text-xs text-slate-600" aria-label="Legend">
        {types.map((t) => (
          <li key={t} className="flex items-center gap-1">
            <svg width="14" height="14" viewBox="-8 -8 16 16" aria-hidden><Shape shape={TYPE_STYLE[t].shape} color={TYPE_STYLE[t].color} size={5} focus={false} /></svg>
            {TYPE_STYLE[t].label}
          </li>
        ))}
        <li className="text-slate-400">· click a node to open it · edges are database relationships</li>
      </ul>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full rounded-lg border border-slate-100 bg-[#fcfcfb]"
        role="img" aria-label={`Relationship network with ${data.nodes.length} entities and ${data.edges.length} links`}>
        {data.edges.map((e, i) => {
          const a = pos[e.source], b = pos[e.target];
          if (!a || !b) return null;
          const dim = neighbours && !(neighbours.has(e.source) && neighbours.has(e.target));
          return (
            <g key={i} opacity={dim ? 0.12 : 1}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#c3c2b7" strokeWidth={1.5} />
              {hover && !dim && (
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 3} fontSize={10} textAnchor="middle" fill="#52514e">{e.label}</text>
              )}
            </g>
          );
        })}
        {data.nodes.map((n, i) => {
          const p = pos[n.id];
          const st = TYPE_STYLE[n.type];
          const dim = neighbours && !neighbours.has(n.id);
          // Pathway nodes drop the "(hsa…)" identifier and all non-focus labels are shortened to limit collisions;
          // the full label stays in the tooltip and the accessible name.
          const base = n.type === "pathway" ? n.label.replace(/\s*\([^)]*\)$/, "") : n.label;
          const max = i === 0 ? 32 : 20;
          const label = base.length > max ? `${base.slice(0, max - 1)}…` : base;
          // Publication nodes cluster tightly; their labels appear on hover/focus to avoid collisions.
          const showLabel = n.type !== "publication" || hover === n.id;
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.2 : 1} style={{ cursor: "pointer" }}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
              onClick={() => navigate(routeFor(n))}
              onKeyDown={(ev) => { if (ev.key === "Enter") navigate(routeFor(n)); }}
              tabIndex={0} role="link" aria-label={`${st.label}: ${n.label}`}>
              <circle r={16} fill="transparent" />
              <Shape shape={st.shape} color={st.color} size={i === 0 ? 10 : 7} focus={i === 0} />
              <title>{`${st.label}: ${n.label}`}</title>
              {showLabel && <text y={i === 0 ? 26 : 20} fontSize={i === 0 ? 13 : 11} fontWeight={i === 0 ? 600 : 400} textAnchor="middle"
                fill="#0b0b0b" stroke="#fcfcfb" strokeWidth={3} paintOrder="stroke">{label}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
