import React from 'react';
import { Info } from 'lucide-react';

interface Props {
  text?: string;
}

export const EthicalBanner: React.FC<Props> = ({ text }) => {
  return (
    <div className="ethical-banner" role="status" aria-label="Network indicator disclaimer">
      <Info size={18} className="ethical-banner-icon" />
      <div>
        <strong>Ethical &amp; Measurement Indicator: </strong>
        {text ||
          'Network-derived indicator of DNS request activity. Does not represent screen time or human engagement duration. Background processes, push notifications, and telemetry generate network requests independently of user activity.'}
      </div>
    </div>
  );
};
