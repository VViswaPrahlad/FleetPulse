import type { ReactNode } from "react";
import { AlertCircle, ArrowLeft, ArrowRight, RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { query, useApi, type Page, type Trend } from "./api";
import { useState } from "react";

export const number = (value: number | null | undefined, digits = 0) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(
        value,
      );
export const compact = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
export const human = (name: string) =>
  name.replace(/^past_/, "").replace(/_/g, " ");
export const tooltipStyle = {
  background: "#182231",
  border: "1px solid #354252",
  borderRadius: 12,
  color: "#eaf1fa",
};
export const colors = ["#59dfbc", "#78a9ff", "#eebd72", "#bfa2ef", "#ed8599"];
export function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Kpi({
  label,
  value,
  unit,
  note,
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  note: string;
  icon: ReactNode;
}) {
  return (
    <div className="kpi">
      <div className="kpi-top">
        <span>{label}</span>
        <span className="kpi-icon">{icon}</span>
      </div>
      <div className="kpi-value">
        {value}
        <small>{unit}</small>
      </div>
      <p>{note}</p>
    </div>
  );
}
export function State({
  loading,
  error,
  retry,
  empty = false,
  children,
}: {
  loading: boolean;
  error?: string;
  retry: () => void;
  empty?: boolean;
  children?: ReactNode;
}) {
  if (loading)
    return (
      <div className="loading" role="status" aria-label="Loading API data">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton" />
        <p>Reading local analytics…</p>
      </div>
    );
  if (error)
    return (
      <div className="state error" role="alert">
        <AlertCircle size={24} />
        <h3>Data unavailable</h3>
        <p>{error}</p>
        <button onClick={retry} className="button secondary">
          <RefreshCw size={15} />
          Retry request
        </button>
      </div>
    );
  if (empty)
    return (
      <div className="state">
        <h3>No matching records</h3>
        <p>Try another filter or date range.</p>
      </div>
    );
  return <>{children}</>;
}
export function Pagination({
  total,
  offset,
  limit,
  change,
}: {
  total: number;
  offset: number;
  limit: number;
  change: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${number(offset + 1)}–${number(Math.min(offset + limit, total))} of ${number(total)}`
          : "0 results"}
      </span>
      <div>
        <button
          aria-label="Previous page"
          disabled={offset === 0}
          onClick={() => change(Math.max(0, offset - limit))}
        >
          <ArrowLeft size={16} />
          Previous
        </button>
        <button
          aria-label="Next page"
          disabled={offset + limit >= total || offset + limit > 100000}
          onClick={() => change(offset + limit)}
        >
          Next
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function Trends({
  title = "Fleet activity",
  compactView = false,
}: {
  title?: string;
  compactView?: boolean;
}) {
  const [period, setPeriod] = useState("monthly"),
    [offset, setOffset] = useState(0),
    [start, setStart] = useState(""),
    [end, setEnd] = useState("");
  const invalid = !!(start && end && start > end);
  const data = useApi<Page<Trend>>(
    query("/trends/" + period, {
      limit: 100,
      offset,
      start_date: invalid ? undefined : start,
      end_date: invalid ? undefined : end,
    }),
  );
  const rows = (data.data?.items ?? []).map((row) => ({
    date: row.trip_start_reference_month ?? row.trip_start_reference_day,
    observations: row.observation_count,
    trips: row.trip_count,
  }));
  return (
    <Panel
      title={title}
      subtitle="Whole trips grouped by dataset-reference start date; timezone unspecified."
      action={
        <div className="segmented">
          {["monthly", "daily"].map((p) => (
            <button
              key={p}
              aria-pressed={p === period}
              onClick={() => {
                setPeriod(p);
                setOffset(0);
              }}
            >
              {p === "monthly" ? "Monthly" : "Daily"}
            </button>
          ))}
        </div>
      }
    >
      {!compactView && (
        <div className="filters">
          <label>
            From
            <input
              type="date"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <button
            className="button secondary"
            onClick={() => {
              setStart("");
              setEnd("");
              setOffset(0);
            }}
          >
            Clear dates
          </button>
          {period === "monthly" && (
            <span className="muted">
              Dates filter stored month-start dates.
            </span>
          )}
        </div>
      )}
      {invalid ? (
        <p role="alert" className="notice">
          Start date must not be after end date.
        </p>
      ) : (
        <State {...data} empty={rows.length === 0}>
          <div
            className="chart"
            role="img"
            aria-label={`${period} observation counts for ${rows.length} date cohorts`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={rows}
                margin={{ left: 0, right: 14, top: 15, bottom: 4 }}
              >
                <defs>
                  <linearGradient
                    id={"activity-" + title.replace(/ /g, "")}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor={colors[0]}
                      stopOpacity={0.25}
                    />
                    <stop offset="100%" stopColor={colors[0]} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#263142" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#8593a7"
                  fontSize={11}
                  minTickGap={32}
                  tickFormatter={(v) =>
                    String(v).slice(0, period === "monthly" ? 7 : 10)
                  }
                />
                <YAxis
                  stroke="#8593a7"
                  fontSize={11}
                  tickFormatter={compact}
                  width={48}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v) => number(Number(v))}
                />
                <Area
                  dataKey="observations"
                  name="Observations"
                  type="monotone"
                  stroke={colors[0]}
                  fill={`url(#activity-${title.replace(/ /g, "")})`}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <Pagination
            total={data.data?.total ?? 0}
            offset={offset}
            limit={100}
            change={setOffset}
          />
          <details className="chart-data">
            <summary>View chart data</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Reference date</th>
                    <th>Observations</th>
                    <th>Trips</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{number(row.observations)}</td>
                      <td>{number(row.trips)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </State>
      )}
    </Panel>
  );
}
