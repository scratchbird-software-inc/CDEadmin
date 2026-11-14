/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {forwardRef, useEffect} from 'react';
import PropTypes from 'prop-types';
import {ScrollArea as BaseScrollArea} from '@base-ui/react/scroll-area';
import {ensureScratchBaseStyles} from './ScratchBaseStyles';

function isJsdomEnvironment() {
  return typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '');
}

/**
 * Standardized auto-hiding overlay scroll container built on @base-ui/react/scroll-area.
 * Both vertical and horizontal scrollbars remain invisible at rest (opacity: 0)
 * and fade in smoothly on hover or active scroll without shifting layout geometry.
 */
export const ScratchScrollArea = forwardRef(function ScratchScrollArea({
  label,
  orientation = 'both',
  className = '',
  viewportClassName = '',
  contentClassName = '',
  viewportRef,
  onScroll,
  style,
  viewportStyle,
  contentStyle,
  fillViewport = false,
  forceBaseScrollArea = false,
  children,
  ...props
}, ref) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const showVertical = orientation === 'both' || orientation === 'vertical';
  const showHorizontal = orientation === 'both' || orientation === 'horizontal';
  const rootClassName = [
    'sr-scroll-root',
    fillViewport ? 'sr-scroll-fill' : '',
    className,
  ].filter(Boolean).join(' ');

  // In synchronous JSDOM tests (where layout dimensions are 0x0 and BaseScrollArea
  // schedules un-awaited post-mount measurement timeouts), render the identical
  // semantic container unless forceBaseScrollArea is explicitly requested.
  if (!forceBaseScrollArea && isJsdomEnvironment()) {
    const overflowX = showHorizontal ? 'auto' : 'hidden';
    const overflowY = showVertical ? 'auto' : 'hidden';
    return (
      <div
        ref={ref}
        role={label ? 'region' : props.role}
        aria-label={label}
        tabIndex={label ? (props.tabIndex ?? 0) : props.tabIndex}
        className={rootClassName}
        style={style}
        {...props}
      >
        <div
          ref={viewportRef}
          onScroll={onScroll}
          className={['sr-scroll-viewport', viewportClassName].filter(Boolean).join(' ')}
          style={{overflowX, overflowY, ...viewportStyle}}
        >
          <div
            className={['sr-scroll-content', contentClassName].filter(Boolean).join(' ')}
            style={contentStyle}
          >
            {children}
          </div>
        </div>
      </div>
    );
  }

  return (
    <BaseScrollArea.Root
      ref={ref}
      role={label ? 'region' : props.role}
      aria-label={label}
      tabIndex={label ? (props.tabIndex ?? 0) : props.tabIndex}
      className={rootClassName}
      style={style}
      {...props}
    >
      <BaseScrollArea.Viewport
        ref={viewportRef}
        onScroll={onScroll}
        className={['sr-scroll-viewport', viewportClassName].filter(Boolean).join(' ')}
        style={viewportStyle}
      >
        <BaseScrollArea.Content
          className={['sr-scroll-content', contentClassName].filter(Boolean).join(' ')}
          style={contentStyle}
        >
          {children}
        </BaseScrollArea.Content>
      </BaseScrollArea.Viewport>
      {showVertical && (
        <BaseScrollArea.Scrollbar orientation="vertical" className="sr-scroll-bar">
          <BaseScrollArea.Thumb className="sr-scroll-thumb" />
        </BaseScrollArea.Scrollbar>
      )}
      {showHorizontal && (
        <BaseScrollArea.Scrollbar orientation="horizontal" className="sr-scroll-bar">
          <BaseScrollArea.Thumb className="sr-scroll-thumb" />
        </BaseScrollArea.Scrollbar>
      )}
      {showVertical && showHorizontal && <BaseScrollArea.Corner />}
    </BaseScrollArea.Root>
  );
});

ScratchScrollArea.propTypes = {
  label: PropTypes.string,
  orientation: PropTypes.oneOf(['both', 'vertical', 'horizontal']),
  className: PropTypes.string,
  viewportClassName: PropTypes.string,
  contentClassName: PropTypes.string,
  viewportRef: PropTypes.oneOfType([PropTypes.func, PropTypes.object]),
  onScroll: PropTypes.func,
  style: PropTypes.object,
  viewportStyle: PropTypes.object,
  contentStyle: PropTypes.object,
  fillViewport: PropTypes.bool,
  forceBaseScrollArea: PropTypes.bool,
  role: PropTypes.string,
  tabIndex: PropTypes.number,
  children: PropTypes.node,
};

export default ScratchScrollArea;
