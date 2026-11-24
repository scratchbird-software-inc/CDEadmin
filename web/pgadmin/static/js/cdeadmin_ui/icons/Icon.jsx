/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import cn from 'classnames';
import usePreferences from '../../../../preferences/static/js/store';
import {
  resolveIconDefinition,
  semanticEngineIconKey,
  semanticObjectIconKey,
} from './registry';

function detectDocumentTone() {
  if (typeof document !== 'undefined' && document.documentElement) {
    const cdeTheme = document.documentElement.getAttribute('data-cde-theme');
    if (cdeTheme === 'dark' || cdeTheme === 'light') {
      return cdeTheme;
    }
    const srScheme = document.documentElement.getAttribute('data-sr-scheme') || '';
    if (srScheme.includes('dark')) {
      return 'dark';
    }
    const rawTheme = document.documentElement.getAttribute('data-theme') || '';
    if (rawTheme.includes('dark')) {
      return 'dark';
    }
    if (rawTheme === 'light') {
      return 'light';
    }
  }
  if (typeof window !== 'undefined') {
    if (window.theme === 'dark' || window.theme === 'light') {
      return window.theme;
    }
  }
  return 'light';
}

function useResolvedIconTone(explicitTone, needsThemeTracking) {
  const [docTone, setDocTone] = useState(() => detectDocumentTone());

  useEffect(() => {
    if (!needsThemeTracking || explicitTone === 'light' || explicitTone === 'dark') {
      return undefined;
    }
    if (typeof document === 'undefined' || !document.documentElement) {
      return undefined;
    }
    const syncTone = () => {
      const next = detectDocumentTone();
      setDocTone((prev) => (prev === next ? prev : next));
    };
    syncTone();
    const observer =
      typeof MutationObserver === 'function'
        ? new MutationObserver(syncTone)
        : null;
    observer?.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-cde-theme', 'data-theme', 'data-sr-scheme'],
    });
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:scheme-changed', syncTone);
    }
    return () => {
      observer?.disconnect();
      if (typeof window !== 'undefined') {
        window.removeEventListener('scratchrobin:scheme-changed', syncTone);
      }
    };
  }, [explicitTone, needsThemeTracking]);

  if (explicitTone === 'dark' || explicitTone === 'light') {
    return explicitTone;
  }
  return docTone;
}

export function Icon({
  iconKey,
  label,
  decorative=false,
  className,
  size,
  tone,
  ...props
}) {
  usePreferences((state)=>state.version);
  const assignments = usePreferences.getState().getPreferences(
    'browser', 'icon_assignments'
  )?.value;
  const definition = resolveIconDefinition(iconKey, {label, assignments});
  const hasDarkVariant = Boolean(definition.darkComponent || definition.darkSvgUrl);
  const resolvedTone = useResolvedIconTone(tone, hasDarkVariant);
  const useDarkVariant = hasDarkVariant && resolvedTone === 'dark';
  const accessible = decorative ? {
    'aria-hidden': true,
  } : {
    role: 'img',
    'aria-label': label || definition.label,
  };
  const style = size ? {width: size, height: size, fontSize: size} :
    (definition.kind === 'component' || definition.kind === 'svg' ? {
      width: '1em',
      height: '1em',
      flexShrink: 0,
    } : undefined);

  if(definition.kind === 'component') {
    const SvgComponent =
      useDarkVariant && definition.darkComponent
        ? definition.darkComponent
        : definition.component;
    return <SvgComponent
      {...props}
      {...accessible}
      className={className}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : (label || definition.label)}
      data-icon-key={definition.key}
      data-icon-variant={hasDarkVariant ? (useDarkVariant ? 'dark' : 'light') : undefined}
      focusable="false"
      style={style}
    />;
  }
  if(definition.kind === 'svg') {
    const svgSrc =
      useDarkVariant && definition.darkSvgUrl
        ? definition.darkSvgUrl
        : definition.svgUrl;
    return <img
      {...props}
      {...accessible}
      className={className}
      src={svgSrc}
      alt={decorative ? '' : (label || definition.label)}
      data-icon-key={definition.key}
      data-icon-variant={hasDarkVariant ? (useDarkVariant ? 'dark' : 'light') : undefined}
      style={style}
    />;
  }
  return <i
    {...props}
    {...accessible}
    className={cn(className, definition.className)}
    data-icon-key={definition.key}
    style={style}
  />;
}

Icon.propTypes = {
  iconKey: PropTypes.string.isRequired,
  label: PropTypes.string,
  decorative: PropTypes.bool,
  className: PropTypes.string,
  size: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  tone: PropTypes.oneOf(['light', 'dark']),
};

export function EngineIcon({engineId, ...props}) {
  return <Icon iconKey={semanticEngineIconKey(engineId)} {...props} />;
}

EngineIcon.propTypes = {
  engineId: PropTypes.string.isRequired,
};

export function ObjectIcon({objectType, iconKey, ...props}) {
  return <Icon
    iconKey={iconKey || semanticObjectIconKey(objectType)}
    {...props}
  />;
}

ObjectIcon.propTypes = {
  objectType: PropTypes.string,
  iconKey: PropTypes.string,
};
