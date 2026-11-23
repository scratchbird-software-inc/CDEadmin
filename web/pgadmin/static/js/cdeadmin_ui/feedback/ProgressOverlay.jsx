/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect} from 'react';
import PropTypes from 'prop-types';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';

export function ProgressOverlay({message, style, autoEllipsis = false, ...props}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  if (!message) {
    return null;
  }

  return (
    <div
      data-label="loader"
      role="status"
      aria-live="polite"
      aria-busy="true"
      style={{
        position: 'absolute',
        inset: 0,
        backgroundColor: 'var(--sr-overlay-bg, rgba(15, 23, 42, 0.45))',
        color: 'var(--sr-text, inherit)',
        zIndex: 1000,
        display: 'flex',
        ...(Array.isArray(style) ? Object.assign({}, ...style) : style),
      }}
      {...props}
    >
      <div
        className="CdeProgressOverlay-body Loader-loaderBody"
        style={{
          display: 'flex',
          alignItems: 'center',
          margin: 'auto',
          gap: 8,
          padding: '8px 14px',
          borderRadius: 8,
          backgroundColor: 'var(--sr-surface, rgba(255, 255, 255, 0.92))',
          border: '1px solid var(--sr-border, rgba(128, 128, 128, 0.25))',
        }}
      >
        <span
          aria-hidden="true"
          className="CdeProgressOverlay-icon Loader-icon sr-spinner"
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            border: '2px solid currentColor',
            borderRightColor: 'transparent',
            display: 'inline-block',
          }}
        />
        <span
          className="CdeProgressOverlay-message Loader-message"
          style={{fontSize: '0.9375rem'}}
        >
          {message}
          {autoEllipsis ? '...' : ''}
        </span>
      </div>
    </div>
  );
}

ProgressOverlay.propTypes = {
  message: PropTypes.string,
  style: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  autoEllipsis: PropTypes.bool,
};
