import {
  CheckCircle2, XCircle, Clock, AlertCircle, Loader2, Ban, RotateCw,
  ShieldCheck, ShieldAlert, FileSearch
} from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '../api';

interface Verification {
  status?: string;
  message?: string;
  method?: string;
}

interface Step {
  id: string;
  description: string;
  status: string;
  error?: string;
  required?: boolean;
  tool?: string;
  verification?: Verification;
  result?: {
    type?: string;
    source_count?: number;
    retrieved_count?: number;
  };
}

interface WorkflowData {
  type: 'workflow_status';
  workflow_id: number;
  status: string;
  goal_title?: string;
  goal_description?: string;
  steps: Step[];
}

const icon = (status: string) => {
  switch (status) {
    case 'COMPLETED': return <CheckCircle2 size={16} className="text-green-400" />;
    case 'FAILED': return <XCircle size={16} className="text-red-400" />;
    case 'EXECUTING': return <Loader2 size={16} className="text-jsecondary animate-spin" />;
    case 'AWAITING_APPROVAL': return <AlertCircle size={16} className="text-yellow-400" />;
    case 'BLOCKED': return <Ban size={16} className="text-orange-400" />;
    default: return <Clock size={16} className="text-jmuted" />;
  }
};

const statusChip = (status: string) => {
  const base = 'text-[10px] px-2 py-1 rounded-lg font-semibold tracking-wide';
  switch (status) {
    case 'COMPLETED': return clsx(base, 'bg-green-500/15 text-green-400 border border-green-500/20');
    case 'FAILED': return clsx(base, 'bg-red-500/15 text-red-400 border border-red-500/20');
    case 'PARTIALLY_COMPLETED': return clsx(base, 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/20');
    case 'AWAITING_APPROVAL': return clsx(base, 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/20');
    case 'IN_PROGRESS': return clsx(base, 'bg-jprimary/20 text-jsecondary border border-jprimary/20');
    default: return clsx(base, 'bg-jmuted/10 text-jmuted border border-jmuted/10');
  }
};

const verificationLabel = (verification?: Verification) => {
  switch (verification?.status) {
    case 'VERIFIED': return 'Independently verified';
    case 'FAILED': return 'Verification failed';
    case 'UNVERIFIED': return 'Not independently verified';
    default: return '';
  }
};

export const WorkflowCard = ({ data, onRetried }: { data: WorkflowData; onRetried?: () => void }) => {
  const steps = Array.isArray(data.steps) ? data.steps : [];
  const completed = steps.filter(step => step.status === 'COMPLETED').length;
  const verified = steps.filter(step => step.verification?.status === 'VERIFIED').length;
  const needsReview = steps.filter(step =>
    ['FAILED', 'UNVERIFIED'].includes(step.verification?.status || '')
  ).length;
  const pendingApproval = steps.filter(step => step.status === 'AWAITING_APPROVAL').length;

  const handleRetry = async (stepId: string) => {
    try {
      await api.post(`/workflows/${data.workflow_id}/retry/${stepId}`);
      onRetried?.();
    } catch (e) {
      alert('Retry failed. Please try again.');
    }
  };

  return (
    <div className="bg-jcard border border-jprimary/30 rounded-2xl p-4 flex flex-col gap-4 mt-4 w-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-bold text-jsecondary">
            <ShieldCheck size={13} /> Mission control
          </div>
          <h4 className="mt-1 text-base font-bold text-white">
            {data.goal_title || 'Your mission'}
          </h4>
          {data.goal_description && (
            <p className="text-xs text-jmuted mt-1 leading-relaxed">{data.goal_description}</p>
          )}
        </div>
        <span className={statusChip(data.status)}>{data.status.replaceAll('_', ' ')}</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="rounded-xl bg-jbg/70 border border-jmuted/10 p-3">
          <p className="text-[9px] uppercase tracking-wider text-jmuted">Steps done</p>
          <p className="text-lg font-bold text-white mt-1 tabular-nums">{completed}<span className="text-xs text-jmuted font-medium"> / {steps.length}</span></p>
        </div>
        <div className="rounded-xl bg-jbg/70 border border-jmuted/10 p-3">
          <p className="text-[9px] uppercase tracking-wider text-jmuted">Verified</p>
          <p className="text-lg font-bold text-emerald-400 mt-1 tabular-nums">{verified}</p>
        </div>
        <div className="rounded-xl bg-jbg/70 border border-jmuted/10 p-3">
          <p className="text-[9px] uppercase tracking-wider text-jmuted">Needs review</p>
          <p className={clsx('text-lg font-bold mt-1 tabular-nums', needsReview ? 'text-amber-400' : 'text-white')}>{needsReview}</p>
        </div>
        <div className="rounded-xl bg-jbg/70 border border-jmuted/10 p-3">
          <p className="text-[9px] uppercase tracking-wider text-jmuted">Approval</p>
          <p className={clsx('text-lg font-bold mt-1 tabular-nums', pendingApproval ? 'text-amber-400' : 'text-white')}>{pendingApproval}</p>
        </div>
      </div>

      {(needsReview > 0 || pendingApproval > 0) && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-400/20 bg-amber-400/5 px-3 py-2.5 text-xs text-amber-200">
          <ShieldAlert size={15} className="shrink-0 mt-0.5" />
          <p>
            {pendingApproval > 0
              ? 'A step is waiting for your approval. Nothing beyond this checkpoint will proceed until you decide.'
              : 'Some results need review. Completed does not automatically mean independently verified.'}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {steps.map(step => {
          const verification = step.verification?.status;
          const label = verificationLabel(step.verification);
          const research = step.result?.type === 'web_research';

          return (
            <div key={step.id} className="flex items-start gap-2.5 text-xs">
              <div className="mt-0.5 shrink-0">{icon(step.status)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={clsx(
                    step.status === 'COMPLETED' ? 'text-jmuted' :
                    step.status === 'FAILED' || step.status === 'BLOCKED' ? 'text-red-300' :
                    'text-white'
                  )}>
                    {step.description}
                  </span>
                  {!step.required && <span className="text-[9px] text-jmuted/70">OPTIONAL</span>}
                </div>
                {label && (
                  <div className={clsx(
                    'mt-1 inline-flex items-center gap-1 text-[10px]',
                    verification === 'VERIFIED' ? 'text-emerald-400' :
                    verification === 'FAILED' ? 'text-red-300' : 'text-amber-300'
                  )}>
                    {verification === 'VERIFIED' ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                    {label}
                  </div>
                )}
                {step.verification?.message && (
                  <p className="text-[10px] text-jmuted mt-1">{step.verification.message}</p>
                )}
                {research && (
                  <p className="mt-1 inline-flex items-center gap-1 text-[10px] text-jmuted">
                    <FileSearch size={11} />
                    {step.result?.retrieved_count || 0} of {step.result?.source_count || 0} pages retrieved
                  </p>
                )}
                {step.error && <p className="text-[10px] text-red-400 mt-1">{step.error}</p>}
              </div>
              {step.status === 'FAILED' && (
                <button
                  type="button"
                  onClick={() => handleRetry(step.id)}
                  className="text-[10px] bg-jprimary/20 hover:bg-jprimary/30 text-jsecondary px-2 py-1 rounded flex items-center gap-1 shrink-0"
                >
                  <RotateCw size={10} /> Retry
                </button>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-jmuted border-t border-jmuted/10 pt-3">
        Warik separates planned work, executed steps and verified outcomes. Review each evidence status before relying on a result.
      </p>
    </div>
  );
};
