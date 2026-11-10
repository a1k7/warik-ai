import { CheckCircle2, XCircle, Clock, AlertCircle, Loader2, Ban, RotateCw } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '../api';

interface Step {
  id: string;
  description: string;
  status: string;
  error?: string;
  required?: boolean;
}

interface WorkflowData {
  type: 'workflow_status';
  workflow_id: number;
  status: string;
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
  const base = 'text-[10px] px-2 py-0.5 rounded font-mono';
  switch (status) {
    case 'COMPLETED': return clsx(base, 'bg-green-500/20 text-green-400');
    case 'FAILED': return clsx(base, 'bg-red-500/20 text-red-400');
    case 'PARTIALLY_COMPLETED': return clsx(base, 'bg-yellow-500/20 text-yellow-400');
    case 'AWAITING_APPROVAL': return clsx(base, 'bg-yellow-500/20 text-yellow-400');
    case 'IN_PROGRESS': return clsx(base, 'bg-jprimary/20 text-jsecondary');
    default: return clsx(base, 'bg-jmuted/20 text-jmuted');
  }
};

export const WorkflowCard = ({ data, onRetried }: { data: WorkflowData; onRetried?: () => void }) => {
  const handleRetry = async (stepId: string) => {
    try {
      await api.post(`/workflows/${data.workflow_id}/retry/${stepId}`);
      onRetried?.();
    } catch (e) {
      alert('Retry failed. Please try again.');
    }
  };

  return (
    <div className="bg-jcard border border-jprimary/30 rounded-2xl p-4 flex flex-col gap-3 mt-4 w-full">
      <div className="flex justify-between items-center">
        <h4 className="font-bold text-white text-sm">Trip Plan Progress</h4>
        <span className={statusChip(data.status)}>{data.status.replace('_', ' ')}</span>
      </div>
      <div className="flex flex-col gap-2">
        {data.steps.map(s => (
          <div key={s.id} className="flex items-start gap-2 text-xs">
            <div className="mt-0.5 shrink-0">{icon(s.status)}</div>
            <div className="flex-1">
              <span className={clsx(
                s.status === 'COMPLETED' ? 'text-jmuted line-through' :
                s.status === 'FAILED' || s.status === 'BLOCKED' ? 'text-red-300' :
                'text-white'
              )}>
                {s.description}
                {!s.required && <span className="text-jmuted/60 ml-1">(optional)</span>}
              </span>
              {s.error && <p className="text-[10px] text-red-400 mt-1">{s.error}</p>}
            </div>
            {s.status === 'FAILED' && (
              <button
                onClick={() => handleRetry(s.id)}
                className="text-[10px] bg-jprimary/20 hover:bg-jprimary/30 text-jsecondary px-2 py-1 rounded flex items-center gap-1 shrink-0"
              >
                <RotateCw size={10} /> Retry
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
