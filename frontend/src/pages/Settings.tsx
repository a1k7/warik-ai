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
} from 'lucide-react';
import {
  swiggyIntegrationApi,
  type SwiggyConnectionStatus,
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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const callbackResult = params.get('swiggy');

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
            <h2>Connected services</h2>
            <p>Manage the services Warik can work with.</p>
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
            Connect your Swiggy account to let Warik access supported food
            discovery features through Swiggy authorization.
          </p>

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

        <p className="integration-footnote">
          Warik never asks for your Swiggy password or OTP. Authorization
          takes place through Swiggy.
        </p>
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
