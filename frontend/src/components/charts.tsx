import { useState, type ReactNode } from "react";
import { BarChart3, TableIcon } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, EmptyState } from "./ui";

// Chart tokens (reference palette, light mode): single-series bars use one hue.
export const CHART = {
  series: "#2a78d6",
  seriesHover: "#1c5cab",
  muted: "#94a3b8",
  grid: "#e1e0d9",
  axis: "#898781",
  ink: "#0b0b0b",
};

// Evidence-vs-prevalence quadrants: three categorical slots (blue, orange, aqua; validated all-pairs for a scatter,
// worst CVD dE 9.2) plus muted grey as the folded fourth group. Position and the legend also carry identity.
export const QUADRANT_COLORS: Record<string, string> = {
  established: "#2a78d6",
  under_curated: "#eb6834",
  niche_supported: "#1baf7a",
  rare_thin: "#94a3b8",
};

export interface Datum {
  label: string;
  value: number;
  id?: number | string;
  muted?: boolean;
}

/** Card that can switch between a chart and an accessible table of the same data. */
export function ChartCard({ title, data, valueLabel, children, actions }: {
  title: string; data: Datum[]; valueLabel: string; children: ReactNode; actions?: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const toggle = (
    <div className="flex items-center gap-2">
      {actions}
      <button
        onClick={() => setAsTable((t) => !t)}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        aria-pressed={asTable}
      >
        {asTable ? <BarChart3 className="h-3.5 w-3.5" aria-hidden /> : <TableIcon className="h-3.5 w-3.5" aria-hidden />}
        {asTable ? "Chart" : "Table"}
      </button>
    </div>
  );
  return (
    <Card title={title} actions={toggle}>
      {data.length === 0 ? (
        <EmptyState message="No data for the current filters." />
      ) : asTable ? (
        <table className="w-full text-sm">
          <caption className="sr-only">{title}</caption>
          <thead><tr className="text-left text-xs uppercase text-slate-500">
            <th className="py-1">Category</th><th className="py-1 text-right">{valueLabel}</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((d) => (
              <tr key={d.label}><td className="py-1">{d.label}</td><td className="tabular py-1 text-right">{d.value}</td></tr>
            ))}
          </tbody>
        </table>
      ) : children}
    </Card>
  );
}

function TooltipBox({ active, payload, valueLabel }: { active?: boolean; payload?: { payload: Datum }[]; valueLabel: string }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md">
      <div className="font-medium text-slate-900">{d.label}</div>
      <div className="tabular text-slate-600">{valueLabel}: {d.value}</div>
    </div>
  );
}

/** Horizontal single-series bar chart; one hue, thin bars, rounded data end. */
export function HBar({ data, valueLabel, onSelect, height }: {
  data: Datum[]; valueLabel: string; onSelect?: (d: Datum) => void; height?: number;
}) {
  const h = height ?? Math.max(160, data.length * 30 + 30);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={CHART.grid} />
        <XAxis type="number" allowDecimals={false} tick={{ fill: CHART.axis, fontSize: 11 }} axisLine={{ stroke: CHART.grid }} tickLine={false} />
        <YAxis type="category" dataKey="label" width={150} tick={{ fill: "#334155", fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip cursor={{ fill: "rgba(42,120,214,0.08)" }} content={<TooltipBox valueLabel={valueLabel} />} />
        <Bar isAnimationActive={false} dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={18}
          onClick={(d) => onSelect?.(d as unknown as Datum)} cursor={onSelect ? "pointer" : undefined}>
          {data.map((d) => <Cell key={d.label} fill={d.muted ? CHART.muted : CHART.series} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Vertical single-series bar chart (used for score histograms). */
export function VBar({ data, valueLabel, height = 220 }: { data: Datum[]; valueLabel: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -16 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={CHART.grid} />
        <XAxis dataKey="label" tick={{ fill: CHART.axis, fontSize: 10 }} axisLine={{ stroke: "#c3c2b7" }} tickLine={false} interval={0} />
        <YAxis allowDecimals={false} tick={{ fill: CHART.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip cursor={{ fill: "rgba(42,120,214,0.08)" }} content={<TooltipBox valueLabel={valueLabel} />} />
        <Bar isAnimationActive={false} dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
          {data.map((d) => <Cell key={d.label} fill={d.muted ? CHART.muted : CHART.series} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function histogramData(bins: { bin: string; count: number; lower: number | null }[]): Datum[] {
  return bins.map((b) => ({ label: b.lower === null ? "n/a" : b.bin, value: b.count, muted: b.lower === null }));
}
