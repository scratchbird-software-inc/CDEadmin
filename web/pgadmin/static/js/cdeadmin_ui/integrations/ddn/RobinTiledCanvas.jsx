/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../../primitives/Layout';

const CARD_HEADER_H = 38;
const FIELD_ROW_H = 22;

const DEFAULT_PALETTE = Object.freeze({
  conceptual: {
    header_bg: '#fef3c7',
    header_fg: '#78350f',
    border: '#d97706',
    badge_bg: '#fde68a',
  },
  logical: {
    header_bg: '#e0f2fe',
    header_fg: '#0c4a6e',
    border: '#0284c7',
    badge_bg: '#bae6fd',
  },
  physical: {
    header_bg: '#dbeafe',
    header_fg: '#1e3a8a',
    border: '#2563eb',
    badge_bg: '#bfdbfe',
  },
  deployment: {
    header_bg: '#dcfce7',
    header_fg: '#14532d',
    border: '#16a34a',
    badge_bg: '#bbf7d0',
  },
});

const CHART_COLORS = [
  '#2563eb',
  '#0284c7',
  '#0d9488',
  '#16a34a',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#db2777',
];

function escapeXml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function unquoteDdnToken(raw) {
  const s = String(raw || '').trim();
  if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) {
    return s.slice(1, -1).replace(/\\"/g, '"');
  }
  return s;
}

/**
 * Lightweight local scene compiler used ONLY when the Python host endpoint
 * (`/cdeadmin/api/ddn/scene`) is absent — e.g. in offline Jest unit tests.
 * Production ScratchRobin sessions always stream host-compiled scenes & tiles.
 */
export function buildLocalFallbackScene(ddnText, requestedView = '') {
  const lines = String(ddnText || '').split(/\r?\n/);
  const views = [];
  const elements = new Map();
  const relations = [];

  let currentShorthandView = null;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('//')) continue;
    const indent = line.length - line.trimStart().length;

    if (indent === 0) {
      currentShorthandView = null;
      const viewMatch = stripped.match(/^view\s+("[^"]+"|\S+)\s+as\s+("[^"]+"|\S+)/);
      if (viewMatch) {
        const vid = unquoteDdnToken(viewMatch[1]);
        const vprof = unquoteDdnToken(viewMatch[2]);
        views.push({id: vid, name: vid, profile: vprof});
        continue;
      }
      const shortMatch = stripped.match(
        /^(erd|architecture|dataflow|flowchart|network|hierarchy|matrix|table|wireframe)\s+("[^"]+"|\S+)/
      );
      if (shortMatch) {
        const vid = unquoteDdnToken(shortMatch[2]);
        currentShorthandView = {id: vid, name: vid, profile: `${shortMatch[1]}@1`};
        views.push(currentShorthandView);
        continue;
      }
      const elMatch = stripped.match(/^element\s+("[^"]+"|\S+)(?:\s+role\s+(\S+))?/);
      if (elMatch) {
        const eid = unquoteDdnToken(elMatch[1]);
        const role = elMatch[2] || 'entity';
        elements.set(eid, {
          id: eid,
          name: eid,
          role,
          fields: [],
        });
        continue;
      }
      const relMatch = stripped.match(
        /^relation\s+("[^"]+"|\S+)\s+from\s+("[^"]+"|\S+)\s+to\s+("[^"]+"|\S+)/
      );
      if (relMatch) {
        relations.push({
          id: unquoteDdnToken(relMatch[1]),
          source: unquoteDdnToken(relMatch[2]),
          target: unquoteDdnToken(relMatch[3]),
          title: '',
        });
        continue;
      }
    } else if (
      currentShorthandView &&
      indent === 4 &&
      stripped !== 'with' &&
      !stripped.startsWith('id ') &&
      !stripped.startsWith('title ')
    ) {
      const tok = unquoteDdnToken(stripped.split(/\s+/)[0]);
      if (tok && !elements.has(tok)) {
        elements.set(tok, {id: tok, name: tok, role: 'entity', fields: []});
      }
    } else if (indent >= 8 && stripped.startsWith('title ')) {
      const tval = unquoteDdnToken(stripped.slice(6));
      if (views.length && currentShorthandView) {
        currentShorthandView.name = tval || currentShorthandView.name;
      }
    }
  }

  if (!views.length) {
    views.push({id: 'main', name: 'Main Diagram', profile: 'ddn@1'});
  }
  const chosenView =
    views.find((v) => v.id === requestedView) || views[0];

  const topNodes = Array.from(elements.values()).filter(
    (e) => !['field', 'index', 'constraint', 'ref', 'record'].includes(e.role)
  );
  const cols = Math.max(1, Math.ceil(Math.sqrt(Math.max(1, topNodes.length))));
  const nodes = topNodes.map((n, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const width = 264;
    const height = 76;
    return {
      id: n.id,
      name: n.name,
      role: n.role || 'table',
      level: 'physical',
      palette: DEFAULT_PALETTE.physical,
      width,
      height,
      x: 48 + col * 360,
      y: 48 + row * 160,
      fields: n.fields || [],
      hidden_field_count: 0,
    };
  });

  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const edges = relations
    .filter((r) => nodeById.has(r.source) && nodeById.has(r.target))
    .map((r) => {
      const s = nodeById.get(r.source);
      const t = nodeById.get(r.target);
      const sx = s.x + s.width;
      const sy = s.y + 38;
      const tx = t.x;
      const ty = t.y + 38;
      const mx = Math.round((sx + tx) / 2);
      return {
        id: r.id,
        source: r.source,
        target: r.target,
        display_label: r.title || '',
        points: [
          {x: sx, y: sy},
          {x: mx, y: sy},
          {x: mx, y: ty},
          {x: tx, y: ty},
        ],
        label_pos: {x: mx, y: Math.round((sy + ty) / 2), w: 56},
        source_mark: 'many',
        target_mark: 'one',
        dashed: false,
        bounds: {
          min_x: Math.min(sx, tx),
          min_y: Math.min(sy, ty),
          max_x: Math.max(sx, tx),
          max_y: Math.max(sy, ty),
        },
      };
    });

  const maxX = nodes.length
    ? Math.max(...nodes.map((n) => n.x + n.width)) + 64
    : 720;
  const maxY = nodes.length
    ? Math.max(...nodes.map((n) => n.y + n.height)) + 64
    : 420;
  const bounds = {
    min_x: 0,
    min_y: 0,
    max_x: maxX,
    max_y: maxY,
    width: maxX,
    height: maxY,
  };
  const tile0 = {
    tx: 0,
    ty: 0,
    coord: '0:0',
    tile_key: 'local-0-0',
    bounds,
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
    zones: [],
    widgets: [],
  };

  return {
    ddn_sha256: 'local-fallback',
    view_id: chosenView.id,
    profile: chosenView.profile || 'ddn@1',
    algorithm: 'scratchrobin-local-fallback@1',
    tile_size: 1024,
    canvas_bounds: bounds,
    views,
    summary: {
      view_count: views.length,
      node_count: nodes.length,
      edge_count: edges.length,
      widget_count: 0,
      tile_count: 1,
    },
    diagnostics: [],
    minimap: nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      w: n.width,
      h: n.height,
      color: '#2563eb',
    })),
    tile_index: [
      {
        tx: 0,
        ty: 0,
        coord: '0:0',
        tile_key: 'local-0-0',
        bounds,
        node_count: nodes.length,
        edge_count: edges.length,
      },
    ],
    loaded_tiles: {'0:0': tile0},
  };
}

function collectMergedTileItems(tilesMap) {
  const nodesMap = new Map();
  const edgesMap = new Map();
  const zonesMap = new Map();
  const widgetsMap = new Map();
  for (const tile of Object.values(tilesMap || {})) {
    if (!tile) continue;
    for (const z of tile.zones || []) {
      if (!zonesMap.has(z.id)) zonesMap.set(z.id, z);
    }
    for (const n of tile.nodes || []) {
      if (!nodesMap.has(n.id)) nodesMap.set(n.id, n);
    }
    for (const e of tile.edges || []) {
      if (!edgesMap.has(e.id)) edgesMap.set(e.id, e);
    }
    for (const w of tile.widgets || []) {
      if (!widgetsMap.has(w.id)) widgetsMap.set(w.id, w);
    }
  }
  return {
    zones: Array.from(zonesMap.values()),
    nodes: Array.from(nodesMap.values()),
    edges: Array.from(edgesMap.values()),
    widgets: Array.from(widgetsMap.values()),
  };
}

/**
 * Deterministic standalone SVG serializer for presentation snapshots and Export SVG.
 */
export function serializeRobinSceneToSvg(scene, tilesOverride = null) {
  if (!scene) {
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"></svg>';
  }
  const cb = scene.canvas_bounds || {
    min_x: 0,
    min_y: 0,
    width: 800,
    height: 520,
  };
  const merged = collectMergedTileItems(tilesOverride || scene.loaded_tiles);
  const vx = cb.min_x ?? 0;
  const vy = cb.min_y ?? 0;
  const vw = Math.max(320, cb.width || 800);
  const vh = Math.max(220, cb.height || 520);

  const out = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vx} ${vy} ${vw} ${vh}" width="${Math.round(vw)}" height="${Math.round(vh)}" font-family="Inter, system-ui, -apple-system, sans-serif">`,
    '<defs>',
    '<marker id="sr-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#475569"/></marker>',
    '<marker id="sr-one" viewBox="0 0 10 12" refX="9" refY="6" markerWidth="8" markerHeight="9" orient="auto"><line x1="6" y1="1" x2="6" y2="11" stroke="#334155" stroke-width="1.6"/></marker>',
    '<marker id="sr-many" viewBox="0 0 14 12" refX="1" refY="6" markerWidth="10" markerHeight="9" orient="auto"><path d="M 13 6 L 1 1 M 13 6 L 1 6 M 13 6 L 1 11" stroke="#334155" stroke-width="1.4" fill="none"/></marker>',
    '</defs>',
    `<rect x="${vx}" y="${vy}" width="${vw}" height="${vh}" fill="#f8fafc"/>`,
  ];

  for (const z of merged.zones) {
    out.push(
      `<g><rect x="${z.x}" y="${z.y}" width="${z.width}" height="${z.height}" rx="10" fill="#ffffff" fill-opacity="0.7" stroke="${escapeXml(z.border || '#94a3b8')}" stroke-dasharray="6 4" stroke-width="1.5"/>`,
      `<rect x="${z.x}" y="${z.y}" width="${z.width}" height="32" rx="10" fill="${escapeXml(z.header_bg || '#e2e8f0')}"/>`,
      `<text x="${z.x + 16}" y="${z.y + 21}" font-size="12" font-weight="700" fill="${escapeXml(z.header_fg || '#0f172a')}">${escapeXml(z.label)}</text></g>`
    );
  }

  for (const e of merged.edges) {
    const pts = e.points || [];
    if (pts.length < 2) continue;
    const dCmd = `M ${pts.map((p) => `${p.x} ${p.y}`).join(' L ')}`;
    const dash = e.dashed ? ' stroke-dasharray="5 4"' : '';
    const mStart = e.source_mark === 'many' ? ' marker-start="url(#sr-many)"' : '';
    const mEnd =
      e.target_mark === 'arrow'
        ? ' marker-end="url(#sr-arrow)"'
        : ' marker-end="url(#sr-one)"';
    out.push(
      `<path d="${dCmd}" fill="none" stroke="#475569" stroke-width="1.5" stroke-linejoin="round"${dash}${mStart}${mEnd}/>`
    );
    if (e.display_label && e.label_pos) {
      const pw = e.label_pos.w || 64;
      out.push(
        `<rect x="${(e.label_pos.x - pw / 2).toFixed(1)}" y="${(e.label_pos.y - 9).toFixed(1)}" width="${pw.toFixed(1)}" height="18" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>`,
        `<text x="${e.label_pos.x.toFixed(1)}" y="${(e.label_pos.y + 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="#334155">${escapeXml(e.display_label)}</text>`
      );
    }
  }

  for (const n of merged.nodes) {
    const pal = n.palette || DEFAULT_PALETTE.physical;
    out.push(
      `<g><rect x="${n.x}" y="${n.y}" width="${n.width}" height="${n.height}" rx="6" fill="#ffffff" stroke="${escapeXml(pal.border)}" stroke-width="1.5"/>`,
      `<rect x="${n.x}" y="${n.y}" width="${n.width}" height="${CARD_HEADER_H}" rx="6" fill="${escapeXml(pal.header_bg)}"/>`,
      `<line x1="${n.x}" y1="${n.y + CARD_HEADER_H}" x2="${n.x + n.width}" y2="${n.y + CARD_HEADER_H}" stroke="${escapeXml(pal.border)}" stroke-width="1"/>`,
      `<text x="${n.x + 12}" y="${n.y + 23}" font-size="12.5" font-weight="700" fill="${escapeXml(pal.header_fg)}">${escapeXml(n.name)}</text>`
    );
    for (const f of n.fields || []) {
      const fy = n.y + (f.port_y || CARD_HEADER_H + 14) + 4;
      const prefix = f.is_pk ? 'PK ' : f.is_fk ? 'FK ' : '';
      out.push(
        `<text x="${n.x + 12}" y="${fy.toFixed(1)}" font-size="11" fill="#1e293b">${escapeXml(prefix + f.name)}</text>`
      );
      if (f.datatype) {
        out.push(
          `<text x="${n.x + n.width - 10}" y="${fy.toFixed(1)}" text-anchor="end" font-size="10.5" fill="#64748b">${escapeXml(String(f.datatype).slice(0, 22))}</text>`
        );
      }
    }
    out.push('</g>');
  }

  for (const w of merged.widgets) {
    out.push(
      `<g><rect x="${w.x}" y="${w.y}" width="${w.width}" height="${w.height}" rx="8" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5"/>`,
      `<rect x="${w.x}" y="${w.y}" width="${w.width}" height="34" rx="8" fill="#f1f5f9"/>`,
      `<text x="${w.x + 14}" y="${w.y + 22}" font-size="12.5" font-weight="700" fill="#0f172a">${escapeXml(w.title || w.id)}</text></g>`
    );
  }

  if (!merged.nodes.length && !merged.widgets.length) {
    out.push(
      `<text x="${vx + vw / 2}" y="${vy + vh / 2}" text-anchor="middle" font-size="13" fill="#64748b">${escapeXml(scene.view_id || 'Empty model view')}</text>`
    );
  }

  out.push('</svg>');
  return out.join('');
}

function DataGridWidgetSvg({widget}) {
  const {x, y, width, height, title, headers = [], rows = []} = widget;
  const colCount = Math.max(1, headers.length);
  const colW = (width - 24) / colCount;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={8}
        fill="#ffffff"
        stroke="#94a3b8"
        strokeWidth={1.5}
      />
      <rect x={x} y={y} width={width} height={38} rx={8} fill="#dbeafe" />
      <text
        x={x + 16}
        y={y + 24}
        fontSize={13}
        fontWeight={700}
        fill="#1e3a8a"
      >
        {title}
      </text>
      <rect
        x={x + 12}
        y={y + 46}
        width={width - 24}
        height={28}
        rx={4}
        fill="#f1f5f9"
      />
      {headers.map((h, ci) => (
        <text
          key={`h-${ci}`}
          x={x + 20 + ci * colW}
          y={y + 64}
          fontSize={11}
          fontWeight={700}
          fill="#334155"
        >
          {String(h).slice(0, 24)}
        </text>
      ))}
      {rows.map((row, ri) => {
        const ry = y + 78 + ri * 34;
        if (ry + 28 > y + height) return null;
        return (
          <g key={`r-${ri}`}>
            {ri % 2 === 1 && (
              <rect
                x={x + 12}
                y={ry}
                width={width - 24}
                height={32}
                fill="#f8fafc"
              />
            )}
            <line
              x1={x + 12}
              y1={ry + 32}
              x2={x + width - 12}
              y2={ry + 32}
              stroke="#e2e8f0"
              strokeWidth={1}
            />
            {(row || []).map((cell, ci) => {
              const text = String(cell ?? '');
              const isBadge =
                ci > 0 && text !== '—' && widget.id === 'cube-usage-matrix-widget';
              return isBadge ? (
                <g key={`c-${ri}-${ci}`}>
                  <rect
                    x={x + 18 + ci * colW}
                    y={ry + 6}
                    width={Math.min(colW - 14, Math.max(66, text.length * 6.8 + 14))}
                    height={20}
                    rx={10}
                    fill={text.includes('inactive') ? '#fef3c7' : '#dcfce7'}
                    stroke={text.includes('inactive') ? '#d97706' : '#16a34a'}
                    strokeWidth={1}
                  />
                  <text
                    x={x + 26 + ci * colW}
                    y={ry + 20}
                    fontSize={10.5}
                    fontWeight={600}
                    fill={text.includes('inactive') ? '#92400e' : '#166534'}
                  >
                    {text.slice(0, 22)}
                  </text>
                </g>
              ) : (
                <text
                  key={`c-${ri}-${ci}`}
                  x={x + 20 + ci * colW}
                  y={ry + 20}
                  fontSize={11}
                  fontWeight={ci === 0 ? 600 : 400}
                  fill={text === '—' ? '#94a3b8' : '#1e293b'}
                >
                  {text.slice(0, 28)}
                </text>
              );
            })}
          </g>
        );
      })}
    </g>
  );
}

function BiCardWidgetSvg({widget}) {
  const {
    x,
    y,
    width,
    height,
    title,
    card_type: cardType,
    chart_type: chartType = 'bar',
    markdown,
    rows = [],
  } = widget;

  const padX = x + 18;
  const bodyY = y + 48;
  const bodyW = Math.max(120, width - 36);
  const bodyH = Math.max(56, height - 64);

  const numericPairs = rows
    .map((r, idx) => {
      if (Array.isArray(r)) {
        const label = String(r[0] ?? `Row ${idx + 1}`);
        const num = Number(r[1] ?? r[r.length - 1] ?? 0);
        return {label, value: Number.isFinite(num) ? num : idx + 1};
      }
      if (r && typeof r === 'object') {
        const vals = Object.values(r);
        const label = String(vals[0] ?? `Row ${idx + 1}`);
        const num = Number(vals[1] ?? vals[vals.length - 1] ?? 0);
        return {label, value: Number.isFinite(num) ? num : idx + 1};
      }
      return {label: `Item ${idx + 1}`, value: Number(r) || idx + 1};
    })
    .slice(0, 12);

  const maxVal = Math.max(
    1,
    ...numericPairs.map((p) => Math.abs(p.value))
  );

  let content = null;
  if (cardType === 'text' || (markdown && !rows.length)) {
    const lines = String(markdown || title || '')
      .replace(/^#+\s*/gm, '')
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(0, 6);
    content = (
      <g>
        {lines.map((ln, idx) => (
          <text
            key={idx}
            x={padX}
            y={bodyY + 18 + idx * 20}
            fontSize={idx === 0 ? 13 : 11.5}
            fontWeight={idx === 0 ? 700 : 400}
            fill={idx === 0 ? '#0f172a' : '#475569'}
          >
            {ln.slice(0, Math.max(28, Math.floor(bodyW / 6.8)))}
          </text>
        ))}
      </g>
    );
  } else if (chartType === 'metric' || chartType === 'kpi') {
    const primary = numericPairs[0] || {label: 'Total', value: 0};
    content = (
      <g>
        <text
          x={padX}
          y={bodyY + Math.min(54, bodyH * 0.55)}
          fontSize={28}
          fontWeight={800}
          fill="#1d4ed8"
        >
          {primary.value.toLocaleString()}
        </text>
        <text
          x={padX}
          y={bodyY + Math.min(78, bodyH * 0.82)}
          fontSize={12}
          fill="#64748b"
        >
          {primary.label}
        </text>
      </g>
    );
  } else if (
    (chartType === 'line' || chartType === 'area') &&
    numericPairs.length >= 2
  ) {
    const chartH = Math.max(48, bodyH - 28);
    const stepX = bodyW / Math.max(1, numericPairs.length - 1);
    const pts = numericPairs.map((p, idx) => ({
      px: padX + idx * stepX,
      py: bodyY + chartH - (Math.max(0, p.value) / maxVal) * (chartH - 16),
      ...p,
    }));
    const linePath = `M ${pts.map((p) => `${p.px.toFixed(1)} ${p.py.toFixed(1)}`).join(' L ')}`;
    const areaPath = `${linePath} L ${pts[pts.length - 1].px.toFixed(1)} ${(bodyY + chartH).toFixed(1)} L ${pts[0].px.toFixed(1)} ${(bodyY + chartH).toFixed(1)} Z`;
    content = (
      <g>
        <line
          x1={padX}
          y1={bodyY + chartH}
          x2={padX + bodyW}
          y2={bodyY + chartH}
          stroke="#cbd5e1"
          strokeWidth={1}
        />
        {chartType === 'area' && (
          <path d={areaPath} fill="#3b82f6" fillOpacity={0.16} />
        )}
        <path
          d={linePath}
          fill="none"
          stroke="#2563eb"
          strokeWidth={2.4}
          strokeLinejoin="round"
        />
        {pts.map((p, idx) => (
          <g key={idx}>
            <circle cx={p.px} cy={p.py} r={3.5} fill="#1d4ed8" />
            {idx % Math.max(1, Math.ceil(pts.length / 6)) === 0 && (
              <text
                x={p.px}
                y={bodyY + chartH + 16}
                textAnchor="middle"
                fontSize={10}
                fill="#64748b"
              >
                {p.label.slice(0, 10)}
              </text>
            )}
          </g>
        ))}
      </g>
    );
  } else if (chartType === 'pie' && numericPairs.length >= 1) {
    const total = Math.max(
      1,
      numericPairs.reduce((acc, p) => acc + Math.max(0, p.value), 0)
    );
    const cx = padX + Math.min(90, bodyH * 0.45);
    const cy = bodyY + bodyH * 0.48;
    const radius = Math.max(28, Math.min(72, bodyH * 0.4));
    let angle = -Math.PI / 2;
    content = (
      <g>
        {numericPairs.slice(0, 6).map((p, idx) => {
          const slice = (Math.max(0, p.value) / total) * Math.PI * 2;
          const x1 = cx + radius * Math.cos(angle);
          const y1 = cy + radius * Math.sin(angle);
          angle += slice;
          const x2 = cx + radius * Math.cos(angle);
          const y2 = cy + radius * Math.sin(angle);
          const large = slice > Math.PI ? 1 : 0;
          const d = `M ${cx} ${cy} L ${x1.toFixed(1)} ${y1.toFixed(1)} A ${radius} ${radius} 0 ${large} 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z`;
          return (
            <path
              key={idx}
              d={d}
              fill={CHART_COLORS[idx % CHART_COLORS.length]}
              stroke="#ffffff"
              strokeWidth={1.5}
            />
          );
        })}
        {numericPairs.slice(0, 6).map((p, idx) => (
          <g key={`leg-${idx}`}>
            <rect
              x={cx + radius + 24}
              y={bodyY + 8 + idx * 20}
              width={10}
              height={10}
              rx={2}
              fill={CHART_COLORS[idx % CHART_COLORS.length]}
            />
            <text
              x={cx + radius + 40}
              y={bodyY + 17 + idx * 20}
              fontSize={10.5}
              fill="#334155"
            >
              {`${p.label.slice(0, 18)} (${p.value.toLocaleString()})`}
            </text>
          </g>
        ))}
      </g>
    );
  } else if (
    chartType === 'table' ||
    cardType === 'metric_panel'
  ) {
    content = (
      <g>
        {numericPairs.slice(0, Math.floor(bodyH / 24)).map((p, idx) => (
          <g key={idx}>
            <line
              x1={padX}
              y1={bodyY + (idx + 1) * 24}
              x2={padX + bodyW}
              y2={bodyY + (idx + 1) * 24}
              stroke="#f1f5f9"
            />
            <text
              x={padX + 4}
              y={bodyY + idx * 24 + 16}
              fontSize={11}
              fill="#1e293b"
            >
              {p.label.slice(0, 34)}
            </text>
            <text
              x={padX + bodyW - 4}
              y={bodyY + idx * 24 + 16}
              textAnchor="end"
              fontSize={11}
              fontWeight={600}
              fill="#0f172a"
            >
              {p.value.toLocaleString()}
            </text>
          </g>
        ))}
      </g>
    );
  } else {
    // Crisp Bar Chart default
    const bars = numericPairs.length
      ? numericPairs
      : [
        {label: 'Q1', value: 42},
        {label: 'Q2', value: 68},
        {label: 'Q3', value: 55},
        {label: 'Q4', value: 89},
      ];
    const localMax = Math.max(1, ...bars.map((b) => Math.abs(b.value)));
    const chartH = Math.max(48, bodyH - 26);
    const slotW = bodyW / Math.max(1, bars.length);
    const barW = Math.max(10, Math.min(48, slotW * 0.64));
    content = (
      <g>
        <line
          x1={padX}
          y1={bodyY + chartH}
          x2={padX + bodyW}
          y2={bodyY + chartH}
          stroke="#cbd5e1"
          strokeWidth={1}
        />
        {bars.map((b, idx) => {
          const bh = Math.max(4, (Math.max(0, b.value) / localMax) * (chartH - 18));
          const bx = padX + idx * slotW + (slotW - barW) / 2;
          const by = bodyY + chartH - bh;
          return (
            <g key={idx}>
              <rect
                x={bx}
                y={by}
                width={barW}
                height={bh}
                rx={4}
                fill={CHART_COLORS[idx % CHART_COLORS.length]}
              />
              <text
                x={bx + barW / 2}
                y={by - 4}
                textAnchor="middle"
                fontSize={9.5}
                fontWeight={600}
                fill="#334155"
              >
                {b.value >= 1000 ? `${(b.value / 1000).toFixed(1)}k` : b.value}
              </text>
              <text
                x={bx + barW / 2}
                y={bodyY + chartH + 14}
                textAnchor="middle"
                fontSize={9.5}
                fill="#64748b"
              >
                {b.label.slice(0, 10)}
              </text>
            </g>
          );
        })}
      </g>
    );
  }

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={10}
        fill="#ffffff"
        stroke="#cbd5e1"
        strokeWidth={1.5}
      />
      <rect x={x} y={y} width={width} height={36} rx={10} fill="#f8fafc" />
      <line
        x1={x}
        y1={y + 36}
        x2={x + width}
        y2={y + 36}
        stroke="#e2e8f0"
        strokeWidth={1}
      />
      <text
        x={x + 16}
        y={y + 23}
        fontSize={12.5}
        fontWeight={700}
        fill="#0f172a"
      >
        {String(title || '').slice(0, Math.max(24, Math.floor(width / 8)))}
      </text>
      <text
        x={x + width - 14}
        y={y + 22}
        textAnchor="end"
        fontSize={10}
        fontWeight={600}
        fill="#64748b"
      >
        {String(chartType || cardType || 'chart').toUpperCase()}
      </text>
      {content}
    </g>
  );
}

function ScreenFrameWidgetSvg({widget}) {
  const {
    x,
    y,
    width,
    height,
    title,
    form_reference: formRef,
    controls = [],
    regions = [],
  } = widget;
  const headerH = 38;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={10}
        fill="#ffffff"
        stroke="#64748b"
        strokeWidth={1.8}
      />
      <rect x={x} y={y} width={width} height={headerH} rx={10} fill="#1e293b" />
      <circle cx={x + 18} cy={y + 19} r={5} fill="#ef4444" />
      <circle cx={x + 34} cy={y + 19} r={5} fill="#f59e0b" />
      <circle cx={x + 50} cy={y + 19} r={5} fill="#22c55e" />
      <text
        x={x + 70}
        y={y + 24}
        fontSize={13}
        fontWeight={700}
        fill="#f8fafc"
      >
        {title}
      </text>
      {formRef && (
        <text
          x={x + width - 14}
          y={y + 23}
          textAnchor="end"
          fontSize={10.5}
          fontWeight={600}
          fill="#93c5fd"
        >
          {formRef}
        </text>
      )}

      {controls.map((ctrl) => {
        const b = ctrl.bounds || {x: 24, y: 24, width: 220, height: 36};
        const cx = x + Number(b.x || 0);
        const cy = y + headerH + Number(b.y || 0);
        const cw = Math.max(48, Number(b.width || 180));
        const ch = Math.max(24, Number(b.height || 34));
        const role = ctrl.role || 'ui.input';

        if (role === 'ui.button') {
          return (
            <g key={ctrl.id}>
              <rect
                x={cx}
                y={cy}
                width={cw}
                height={ch}
                rx={6}
                fill="#2563eb"
              />
              <text
                x={cx + cw / 2}
                y={cy + ch / 2 + 4}
                textAnchor="middle"
                fontSize={11.5}
                fontWeight={600}
                fill="#ffffff"
              >
                {ctrl.name || 'Action'}
              </text>
            </g>
          );
        }
        if (role === 'ui.tabs') {
          const tabs =
            ctrl.options && ctrl.options.length
              ? ctrl.options
              : ['Details', 'Accounting', 'Connections'];
          return (
            <g key={ctrl.id}>
              <line
                x1={cx}
                y1={cy + ch}
                x2={cx + cw}
                y2={cy + ch}
                stroke="#cbd5e1"
                strokeWidth={1.5}
              />
              {tabs.slice(0, 6).map((tab, ti) => (
                <g key={ti}>
                  <rect
                    x={cx + ti * 124}
                    y={cy + 2}
                    width={116}
                    height={ch - 2}
                    rx={5}
                    fill={ti === 0 ? '#eff6ff' : '#f8fafc'}
                    stroke={ti === 0 ? '#2563eb' : '#cbd5e1'}
                    strokeWidth={1}
                  />
                  <text
                    x={cx + ti * 124 + 58}
                    y={cy + ch / 2 + 4}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={ti === 0 ? 700 : 500}
                    fill={ti === 0 ? '#1d4ed8' : '#475569'}
                  >
                    {String(tab).slice(0, 16)}
                  </text>
                </g>
              ))}
            </g>
          );
        }
        if (role === 'ui.grid') {
          const cols =
            ctrl.columns && ctrl.columns.length
              ? ctrl.columns
              : ['ID', 'Name', 'Status', 'Modified'];
          const gColW = cw / Math.max(1, cols.length);
          return (
            <g key={ctrl.id}>
              <rect
                x={cx}
                y={cy}
                width={cw}
                height={ch}
                rx={6}
                fill="#ffffff"
                stroke="#94a3b8"
                strokeWidth={1.2}
              />
              <rect
                x={cx}
                y={cy}
                width={cw}
                height={28}
                rx={6}
                fill="#f1f5f9"
              />
              {cols.slice(0, 8).map((col, ci) => (
                <text
                  key={ci}
                  x={cx + 10 + ci * gColW}
                  y={cy + 18}
                  fontSize={10.5}
                  fontWeight={700}
                  fill="#334155"
                >
                  {String(col.name || col).slice(0, 18)}
                </text>
              ))}
              {[1, 2, 3].map((ri) =>
                cy + 28 + ri * 26 < cy + ch ? (
                  <line
                    key={ri}
                    x1={cx}
                    y1={cy + 28 + ri * 26}
                    x2={cx + cw}
                    y2={cy + 28 + ri * 26}
                    stroke="#f1f5f9"
                  />
                ) : null
              )}
              {ctrl.binding_ref && (
                <text
                  x={cx + cw - 8}
                  y={cy + ch - 8}
                  textAnchor="end"
                  fontSize={9.5}
                  fontWeight={600}
                  fill="#0284c7"
                >
                  {`⇢ ${String(ctrl.binding_ref).slice(-36)}`}
                </text>
              )}
            </g>
          );
        }
        if (role === 'ui.label') {
          return (
            <text
              key={ctrl.id}
              x={cx}
              y={cy + 18}
              fontSize={12.5}
              fontWeight={700}
              fill="#0f172a"
            >
              {ctrl.name}
            </text>
          );
        }
        return (
          <g key={ctrl.id}>
            <text
              x={cx}
              y={cy - 4}
              fontSize={10}
              fontWeight={600}
              fill="#475569"
            >
              {ctrl.name}
            </text>
            <rect
              x={cx}
              y={cy}
              width={cw}
              height={ch}
              rx={5}
              fill="#f8fafc"
              stroke="#cbd5e1"
              strokeWidth={1.2}
            />
            <text
              x={cx + 10}
              y={cy + ch / 2 + 4}
              fontSize={10.5}
              fill="#64748b"
            >
              {ctrl.placeholder ||
                (role === 'ui.dropdown' ? 'Select… ▾' : ctrl.binding_ref || '')}
            </text>
          </g>
        );
      })}

      {regions.map((reg) => {
        const b = reg.bounds || {x: 16, y: 16, width: 160, height: 80};
        const rx = x + Number(b.x || 0);
        const ry = y + headerH + Number(b.y || 0);
        return (
          <g key={reg.id}>
            <rect
              x={rx}
              y={ry}
              width={Math.max(40, Number(b.width || 140))}
              height={Math.max(28, Number(b.height || 60))}
              rx={4}
              fill="#fef3c7"
              fillOpacity={0.22}
              stroke="#d97706"
              strokeDasharray="5 3"
              strokeWidth={1.4}
            />
            <text
              x={rx + 6}
              y={ry + 14}
              fontSize={10}
              fontWeight={700}
              fill="#92400e"
            >
              {reg.name || 'Bound Region'}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/**
 * ScratchRobin Native Host-Tiled Vector Canvas.
 * Renders host-computed Sugiyama layouts & obstacle-avoiding orthogonal routes
 * streamed by spatial `(tx, ty)` tiles, with LOD switching, Minimap, and drag-to-pin.
 */
export function RobinTiledCanvas({
  scene,
  loadedTiles,
  onRequestTiles,
  selectedNodeId = '',
  onSelectNode,
  editable = false,
  onPinNode,
  canvasApiRef = null,
  ariaLabel = 'DDN diagram',
}) {
  const containerRef = useRef(null);
  const [viewportSize, setViewportSize] = useState({width: 960, height: 620});
  const [camera, setCamera] = useState({x: 0, y: 0, zoom: 1});
  const [hoveredNodeId, setHoveredNodeId] = useState('');
  const [dragState, setDragState] = useState(null);
  const [nodeOverrides, setNodeOverrides] = useState({});
  const requestedCoordsRef = useRef(new Set());
  const fitSignatureRef = useRef('');

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const obs = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect && rect.width > 40 && rect.height > 40) {
        setViewportSize({width: rect.width, height: rect.height});
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const fitWorkarea = useCallback(() => {
    if (!scene?.canvas_bounds) return;
    const cb = scene.canvas_bounds;
    const cw = Math.max(240, cb.width || 800);
    const ch = Math.max(180, cb.height || 520);
    const vw = Math.max(320, viewportSize.width || 960);
    const vh = Math.max(220, viewportSize.height || 620);
    const scale = Math.min((vw - 48) / cw, (vh - 48) / ch);
    // Keep very large diagrams readable on initial open while centered nicely
    const clampedZoom = Math.max(0.28, Math.min(1.15, scale));
    const tx = (vw - cw * clampedZoom) / 2 - (cb.min_x || 0) * clampedZoom;
    const ty = Math.max(18, (vh - ch * clampedZoom) / 2) - (cb.min_y || 0) * clampedZoom;
    setCamera({x: tx, y: ty, zoom: clampedZoom});
  }, [scene, viewportSize.height, viewportSize.width]);

  // Reset overrides and auto-fit whenever a new model or view is loaded
  useEffect(() => {
    if (!scene) return;
    const sig = `${scene.ddn_sha256}:${scene.view_id}`;
    requestedCoordsRef.current = new Set(Object.keys(loadedTiles || {}));
    if (fitSignatureRef.current !== sig) {
      fitSignatureRef.current = sig;
      setNodeOverrides({});
      fitWorkarea();
    }
  }, [scene, loadedTiles, fitWorkarea]);

  // Stream missing spatial tiles intersecting the current camera + 1-tile prefetch margin
  useEffect(() => {
    if (!scene?.tile_index?.length || typeof onRequestTiles !== 'function') {
      return;
    }
    const z = Math.max(0.08, camera.zoom);
    const worldMinX = -camera.x / z - (scene.tile_size || 1024) * 0.65;
    const worldMinY = -camera.y / z - (scene.tile_size || 1024) * 0.65;
    const worldMaxX =
      (viewportSize.width - camera.x) / z + (scene.tile_size || 1024) * 0.65;
    const worldMaxY =
      (viewportSize.height - camera.y) / z + (scene.tile_size || 1024) * 0.65;

    const missing = [];
    for (const t of scene.tile_index) {
      const coord = t.coord || `${t.tx}:${t.ty}`;
      if (loadedTiles?.[coord] || requestedCoordsRef.current.has(coord)) {
        continue;
      }
      const b = t.bounds;
      if (
        b &&
        !(
          b.max_x < worldMinX ||
          b.min_x > worldMaxX ||
          b.max_y < worldMinY ||
          b.min_y > worldMaxY
        )
      ) {
        requestedCoordsRef.current.add(coord);
        missing.push(coord);
      }
    }
    if (missing.length) {
      onRequestTiles(missing.slice(0, 16));
    }
  }, [
    camera,
    loadedTiles,
    onRequestTiles,
    scene,
    viewportSize.height,
    viewportSize.width,
  ]);

  useImperativeHandle(
    canvasApiRef,
    () => ({
      fitWorkarea,
      zoomIn: () =>
        setCamera((c) => ({...c, zoom: Math.min(2.6, c.zoom * 1.22)})),
      zoomOut: () =>
        setCamera((c) => ({...c, zoom: Math.max(0.12, c.zoom / 1.22)})),
      resetZoom: () => setCamera((c) => ({...c, zoom: 1})),
      exportSvg: () => serializeRobinSceneToSvg(scene, loadedTiles),
    }),
    [fitWorkarea, loadedTiles, scene]
  );

  // Deduplicate visible primitives across loaded tiles intersecting the viewport
  const visibleScene = useMemo(() => {
    const tilesObj = loadedTiles || scene?.loaded_tiles || {};
    const z = Math.max(0.08, camera.zoom);
    const pad = (scene?.tile_size || 1024) * 0.9;
    const vx1 = -camera.x / z - pad;
    const vy1 = -camera.y / z - pad;
    const vx2 = (viewportSize.width - camera.x) / z + pad;
    const vy2 = (viewportSize.height - camera.y) / z + pad;

    const activeTileMap = {};
    for (const [coord, tile] of Object.entries(tilesObj)) {
      if (!tile) continue;
      const b = tile.bounds;
      if (
        !b ||
        !(b.max_x < vx1 || b.min_x > vx2 || b.max_y < vy1 || b.min_y > vy2)
      ) {
        activeTileMap[coord] = tile;
      }
    }
    return collectMergedTileItems(activeTileMap);
  }, [
    camera.x,
    camera.y,
    camera.zoom,
    loadedTiles,
    scene,
    viewportSize.height,
    viewportSize.width,
  ]);

  const activeFocusId = selectedNodeId || hoveredNodeId;
  const connectedIds = useMemo(() => {
    const s = new Set();
    if (!activeFocusId) return s;
    s.add(activeFocusId);
    for (const e of visibleScene.edges) {
      if (e.source === activeFocusId || e.target === activeFocusId) {
        s.add(e.source);
        s.add(e.target);
      }
    }
    return s;
  }, [activeFocusId, visibleScene.edges]);

  const handleWheel = useCallback((evt) => {
    evt.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    const mx = rect ? evt.clientX - rect.left : 480;
    const my = rect ? evt.clientY - rect.top : 300;
    const factor = evt.deltaY < 0 ? 1.12 : 1 / 1.12;
    setCamera((cur) => {
      const nextZoom = Math.max(0.1, Math.min(2.8, cur.zoom * factor));
      const scaleChange = nextZoom / cur.zoom;
      return {
        zoom: nextZoom,
        x: mx - (mx - cur.x) * scaleChange,
        y: my - (my - cur.y) * scaleChange,
      };
    });
  }, []);

  const handlePointerDownCanvas = (evt) => {
    if (evt.button !== 0) return;
    setDragState({
      kind: 'pan',
      startClientX: evt.clientX,
      startClientY: evt.clientY,
      origX: camera.x,
      origY: camera.y,
    });
  };

  const handlePointerDownNode = (evt, node) => {
    evt.stopPropagation();
    onSelectNode?.(node);
    if (!editable || evt.button !== 0) return;
    const override = nodeOverrides[node.id];
    setDragState({
      kind: 'node',
      nodeId: node.id,
      startClientX: evt.clientX,
      startClientY: evt.clientY,
      origX: override ? override.x : node.x,
      origY: override ? override.y : node.y,
    });
  };

  const handlePointerMove = (evt) => {
    if (!dragState) return;
    if (dragState.kind === 'pan') {
      const dx = evt.clientX - dragState.startClientX;
      const dy = evt.clientY - dragState.startClientY;
      setCamera((c) => ({...c, x: dragState.origX + dx, y: dragState.origY + dy}));
    } else if (dragState.kind === 'node') {
      const dx = (evt.clientX - dragState.startClientX) / Math.max(0.1, camera.zoom);
      const dy = (evt.clientY - dragState.startClientY) / Math.max(0.1, camera.zoom);
      const nx = Math.round(dragState.origX + dx);
      const ny = Math.round(dragState.origY + dy);
      setNodeOverrides((prev) => ({...prev, [dragState.nodeId]: {x: nx, y: ny}}));
    }
  };

  const handlePointerUp = () => {
    if (dragState?.kind === 'node') {
      const pos = nodeOverrides[dragState.nodeId];
      if (pos && onPinNode) {
        onPinNode(dragState.nodeId, pos.x, pos.y);
      }
    }
    if (dragState) setDragState(null);
  };

  const totalNodeCount = scene?.summary?.node_count || visibleScene.nodes.length;
  const overviewLod = camera.zoom < 0.44 && totalNodeCount > 18;
  const loadedTileCount = Object.keys(loadedTiles || scene?.loaded_tiles || {}).length;
  const totalTileCount = scene?.tile_index?.length || 1;

  return (
    <Box
      ref={containerRef}
      aria-label={ariaLabel}
      onWheel={handleWheel}
      onPointerDown={handlePointerDownCanvas}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
      sx={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 300,
        overflow: 'hidden',
        bgcolor: '#f8fafc',
        userSelect: 'none',
        cursor: dragState?.kind === 'pan' ? 'grabbing' : 'grab',
      }}
    >
      <svg
        width="100%"
        height="100%"
        style={{display: 'block', width: '100%', height: '100%'}}
      >
        <defs>
          <pattern
            id="robin-grid-dots"
            width={24 * camera.zoom}
            height={24 * camera.zoom}
            patternUnits="userSpaceOnUse"
            x={camera.x}
            y={camera.y}
          >
            <circle
              cx={1.5}
              cy={1.5}
              r={Math.max(0.7, Math.min(1.4, camera.zoom * 1.1))}
              fill="#cbd5e1"
            />
          </pattern>
          <marker
            id="robin-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#475569" />
          </marker>
          <marker
            id="robin-arrow-hi"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#2563eb" />
          </marker>
          <marker
            id="robin-one"
            viewBox="0 0 10 12"
            refX="9"
            refY="6"
            markerWidth="8"
            markerHeight="9"
            orient="auto"
          >
            <line
              x1="6"
              y1="1"
              x2="6"
              y2="11"
              stroke="#334155"
              strokeWidth="1.7"
            />
          </marker>
          <marker
            id="robin-many"
            viewBox="0 0 14 12"
            refX="1"
            refY="6"
            markerWidth="10"
            markerHeight="9"
            orient="auto"
          >
            <path
              d="M 13 6 L 1 1 M 13 6 L 1 6 M 13 6 L 1 11"
              stroke="#334155"
              strokeWidth="1.4"
              fill="none"
            />
          </marker>
        </defs>

        <rect width="100%" height="100%" fill="url(#robin-grid-dots)" />

        <g transform={`translate(${camera.x}, ${camera.y}) scale(${camera.zoom})`}>
          {/* 1. Architectural Level Swimlanes */}
          {visibleScene.zones.map((z) => (
            <g key={z.id}>
              <rect
                x={z.x}
                y={z.y}
                width={z.width}
                height={z.height}
                rx={10}
                fill="#ffffff"
                fillOpacity={0.68}
                stroke={z.border || '#94a3b8'}
                strokeDasharray="6 4"
                strokeWidth={1.5}
              />
              <rect
                x={z.x}
                y={z.y}
                width={z.width}
                height={34}
                rx={10}
                fill={z.header_bg || '#e2e8f0'}
              />
              <text
                x={z.x + 16}
                y={z.y + 22}
                fontSize={12.5}
                fontWeight={700}
                fill={z.header_fg || '#0f172a'}
              >
                {z.label}
              </text>
            </g>
          ))}

          {/* 2. Obstacle-Avoiding Orthogonal Relationship Routes */}
          {visibleScene.edges.map((e) => {
            const pts = e.points || [];
            if (pts.length < 2) return null;
            const dCmd = `M ${pts.map((p) => `${p.x} ${p.y}`).join(' L ')}`;
            const isHighlighted =
              activeFocusId &&
              (e.source === activeFocusId || e.target === activeFocusId);
            const isDimmed = Boolean(activeFocusId && !isHighlighted);
            const strokeColor = isHighlighted ? '#2563eb' : '#475569';
            const strokeW = isHighlighted ? 2.4 : 1.45;
            return (
              <g key={e.id} opacity={isDimmed ? 0.25 : 1}>
                <path
                  d={dCmd}
                  fill="none"
                  stroke={strokeColor}
                  strokeWidth={strokeW}
                  strokeLinejoin="round"
                  strokeDasharray={e.dashed ? '5 4' : undefined}
                  markerStart={
                    e.source_mark === 'many' ? 'url(#robin-many)' : undefined
                  }
                  markerEnd={
                    e.target_mark === 'arrow'
                      ? isHighlighted
                        ? 'url(#robin-arrow-hi)'
                        : 'url(#robin-arrow)'
                      : 'url(#robin-one)'
                  }
                />
                {!overviewLod && e.display_label && e.label_pos && (
                  <g>
                    <rect
                      x={e.label_pos.x - (e.label_pos.w || 64) / 2}
                      y={e.label_pos.y - 9}
                      width={e.label_pos.w || 64}
                      height={18}
                      rx={4}
                      fill="#ffffff"
                      stroke={isHighlighted ? '#2563eb' : '#cbd5e1'}
                      strokeWidth={1}
                    />
                    <text
                      x={e.label_pos.x}
                      y={e.label_pos.y + 3.5}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight={isHighlighted ? 700 : 500}
                      fill={isHighlighted ? '#1d4ed8' : '#334155'}
                    >
                      {e.display_label}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {/* 3. Specialized Task Widgets (BI Charts/Dashboards, Cube Matrix/Grid, Screen Frames) */}
          {visibleScene.widgets.map((w) => {
            if (w.widget_kind === 'data_grid') {
              return <DataGridWidgetSvg key={w.id} widget={w} />;
            }
            if (w.widget_kind === 'bi_card') {
              return <BiCardWidgetSvg key={w.id} widget={w} />;
            }
            if (w.widget_kind === 'screen_frame') {
              return <ScreenFrameWidgetSvg key={w.id} widget={w} />;
            }
            return null;
          })}

          {/* 4. Entity / Table / Dimensional / Topology Cards */}
          {visibleScene.nodes.map((n) => {
            const override = nodeOverrides[n.id];
            const nx = override ? override.x : n.x;
            const ny = override ? override.y : n.y;
            const pal = n.palette || DEFAULT_PALETTE[n.level] || DEFAULT_PALETTE.physical;
            const isSelected = selectedNodeId === n.id;
            const isConnected = connectedIds.has(n.id);
            const dimmed = Boolean(activeFocusId && !isConnected);
            const roleBadge = (n.engine || n.role || n.level || 'table')
              .toUpperCase()
              .slice(0, 10);

            return (
              <g
                key={n.id}
                transform={`translate(${nx}, ${ny})`}
                opacity={dimmed ? 0.38 : 1}
                style={{cursor: editable ? 'move' : 'pointer'}}
                onPointerEnter={() => setHoveredNodeId(n.id)}
                onPointerLeave={() =>
                  setHoveredNodeId((cur) => (cur === n.id ? '' : cur))
                }
                onPointerDown={(evt) => handlePointerDownNode(evt, n)}
              >
                <rect
                  x={0}
                  y={0}
                  width={n.width}
                  height={n.height}
                  rx={6}
                  fill="#ffffff"
                  stroke={isSelected ? '#1d4ed8' : pal.border}
                  strokeWidth={isSelected ? 2.8 : 1.5}
                />
                <rect
                  x={0}
                  y={0}
                  width={n.width}
                  height={CARD_HEADER_H}
                  rx={6}
                  fill={pal.header_bg}
                />
                <line
                  x1={0}
                  y1={CARD_HEADER_H}
                  x2={n.width}
                  y2={CARD_HEADER_H}
                  stroke={pal.border}
                  strokeWidth={1}
                />
                <text
                  x={12}
                  y={23}
                  fontSize={12.5}
                  fontWeight={700}
                  fill={pal.header_fg}
                >
                  {String(n.name || '').slice(
                    0,
                    Math.max(18, Math.floor((n.width - 78) / 7.2))
                  )}
                </text>
                <rect
                  x={n.width - Math.max(46, roleBadge.length * 6.2 + 12) - 8}
                  y={9}
                  width={Math.max(46, roleBadge.length * 6.2 + 12)}
                  height={19}
                  rx={4}
                  fill={pal.badge_bg || '#bfdbfe'}
                />
                <text
                  x={n.width - 14}
                  y={22}
                  textAnchor="end"
                  fontSize={9.5}
                  fontWeight={700}
                  fill={pal.header_fg}
                >
                  {roleBadge}
                </text>

                {overviewLod ? (
                  <text
                    x={12}
                    y={CARD_HEADER_H + 22}
                    fontSize={11.5}
                    fontWeight={600}
                    fill="#475569"
                  >
                    {`${(n.fields?.length || 0) + (n.hidden_field_count || 0)} attributes`}
                  </text>
                ) : (
                  <>
                    {(n.fields || []).map((f, fi) => {
                      const rowY = CARD_HEADER_H + fi * FIELD_ROW_H;
                      return (
                        <g key={f.id || fi}>
                          {fi % 2 === 1 && (
                            <rect
                              x={1.5}
                              y={rowY}
                              width={n.width - 3}
                              height={FIELD_ROW_H}
                              fill="#f8fafc"
                            />
                          )}
                          {f.is_pk && (
                            <rect
                              x={8}
                              y={rowY + 4}
                              width={20}
                              height={14}
                              rx={3}
                              fill="#fef3c7"
                              stroke="#d97706"
                              strokeWidth={0.8}
                            />
                          )}
                          {!f.is_pk && f.is_fk && (
                            <rect
                              x={8}
                              y={rowY + 4}
                              width={20}
                              height={14}
                              rx={3}
                              fill="#dbeafe"
                              stroke="#2563eb"
                              strokeWidth={0.8}
                            />
                          )}
                          {(f.is_pk || f.is_fk) && (
                            <text
                              x={18}
                              y={rowY + 14}
                              textAnchor="middle"
                              fontSize={8.5}
                              fontWeight={700}
                              fill={f.is_pk ? '#92400e' : '#1e40af'}
                            >
                              {f.is_pk ? 'PK' : 'FK'}
                            </text>
                          )}
                          <text
                            x={f.is_pk || f.is_fk ? 34 : 12}
                            y={rowY + 15}
                            fontSize={11}
                            fontWeight={f.is_pk ? 700 : 500}
                            fill="#1e293b"
                          >
                            {`${String(f.name || '').slice(0, 26)}${f.nullable === false ? ' *' : ''}`}
                          </text>
                          {f.datatype && (
                            <text
                              x={n.width - 10}
                              y={rowY + 15}
                              textAnchor="end"
                              fontSize={10}
                              fill="#64748b"
                            >
                              {String(f.datatype).slice(0, 18)}
                            </text>
                          )}
                        </g>
                      );
                    })}
                    {n.hidden_field_count > 0 && (
                      <text
                        x={12}
                        y={
                          CARD_HEADER_H +
                          (n.fields?.length || 0) * FIELD_ROW_H +
                          15
                        }
                        fontSize={10.5}
                        fontStyle="italic"
                        fill="#64748b"
                      >
                        {`+${n.hidden_field_count} more columns…`}
                      </text>
                    )}
                  </>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Bottom-left Host Tile & Zoom HUD */}
      {scene && (
        <Box
          sx={{
            position: 'absolute',
            left: 10,
            bottom: 8,
            px: 1,
            py: 0.35,
            borderRadius: 1,
            bgcolor: 'rgba(255,255,255,0.9)',
            border: '1px solid #cbd5e1',
            fontSize: '0.72rem',
            color: '#334155',
            pointerEvents: 'none',
          }}
        >
          {`${scene.summary?.view_count || scene.views?.length || 1} views · ${
            (scene.summary?.node_count || 0) + (scene.summary?.widget_count || 0)
          } items · ${scene.summary?.edge_count || 0} relations · Tiles ${loadedTileCount}/${totalTileCount} · ${Math.round(
            camera.zoom * 100
          )}%${overviewLod ? ' (Overview LOD)' : ''}`}
        </Box>
      )}

      {/* Bottom-right Interactive Minimap for multi-card models */}
      {scene?.minimap?.length > 6 && scene?.canvas_bounds && (
        <Box
          sx={{
            position: 'absolute',
            right: 12,
            bottom: 10,
            width: 168,
            height: 112,
            bgcolor: 'rgba(255,255,255,0.92)',
            border: '1px solid #94a3b8',
            borderRadius: 1,
            boxShadow: 1,
            overflow: 'hidden',
            pointerEvents: 'none',
          }}
        >
          <svg
            width="168"
            height="112"
            viewBox={`${scene.canvas_bounds.min_x} ${scene.canvas_bounds.min_y} ${scene.canvas_bounds.width} ${scene.canvas_bounds.height}`}
            preserveAspectRatio="xMidYMid meet"
          >
            {scene.minimap.map((m) => (
              <rect
                key={m.id}
                x={m.x}
                y={m.y}
                width={m.w}
                height={m.h}
                rx={4}
                fill={m.color || '#2563eb'}
                fillOpacity={0.55}
              />
            ))}
            <rect
              x={-camera.x / Math.max(0.08, camera.zoom)}
              y={-camera.y / Math.max(0.08, camera.zoom)}
              width={viewportSize.width / Math.max(0.08, camera.zoom)}
              height={viewportSize.height / Math.max(0.08, camera.zoom)}
              fill="none"
              stroke="#dc2626"
              strokeWidth={Math.max(6, scene.canvas_bounds.width / 80)}
            />
          </svg>
        </Box>
      )}
    </Box>
  );
}

RobinTiledCanvas.propTypes = {
  scene: PropTypes.object,
  loadedTiles: PropTypes.object,
  onRequestTiles: PropTypes.func,
  selectedNodeId: PropTypes.string,
  onSelectNode: PropTypes.func,
  editable: PropTypes.bool,
  onPinNode: PropTypes.func,
  canvasApiRef: PropTypes.object,
  ariaLabel: PropTypes.string,
};
