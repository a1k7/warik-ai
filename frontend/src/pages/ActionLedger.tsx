import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Circle, Clock3, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { commitmentsApi, CommitmentItem, CommitmentStatus } from '../api';

const blank = { title: '', details: '', counterparty: '', due_at: '' };
const statuses: CommitmentStatus[] = ['open', 'in_progress', 'waiting', 'blocked', 'completed'];
const label = (value: CommitmentStatus) => value.replace('_', ' ');

export function ActionLedger() {
  const [items, setItems] = useState<CommitmentItem[]>([]);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'active' | 'all' | 'completed'>('active');

  const load = async () => {
    setBusy(true); setError('');
    try { setItems(await commitmentsApi.list()); }
    catch { setError('Could not load your Action Ledger. Check the backend connection.'); }
    finally { setBusy(false); }
  };
  useEffect(() => { void load(); }, []);

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.title.trim()) return;
    setBusy(true); setError('');
    try {
      await commitmentsApi.create({
        title: form.title.trim(),
        details: form.details.trim() || undefined,
        counterparty: form.counterparty.trim() || undefined,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : undefined,
      });
      setForm(blank); await load();
    } catch { setError('Could not create this commitment.'); setBusy(false); }
  };

  const changeStatus = async (item: CommitmentItem, next: CommitmentStatus) => {
    let verification_note: string | undefined;
    if (next === 'completed') {
      const note = window.prompt('What proves this is complete? Add a short outcome or evidence note:');
      if (!note || note.trim().length < 3) return;
      verification_note = note.trim();
    }
    try { await commitmentsApi.update(item.id, { status: next, verification_note }); await load(); }
    catch (err: any) { setError(err?.response?.data?.detail || 'Status could not be updated.'); }
  };

  const remove = async (id: number) => {
    if (!window.confirm('Delete this commitment permanently?')) return;
    try { await commitmentsApi.remove(id); await load(); }
    catch { setError('Could not delete this commitment.'); }
  };

  const active = items.filter(item => item.status !== 'completed');
  const shown = items.filter(item => filter === 'all' || (filter === 'active' ? item.status !== 'completed' : item.status === 'completed'));
  const overdue = active.filter(item => item.due_at && new Date(item.due_at).getTime() < Date.now());
  const waiting = active.filter(item => item.status === 'waiting' || item.status === 'blocked');

  return <section className="feature-page">
    <div className="feature-heading"><div><span className="eyebrow">WARIK DIFFERENCE · FOLLOW-THROUGH</span><h1>Action Ledger</h1><p>Track what you said you would do, what is waiting, and what has actually been completed.</p></div><button className="icon-refresh" onClick={() => void load()} aria-label="Refresh"><Activity size={17}/></button></div>
    <div className="metric-row">
      <div className="metric-card"><span>Active commitments</span><strong>{active.length}</strong></div>
      <div className="metric-card"><span>Waiting / blocked</span><strong>{waiting.length}</strong></div>
      <div className="metric-card"><span>Overdue</span><strong>{overdue.length}</strong></div>
      <div className="metric-card"><span>Verified complete</span><strong>{items.filter(item => item.status === 'completed' && item.verified_at).length}</strong></div>
    </div>
    <form className="feature-form" onSubmit={add}>
      <h2><Plus size={18}/> Capture a commitment</h2>
      <div className="form-grid">
        <label className="wide">What needs to happen?<input required maxLength={200} value={form.title} onChange={e => setForm({...form, title:e.target.value})} placeholder="e.g. Get Rahul's feedback on the project report"/></label>
        <label className="wide">Context / next step<input maxLength={4000} value={form.details} onChange={e => setForm({...form, details:e.target.value})} placeholder="What is the expected outcome?"/></label>
        <label>Waiting on / person<input maxLength={120} value={form.counterparty} onChange={e => setForm({...form, counterparty:e.target.value})} placeholder="e.g. Rahul (optional)"/></label>
        <label>Due date<input type="datetime-local" value={form.due_at} onChange={e => setForm({...form, due_at:e.target.value})}/></label>
      </div>
      <button className="primary-action" type="submit" disabled={busy || !form.title.trim()}>Add to Action Ledger</button>
    </form>
    <div className="list-toolbar"><h2>Your commitments</h2><div className="filter-pills">{(['active','all','completed'] as const).map(f => <button key={f} className={filter===f?'selected':''} onClick={() => setFilter(f)}>{f==='active'?'Active':f==='all'?'All':'Completed'}</button>)}</div></div>
    {error && <p className="inline-error">{error}</p>}
    {busy && items.length===0 ? <p className="empty-state">Loading commitments…</p> : shown.length===0 ? <p className="empty-state">Nothing here yet. Capture a commitment above; Warik will keep its outcome visible.</p> :
      <div className="record-list">{shown.map(item => <article className={'record-card ' + (item.status==='completed'?'is-complete':'')} key={item.id}>
        <span className="complete-button" aria-hidden="true">{item.status==='completed'?<CheckCircle2 size={18}/>:<Circle size={18}/>}</span>
        <div className="record-main"><strong>{item.title}</strong>{item.details && <p>{item.details}</p>}
          <div className="record-meta">{item.counterparty && <span>Waiting on: {item.counterparty}</span>}{item.due_at && <span><Clock3 size={13}/>{new Date(item.due_at).toLocaleString()}</span>}<span className={'priority priority-' + (item.status==='completed'?'low':item.status==='blocked'?'high':'medium')}>{label(item.status)}</span></div>
          {item.verification_note && <p><ShieldCheck size={13}/> Verified outcome: {item.verification_note}</p>}
        </div>
        <div className="record-actions">{item.status!=='completed' && <select aria-label="Update commitment status" value={item.status} onChange={e => void changeStatus(item,e.target.value as CommitmentStatus)}>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select>}<button className="delete-button" onClick={() => void remove(item.id)} aria-label="Delete commitment"><Trash2 size={16}/></button></div>
      </article>)}</div>}
    <p className="empty-state"><ShieldCheck size={15}/> Completion requires a short verification note. Warik distinguishes a promise from a verified outcome.</p>
  </section>;
}
