/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import {Separator as BaseSeparator} from '@base-ui/react/separator';
import {ScratchScrollArea} from '../base/ScratchScrollArea';

function spacingPx(value) {
  const map = {compact: 4, standard: 8, comfortable: 16};
  if (map[value] !== undefined) return `${map[value]}px`;
  if (typeof value === 'number') return `${value * 8}px`;
  return value;
}

export function Box({
  component: Component = 'div',
  sx,
  style,
  display,
  flex,
  flexDirection,
  flexWrap,
  alignItems,
  justifyContent,
  gap,
  minWidth,
  maxWidth,
  minHeight,
  maxHeight,
  width,
  height,
  overflow,
  position,
  // Strip MUI-only theme props if passed directly
  // eslint-disable-next-line no-unused-vars
  bgcolor,
  // eslint-disable-next-line no-unused-vars
  borderColor,
  // eslint-disable-next-line no-unused-vars
  p,
  // eslint-disable-next-line no-unused-vars
  px,
  // eslint-disable-next-line no-unused-vars
  py,
  // eslint-disable-next-line no-unused-vars
  m,
  // eslint-disable-next-line no-unused-vars
  mt,
  // eslint-disable-next-line no-unused-vars
  mb,
  // eslint-disable-next-line no-unused-vars
  ml,
  // eslint-disable-next-line no-unused-vars
  mr,
  ...props
}) {
  const directStyle = {
    ...(display !== undefined ? {display} : {}),
    ...(flex !== undefined ? {flex} : {}),
    ...(flexDirection !== undefined ? {flexDirection} : {}),
    ...(flexWrap !== undefined ? {flexWrap} : {}),
    ...(alignItems !== undefined ? {alignItems} : {}),
    ...(justifyContent !== undefined ? {justifyContent} : {}),
    ...(gap !== undefined ? {gap: typeof gap === 'number' ? `${gap * 8}px` : spacingPx(gap)} : {}),
    ...(minWidth !== undefined ? {minWidth} : {}),
    ...(maxWidth !== undefined ? {maxWidth} : {}),
    ...(minHeight !== undefined ? {minHeight} : {}),
    ...(maxHeight !== undefined ? {maxHeight} : {}),
    ...(width !== undefined ? {width} : {}),
    ...(height !== undefined ? {height} : {}),
    ...(overflow !== undefined ? {overflow} : {}),
    ...(position !== undefined ? {position} : {}),
  };
  const sxStyle = sx && typeof sx === 'object' ? {
    ...(sx.display !== undefined ? {display: sx.display} : {}),
    ...(sx.flex !== undefined ? {flex: sx.flex} : {}),
    ...(sx.flexDirection !== undefined ? {flexDirection: sx.flexDirection} : {}),
    ...(sx.flexWrap !== undefined ? {flexWrap: sx.flexWrap} : {}),
    ...(sx.alignItems !== undefined ? {alignItems: sx.alignItems} : {}),
    ...(sx.justifyContent !== undefined ? {justifyContent: sx.justifyContent} : {}),
    ...(sx.gap !== undefined ? {gap: typeof sx.gap === 'number' ? `${sx.gap * 8}px` : sx.gap} : {}),
    ...(sx.p !== undefined ? {padding: typeof sx.p === 'number' ? `${sx.p * 8}px` : sx.p} : {}),
    ...(sx.px !== undefined ? {paddingInline: typeof sx.px === 'number' ? `${sx.px * 8}px` : sx.px} : {}),
    ...(sx.py !== undefined ? {paddingBlock: typeof sx.py === 'number' ? `${sx.py * 8}px` : sx.py} : {}),
    ...(sx.pt !== undefined ? {paddingTop: typeof sx.pt === 'number' ? `${sx.pt * 8}px` : sx.pt} : {}),
    ...(sx.pb !== undefined ? {paddingBottom: typeof sx.pb === 'number' ? `${sx.pb * 8}px` : sx.pb} : {}),
    ...(sx.pl !== undefined ? {paddingLeft: typeof sx.pl === 'number' ? `${sx.pl * 8}px` : sx.pl} : {}),
    ...(sx.pr !== undefined ? {paddingRight: typeof sx.pr === 'number' ? `${sx.pr * 8}px` : sx.pr} : {}),
    ...(sx.m !== undefined ? {margin: typeof sx.m === 'number' ? `${sx.m * 8}px` : sx.m} : {}),
    ...(sx.mt !== undefined ? {marginTop: typeof sx.mt === 'number' ? `${sx.mt * 8}px` : sx.mt} : {}),
    ...(sx.mb !== undefined ? {marginBottom: typeof sx.mb === 'number' ? `${sx.mb * 8}px` : sx.mb} : {}),
    ...(sx.ml !== undefined ? {marginLeft: sx.ml === 'auto' ? 'auto' : `${sx.ml * 8}px`} : {}),
    ...(sx.mr !== undefined ? {marginRight: sx.mr === 'auto' ? 'auto' : `${sx.mr * 8}px`} : {}),
    ...(sx.minWidth !== undefined ? {minWidth: sx.minWidth} : {}),
    ...(sx.maxWidth !== undefined ? {maxWidth: sx.maxWidth} : {}),
    ...(sx.minHeight !== undefined ? {minHeight: sx.minHeight} : {}),
    ...(sx.maxHeight !== undefined ? {maxHeight: sx.maxHeight} : {}),
    ...(sx.width !== undefined ? {width: sx.width} : {}),
    ...(sx.height !== undefined ? {height: sx.height} : {}),
    ...(sx.overflow !== undefined ? {overflow: sx.overflow} : {}),
    ...(sx.position !== undefined ? {position: sx.position} : {}),
  } : undefined;

  return <Component style={{...directStyle, ...sxStyle, ...style}} {...props} />;
}

Box.propTypes = {
  component: PropTypes.elementType,
  sx: PropTypes.object,
  style: PropTypes.object,
};

export function Stack({gap = 'standard', direction = 'column', style, ...props}) {
  return (
    <Box
      style={{
        display: 'flex',
        flexDirection: direction,
        gap: spacingPx(gap),
        ...style,
      }}
      {...props}
    />
  );
}

export function Grid({columns = 1, gap = 'standard', style, ...props}) {
  return (
    <Box
      style={{
        display: 'grid',
        gridTemplateColumns: typeof columns === 'number'
          ? `repeat(${columns}, minmax(0, 1fr))`
          : columns,
        gap: spacingPx(gap),
        ...style,
      }}
      {...props}
    />
  );
}

export function Panel({variant = 'flat', style, ...props}) {
  return (
    <Box
      style={{
        borderRadius: 'var(--sr-island-radius, 12px)',
        border: '1px solid var(--sr-border-default, #cbd5e1)',
        background: 'var(--sr-surface-card, #ffffff)',
        boxShadow: variant === 'raised' ? 'var(--sr-popup-shadow)' : 'none',
        ...style,
      }}
      {...props}
    />
  );
}

export function ScrollArea({label, orientation = 'both', sx, style, children, ...props}) {
  const sxStyle = sx && typeof sx === 'object' ? {
    ...(sx.flex !== undefined ? {flex: sx.flex} : {}),
    ...(sx.height !== undefined ? {height: sx.height} : {}),
    ...(sx.maxHeight !== undefined ? {maxHeight: sx.maxHeight} : {}),
    ...(sx.minHeight !== undefined ? {minHeight: sx.minHeight} : {}),
    ...(sx.width !== undefined ? {width: sx.width} : {}),
  } : undefined;
  const contentPadding = sx && typeof sx === 'object' ? {
    ...(sx.p !== undefined ? {padding: typeof sx.p === 'number' ? `${sx.p * 8}px` : sx.p} : {}),
    ...(sx.px !== undefined ? {paddingInline: typeof sx.px === 'number' ? `${sx.px * 8}px` : sx.px} : {}),
    ...(sx.py !== undefined ? {paddingBlock: typeof sx.py === 'number' ? `${sx.py * 8}px` : sx.py} : {}),
    ...(sx.pt !== undefined ? {paddingTop: typeof sx.pt === 'number' ? `${sx.pt * 8}px` : sx.pt} : {}),
    ...(sx.pb !== undefined ? {paddingBottom: typeof sx.pb === 'number' ? `${sx.pb * 8}px` : sx.pb} : {}),
    ...(sx.pl !== undefined ? {paddingLeft: typeof sx.pl === 'number' ? `${sx.pl * 8}px` : sx.pl} : {}),
    ...(sx.pr !== undefined ? {paddingRight: typeof sx.pr === 'number' ? `${sx.pr * 8}px` : sx.pr} : {}),
  } : null;
  const hasContentPadding = contentPadding && Object.keys(contentPadding).length > 0;
  return (
    <ScratchScrollArea
      label={label}
      orientation={orientation}
      style={{...sxStyle, ...style}}
      {...props}
    >
      {hasContentPadding ? <div style={{boxSizing: 'border-box', ...contentPadding}}>{children}</div> : children}
    </ScratchScrollArea>
  );
}

ScrollArea.propTypes = {
  label: PropTypes.string,
  orientation: PropTypes.oneOf(['vertical', 'horizontal', 'both']),
  sx: PropTypes.object,
  style: PropTypes.object,
  children: PropTypes.node,
};

export function Divider({orientation = 'horizontal', style, ...props}) {
  return (
    <BaseSeparator
      orientation={orientation}
      style={{
        backgroundColor: 'var(--sr-border-subtle, #e2e8f0)',
        ...(orientation === 'vertical'
          ? {width: 1, alignSelf: 'stretch', marginInline: 4}
          : {height: 1, width: '100%', marginBlock: 4}),
        ...style,
      }}
      {...props}
    />
  );
}

Divider.propTypes = {
  orientation: PropTypes.oneOf(['horizontal', 'vertical']),
  style: PropTypes.object,
};

export function Link({external = false, disabled = false, children, sx, style, ...props}) {
  const Tag = disabled ? 'span' : (props.component || 'a');
  const rest = {...props};
  delete rest.component;
  return (
    <Tag
      {...rest}
      href={disabled ? undefined : props.href}
      role={disabled ? 'link' : props.role}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : props.tabIndex}
      target={external ? '_blank' : props.target}
      rel={external ? 'noopener noreferrer' : props.rel}
      style={{
        color: disabled ? 'var(--sr-text-muted)' : 'var(--sr-accent)',
        textDecoration: 'underline',
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...(sx || {}),
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}

Stack.propTypes = {
  gap: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  direction: PropTypes.string,
  style: PropTypes.object,
};

Grid.propTypes = {
  columns: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  gap: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  style: PropTypes.object,
};

Panel.propTypes = {
  variant: PropTypes.oneOf(['flat', 'raised']),
  style: PropTypes.object,
};

ScrollArea.propTypes = {
  label: PropTypes.string,
  orientation: PropTypes.oneOf(['both', 'vertical', 'horizontal']),
  sx: PropTypes.object,
  style: PropTypes.object,
};

Link.propTypes = {
  external: PropTypes.bool,
  disabled: PropTypes.bool,
  children: PropTypes.node,
  component: PropTypes.elementType,
  href: PropTypes.string,
  role: PropTypes.string,
  tabIndex: PropTypes.number,
  sx: PropTypes.object,
  style: PropTypes.object,
  target: PropTypes.string,
  rel: PropTypes.string,
};
