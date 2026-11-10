import { clsx } from 'clsx';

export const AIOrb = ({
  state = 'idle',
  size = 'lg',
}: {
  state?: 'idle' | 'listening' | 'thinking';
  size?: 'sm' | 'lg';
}) => (
  <div className={clsx('warik-orb-wrap', `orb-${size}`, `orb-${state}`)} aria-label={`Assistant ${state}`}>
    <div className="orb-halo halo-one"/>
    <div className="orb-halo halo-two"/>
    <div className="warik-orb">
      <div className="orb-shine"/>
      <div className="orb-core"/>
    </div>
    {size === 'lg' && <div className="orb-rings"><span/><span/><span/></div>}
  </div>
);
