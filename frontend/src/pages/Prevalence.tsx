import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BarChart3, TableIcon } from "lucide-react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { Discordance, DiscordanceItem } from "../api/types";
import { CHART, QUADRANT_COLORS } from "../components/charts";
import { AsyncBlock, Card, Disclaimer, PageHeader, RoleBadge, ScorePill, Select, Table } from "../components/ui";
import { formatFrequency, humanize, QUADRANT_ORDER } from "../lib/format";
import { useApi } from "../lib/useApi";

interface Point extends DiscordanceItem {
  pct: number;
}

/** Dot marker: >= 12px, 2px surface ring so overlapping points stay separable; hollow = gene-level upper bound. */
function Dot(props: { cx?: number; cy?: number; payload?: Point }) {
  const { cx = 0, cy = 0, payload } = props;
  if (!payload) return null;
  const color = QUADRANT_COLORS[payload.quadrant];
  return payload.upper_bound ? (
    <circle cx={cx} cy={cy} r={6} fill="#ffffff" stroke={color} strokeWidth={2.5} />
  ) : (
    <circle cx={cx} cy={cy} r={6.5} fill={color} stroke="#ffffff" strokeWidth={2} />
  );
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="max-w-xs rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md">
      <div className="font-medium text-slate-900">{p.biomarker_name}</div>
      <div className="text-slate-600">{p.cancer_name} · {humanize(p.biomarker_role)}</div>
      <div className="tabular mt-1 text-slate-700">
        TCGA {p.upper_bound ? "≤ " : ""}{formatFrequency(p.frequency)} ({p.altered_cases}/{p.profiled_cases}) · score {p.overall_score.toFixed(1)}
      </div>
      <div className="text-slate-500">{humanize(p.quadrant)}</div>
    </div>
  );
}

export function quadrantPoints(items: DiscordanceItem[]): Record<string, Point[]> {
  const out: Record<string, Point[]> = {};
  for (const q of QUADRANT_ORDER) out[q] = [];
  for (const it of items) out[it.quadrant].push({ ...it, pct: Math.max(0.5, it.frequency * 100) });
  return out;
}

export default function Prevalence() {
  const [params, setParams] = useSearchParams();
  const score = params.get("score") ?? "75";
  const common = params.get("common") ?? "0.1";
  const focus = params.get("quadrant") ?? "";
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  const state = useApi<Discordance>("/prevalence/discordance", { score_threshold: score, common_threshold: common });
  const [asTable, setAsTable] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="space-y-5">
      <PageHeader title="Evidence vs Prevalence"
        subtitle="Each point is a biomarker-cancer association: how common the defining alteration is in tumours (TCGA, x-axis) against how well it is supported by the evidence recorded here (y-axis). Common alterations with thin evidence are where curation effort matters most." />

      <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-4">
        <Select label="Well supported if score ≥" value={score} onChange={(v) => set("score", v)} allLabel={null}
          options={["60", "65", "70", "75", "80", "85"].map((v) => ({ value: v, label: v }))} />
        <Select label="Common if frequency ≥" value={common} onChange={(v) => set("common", v)} allLabel={null}
          options={[["0.05", "5%"], ["0.1", "10%"], ["0.2", "20%"]].map(([v, l]) => ({ value: v, label: l }))} />
      </div>

      <AsyncBlock state={state}>
        {(d) => {
          const groups = quadrantPoints(d.items);
          const rows = focus ? d.items.filter((i) => i.quadrant === focus) : d.items;
          return (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {QUADRANT_ORDER.map((q) => (
                  <button key={q} onClick={() => set("quadrant", focus === q ? "" : q)} aria-pressed={focus === q}
                    title={d.quadrant_descriptions[q]}
                    className={`rounded-xl border bg-white p-3 text-left shadow-sm transition ${focus === q ? "border-teal-brand ring-2 ring-teal-brand/30" : "border-slate-200 hover:border-navy-200"}`}>
                    <div className="flex items-center gap-2">
                      <span className="inline-block h-3 w-3 rounded-full" style={{ background: QUADRANT_COLORS[q] }} aria-hidden />
                      <span className="tabular text-xl font-semibold text-navy-900">{d.quadrant_counts[q]}</span>
                    </div>
                    <div className="text-xs font-medium text-slate-600">{humanize(q)}</div>
                  </button>
                ))}
              </div>

              <Card title={`${d.n_plotted} associations with both a score and a TCGA frequency`}
                actions={<button onClick={() => setAsTable((t) => !t)} aria-pressed={asTable}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100">
                  {asTable ? <BarChart3 className="h-3.5 w-3.5" aria-hidden /> : <TableIcon className="h-3.5 w-3.5" aria-hidden />}
                  {asTable ? "Chart" : "Table"}</button>}>
                {asTable ? (
                  <Table head={["Association", "Role", "TCGA frequency", "Score", "Quadrant"]} caption="Evidence versus prevalence">
                    {rows.map((r) => (
                      <tr key={r.association_id} className="hover:bg-slate-50">
                        <td className="px-3 py-1.5"><Link to={`/associations/${r.association_id}`} className="font-medium text-navy-700 hover:underline">{r.biomarker_name}</Link>
                          <div className="text-xs text-slate-500">{r.cancer_name}</div></td>
                        <td className="px-3 py-1.5"><RoleBadge role={r.biomarker_role} /></td>
                        <td className="tabular px-3 py-1.5">{r.upper_bound ? "≤ " : ""}{formatFrequency(r.frequency)}</td>
                        <td className="px-3 py-1.5"><ScorePill score={r.overall_score} status={r.score_status} /></td>
                        <td className="px-3 py-1.5 text-xs">{humanize(r.quadrant)}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={430}>
                      <ScatterChart margin={{ top: 12, right: 24, bottom: 28, left: 4 }}>
                        <CartesianGrid stroke={CHART.grid} />
                        <XAxis type="number" dataKey="pct" scale="log" domain={[0.5, 100]} ticks={[1, 2, 5, 10, 20, 50, 100]}
                          allowDataOverflow tickFormatter={(v: number) => `${v}%`} tick={{ fill: CHART.axis, fontSize: 11 }}
                          axisLine={{ stroke: CHART.grid }} tickLine={false}
                          label={{ value: "Tumours with the alteration (TCGA, log scale)", position: "insideBottom", offset: -16, fill: "#52514e", fontSize: 12 }} />
                        <YAxis type="number" dataKey="overall_score" domain={[40, 100]} tick={{ fill: CHART.axis, fontSize: 11 }}
                          axisLine={false} tickLine={false}
                          label={{ value: "Evidence-support score", angle: -90, position: "insideLeft", offset: 14, fill: "#52514e", fontSize: 12 }} />
                        <ReferenceLine x={Number(common) * 100} stroke={CHART.axis} strokeDasharray="4 4" />
                        <ReferenceLine y={Number(score)} stroke={CHART.axis} strokeDasharray="4 4" />
                        <Tooltip content={<PointTooltip />} cursor={{ strokeDasharray: "3 3", stroke: CHART.axis }} />
                        {QUADRANT_ORDER.map((q) => (
                          <Scatter key={q} name={humanize(q)} data={groups[q].filter(() => !focus || focus === q)} isAnimationActive={false}
                            shape={<Dot />} cursor="pointer"
                            onClick={(p) => navigate(`/associations/${(p as unknown as Point).association_id}`)} />
                        ))}
                      </ScatterChart>
                    </ResponsiveContainer>
                    <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600" aria-label="Legend">
                      {QUADRANT_ORDER.map((q) => (
                        <li key={q} className="inline-flex items-center gap-1.5">
                          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: QUADRANT_COLORS[q] }} aria-hidden />{humanize(q)}
                        </li>
                      ))}
                      <li className="inline-flex items-center gap-1.5">
                        <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-slate-500 bg-white" aria-hidden />
                        Hollow: gene-level frequency, an upper bound for the specific variant
                      </li>
                      <li>Dashed lines: thresholds · click a point to open its evidence</li>
                    </ul>
                  </>
                )}
              </Card>

              <Card title="How to read this">
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {d.caveats.map((c) => <li key={c}>{c}</li>)}
                  <li>{d.n_not_applicable} associations are not plotted because no gene-level TCGA frequency applies to them.</li>
                </ul>
              </Card>
              <Disclaimer />
            </>
          );
        }}
      </AsyncBlock>
    </div>
  );
}
