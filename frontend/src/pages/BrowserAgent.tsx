import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Activity, ArrowRight, CheckCircle2, Circle, ExternalLink,
  History, Loader2, LockKeyhole, MonitorPlay, ShieldCheck, Sparkles,
  XCircle, Zap
} from 'lucide-react';
import { api } from '../api';
import './browser-agent.css';

type AgentStep = {
  id: number;
  sequence: number;
  thought: string;
  action: string;
  status: string;
  details?: string | null;
  screenshot_url?: string | null;
  created_at?: string | null;
};

type AgentApproval = {
  id: number;
  action: string;
  summary: string;
  status: string;
  expires_at?: string;
};

type AgentTask = {
  id: number;
  goal: string;
  status: string;
  final_answer?: string | null;
  memory_files: string[];
  created_at?: string | null;
  steps?: AgentStep[];
  approval?: AgentApproval | null;
};

const DEFAULT_GOAL = 'Find the cheapest non-stop flight from Delhi to Mumbai tomorrow evening and hold the cheapest option.';
const terminal = (status: string) => ['done', 'failed', 'denied'].includes(status);
const statusLabel = (status: string) => {
  const labels: Record<string, string> = { queued: 'Queued', running: 'Running', waiting_approval: 'Awaiting approval', done: 'Completed', failed: 'Failed', denied: 'Denied' };
  return labels[status] || status.replaceAll('_', ' ');
};

function Screenshot({ url, className = '' }: { url?: string | null; className?: string }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let objectUrl = '';
    let active = true;
    if (url) {
      api.get(url, { responseType: 'blob' }).then((response) => {
        objectUrl = URL.createObjectURL(response.data);
        if (active) setSrc(objectUrl);
      }).catch(() => setSrc(''));
    }
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  if (!src) return <div className={'agent-shot-placeholder ' + className}><MonitorPlay size={20}/><span>Browser snapshot</span></div>;
  return <img className={'agent-shot ' + className} src={src} alt="Browser action screenshot"/>;
}

function StepItem({ step }: { step: AgentStep }) {
  return (
    <article className="agent-step">
      <div className="agent-step-rail"><span className={step.status === 'failed' || step.status === 'denied' ? 'is-error' : ''}>{step.status === 'completed' ? <CheckCircle2 size={15}/> : <Circle size={15}/>}</span></div>
      <div className="agent-step-body">
        <div className="agent-step-top"><strong>{step.action.replaceAll('_', ' ')}</strong><span>STEP {String(step.sequence).padStart(2, '0')}</span></div>
        <p>{step.thought}</p>
        {step.details && step.action === 'read_page' && (() => {
          try {
            const detail = JSON.parse(step.details || '{}');
            return detail.selected ? <div className="agent-selection"><b>{detail.selected.airline}</b><span>{detail.selected.route}</span><strong>₹{Number(detail.selected.price).toLocaleString('en-IN')}</strong></div> : null;
          } catch { return null; }
        })()}
        {step.screenshot_url && <Screenshot url={step.screenshot_url} className="agent-step-shot"/>}
      </div>
    </article>
  );
}

export function BrowserAgent() {
  const navigate = useNavigate();
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [task, setTask] = useState<AgentTask | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [approval, setApproval] = useState<AgentApproval | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [decisionBusy, setDecisionBusy] = useState(false);
  const streamRef = useRef<AbortController | null>(null);

  useEffect(() => () => streamRef.current?.abort(), []);

  const connectStream = async (taskId: number, controller: AbortController) => {
    const base = (api.defaults.baseURL || 'http://127.0.0.1:8000/api').replace(/\/$/, '');
    const token = localStorage.getItem('warik_token') || '';
    const response = await fetch(base + '/browser-agent/tasks/' + taskId + '/stream', {
      headers: { Authorization: 'Bearer ' + token, Accept: 'text/event-stream' },
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error('Unable to connect to the live task stream.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const packet = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLine = packet.split('\n').find((line) => line.startsWith('data:'));
        if (dataLine) {
          const payload = JSON.parse(dataLine.slice(5).trim());
          if (payload.task) {
            setTask(payload.task);
            if (payload.task.approval) setApproval(payload.task.approval);
            if (terminal(payload.task.status)) setApproval(null);
          }
          if (Array.isArray(payload.steps) && payload.steps.length) {
            setSteps((previous) => {
              const known = new Set(previous.map((step) => step.id));
              return [...previous, ...payload.steps.filter((step: AgentStep) => !known.has(step.id))];
            });
          }
          if (payload.task && terminal(payload.task.status)) {
            setBusy(false);
            return;
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
    setBusy(false);
  };

  const startTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!goal.trim() || busy) return;
    setError('');
    setBusy(true);
    setTask(null);
    setSteps([]);
    setApproval(null);
    streamRef.current?.abort();
    const controller = new AbortController();
    streamRef.current = controller;
    try {
      const response = await api.post('/browser-agent/tasks', { goal: goal.trim() });
      setTask(response.data);
      await connectStream(response.data.id, controller);
    } catch (err: any) {
      if (err?.name !== 'AbortError') setError(err?.response?.data?.detail || err?.message || 'Unable to start the browser task.');
      setBusy(false);
    }
  };

  const decide = async (decision: 'approve' | 'deny') => {
    if (!approval || decisionBusy) return;
    setDecisionBusy(true);
    try {
      await api.post('/browser-agent/approvals/' + approval.id, { decision });
      setApproval({ ...approval, status: decision === 'approve' ? 'approved' : 'denied' });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Unable to record this decision.');
    } finally {
      setDecisionBusy(false);
    }
  };

  const lastShot = [...steps].reverse().find((step) => step.screenshot_url)?.screenshot_url;

  return (
    <div className="browser-agent-page">
      <header className="agent-topbar">
        <Link to="/" className="agent-brand"><span><Sparkles size={16}/></span> warik<span>.ai</span></Link>
        <div className="agent-top-nav">
          <Link className="active" to="/agent">Agent</Link>
          <Link to="/dashboard">Activity <History size={14}/></Link>
          <span className="agent-live-indicator"><i/> LOCAL SANDBOX</span>
        </div>
      </header>

      <section className="agent-heading">
        <div><div className="agent-overline"><span/> PERSONAL EXECUTION ENGINE</div>
          <h1>Tell Warik what to <em>make happen.</em></h1>
          <p>Warik can operate a browser, show every step, and stop for your approval before it commits an action.</p>
        </div>
        <div className="agent-heading-mark"><div><Zap size={28}/></div><span>PLAN · ACT · VERIFY</span></div>
      </section>

      <div className="agent-workspace">
        <section className="agent-left">
          <div className="agent-panel agent-request">
            <div className="agent-panel-head"><span>01 / YOUR REQUEST</span><span className="agent-muted">NATURAL LANGUAGE</span></div>
            <form onSubmit={startTask}>
              <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} placeholder="Describe a task for Warik to complete..."/>
              <div className="agent-request-foot"><span><LockKeyhole size={13}/> Approval required before holds, sends or payments</span><button type="submit" disabled={busy || !goal.trim()}>{busy ? <><Loader2 size={16} className="agent-spin"/> Working</> : <>Run task <ArrowRight size={16}/></>}</button></div>
            </form>
            <div className="agent-examples"><span>TRY A TASK</span><button onClick={() => setGoal(DEFAULT_GOAL)}>Compare flights</button><button onClick={() => setGoal('Find and compare three non-stop evening flights from Bengaluru to Goa tomorrow, then hold the cheapest option.')}>Change route</button></div>
          </div>

          <div className="agent-panel agent-execution">
            <div className="agent-panel-head"><span>02 / LIVE EXECUTION</span><span className={'agent-status status-' + (task?.status || 'idle')}>{task ? statusLabel(task.status) : 'Ready'}</span></div>
            {!task && <div className="agent-idle"><div><MonitorPlay size={28}/></div><h3>Your browser session will appear here.</h3><p>Start with the sample flight task. The agent will open Chromium, search the local catalogue, compare the results, and request approval.</p></div>}
            {task && <>
              <div className="agent-current-task"><span>TASK #{task.id}</span><strong>{task.goal}</strong></div>
              <div className="agent-timeline">{steps.map((step) => <StepItem key={step.id} step={step}/>)}
                {busy && !terminal(task.status) && <div className="agent-running-line"><span className="agent-spinner"/> Waiting for the next browser event…</div>}
              </div>
              {approval?.status === 'pending' && <div className="agent-approval">
                <div className="agent-approval-icon"><ShieldCheck size={20}/></div>
                <div className="agent-approval-content"><span>HUMAN APPROVAL REQUIRED</span><strong>{approval.summary}</strong><p>This action is paused. The browser will not continue until you approve it.</p>
                  <div className="agent-approval-actions"><button className="approve" disabled={decisionBusy} onClick={() => decide('approve')}><CheckCircle2 size={15}/> Approve action</button><button className="deny" disabled={decisionBusy} onClick={() => decide('deny')}><XCircle size={15}/> Deny</button></div>
                </div>
              </div>}
              {approval && approval.status !== 'pending' && <div className="agent-decision"><ShieldCheck size={17}/> Approval {approval.status}. The agent is updating the task.</div>}
              {task.final_answer && <div className="agent-final"><CheckCircle2 size={18}/><div><span>RESULT</span><p>{task.final_answer}</p></div></div>}
              <div className="agent-task-links"><button onClick={() => navigate('/tasks/' + task.id)}>Open task record <ArrowRight size={14}/></button><button onClick={() => navigate('/dashboard')}>All activity <History size={14}/></button></div>
            </>}
            {error && <div className="agent-error">{error}</div>}
          </div>
        </section>

        <aside className="agent-right">
          <div className="agent-panel agent-browser-panel">
            <div className="agent-panel-head"><span>LIVE BROWSER</span><span className="agent-browser-light"><i/> CHROMIUM</span></div>
            {lastShot ? <Screenshot url={lastShot} className="agent-live-shot"/> : <div className="agent-browser-empty"><MonitorPlay size={28}/><span>Waiting for browser activity</span></div>}
            <div className="agent-browser-caption"><span>LOCAL DEMO WEBSITE</span><a href={(api.defaults.baseURL || 'http://127.0.0.1:8000/api').replace(/\/api\/?$/, '') + '/api/browser-agent/demo-site'} target="_blank" rel="noreferrer">Open site <ExternalLink size={12}/></a></div>
          </div>
          <div className="agent-panel agent-safety">
            <div className="agent-safety-icon"><ShieldCheck size={20}/></div><div><strong>Human-in-the-loop control</strong><p>Submit, hold, book, pay and send operations are gated. Requests expire to DENY after 10 minutes.</p></div>
          </div>
          <div className="agent-panel agent-memory">
            <div className="agent-panel-head"><span>MEMORY CONTEXT</span><span className="agent-muted">MARKDOWN</span></div>
            {task?.memory_files?.length ? task.memory_files.map((file) => <div key={file} className="agent-memory-file"><span>MD</span>{file}</div>) : <p>Relevant preference files will appear here when a task starts.</p>}
          </div>
          <Link className="agent-dashboard-link" to="/dashboard"><Activity size={17}/> View task history <ArrowRight size={15}/></Link>
        </aside>
      </div>
      <footer className="agent-footer"><span>WARIK AI · EXECUTION PREVIEW</span><span>Real browser control · Local demo inventory · No external bookings</span></footer>
    </div>
  );
}

export function AgentDashboard() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  useEffect(() => {
    api.get('/browser-agent/tasks').then((response) => setTasks(response.data)).catch(() => setError('Unable to load task history.')).finally(() => setLoading(false));
  }, []);
  return <div className="browser-agent-page agent-history-page">
    <header className="agent-topbar"><Link to="/" className="agent-brand"><span><Sparkles size={16}/></span> warik<span>.ai</span></Link><div className="agent-top-nav"><Link to="/agent">Agent</Link><Link className="active" to="/dashboard">Activity <History size={14}/></Link></div></header>
    <div className="agent-history-head"><div><div className="agent-overline"><span/> EXECUTION HISTORY</div><h1>Every action, <em>accounted for.</em></h1><p>Review agent runs, outcomes, and approval decisions.</p></div><button onClick={() => navigate('/agent')}>New task <ArrowRight size={16}/></button></div>
    {error && <div className="agent-error">{error}</div>}
    {loading ? <div className="agent-loading"><Loader2 className="agent-spin"/> Loading tasks…</div> : <div className="agent-task-list">
      {tasks.map((item) => <button className="agent-task-row" key={item.id} onClick={() => navigate('/tasks/' + item.id)}>
        <div className="agent-task-row-icon"><Activity size={18}/></div><div className="agent-task-row-main"><strong>{item.goal}</strong><span>Task #{item.id} · {item.created_at ? new Date(item.created_at).toLocaleString() : 'Recent'}</span></div><span className={'agent-status status-' + item.status}>{statusLabel(item.status)}</span><ArrowRight size={16}/>
      </button>)}
      {!tasks.length && <div className="agent-idle"><h3>No tasks yet</h3><p>Your browser-agent activity will be listed here.</p></div>}
    </div>}
  </div>;
}

export function AgentTaskDetail() {
  const { id } = useParams();
  const [task, setTask] = useState<AgentTask | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  useEffect(() => {
    let active = true;
    const load = () => api.get('/browser-agent/tasks/' + id).then((response) => { if (active) setTask(response.data); }).catch(() => { if (active) setTask(null); }).finally(() => { if (active) setLoading(false); });
    load();
    const poll = window.setInterval(() => { if (task && !terminal(task.status)) load(); }, 1800);
    return () => { active = false; window.clearInterval(poll); };
  }, [id, task?.status]);
  return <div className="browser-agent-page agent-detail-page">
    <header className="agent-topbar"><Link to="/" className="agent-brand"><span><Sparkles size={16}/></span> warik<span>.ai</span></Link><div className="agent-top-nav"><Link to="/agent">Agent</Link><Link to="/dashboard">Activity <History size={14}/></Link></div></header>
    <div className="agent-detail-head"><button onClick={() => navigate('/dashboard')}>← All tasks</button><span className={'agent-status status-' + (task?.status || 'idle')}>{task ? statusLabel(task.status) : 'Task record'}</span></div>
    {loading ? <div className="agent-loading"><Loader2 className="agent-spin"/> Loading task record…</div> : !task ? <div className="agent-idle"><h3>Task not found</h3><p>This task may have been removed or may not belong to your account.</p></div> : <>
      <div className="agent-detail-title"><div className="agent-overline"><span/> TASK #{task.id}</div><h1>{task.goal}</h1><p>{task.final_answer || 'The browser-agent task is still running.'}</p></div>
      <div className="agent-detail-grid"><section className="agent-panel agent-detail-timeline"><div className="agent-panel-head"><span>EXECUTION TIMELINE</span><span className="agent-muted">{(task.steps || []).length} EVENTS</span></div>{(task.steps || []).map((step) => <StepItem key={step.id} step={step}/>)}{!(task.steps || []).length && <p className="agent-muted">No browser steps have been recorded yet.</p>}</section>
        <aside className="agent-panel agent-detail-memory"><div className="agent-panel-head"><span>MEMORY USED</span><span className="agent-muted">LOCAL MARKDOWN</span></div>{task.memory_files?.length ? task.memory_files.map((file) => <div key={file} className="agent-memory-file"><span>MD</span>{file}</div>) : <p>No matching memory files were selected for this task.</p>}<div className="agent-detail-note"><LockKeyhole size={16}/><span>Approval status and every browser action are recorded with this task.</span></div></aside></div>
    </>}
  </div>;
}
