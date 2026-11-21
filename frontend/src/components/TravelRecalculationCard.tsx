import { AlertCircle, CheckCircle2, Clock3, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';

type DataRecord = Record<string, any>;

interface Props {
  data: DataRecord;
}

const isRecord = (value: unknown): value is DataRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const record = (...values: unknown[]): DataRecord => {
  for (const value of values) if (isRecord(value)) return value;
  return {};
};

const firstArray = (...values: unknown[]): any[] => {
  let empty: any[] | undefined;
  for (const value of values) {
    if (Array.isArray(value)) {
      if (value.length > 0) return value;
      empty ??= value;
    }
  }
  return empty ?? [];
};

const artifactName = (item: unknown): string => {
  if (typeof item === 'string') return item.replace(/^travel-recalc-/, '').replace(/_/g, ' ');
  if (!isRecord(item)) return '';
  const value = item.artifact ?? item.name ?? item.label ?? item.tool ?? item.id;
  return typeof value === 'string' ? value.replace(/^travel-recalc-/, '').replace(/_/g, ' ') : '';
};

const artifactReason = (item: unknown): string => {
  if (!isRecord(item)) return '';
  const value = item.reason ?? item.blocked_reason ?? item.error ?? item.detail;
  return typeof value === 'string' ? value : '';
};

const pretty = (value: unknown): string =>
  typeof value === 'string' ? value.replace(/_/g, ' ') : 'Status unavailable';

function ArtifactList({ title, items, tone }: { title: string; items: unknown[]; tone: 'success' | 'warning' | 'muted' }) {
  if (!items.length) return null;
  const palette = tone === 'success'
    ? 'text-emerald-300 border-emerald-400/20 bg-emerald-400/[0.06]'
    : tone === 'warning'
      ? 'text-amber-200 border-amber-400/20 bg-amber-400/[0.06]'
      : 'text-jmuted border-jmuted/20 bg-jmuted/[0.04]';
  const Icon = tone === 'success' ? CheckCircle2 : tone === 'warning' ? AlertCircle : Clock3;

  return (
    <section className={`rounded-xl border p-3 ${palette}`}>
      <h5 className="text-[10px] font-bold uppercase tracking-[0.18em] mb-2">{title}</h5>
      <div className="flex flex-col gap-2">
        {items.map((item, index) => {
          const name = artifactName(item) || `Item ${index + 1}`;
          const reason = artifactReason(item);
          return (
            <div key={`${name}-${index}`} className="flex items-start gap-2 text-xs">
              <Icon size={14} className="mt-0.5 shrink-0" />
              <div className="min-w-0">
                <p className="capitalize text-white">{name}</p>
                {reason && <p className="mt-1 text-[11px] text-jmuted leading-relaxed">{reason}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export const TravelRecalculationCard = ({ data }: Props) => {
  if (!isRecord(data)) return null;

  const report = record(data.report, data.recalculation, data);
  const mission = record(data.mission, data.travel_mission);
  const status = report.status ?? data.status ?? data.workflow_status ?? 'received';
  const queue = firstArray(
    data.pending_recalculations,
    mission.pending_recalculations,
    report.pending_recalculations,
  );
  const blocked = firstArray(data.blocked, data.blocked_artifacts, report.blocked, report.blocked_artifacts);
  const pendingExplicit = firstArray(data.pending, data.pending_artifacts, report.pending, report.pending_artifacts);
  const pending = pendingExplicit.length ? pendingExplicit : queue.filter((item) =>
    isRecord(item) && ['pending', 'dispatching', 'running', 'awaiting_approval'].includes(String(item.status ?? 'pending').toLowerCase()),
  );
  const refreshed = firstArray(
    data.refreshed_artifacts,
    data.refreshed,
    data.completed_artifacts,
    report.refreshed_artifacts,
    report.refreshed,
    report.completed_artifacts,
  );
  const artifacts = record(data.artifacts, mission.artifacts, data.current_artifacts);
  const currentEvidence = Object.entries(artifacts)
    .filter(([, value]) => isRecord(value) && String(value.status ?? '').toLowerCase() === 'current')
    .map(([name]) => name);
  const feasibility = record(data.feasibility, report.feasibility, mission.feasibility);
  const feasibilityStatus = feasibility.status ?? feasibility.overall_status ?? feasibility.result;
  const checks = firstArray(feasibility.checks, feasibility.components);
  const executed = firstArray(report.executed_steps, data.executed_steps);
  const workflowId = report.workflow_id ?? data.workflow_id;
  const selection = record(data.selections, mission.selections);
  const flightSelection = record(data.flight_selection, selection.flights);
  const selectionStatus = data.selection_status ?? data.flight_selection_status ?? flightSelection.selection_status;
  const safeStatus = String(status).toLowerCase();
  const statusClass = ['completed', 'completed_locally'].includes(safeStatus)
    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
    : ['blocked', 'failed'].includes(safeStatus)
      ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
      : 'border-jprimary/30 bg-jprimary/10 text-jsecondary';

  return (
    <div className="mt-4 w-full rounded-2xl border border-jprimary/30 bg-jcard p-4 sm:p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl bg-jprimary/15 border border-jprimary/20 flex items-center justify-center text-jsecondary">
            <RefreshCw size={17} />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white">Travel evidence refresh</h4>
            <p className="text-[11px] text-jmuted mt-0.5">Search and planning updates</p>
          </div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${statusClass}`}>
          {pretty(status)}
        </span>
      </div>

      {(workflowId != null || executed.length > 0) && (
        <div className="flex flex-wrap gap-3 text-[11px] text-jmuted">
          {workflowId != null && <span>Workflow #{workflowId}</span>}
          {executed.length > 0 && <span>{executed.length} workflow step(s) executed</span>}
        </div>
      )}

      {refreshed.length > 0 ? (
        <ArtifactList title="Refreshed" items={refreshed} tone="success" />
      ) : currentEvidence.length > 0 ? (
        <ArtifactList title="Current evidence" items={currentEvidence} tone="success" />
      ) : null}

      <ArtifactList title="Needs attention" items={blocked} tone="warning" />
      <ArtifactList title="Still pending" items={pending} tone="muted" />

      {feasibilityStatus != null && (
        <section className="rounded-xl border border-jprimary/20 bg-jbg/60 p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-white">
              <ShieldCheck size={15} className="text-jsecondary" /> Feasibility assessment
            </div>
            <span className="text-[10px] uppercase tracking-wider text-jsecondary">{pretty(feasibilityStatus)}</span>
          </div>
          {checks.length > 0 && (
            <div className="mt-3 flex flex-col gap-2">
              {checks.slice(0, 6).map((check, index) => {
                const item = record(check);
                const checkName = artifactName(item) || `Check ${index + 1}`;
                const checkStatus = String(item.status ?? 'unknown').toUpperCase();
                return (
                  <div key={`${checkName}-${index}`} className="flex items-start justify-between gap-3 text-[11px]">
                    <span className="text-jmuted capitalize">{checkName}</span>
                    <span className={checkStatus === 'PASS' ? 'text-emerald-300' : checkStatus === 'FAIL' ? 'text-red-300' : 'text-amber-200'}>{pretty(checkStatus)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {selectionStatus != null && (
        <div className="text-[11px] text-jmuted">Flight selection: <span className="text-white">{pretty(selectionStatus)}</span></div>
      )}

      <div className="flex items-start gap-2 border-t border-jprimary/15 pt-3 text-[11px] text-jmuted leading-relaxed">
        <XCircle size={13} className="mt-0.5 shrink-0 text-jsecondary" />
        A refreshed search or selected option is not a confirmed booking. Reservations and payments require your explicit action.
      </div>
    </div>
  );
};
