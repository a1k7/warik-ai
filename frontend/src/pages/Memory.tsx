import { useCallback, useEffect, useState } from 'react';
import { Brain, Plus, Trash2, Pencil, X, Check, ShieldCheck, RefreshCw } from 'lucide-react';
import { api } from '../api';

type MemoryItem = {
  id: number;
  content: string;
  category: string | null;
  source: string;
  created_at: string;
  updated_at: string;
};

const categories = ['Preference', 'Personal context', 'Work', 'Study', 'Travel', 'Other'];

export const MemoryPage = () => {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('Preference');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get<MemoryItem[]>('/memories/');
      setItems(response.data);
    } catch {
      setError('Could not load saved memories. Check your connection and try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const resetForm = () => { setContent(''); setCategory('Preference'); setEditingId(null); };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = content.trim();
    if (!value) return;
    setSaving(true); setError(''); setNotice('');
    try {
      if (editingId !== null) {
        await api.put(`/memories/${editingId}`, { content: value, category });
        setNotice('Memory updated.');
      } else {
        await api.post('/memories/', { content: value, category });
        setNotice('Memory saved. Warik can use it when it is relevant.');
      }
      resetForm();
      await load();
    } catch {
      setError('Could not save this memory. Please try again.');
    } finally { setSaving(false); }
  };

  const edit = (item: MemoryItem) => {
    setEditingId(item.id);
    setContent(item.content);
    setCategory(item.category || 'Other');
    setNotice('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const remove = async (id: number) => {
    if (!window.confirm('Delete this saved memory?')) return;
    try {
      await api.delete(`/memories/${id}`);
      setItems(current => current.filter(item => item.id !== id));
      if (editingId === id) resetForm();
      setNotice('Memory deleted.');
    } catch { setError('Could not delete this memory.'); }
  };

  const clearAll = async () => {
    if (!window.confirm('Permanently delete every saved memory for this account? This cannot be undone.')) return;
    try {
      await api.delete('/memories/');
      setItems([]);
      resetForm();
      setNotice('All saved memories have been deleted.');
    } catch { setError('Could not clear saved memories.'); }
  };

  return (
    <main className="memory-page">
      <header className="memory-header">
        <div>
          <span className="memory-eyebrow">PERSONAL CONTEXT</span>
          <h1>Your memory</h1>
          <p>Choose what Warik should remember and use when it is relevant.</p>
        </div>
        <div className="memory-count"><Brain size={17}/><strong>{items.length}</strong><span>saved</span></div>
      </header>

      <section className="memory-privacy">
        <span><ShieldCheck size={18}/></span>
        <div><strong>You stay in control</strong><p>Only memories you explicitly save appear here. You can edit or delete them at any time. Warik uses relevant saved details as context, not as instructions that override what you ask now.</p></div>
      </section>

      <form className="memory-form" onSubmit={save}>
        <div className="memory-form-title"><span>{editingId ? <Pencil size={17}/> : <Plus size={18}/>}</span><strong>{editingId ? 'Edit memory' : 'Save a memory'}</strong></div>
        <label htmlFor="memory-content">What should Warik remember?</label>
        <textarea id="memory-content" value={content} onChange={event => setContent(event.target.value)} maxLength={2000} rows={3} placeholder="Example: I prefer concise explanations with practical examples." required/>
        <div className="memory-form-bottom">
          <label className="memory-category">Category
            <select value={category} onChange={event => setCategory(event.target.value)}>{categories.map(item => <option key={item} value={item}>{item}</option>)}</select>
          </label>
          <div className="memory-form-actions">
            {editingId !== null && <button type="button" className="memory-cancel" onClick={resetForm}><X size={15}/> Cancel</button>}
            <button type="submit" className="memory-save" disabled={saving || !content.trim()}>{saving ? 'Saving…' : <><Check size={15}/> {editingId ? 'Update memory' : 'Save memory'}</>}</button>
          </div>
        </div>
        <div className="memory-char-count">{content.length}/2000 characters</div>
      </form>

      {error && <p className="memory-feedback error" role="alert">{error}</p>}
      {notice && <p className="memory-feedback" role="status">{notice}</p>}

      <div className="memory-list-head"><div><span className="memory-eyebrow">YOUR SAVED DETAILS</span><h2>Memories</h2></div><button onClick={() => void load()} disabled={loading} aria-label="Refresh memories"><RefreshCw size={16}/></button></div>

      {loading ? <div className="memory-empty">Loading your memories…</div> : items.length === 0 ? (
        <div className="memory-empty"><Brain size={25}/><strong>No saved memories yet</strong><p>Add a preference, ongoing goal or detail you want Warik to remember across relevant conversations.</p></div>
      ) : (
        <div className="memory-list">{items.map(item => (
          <article className="memory-item" key={item.id}>
            <div className="memory-item-main"><span className="memory-tag">{item.category || 'Uncategorised'}</span><p>{item.content}</p><small>Updated {new Date(item.updated_at).toLocaleDateString()}</small></div>
            <div className="memory-item-actions"><button onClick={() => edit(item)} aria-label="Edit memory"><Pencil size={15}/></button><button onClick={() => void remove(item.id)} aria-label="Delete memory"><Trash2 size={15}/></button></div>
          </article>
        ))}</div>
      )}
      {items.length > 0 && <button className="memory-clear" onClick={() => void clearAll()}>Delete all memories</button>}
    </main>
  );
};
