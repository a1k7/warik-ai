import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Sun,
  Bell,
  ShieldCheck,
  Check,
  Utensils,
  RefreshCw,
  Unplug,
  ExternalLink,
  Mail,
  Search,
} from 'lucide-react';
import {
  swiggyIntegrationApi,
  type SwiggyConnectionStatus,
  gmailIntegrationApi,
  type GmailConnectionStatus,
  type GmailContextItem,
} from '../api';

const palettes = [
  { name: 'Lavender', value: '#8b5cf6' },
  { name: 'Ocean', value: '#4d8ee8' },
  { name: 'Rose', value: '#d76b9b' },
  { name: 'Mint', value: '#329c83' },
];

export const Settings = () => {
  const navigate = useNavigate();

  const [dark, setDark] = useState(
    localStorage.getItem('warik_theme') === 'dark'
  );
  const [accent, setAccent] = useState(
    localStorage.getItem('warik_accent') || '#8b5cf6'
  );
  const [fontSize, setFontSize] = useState(
    localStorage.getItem('warik_font_size') || 'Regular'
  );

  const [swiggyStatus, setSwiggyStatus] =
    useState<SwiggyConnectionStatus | null>(null);
  const [swiggyLoading, setSwiggyLoading] = useState(true);
  const [swiggyBusy, setSwiggyBusy] = useState(false);
  const [swiggyMessage, setSwiggyMessage] = useState('');
  const [swiggyMessageType, setSwiggyMessageType] =
    useState<'success' | 'error' | ''>('');

  const [gmailStatus, setGmailStatus] = useState<GmailConnectionStatus | null>(null);
  const [gmailLoading, setGmailLoading] = useState(true);
  const [gmailBusy, setGmailBusy] = useState(false);
  const [gmailScanBusy, setGmailScanBusy] = useState(false);
  const [gmailMessage, setGmailMessage] = useState('');
  const [gmailMessageType, setGmailMessageType] = useState<'success' | 'error' | ''>('');
  const [gmailItems, setGmailItems] = useState<GmailContextItem[]>([]);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.documentElement.style.setProperty('--warik-accent', accent);
    document.documentElement.dataset.fontSize = fontSize.toLowerCase();

    localStorage.setItem('warik_theme', dark ? 'dark' : 'light');
    localStorage.setItem('warik_accent', accent);
    localStorage.setItem('warik_font_size', fontSize);
  }, [dark, accent, fontSize]);

  const loadSwiggyStatus = async () => {
    setSwiggyLoading(true);
    try {
      const status = await swiggyIntegrationApi.status();
      setSwiggyStatus(status);
    } catch {
      setSwiggyMessage('Unable to load Swiggy connection status.');
      setSwiggyMessageType('error');
    } finally {
      setSwiggyLoading(false);
    }
  };

  const loadGmailStatus = async () => {
    setGmailLoading(true);
    try {
      setGmailStatus(await gmailIntegrationApi.status());
    } catch {
      setGmailMessage('Unable to load Gmail connection status.');
      setGmailMessageType('error');
    } finally {
      setGmailLoading(false);
    }
  };

  const connectGmail = async () => {
    setGmailBusy(true);
    setGmailMessage('');
    setGmailMessageType('');
    try {
      const response = await gmailIntegrationApi.startOAuth();
      if (!response.authorization_url) throw new Error('Google authorization URL was not returned.');
      window.location.assign(response.authorization_url);
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Could not start Google authorization. Check the backend configuration.';
      setGmailMessage(message);
      setGmailMessageType('error');
      setGmailBusy(false);
    }
  };

  const disconnectGmail = async () => {
    if (!window.confirm('Disconnect Gmail from Warik? Local OAuth credentials will be deleted.')) return;
    setGmailBusy(true);
    setGmailMessage('');
    try {
      await gmailIntegrationApi.disconnect();
      setGmailStatus({ connected: false, status: 'disconnected', permission: 'read_only' });
      setGmailItems([]);
      setGmailMessage('Gmail disconnected. Local credentials have been deleted.');
      setGmailMessageType('success');
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Could not disconnect Gmail.';
      setGmailMessage(message);
      setGmailMessageType('error');
    } finally {
      setGmailBusy(false);
    }
  };

  const scanGmail = async () => {
    setGmailScanBusy(true);
    setGmailMessage('');
    setGmailMessageType('');
    try {
      const result = await gmailIntegrationApi.travelConfirmations(20);
      setGmailItems(result.items);
      setGmailMessage(`Found ${result.count} matching messages. Results are on-demand and were not saved by Warik.`);
      setGmailMessageType('success');
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Could not search Gmail. Reconnect and try again.';
      setGmailMessage(message);
      setGmailMessageType('error');
    } finally {
      setGmailScanBusy(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const callbackResult = params.get('swiggy');
    const gmailCallbackResult = params.get('gmail');

    if (gmailCallbackResult === 'connected') {
      setGmailMessage('Gmail connected. Warik has read-only access to selected message metadata.');
      setGmailMessageType('success');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (gmailCallbackResult === 'error') {
      setGmailMessage('Google authorization could not be completed. Please check your OAuth setup and try again.');
      setGmailMessageType('error');
      window.history.replaceState({}, '', window.location.pathname);
    }

    if (callbackResult === 'connected') {
      setSwiggyMessage('Swiggy authorization completed.');
      setSwiggyMessageType('success');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (callbackResult === 'error') {
      setSwiggyMessage(
        'Swiggy authorization could not be completed. Please try again.'
      );
      setSwiggyMessageType('error');
      window.history.replaceState({}, '', window.location.pathname);
    }

    void loadSwiggyStatus();
    void loadGmailStatus();
  }, []);

  const connectSwiggy = async () => {
    setSwiggyBusy(true);
    setSwiggyMessage('');
    setSwiggyMessageType('');

    try {
      const response = await swiggyIntegrationApi.startOAuth();

      if (!response.authorization_url) {
        throw new Error('Authorization URL was not returned.');
      }

      window.location.assign(response.authorization_url);
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail ||
        'Could not start Swiggy authorization. Check your configuration.';

      setSwiggyMessage(message);
      setSwiggyMessageType('error');
      setSwiggyBusy(false);
    }
  };

  const disconnectSwiggy = async () => {
    if (!window.confirm('Disconnect your Swiggy account from Warik AI?')) {
      return;
    }

    setSwiggyBusy(true);
    setSwiggyMessage('');

    try {
      await swiggyIntegrationApi.disconnect();
      setSwiggyStatus({
        connected: false,
        status: 'disconnected',
      });
      setSwiggyMessage('Swiggy account disconnected.');
      setSwiggyMessageType('success');
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail || 'Could not disconnect Swiggy.';

      setSwiggyMessage(message);
      setSwiggyMessageType('error');
    } finally {
      setSwiggyBusy(false);
    }
  };

  const connected = swiggyStatus?.connected === true;

  return (
    <main className="settings-page">
      <header className="settings-header">
        <button className="back-button" onClick={() => navigate('/')}>
          <ArrowLeft size={18} /> Back to home
        </button>
        <span className="overline">PERSONALISE YOUR EXPERIENCE</span>
        <h1>Settings</h1>
        <p>Make Warik feel like yours.</p>
      </header>

      <section className="settings-card">
        <div className="settings-card-title">
          <span className="settings-icon"><Sun size={19} /></span>
          <div>
            <h2>Appearance</h2>
            <p>Choose how Warik looks on your device.</p>
          </div>
        </div>

        <div className="setting-row">
          <div>
            <strong>Dark mode</strong>
            <small>Switch to a deeper, low-light interface.</small>
          </div>
          <button
            className={`toggle ${dark ? 'on' : ''}`}
            onClick={() => setDark(value => !value)}
            aria-label="Toggle dark mode"
          >
            <span />
          </button>
        </div>

        <div className="setting-row palette-row">
          <div>
            <strong>Accent colour</strong>
            <small>Choose a colour for highlights and controls.</small>
          </div>
          <div className="palette-options">
            {palettes.map(palette => (
              <button
                key={palette.name}
                title={palette.name}
                aria-label={palette.name}
                className={accent === palette.value ? 'selected' : ''}
                style={{
                  '--swatch': palette.value,
                } as React.CSSProperties}
                onClick={() => setAccent(palette.value)}
              >
                {accent === palette.value && <Check size={15} />}
              </button>
            ))}
          </div>
        </div>

        <div className="setting-row">
          <div>
            <strong>Text size</strong>
            <small>Adjust the reading size across the interface.</small>
          </div>
          <div className="font-options">
            {['Small', 'Regular', 'Large'].map(size => (
              <button
                key={size}
                className={fontSize === size ? 'selected' : ''}
                onClick={() => setFontSize(size)}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <span className="settings-icon"><Utensils size={19} /></span>
          <div>
            <h2>Account Hub</h2>
            <p>Connect personal accounts and control exactly what Warik can access.</p>
          </div>
        </div>

        <div className="integration-provider">
          <div className="integration-provider-heading">
            <div>
              <strong>Swiggy</strong>
              <small>Food discovery and ordering integration</small>
            </div>

            <span className={`integration-badge ${connected ? 'connected' : ''}`}>
              {swiggyLoading
                ? 'Checking'
                : connected
                  ? 'Connected'
                  : 'Not connected'}
            </span>
          </div>

          <p className="integration-description">
            Connect through Swiggy authorization. Warik never asks for your password or OTP.
            Available tools and live access depend on your approved Swiggy MCP mode.
          </p>
          {swiggyStatus?.mode && (
            <p className="integration-meta">
              Connector mode: {swiggyStatus.mode}. {swiggyStatus.live_services_enabled
                ? 'Production services enabled.'
                : 'Live Swiggy services are not enabled in this deployment.'}
            </p>
          )}

          {swiggyStatus?.expires_at && connected && (
            <p className="integration-meta">
              Authorization expiry:{' '}
              {new Date(swiggyStatus.expires_at).toLocaleString()}
            </p>
          )}

          {swiggyStatus?.scope && connected && (
            <p className="integration-meta">
              Permission scope: {swiggyStatus.scope}
            </p>
          )}

          <div className="integration-actions">
            {connected ? (
              <button
                className="integration-button secondary"
                onClick={() => void disconnectSwiggy()}
                disabled={swiggyBusy || swiggyLoading}
              >
                <Unplug size={15} />
                {swiggyBusy ? 'Disconnecting...' : 'Disconnect'}
              </button>
            ) : (
              <button
                className="integration-button primary"
                onClick={() => void connectSwiggy()}
                disabled={swiggyBusy || swiggyLoading}
              >
                <ExternalLink size={15} />
                {swiggyBusy ? 'Connecting...' : 'Connect Swiggy'}
              </button>
            )}

            <button
              className="integration-refresh"
              onClick={() => void loadSwiggyStatus()}
              disabled={swiggyLoading || swiggyBusy}
              aria-label="Refresh connection status"
            >
              <RefreshCw size={15} />
            </button>
          </div>

          {swiggyMessage && (
            <p
              className={`integration-message ${swiggyMessageType}`}
              role="status"
            >
              {swiggyMessage}
            </p>
          )}
        </div>

        <div className="account-hub-divider" />
        <div className="integration-provider">
          <div className="integration-provider-heading">
            <div>
              <strong><Mail size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 6 }} />Google Gmail</strong>
              <small>Read-only personal context for travel and order confirmations</small>
            </div>
            <span className={`integration-badge ${gmailStatus?.connected ? 'connected' : ''}`}>
              {gmailLoading ? 'Checking' : gmailStatus?.connected ? 'Connected' : 'Not connected'}
            </span>
          </div>
          <p className="integration-description">
            When you request it, Warik searches a limited two-year window for travel,
            hotel, ride and food confirmations. It reads selected headers and a short
            Gmail snippet only; it does not fetch full message bodies or save scan results.
          </p>
          {gmailStatus?.email_address && gmailStatus.connected && (
            <p className="integration-meta">Connected account: {gmailStatus.email_address}</p>
          )}
          {gmailStatus?.scope && gmailStatus.connected && (
            <p className="integration-meta">Permission: Gmail read-only ({gmailStatus.scope})</p>
          )}
          <div className="integration-actions">
            {gmailStatus?.connected ? (
              <>
                <button className="integration-button primary" onClick={() => void scanGmail()} disabled={gmailBusy || gmailScanBusy || gmailLoading}>
                  <Search size={15} /> {gmailScanBusy ? 'Searching…' : 'Find my confirmations'}
                </button>
                <button className="integration-button secondary" onClick={() => void disconnectGmail()} disabled={gmailBusy || gmailScanBusy || gmailLoading}>
                  <Unplug size={15} /> {gmailBusy ? 'Disconnecting…' : 'Disconnect'}
                </button>
              </>
            ) : (
              <button className="integration-button primary" onClick={() => void connectGmail()} disabled={gmailBusy || gmailLoading}>
                <ExternalLink size={15} /> {gmailBusy ? 'Connecting…' : 'Connect Gmail'}
              </button>
            )}
            <button className="integration-refresh" onClick={() => void loadGmailStatus()} disabled={gmailLoading || gmailBusy} aria-label="Refresh Gmail status">
              <RefreshCw size={15} />
            </button>
          </div>
          {gmailMessage && <p className={`integration-message ${gmailMessageType}`} role="status">{gmailMessage}</p>}
          {gmailItems.length > 0 && (
            <div className="gmail-context-results">
              <div className="gmail-context-heading">Recent matching messages · not stored</div>
              {gmailItems.map(item => (
                <article className="gmail-context-item" key={item.message_id}>
                  <div className="gmail-context-meta">
                    <span>{item.category.replace('_', ' ')}</span>
                    <time>{item.received_at}</time>
                  </div>
                  <strong>{item.subject}</strong>
                  <small>{item.from}</small>
                  {item.snippet && <p>{item.snippet}</p>}
                </article>
              ))}
            </div>
          )}
          <p className="integration-footnote">
            Gmail access is read-only. Warik cannot send, delete, modify or archive email.
            Disconnecting removes the locally stored OAuth credentials.
          </p>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <span className="settings-icon"><Bell size={19} /></span>
          <div>
            <h2>Notifications</h2>
            <p>Manage how Warik keeps you updated.</p>
          </div>
        </div>

        <div className="setting-row">
          <div>
            <strong>In-app notifications</strong>
            <small>Updates about tasks and assistant activity.</small>
          </div>
          <span className="setting-status">Managed in app</span>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <span className="settings-icon"><ShieldCheck size={19} /></span>
          <div>
            <h2>Privacy & control</h2>
            <p>Your data and actions remain under your control.</p>
          </div>
        </div>

        <div className="setting-row">
          <div>
            <strong>Action approval</strong>
            <small>
              Warik should ask before taking supported external actions.
            </small>
          </div>
          <span className="setting-status">Protected</span>
        </div>
      </section>

      <p className="settings-footnote">
        Preferences are stored in this browser on this device.
      </p>
    </main>
  );
};
