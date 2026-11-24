/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {forwardRef, useEffect} from 'react';
import CustomPropTypes from '../custom_prop_types';
import {ensureScratchBaseStyles} from '../cdeadmin_ui/base/ScratchBaseStyles';

export const ModalContent = forwardRef(function ModalContent(
  {children, style, className, ...props},
  ref
) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <div
      ref={ref}
      className={['sr-modal-content', className].filter(Boolean).join(' ')}
      style={{
        height: '100%',
        width: '100%',
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--sr-surface, var(--sr-bg, inherit))',
        color: 'var(--sr-text, inherit)',
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
});
ModalContent.displayName = 'ModalContent';
ModalContent.propTypes = {
  children: CustomPropTypes.children,
  style: CustomPropTypes.style,
  className: CustomPropTypes.className,
};

export function ModalFooter({children, classNameRoot, style, ...props}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  return (
    <div
      className={[classNameRoot].filter(Boolean).join(' ') || undefined}
      style={style}
      {...props}
    >
      <div
        className="ModalContent-footer sr-dialog-footer"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          padding: '8px 12px',
          borderTop: '1px solid var(--sr-border, rgba(128, 128, 128, 0.25))',
          gap: 6,
        }}
      >
        {children}
      </div>
    </div>
  );
}

ModalFooter.propTypes = {
  children: CustomPropTypes.children,
  classNameRoot: CustomPropTypes.className,
  style: CustomPropTypes.style,
};
