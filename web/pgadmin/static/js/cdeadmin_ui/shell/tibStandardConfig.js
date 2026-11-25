/////////////////////////////////////////////////////////////
//
// ScratchRobin — Canonical Unified TiB Configuration, 26 Standard Sections,
// Action Definitions & Callable Code Target Registry
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export const TIB_CONFIG_SCHEMA = 'scratchrobin.tib-config.v1';

export const DEFAULT_TIB_PALETTE_LIGHT = Object.freeze({
  section_bg: '#F8FAFD',
  section_border: '#CFD8E6',
  button_bg: '#E8F0FE',
  button_border: '#9BBBF3',
  button_hover_bg: '#D6E6FD',
  button_checked_bg: '#CBE0FD',
  button_checked_border: '#238BE8',
  footer_fg: '#61748D',
  icon_primary: '#123B70',
  icon_secondary: '#238BE8',
  icon_accent: '#079E91',
  icon_tint: '#C7E7FF',
  icon_accent_tint: '#B8EEE5',
});

export const DEFAULT_TIB_PALETTE_DARK = Object.freeze({
  section_bg: '#161F2E',
  section_border: '#2B3A52',
  button_bg: '#1E2D45',
  button_border: '#3B5B8C',
  button_hover_bg: '#263B5B',
  button_checked_bg: '#1E40AF',
  button_checked_border: '#60A5FA',
  footer_fg: '#94A3B8',
  icon_primary: '#E2E8F0',
  icon_secondary: '#60A5FA',
  icon_accent: '#2DD4BF',
  icon_tint: 'rgba(96, 165, 250, 0.22)',
  icon_accent_tint: 'rgba(45, 212, 191, 0.24)',
});

/**
 * Single authoritative global TiB configuration.
 * Modifying any field here immediately updates all TiB instances across all worksurfaces.
 * `subtab_visibility` defaults to `'multi_only'` (hides the sub-tab bar when a
 * worksurface has only 1 sub-tab).
 */
export const DEFAULT_TIB_CONFIG = Object.freeze({
  subtab_visibility: 'multi_only', // 'multi_only' | 'always' | 'hidden'
  show_quick_access: true,
  show_section_headers: true,
  show_section_icons: true,
  show_cluster_dividers: true,
  show_hover_hints: true,
  section_height_px: 82,
  hero_button_px: 42,
  hero_icon_px: 28,
  grid_button_px: 20,
  grid_icon_px: 16,
  grid_gap_px: 2,
  section_gap_px: 8,
  section_radius_px: 3.5,
  button_radius_px: 2.4,
  palette_mode: 'theme', // 'theme' | 'custom'
  custom_palette: {...DEFAULT_TIB_PALETTE_LIGHT},
});

function clampNum(val, lo, hi, fallback) {
  const n = Number(val);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(lo, Math.min(hi, n));
}

export function normalizeTiBConfig(raw = {}) {
  const src = raw && typeof raw === 'object' ? raw : {};
  const subVis = ['multi_only', 'always', 'hidden'].includes(src.subtab_visibility)
    ? src.subtab_visibility
    : DEFAULT_TIB_CONFIG.subtab_visibility;
  const palMode = src.palette_mode === 'custom' ? 'custom' : 'theme';
  const rawPal = src.custom_palette && typeof src.custom_palette === 'object' ? src.custom_palette : {};
  const customPalette = {...DEFAULT_TIB_PALETTE_LIGHT};
  Object.keys(customPalette).forEach((k) => {
    if (typeof rawPal[k] === 'string' && rawPal[k].trim()) {
      customPalette[k] = rawPal[k].trim();
    }
  });
  return {
    subtab_visibility: subVis,
    show_quick_access: src.show_quick_access !== false,
    show_section_headers: src.show_section_headers !== false,
    show_section_icons: src.show_section_icons !== false,
    show_cluster_dividers: src.show_cluster_dividers !== false,
    show_hover_hints: src.show_hover_hints !== false,
    section_height_px: Math.round(clampNum(src.section_height_px, 56, 124, DEFAULT_TIB_CONFIG.section_height_px)),
    hero_button_px: Math.round(clampNum(src.hero_button_px, 28, 64, DEFAULT_TIB_CONFIG.hero_button_px)),
    hero_icon_px: Math.round(clampNum(src.hero_icon_px, 16, 44, DEFAULT_TIB_CONFIG.hero_icon_px)),
    grid_button_px: Math.round(clampNum(src.grid_button_px, 16, 32, DEFAULT_TIB_CONFIG.grid_button_px)),
    grid_icon_px: Math.round(clampNum(src.grid_icon_px, 12, 24, DEFAULT_TIB_CONFIG.grid_icon_px)),
    grid_gap_px: Math.round(clampNum(src.grid_gap_px, 1, 8, DEFAULT_TIB_CONFIG.grid_gap_px)),
    section_gap_px: Math.round(clampNum(src.section_gap_px, 2, 20, DEFAULT_TIB_CONFIG.section_gap_px)),
    section_radius_px: Number(clampNum(src.section_radius_px, 0, 14, DEFAULT_TIB_CONFIG.section_radius_px).toFixed(1)),
    button_radius_px: Number(clampNum(src.button_radius_px, 0, 12, DEFAULT_TIB_CONFIG.button_radius_px).toFixed(1)),
    palette_mode: palMode,
    custom_palette: customPalette,
  };
}

export function buildTiBCssVariables(rawConfig = {}, tone = 'light', zoom3b = 1) {
  const cfg = normalizeTiBConfig(rawConfig);
  const pal =
    cfg.palette_mode === 'custom'
      ? cfg.custom_palette
      : tone === 'dark'
        ? DEFAULT_TIB_PALETTE_DARK
        : DEFAULT_TIB_PALETTE_LIGHT;
  return {
    '--sr-zoom-3b': String(zoom3b),
    '--tib-section-height': `calc(${cfg.section_height_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-hero-size': `calc(${cfg.hero_button_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-hero-icon-size': `calc(${cfg.hero_icon_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-grid-btn-size': `calc(${cfg.grid_button_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-grid-icon-size': `calc(${cfg.grid_icon_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-grid-gap': `calc(${cfg.grid_gap_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-section-gap': `calc(${cfg.section_gap_px}px * var(--sr-zoom-3b, 1))`,
    '--tib-section-radius': `${cfg.section_radius_px}px`,
    '--tib-btn-radius': `${cfg.button_radius_px}px`,
    '--tib-section-bg': pal.section_bg,
    '--tib-section-border': pal.section_border,
    '--tib-btn-bg': pal.button_bg,
    '--tib-btn-border': pal.button_border,
    '--tib-btn-hover-bg': pal.button_hover_bg,
    '--tib-btn-checked-bg': pal.button_checked_bg,
    '--tib-btn-checked-border': pal.button_checked_border,
    '--tib-footer-fg': pal.footer_fg,
    '--tib-primary': pal.icon_primary,
    '--tib-secondary': pal.icon_secondary,
    '--tib-accent': pal.icon_accent,
    '--tib-tint': pal.icon_tint,
    '--tib-accent-tint': pal.icon_accent_tint || DEFAULT_TIB_PALETTE_LIGHT.icon_accent_tint,
  };
}

export const STANDARD_TIB_SECTIONS = Object.freeze([
  {
    'num': 1,
    'id': 'SEC-WORKSPACE',
    'slug': 'workspace_panels',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Workspace & Panels',
    'sectionIcon': 'tib.section_panels',
    'usedOn': 'Data Viewer \u00b7 SQL Editor \u00b7 Catalog Inspector \u00b7 Cube \u00b7 BI \u00b7 Schema Compare',
    'summary': 'Controls primary/secondary split pane layout and toggles companion views (Data, SQL, Visual Builder, Metrics/Plan, Fields, Object Info, Metadata, Messages).',
    'heroActions': [
      'tib.workspace.primary_surface',
      'tib.workspace.secondary_split_pane'
    ],
    'gridClusters': [
      [
        [
          'tib.workspace.data_grid_view',
          'tib.workspace.fields_list'
        ],
        [
          'tib.workspace.sql_source',
          'tib.workspace.object_info'
        ],
        [
          'tib.workspace.visual_sql_builder',
          'tib.workspace.ddl_metadata'
        ],
        [
          'tib.workspace.metrics_plan',
          'tib.workspace.messages'
        ]
      ]
    ]
  },
  {
    'num': 2,
    'id': 'SEC-PRES',
    'slug': 'data_presentation',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Data Presentation',
    'sectionIcon': 'tib.section_data_presentation',
    'usedOn': 'Data Viewer (Data & View) \u00b7 SQL Editor (Data) \u00b7 BI Accessible Table',
    'summary': 'Switches between Standard Grid, Mini-Forms, Hybrid Split, Single Record Form, and Hybrid-on-Edit, and manages UserConfigurationDatabase layout templates.',
    'heroActions': [
      'tib.pres.standard_grid',
      'tib.pres.layout_templates'
    ],
    'gridClusters': [
      [
        [
          'tib.pres.mini_forms',
          'tib.pres.hybrid_on_edit'
        ],
        [
          'tib.pres.hybrid_split',
          'tib.pres.inherit_defaults'
        ],
        [
          'tib.pres.single_form',
          'tib.pres.save_object_layout'
        ]
      ]
    ]
  },
  {
    'num': 3,
    'id': 'SEC-COLTEXT',
    'slug': 'columns_text',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Columns & Text',
    'sectionIcon': 'tib.section_columns_text',
    'usedOn': 'Data Viewer (View & Format) \u00b7 SQL Editor (View & Format) \u00b7 BI \u00b7 Screen Mesh Spec',
    'summary': 'Customizes per-column font/colour, horizontal & vertical alignment, text wrap clamping, autosize, column visibility, and frozen columns.',
    'heroActions': [
      'tib.coltext.font_colour_selector'
    ],
    'gridClusters': [
      [
        [
          'tib.coltext.align_left',
          'tib.coltext.align_top'
        ],
        [
          'tib.coltext.align_centre',
          'tib.coltext.align_middle'
        ],
        [
          'tib.coltext.align_right',
          'tib.coltext.align_bottom'
        ],
        [
          'tib.coltext.full_justify',
          'tib.coltext.wrap_clamped'
        ],
        [
          'tib.coltext.no_wrap',
          'tib.coltext.full_wrap'
        ]
      ],
      [
        [
          'tib.coltext.autosize_column',
          'tib.coltext.freeze_column'
        ],
        [
          'tib.coltext.visible_columns',
          'tib.coltext.reset_layout'
        ]
      ]
    ]
  },
  {
    'num': 4,
    'id': 'SEC-VALFMT',
    'slug': 'value_formatting',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Value Formatting',
    'sectionIcon': 'tib.section_value_formatting',
    'usedOn': 'Data Viewer (View & Format) \u00b7 SQL Editor (View & Format) \u00b7 BI \u00b7 Object DDL',
    'summary': 'Controls SQL pretty-printing and display representation of Booleans, NULL markers, numeric precision, and timestamps/timezones.',
    'heroActions': [
      'tib.valfmt.format_sql_values'
    ],
    'gridClusters': [
      [
        [
          'tib.valfmt.boolean_t_f',
          'tib.valfmt.null_badge_style'
        ],
        [
          'tib.valfmt.boolean_yes_no',
          'tib.valfmt.numeric_precision'
        ],
        [
          'tib.valfmt.boolean_1_0',
          'tib.valfmt.date_timezone'
        ]
      ]
    ]
  },
  {
    'num': 5,
    'id': 'SEC-EXEC',
    'slug': 'query_execution',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Query Execution',
    'sectionIcon': 'tib.section_execution',
    'usedOn': 'SQL Editor (Query) \u00b7 Command Line / ISQL (Terminal) \u00b7 Cube & BI SQL Test',
    'summary': 'Modular statement/script execution, query plan analysis, cancellation, statement preparation, parameter binding, and Firebird/PSQL delimiter switching.',
    'heroActions': [
      'tib.exec.execute_sql',
      'tib.exec.execute_script'
    ],
    'gridClusters': [
      [
        [
          'tib.exec.explain_plan',
          'tib.exec.prepare_statement'
        ],
        [
          'tib.exec.analyze_metrics',
          'tib.exec.bind_parameters'
        ],
        [
          'tib.exec.cancel_query',
          'tib.exec.statement_terminator'
        ]
      ]
    ]
  },
  {
    'num': 6,
    'id': 'SEC-TX',
    'slug': 'transaction',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Transaction',
    'sectionIcon': 'tib.section_transaction',
    'usedOn': 'Data Viewer (Data) \u00b7 SQL Editor (Query & Data) \u00b7 Command Line (Terminal)',
    'summary': 'Identical transaction control across Data Viewer staged row edits and SQL Editor sessions: Commit, Rollback, explicit Start, Auto-commit, 2PC, and Staged SQL.',
    'heroActions': [
      'tib.tx.commit',
      'tib.tx.rollback'
    ],
    'gridClusters': [
      [
        [
          'tib.tx.start_transaction',
          'tib.tx.prepare_2pc'
        ],
        [
          'tib.tx.auto_commit_toggle',
          'tib.tx.inspect_staged_sql'
        ]
      ]
    ]
  },
  {
    'num': 7,
    'id': 'SEC-REC',
    'slug': 'records',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Records',
    'sectionIcon': 'tib.section_records',
    'usedOn': 'Data Viewer (Data) \u00b7 SQL Editor (Data) \u00b7 Object Editor Child Grids',
    'summary': 'Stages row-level CRUD mutations (Edit/Accept, Insert, Duplicate, Delete, Set NULL, Revert) across grid, mini-form, hybrid, and single-form views.',
    'heroActions': [
      'tib.rec.edit_accept_row',
      'tib.rec.insert_row'
    ],
    'gridClusters': [
      [
        [
          'tib.rec.duplicate_row',
          'tib.rec.set_null'
        ],
        [
          'tib.rec.delete_row',
          'tib.rec.revert_row'
        ]
      ]
    ]
  },
  {
    'num': 8,
    'id': 'SEC-NAV',
    'slug': 'navigation',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Navigation',
    'sectionIcon': 'tib.section_navigation',
    'usedOn': 'Data Viewer (Data) \u00b7 SQL Editor (Data) \u00b7 Schema Compare (Compare)',
    'summary': 'Deterministic cursor, page, primary-key locate, and session bookmark (! / !< / !>) transport.',
    'heroActions': [
      'tib.nav.locate_jump',
      'tib.nav.bookmark'
    ],
    'gridClusters': [
      [
        [
          'tib.nav.first_row',
          'tib.nav.last_row'
        ],
        [
          'tib.nav.prev_page',
          'tib.nav.next_page'
        ],
        [
          'tib.nav.prev_row',
          'tib.nav.next_row'
        ],
        [
          'tib.nav.prev_bookmark',
          'tib.nav.next_bookmark'
        ]
      ]
    ]
  },
  {
    'num': 9,
    'id': 'SEC-FIND',
    'slug': 'find_filter',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Find & Filter',
    'sectionIcon': 'tib.section_find_filter',
    'usedOn': 'Data Viewer \u00b7 SQL Editor \u00b7 Properties \u00b7 Project Assets \u00b7 Schema Compare \u00b7 Screen Mesh',
    'summary': 'Unified client quick-find, visual WHERE/predicate filter builder, local vs. server sorting, refresh, and row fetch limits.',
    'heroActions': [
      'tib.find.quick_find',
      'tib.find.filter_builder'
    ],
    'gridClusters': [
      [
        [
          'tib.find.local_sort',
          'tib.find.refresh_data'
        ],
        [
          'tib.find.server_order_by',
          'tib.find.fetch_step_limits'
        ],
        [
          'tib.find.clear_filters_sort',
          'tib.find.target_info'
        ]
      ]
    ]
  },
  {
    'num': 10,
    'id': 'SEC-CLIP',
    'slug': 'clipboard',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Clipboard',
    'sectionIcon': 'tib.section_clipboard',
    'usedOn': 'SQL Editor \u00b7 Data Viewer \u00b7 All 4 DDN Designers \u00b7 Object Editor \u00b7 CLI',
    'summary': 'Standardized Copy, Paste, Cut, format-aware Copy Special (CSV/TSV/JSON/INSERT/SVG/DDN), Select All, Undo, and Redo.',
    'heroActions': [
      'tib.clip.copy',
      'tib.clip.paste'
    ],
    'gridClusters': [
      [
        [
          'tib.clip.cut',
          'tib.clip.undo'
        ],
        [
          'tib.clip.copy_special',
          'tib.clip.redo'
        ],
        [
          'tib.clip.select_all',
          'tib.clip.duplicate'
        ]
      ]
    ]
  },
  {
    'num': 11,
    'id': 'SEC-FILE',
    'slug': 'files_scripts',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Files & Scripts',
    'sectionIcon': 'tib.section_files',
    'usedOn': 'SQL Editor (Transfer & Files) \u00b7 Project Assets \u00b7 Schema Compare \u00b7 Command Line',
    'summary': 'Manages local and Git-backed SQL scripts, migration plans, project assets, and console transcripts.',
    'heroActions': [
      'tib.file.save',
      'tib.file.open_file'
    ],
    'gridClusters': [
      [
        [
          'tib.file.new',
          'tib.file.recent_history'
        ],
        [
          'tib.file.save_as',
          'tib.file.git_sync'
        ],
        [
          'tib.file.revert_file',
          'tib.file.clear_buffer'
        ]
      ]
    ]
  },
  {
    'num': 12,
    'id': 'SEC-QLIB',
    'slug': 'query_library',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Query Library',
    'sectionIcon': 'tib.section_query_library',
    'usedOn': 'SQL Editor (Query & Transfer) \u00b7 BI Question Designer \u00b7 Command Line',
    'summary': 'Provides instant access to project Saved Queries, reusable SQL Snippets, execution history, and authored SQL Notebooks.',
    'heroActions': [
      'tib.qlib.saved_queries',
      'tib.qlib.sql_snippets'
    ],
    'gridClusters': [
      [
        [
          'tib.qlib.save_to_library',
          'tib.qlib.execution_history'
        ],
        [
          'tib.qlib.save_selection_as_snippet',
          'tib.qlib.sql_notebook_mode'
        ]
      ]
    ]
  },
  {
    'num': 13,
    'id': 'SEC-TRANSFER',
    'slug': 'import_export',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Import & Export',
    'sectionIcon': 'tib.section_import_export',
    'usedOn': 'Data Viewer \u00b7 SQL Editor \u00b7 Catalog Properties \u00b7 All 4 DDN Designers \u00b7 Schema Compare',
    'summary': 'Standardizes file import/export (CSV, TSV, JSON, Excel/ODS, PDF), SQL INSERT/UPDATE generation, SQL Editor handoff, and BI Question promotion.',
    'heroActions': [
      'tib.transfer.export_data_asset',
      'tib.transfer.import_data_bundle'
    ],
    'gridClusters': [
      [
        [
          'tib.transfer.excel_ods',
          'tib.transfer.copy_inserts'
        ],
        [
          'tib.transfer.pdf_report',
          'tib.transfer.copy_updates'
        ],
        [
          'tib.transfer.copy_csv_tsv',
          'tib.transfer.open_in_sql_editor'
        ],
        [
          'tib.transfer.copy_json',
          'tib.transfer.save_as_bi_question'
        ]
      ]
    ]
  },
  {
    'num': 14,
    'id': 'SEC-TELEM',
    'slug': 'refresh_history',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Refresh & History',
    'sectionIcon': 'tib.metrics_plan',
    'usedOn': 'Catalog Tabs (Dashboard & Properties) \u00b7 Data Navigator \u00b7 Engine Monitoring',
    'summary': 'Governs zero-churn on-demand metric snapshots, explicit deep table scans, and encrypted Firebird Embedded UserConfigurationDatabase historic trends.',
    'heroActions': [
      'tib.telem.refresh_snapshot',
      'tib.telem.compute_deep_stats'
    ],
    'gridClusters': [
      [
        [
          'tib.telem.live_session',
          'tib.telem.auto_refresh'
        ],
        [
          'tib.telem.1h_24h_rollups',
          'tib.telem.persist_to_vault'
        ],
        [
          'tib.telem.30d_365d_vault',
          'tib.telem.prune_history'
        ],
        [
          'tib.telem.customize_cards',
          'tib.telem.export_health_report'
        ]
      ]
    ]
  },
  {
    'num': 15,
    'id': 'SEC-CANVAS',
    'slug': 'canvas_zoom',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Canvas & Zoom',
    'sectionIcon': 'tib.section_canvas',
    'usedOn': 'Shared identically across ERD \u00b7 Cube \u00b7 BI \u00b7 Screen Mesh DDN Designers',
    'summary': 'Shared DDN vector viewer/designer tools: pointer/marquee/pan, deterministic server-computed layered layout, node pinning, sketch look, and zoom/tiling.',
    'heroActions': [
      'tib.canvas.pointer_select',
      'tib.canvas.recompute_layout'
    ],
    'gridClusters': [
      [
        [
          'tib.canvas.marquee_select',
          'tib.canvas.zoom_in'
        ],
        [
          'tib.canvas.pan_canvas',
          'tib.canvas.zoom_out'
        ],
        [
          'tib.canvas.align_distribute',
          'tib.canvas.zoom_to_fit'
        ],
        [
          'tib.canvas.pin_lock_node',
          'tib.canvas.actual_size_1_1'
        ],
        [
          'tib.canvas.sketch_look',
          'tib.canvas.minimap_tiling'
        ]
      ]
    ]
  },
  {
    'num': 16,
    'id': 'SEC-GOV',
    'slug': 'checkpoints_git',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Checkpoints & Git',
    'sectionIcon': 'tib.section_files',
    'usedOn': 'Shared identically across ERD \u00b7 Cube \u00b7 BI \u00b7 Screen Mesh Designers \u00b7 Project Assets',
    'summary': 'Directed save-point checkpoints in designs.db, RBAC status progression (Draft -> In-Progress -> In-Review -> Accepted), Git .ddn sync, and Where Used lineage.',
    'heroActions': [
      'tib.gov.save_draft',
      'tib.gov.accept_version'
    ],
    'gridClusters': [
      [
        [
          'tib.gov.in_progress',
          'tib.gov.checkpoints_diff'
        ],
        [
          'tib.gov.submit_for_review',
          'tib.gov.git_load_save'
        ],
        [
          'tib.gov.branch_draft',
          'tib.gov.export_ddn'
        ],
        [
          'tib.gov.reconcile_active',
          'tib.gov.where_used'
        ]
      ]
    ]
  },
  {
    'num': 17,
    'id': 'SEC-NATREV',
    'slug': 'ddl_native_review',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'DDL & Native Review',
    'sectionIcon': 'tib.section_sql_generation',
    'usedOn': 'Object Creator/Alter \u00b7 ERD Alter Plan \u00b7 Cube Materialize \u00b7 BI Outward Gate \u00b7 Schema Compare',
    'summary': 'Gates all outward database/exposure effects through native DDL preview, live catalog diff, destructive data-loss checks, and OperationBus review.',
    'heroActions': [
      'tib.natrev.preview_native_ddl',
      'tib.natrev.apply_via_review'
    ],
    'gridClusters': [
      [
        [
          'tib.natrev.diff_vs_live_catalog',
          'tib.natrev.open_in_sql_editor'
        ],
        [
          'tib.natrev.destructive_check',
          'tib.natrev.discard_changes'
        ]
      ]
    ]
  },
  {
    'num': 18,
    'id': 'SEC-CONN',
    'slug': 'connection_session',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Connection',
    'sectionIcon': 'tib.section_connection',
    'usedOn': 'Data Navigator \u00b7 SQL Editor \u00b7 Command Line \u00b7 Schema Compare \u00b7 Engine Operations',
    'summary': 'Target database connection switcher, new engine registration, session health verification, disconnect, and role/isolation preferences.',
    'heroActions': [
      'tib.conn.switch_target',
      'tib.conn.register_connector'
    ],
    'gridClusters': [
      [
        [
          'tib.conn.verify_reconnect',
          'tib.conn.session_limits'
        ],
        [
          'tib.conn.disconnect',
          'tib.conn.role_isolation'
        ]
      ]
    ]
  },
  {
    'num': 19,
    'id': 'SEC-CAT-ACT',
    'slug': 'catalog_object_actions',
    'tier': 'Tier 2 \u00b7 Domain (Catalog Inspector)',
    'title': 'Object Actions',
    'sectionIcon': 'tib.section_sql_generation',
    'usedOn': 'Catalog Tabs (server: / database: / table: / view: -> Dashboard & Properties)',
    'summary': 'Context-aware actions for the selected navigation-tree object: browse data, open SQL Editor, create/alter/drop object, compare schema, or launch ERD.',
    'heroActions': [
      'tib.cat_act.browse_data',
      'tib.cat_act.open_sql_editor'
    ],
    'gridClusters': [
      [
        [
          'tib.cat_act.create_child_object',
          'tib.cat_act.schema_compare'
        ],
        [
          'tib.cat_act.alter_edit_object',
          'tib.cat_act.discover_into_erd'
        ],
        [
          'tib.cat_act.drop_object',
          'tib.cat_act.maintenance_backup'
        ]
      ]
    ]
  },
  {
    'num': 20,
    'id': 'SEC-ERD-MOD',
    'slug': 'erd_entities_levels',
    'tier': 'Tier 2 \u00b7 Domain (ERD Designer)',
    'title': 'Entities & Levels',
    'sectionIcon': 'tib.erd_level_all',
    'usedOn': 'ERD & Data Modelling (Model & Author)',
    'summary': 'Authors whiteboard sketches and structured entities across all four linked DDN modelling levels (Conceptual, Logical, Physical, Deployment).',
    'heroActions': [
      'tib.erd_mod.entity_table',
      'tib.erd_mod.relationship'
    ],
    'gridClusters': [
      [
        [
          'tib.erd_mod.conceptual_box',
          'tib.erd_mod.level_all'
        ],
        [
          'tib.erd_mod.logical_entity',
          'tib.erd_mod.level_conceptual'
        ],
        [
          'tib.erd_mod.physical_table',
          'tib.erd_mod.level_logical'
        ],
        [
          'tib.erd_mod.deployment_node',
          'tib.erd_mod.level_physical'
        ],
        [
          'tib.erd_mod.whiteboard_note',
          'tib.erd_mod.level_deployment'
        ]
      ]
    ]
  },
  {
    'num': 21,
    'id': 'SEC-ERD-CONV',
    'slug': 'erd_convert_drift',
    'tier': 'Tier 2 \u00b7 Domain (ERD Designer)',
    'title': 'Convert & Drift',
    'sectionIcon': 'tib.erd_engine_convert',
    'usedOn': 'ERD & Data Modelling (Compare & Deploy)',
    'summary': 'Handles engine-to-engine conversion via editable type maps, naming standards, suspect bindings, live catalog import, and topology drift.',
    'heroActions': [
      'tib.erd_conv.engine_conversion',
      'tib.erd_conv.alter_migration_plan'
    ],
    'gridClusters': [
      [
        [
          'tib.erd_conv.udt_type_maps',
          'tib.erd_conv.import_catalog_ddl'
        ],
        [
          'tib.erd_conv.naming_standards',
          'tib.erd_conv.system_drift_overlay'
        ],
        [
          'tib.erd_conv.suspect_bindings',
          'tib.erd_conv.environment_matrix'
        ]
      ]
    ]
  },
  {
    'num': 22,
    'id': 'SEC-CUBE-DIM',
    'slug': 'cube_dimensions_rules',
    'tier': 'Tier 2 \u00b7 Domain (Cube Designer)',
    'title': 'Dimensions & Rules',
    'sectionIcon': 'tib.cube_add_dimension',
    'usedOn': 'Cube Designer (Cube & Elements)',
    'summary': 'Authors cube.dimensional@1 measures, role-playing dimensions, Star Schema / Usage Matrix / Aggregation Grid DDN views, and materialization plans.',
    'heroActions': [
      'tib.cube_dim.measure',
      'tib.cube_dim.dimension'
    ],
    'gridClusters': [
      [
        [
          'tib.cube_dim.star_schema_view',
          'tib.cube_dim.rule_reducer'
        ],
        [
          'tib.cube_dim.usage_matrix_view',
          'tib.cube_dim.aggregation_plans'
        ],
        [
          'tib.cube_dim.aggregation_grid',
          'tib.cube_dim.check_connection'
        ],
        [
          'tib.cube_dim.cube_properties',
          'tib.cube_dim.ai_draft_proposal'
        ]
      ]
    ]
  },
  {
    'num': 23,
    'id': 'SEC-BI-QRY',
    'slug': 'bi_query_charts',
    'tier': 'Tier 2 \u00b7 Domain (BI Designer)',
    'title': 'BI Query & Charts',
    'sectionIcon': 'tib.section_reports_bi',
    'usedOn': 'BI Questions & Dashboards (Question & Query \u00b7 Chart & Dashboard)',
    'summary': 'Builds SBsql structured questions, DDN chart profiles, composed dashboard cards, cross-filter rules, Superset/Metabase imports, and outward switches.',
    'heroActions': [
      'tib.bi_qry.structured_query',
      'tib.bi_qry.chart_profile'
    ],
    'gridClusters': [
      [
        [
          'tib.bi_qry.dashboard_card',
          'tib.bi_qry.byok_ai_draft'
        ],
        [
          'tib.bi_qry.filters_pinning',
          'tib.bi_qry.import_bi_bundle'
        ],
        [
          'tib.bi_qry.cross_filter_mode',
          'tib.bi_qry.alerts_subscriptions'
        ],
        [
          'tib.bi_qry.accessible_table',
          'tib.bi_qry.kiosk_embeds'
        ]
      ]
    ]
  },
  {
    'num': 24,
    'id': 'SEC-MESH-UI',
    'slug': 'screen_mesh_hotspots',
    'tier': 'Tier 2 \u00b7 Domain (Screen Mesh Designer)',
    'title': 'Screens & Hotspots',
    'sectionIcon': 'tib.mesh_add_screen',
    'usedOn': 'Screen Mesh Designer (Wireframe & Regions)',
    'summary': 'Designs wireframe.ui@1 frames, extended controls (grid/dropdown/radio/tabs), screenshot ui.region hotspots, destructive redaction, and navigation flows.',
    'heroActions': [
      'tib.mesh_ui.screen_frame',
      'tib.mesh_ui.stencil_control'
    ],
    'gridClusters': [
      [
        [
          'tib.mesh_ui.data_grid',
          'tib.mesh_ui.upload_screenshot'
        ],
        [
          'tib.mesh_ui.dropdown_radio',
          'tib.mesh_ui.draw_hotspot_region'
        ],
        [
          'tib.mesh_ui.tab_bar',
          'tib.mesh_ui.redact_regions'
        ],
        [
          'tib.mesh_ui.data_binding',
          'tib.mesh_ui.trace_as_mesh'
        ],
        [
          'tib.mesh_ui.navigation_link',
          'tib.mesh_ui.import_sr_f_form'
        ]
      ]
    ]
  },
  {
    'num': 25,
    'id': 'SEC-CMP-SRC',
    'slug': 'schema_compare_map',
    'tier': 'Tier 2 \u00b7 Domain (Schema Comparison)',
    'title': 'Compare & Map',
    'sectionIcon': 'tib.cat_schema_compare',
    'usedOn': 'Schema Comparison (Compare)',
    'summary': 'Selects left/right live catalog, DDN design, or DDL script endpoints, runs structural diff, resolves rename mappings, and builds migration plans.',
    'heroActions': [
      'tib.cmp_src.run_comparison',
      'tib.cmp_src.build_change_plan'
    ],
    'gridClusters': [
      [
        [
          'tib.cmp_src.left_source',
          'tib.cmp_src.map_rename'
        ],
        [
          'tib.cmp_src.right_target',
          'tib.cmp_src.carry_difference'
        ],
        [
          'tib.cmp_src.object_type_scope',
          'tib.cmp_src.skip_difference'
        ],
        [
          'tib.cmp_src.ignore_options',
          'tib.cmp_src.swap_endpoints'
        ]
      ]
    ]
  },
  {
    'num': 26,
    'id': 'SEC-OPS-RUN',
    'slug': 'engine_operations',
    'tier': 'Tier 2 \u00b7 Domain (Engine Operations)',
    'title': 'Engine Operations',
    'sectionIcon': 'tib.cat_maintenance',
    'usedOn': 'Backup / Restore \u00b7 Maintenance \u00b7 Firebird Sweep / Trace / Limbo Recovery',
    'summary': 'Executes native provider administration workflows (gbak/nbackup/pg_dump, sweep/vacuum/analyze, live trace sessions, and limbo recovery).',
    'heroActions': [
      'tib.ops_run.start_operation',
      'tib.ops_run.stop_operation'
    ],
    'gridClusters': [
      [
        [
          'tib.ops_run.backup_database',
          'tib.ops_run.live_engine_trace'
        ],
        [
          'tib.ops_run.restore_database',
          'tib.ops_run.limbo_tx_recovery'
        ],
        [
          'tib.ops_run.sweep_vacuum',
          'tib.ops_run.download_job_log'
        ]
      ]
    ]
  },
  {
    'num': 27,
    'id': 'SEC-SECURITY',
    'slug': 'security_permissions',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Security & Access',
    'sectionIcon': 'tib.section_security',
    'usedOn': 'Data Navigator (Server / Database / Object) \u00b7 Principal Security Manager',
    'summary': 'Engine-native server/database User & Role management and per-object Principal \u00d7 Privilege matrix authorization.',
    'heroActions': [
      'tib.security.manage_users',
      'tib.security.object_permissions'
    ],
    'gridClusters': [
      [
        [
          'tib.security.manage_roles',
          'tib.security.new_principal'
        ]
      ]
    ]
  },
  {
    'num': 28,
    'id': 'SEC-INSPECTOR',
    'slug': 'inspector_sections',
    'tier': 'Tier 1 \u00b7 Standard',
    'title': 'Inspector Sections',
    'sectionIcon': 'tib.inspect_all',
    'usedOn': 'Data Navigator Object Inspector (Properties Sub-Tab)',
    'summary': 'Standard TiB section replacing deprecated filter pills: switches between All Sections, Permissions & Grants, Overview, Structure, DDL / SQL, and Dependencies.',
    'heroActions': [
      'tib.inspector.all',
      'tib.inspector.permissions'
    ],
    'gridClusters': [
      [
        [
          'tib.inspector.overview',
          'tib.inspector.structure'
        ],
        [
          'tib.inspector.ddl',
          'tib.inspector.dependencies'
        ]
      ]
    ]
  }
]);

export const STANDARD_TIB_SECTIONS_BY_ID = Object.freeze(
  Object.fromEntries(STANDARD_TIB_SECTIONS.map((s) => [s.id, s]))
);

export const STANDARD_TIB_ACTIONS = Object.freeze([
  {
    'id': 'tib.workspace.primary_surface',
    'label': 'Primary Surface',
    'hint': 'Choose primary workspace surface or split orientation.',
    'icon': 'tib.pane_primary_layout',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'hero',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.primary_surface'
  },
  {
    'id': 'tib.workspace.secondary_split_pane',
    'label': 'Secondary Split Pane',
    'hint': 'Toggle docked companion split pane (Right / Bottom / Off).',
    'icon': 'tib.pane_secondary_layout',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'hero',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.secondary_split_pane'
  },
  {
    'id': 'tib.workspace.data_grid_view',
    'label': 'Data Grid View',
    'hint': 'Show tabular/form result set panel.',
    'icon': 'tib.data',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.data_grid_view'
  },
  {
    'id': 'tib.workspace.fields_list',
    'label': 'Fields List',
    'hint': 'Show column types, keys, and nullability.',
    'icon': 'tib.fields',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.fields_list'
  },
  {
    'id': 'tib.workspace.sql_source',
    'label': 'SQL Source',
    'hint': 'Show underlying SELECT / DML SQL text.',
    'icon': 'tib.sql',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.sql_source'
  },
  {
    'id': 'tib.workspace.object_info',
    'label': 'Object Info',
    'hint': 'Show table/view statistics and storage.',
    'icon': 'tib.information',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.object_info'
  },
  {
    'id': 'tib.workspace.visual_sql_builder',
    'label': 'Visual SQL Builder',
    'hint': 'Show SBsql structured visual join & filter builder.',
    'icon': 'tib.builder',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.visual_sql_builder'
  },
  {
    'id': 'tib.workspace.ddl_metadata',
    'label': 'DDL Metadata',
    'hint': 'Show native catalog DDL script.',
    'icon': 'tib.metadata',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.ddl_metadata'
  },
  {
    'id': 'tib.workspace.metrics_plan',
    'label': 'Metrics & Plan',
    'hint': 'Show execution timing, IO stats, and query plan.',
    'icon': 'tib.metrics_plan',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.metrics_plan'
  },
  {
    'id': 'tib.workspace.messages',
    'label': 'Messages',
    'hint': 'Show engine notices, warnings, and row counts.',
    'icon': 'tib.messages',
    'sectionId': 'SEC-WORKSPACE',
    'sectionTitle': 'Workspace & Panels',
    'slotKind': 'grid',
    'scope': 'Workspace & Panels',
    'handlerId': 'handler.workspace.messages'
  },
  {
    'id': 'tib.pres.standard_grid',
    'label': 'Standard Grid',
    'hint': 'Classic dense tabular result grid.',
    'icon': 'tib.grid',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'hero',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.standard_grid'
  },
  {
    'id': 'tib.pres.layout_templates',
    'label': 'Layout Templates',
    'hint': 'Apply or save reusable column/font/wrap templates in UserConfigurationDatabase.',
    'icon': 'tib.layout_template',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'hero',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.layout_templates'
  },
  {
    'id': 'tib.pres.mini_forms',
    'label': 'Mini-Forms',
    'hint': 'Render each record as a multi-column card.',
    'icon': 'tib.mini_forms',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.mini_forms'
  },
  {
    'id': 'tib.pres.hybrid_on_edit',
    'label': 'Hybrid-on-Edit',
    'hint': 'Browse as grid; expand inline hybrid form automatically on row edit.',
    'icon': 'tib.hybrid_edit',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.hybrid_on_edit'
  },
  {
    'id': 'tib.pres.hybrid_split',
    'label': 'Hybrid Split',
    'hint': 'Dense grid with inline expanded wrapped record form.',
    'icon': 'tib.hybrid',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.hybrid_split'
  },
  {
    'id': 'tib.pres.inherit_defaults',
    'label': 'Inherit Defaults',
    'hint': 'Reset object override to follow global field-type display defaults.',
    'icon': 'tib.inherit_layout',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.inherit_defaults'
  },
  {
    'id': 'tib.pres.single_form',
    'label': 'Single Form',
    'hint': 'Full-page single-record inspector form.',
    'icon': 'tib.single_form',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.single_form'
  },
  {
    'id': 'tib.pres.save_object_layout',
    'label': 'Save Object Layout',
    'hint': 'Persist column widths, fonts, colours & wrap for this table/view.',
    'icon': 'tib.save',
    'sectionId': 'SEC-PRES',
    'sectionTitle': 'Data Presentation',
    'slotKind': 'grid',
    'scope': 'Data Presentation',
    'handlerId': 'handler.pres.save_object_layout'
  },
  {
    'id': 'tib.coltext.font_colour_selector',
    'label': 'Font & Colour Selector',
    'hint': 'Select font family, size, style, foreground colour, and cell background.',
    'icon': 'tib.font_colour_selector',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'hero',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.font_colour_selector'
  },
  {
    'id': 'tib.coltext.align_left',
    'label': 'Align Left',
    'hint': 'Left-align text in selected column(s).',
    'icon': 'tib.align_left',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_left'
  },
  {
    'id': 'tib.coltext.align_top',
    'label': 'Align Top',
    'hint': 'Align cell content to vertical top.',
    'icon': 'tib.valign_top',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_top'
  },
  {
    'id': 'tib.coltext.align_centre',
    'label': 'Align Centre',
    'hint': 'Centre-align text horizontally.',
    'icon': 'tib.align_centre',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_centre'
  },
  {
    'id': 'tib.coltext.align_middle',
    'label': 'Align Middle',
    'hint': 'Centre cell content vertically.',
    'icon': 'tib.valign_middle',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_middle'
  },
  {
    'id': 'tib.coltext.align_right',
    'label': 'Align Right',
    'hint': 'Right-align numeric or text values.',
    'icon': 'tib.align_right',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_right'
  },
  {
    'id': 'tib.coltext.align_bottom',
    'label': 'Align Bottom',
    'hint': 'Align cell content to vertical bottom.',
    'icon': 'tib.valign_bottom',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.align_bottom'
  },
  {
    'id': 'tib.coltext.full_justify',
    'label': 'Full Justify',
    'hint': 'Justify multi-line text across column width.',
    'icon': 'tib.align_justify',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.full_justify'
  },
  {
    'id': 'tib.coltext.wrap_clamped',
    'label': 'Wrap Clamped',
    'hint': 'Wrap up to user-configured max displayed lines.',
    'icon': 'tib.wrap_clamp',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.wrap_clamped'
  },
  {
    'id': 'tib.coltext.no_wrap',
    'label': 'No Wrap',
    'hint': 'Keep column text on a single clipped line.',
    'icon': 'tib.wrap_none',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.no_wrap'
  },
  {
    'id': 'tib.coltext.full_wrap',
    'label': 'Full Wrap',
    'hint': 'Expand row height to show all wrapped lines.',
    'icon': 'tib.wrap_full',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.full_wrap'
  },
  {
    'id': 'tib.coltext.autosize_column',
    'label': 'Autosize Column',
    'hint': 'Fit column width to widest visible value/header.',
    'icon': 'tib.auto_fit',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.autosize_column'
  },
  {
    'id': 'tib.coltext.freeze_column',
    'label': 'Freeze Column',
    'hint': 'Pin selected column(s) to left scroll edge.',
    'icon': 'tib.freeze_column',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.freeze_column'
  },
  {
    'id': 'tib.coltext.visible_columns',
    'label': 'Visible Columns',
    'hint': 'Show, hide, or reorder result columns.',
    'icon': 'tib.visible_columns',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.visible_columns'
  },
  {
    'id': 'tib.coltext.reset_layout',
    'label': 'Reset Layout',
    'hint': 'Restore default column widths and text formatting.',
    'icon': 'tib.reset_layout',
    'sectionId': 'SEC-COLTEXT',
    'sectionTitle': 'Columns & Text',
    'slotKind': 'grid',
    'scope': 'Columns & Text',
    'handlerId': 'handler.coltext.reset_layout'
  },
  {
    'id': 'tib.valfmt.format_sql_values',
    'label': 'Format SQL / Values',
    'hint': 'Pretty-print active SQL statement or reapply value formatters.',
    'icon': 'tib.format_sql',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'hero',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.format_sql_values'
  },
  {
    'id': 'tib.valfmt.boolean_t_f',
    'label': 'Boolean T / F',
    'hint': 'Render boolean columns as T / F.',
    'icon': 'tib.boolean_tf',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.boolean_t_f'
  },
  {
    'id': 'tib.valfmt.null_badge_style',
    'label': 'NULL Badge Style',
    'hint': 'Choose visual badge or placeholder text for SQL NULL.',
    'icon': 'tib.record_null',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.null_badge_style'
  },
  {
    'id': 'tib.valfmt.boolean_yes_no',
    'label': 'Boolean Yes / No',
    'hint': 'Render boolean columns as Yes / No.',
    'icon': 'tib.boolean_yes_no',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.boolean_yes_no'
  },
  {
    'id': 'tib.valfmt.numeric_precision',
    'label': 'Numeric Precision',
    'hint': 'Configure thousands separators, decimals, and currency.',
    'icon': 'tib.numeric_format',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.numeric_precision'
  },
  {
    'id': 'tib.valfmt.boolean_1_0',
    'label': 'Boolean 1 / 0',
    'hint': 'Render boolean columns as 1 / 0.',
    'icon': 'tib.boolean_10',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.boolean_1_0'
  },
  {
    'id': 'tib.valfmt.date_timezone',
    'label': 'Date & Timezone',
    'hint': 'Configure ISO/locale date format and UTC/session timezone.',
    'icon': 'tib.datetime_tz',
    'sectionId': 'SEC-VALFMT',
    'sectionTitle': 'Value Formatting',
    'slotKind': 'grid',
    'scope': 'Value Formatting',
    'handlerId': 'handler.valfmt.date_timezone'
  },
  {
    'id': 'tib.exec.execute_sql',
    'label': 'Execute SQL',
    'hint': 'Run active statement or highlighted SQL selection (F5).',
    'icon': 'tib.execute_statement',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'hero',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.execute_sql'
  },
  {
    'id': 'tib.exec.execute_script',
    'label': 'Execute Script',
    'hint': 'Run complete multi-statement SQL script sequentially.',
    'icon': 'tib.execute_script',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'hero',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.execute_script'
  },
  {
    'id': 'tib.exec.explain_plan',
    'label': 'Explain Plan',
    'hint': 'Generate engine execution plan without mutating data.',
    'icon': 'tib.explain_plan',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.explain_plan'
  },
  {
    'id': 'tib.exec.prepare_statement',
    'label': 'Prepare Statement',
    'hint': 'Validate syntax and inspect prepared parameter/column types.',
    'icon': 'tib.prepare_statement',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.prepare_statement'
  },
  {
    'id': 'tib.exec.analyze_metrics',
    'label': 'Analyze & Metrics',
    'hint': 'Execute with per-operator timing, buffers, and IO stats.',
    'icon': 'tib.metrics_plan',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.analyze_metrics'
  },
  {
    'id': 'tib.exec.bind_parameters',
    'label': 'Bind Parameters',
    'hint': 'Open typed :param / ? bind parameter value dialog.',
    'icon': 'tib.parameters',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.bind_parameters'
  },
  {
    'id': 'tib.exec.cancel_query',
    'label': 'Cancel Query',
    'hint': 'Abort currently running query on active session.',
    'icon': 'tib.cancel',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.cancel_query'
  },
  {
    'id': 'tib.exec.statement_terminator',
    'label': 'Statement Terminator',
    'hint': 'Switch script terminator (; / !! / ~) for routines & PSQL.',
    'icon': 'tib.set_term',
    'sectionId': 'SEC-EXEC',
    'sectionTitle': 'Query Execution',
    'slotKind': 'grid',
    'scope': 'Query Execution',
    'handlerId': 'handler.exec.statement_terminator'
  },
  {
    'id': 'tib.tx.commit',
    'label': 'Commit',
    'hint': 'Commit staged row mutations or active SQL transaction.',
    'icon': 'tib.commit',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'hero',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.commit'
  },
  {
    'id': 'tib.tx.rollback',
    'label': 'Rollback',
    'hint': 'Roll back uncommitted changes to transaction start.',
    'icon': 'tib.rollback',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'hero',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.rollback'
  },
  {
    'id': 'tib.tx.start_transaction',
    'label': 'Start Transaction',
    'hint': 'Start explicit transaction with isolation/lock options.',
    'icon': 'tib.transaction_start',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'grid',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.start_transaction'
  },
  {
    'id': 'tib.tx.prepare_2pc',
    'label': 'Prepare 2PC',
    'hint': 'Prepare two-phase commit transaction where supported.',
    'icon': 'tib.transaction_prepare',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'grid',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.prepare_2pc'
  },
  {
    'id': 'tib.tx.auto_commit_toggle',
    'label': 'Auto-commit Toggle',
    'hint': 'Toggle automatic per-statement commit on or off.',
    'icon': 'tib.autocommit',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'grid',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.auto_commit_toggle'
  },
  {
    'id': 'tib.tx.inspect_staged_sql',
    'label': 'Inspect Staged SQL',
    'hint': 'Review pending INSERT/UPDATE/DELETE statements before commit.',
    'icon': 'tib.staged_sql',
    'sectionId': 'SEC-TX',
    'sectionTitle': 'Transaction',
    'slotKind': 'grid',
    'scope': 'Transaction',
    'handlerId': 'handler.tx.inspect_staged_sql'
  },
  {
    'id': 'tib.rec.edit_accept_row',
    'label': 'Edit / Accept Row',
    'hint': 'Enter edit mode or validate and stage current row edits.',
    'icon': 'tib.record_edit',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'hero',
    'scope': 'Records',
    'handlerId': 'handler.rec.edit_accept_row'
  },
  {
    'id': 'tib.rec.insert_row',
    'label': 'Insert Row',
    'hint': 'Append a new staged record.',
    'icon': 'tib.record_insert',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'hero',
    'scope': 'Records',
    'handlerId': 'handler.rec.insert_row'
  },
  {
    'id': 'tib.rec.duplicate_row',
    'label': 'Duplicate Row',
    'hint': 'Clone selected record values into a new staged row.',
    'icon': 'tib.record_duplicate',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'grid',
    'scope': 'Records',
    'handlerId': 'handler.rec.duplicate_row'
  },
  {
    'id': 'tib.rec.set_null',
    'label': 'Set NULL',
    'hint': 'Explicitly assign SQL NULL to focused cell/field.',
    'icon': 'tib.record_null',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'grid',
    'scope': 'Records',
    'handlerId': 'handler.rec.set_null'
  },
  {
    'id': 'tib.rec.delete_row',
    'label': 'Delete Row',
    'hint': 'Stage deletion of selected row(s).',
    'icon': 'tib.record_delete',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'grid',
    'scope': 'Records',
    'handlerId': 'handler.rec.delete_row'
  },
  {
    'id': 'tib.rec.revert_row',
    'label': 'Revert Row',
    'hint': 'Discard staged edits on active record.',
    'icon': 'tib.record_revert',
    'sectionId': 'SEC-REC',
    'sectionTitle': 'Records',
    'slotKind': 'grid',
    'scope': 'Records',
    'handlerId': 'handler.rec.revert_row'
  },
  {
    'id': 'tib.nav.locate_jump',
    'label': 'Locate / Jump',
    'hint': 'Jump to row number or locate record by primary key.',
    'icon': 'tib.locate_row',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'hero',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.locate_jump'
  },
  {
    'id': 'tib.nav.bookmark',
    'label': 'Bookmark (!)',
    'hint': 'Toggle session bookmark on active row or diff item.',
    'icon': 'tib.bookmark',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'hero',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.bookmark'
  },
  {
    'id': 'tib.nav.first_row',
    'label': 'First Row (|<)',
    'hint': 'Jump to first loaded item.',
    'icon': 'tib.nav_first',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.first_row'
  },
  {
    'id': 'tib.nav.last_row',
    'label': 'Last Row (>|)',
    'hint': 'Jump to last loaded item.',
    'icon': 'tib.nav_last',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.last_row'
  },
  {
    'id': 'tib.nav.prev_page',
    'label': 'Prev Page (<<)',
    'hint': 'Step back one page.',
    'icon': 'tib.nav_prev_page',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.prev_page'
  },
  {
    'id': 'tib.nav.next_page',
    'label': 'Next Page (>>)',
    'hint': 'Advance one page.',
    'icon': 'tib.nav_next_page',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.next_page'
  },
  {
    'id': 'tib.nav.prev_row',
    'label': 'Prev Row (<)',
    'hint': 'Move up one item.',
    'icon': 'tib.nav_prev_row',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.prev_row'
  },
  {
    'id': 'tib.nav.next_row',
    'label': 'Next Row (>)',
    'hint': 'Move down one item.',
    'icon': 'tib.nav_next_row',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.next_row'
  },
  {
    'id': 'tib.nav.prev_bookmark',
    'label': 'Prev Bookmark (!<)',
    'hint': 'Jump to previous bookmark.',
    'icon': 'tib.bookmark_prev',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.prev_bookmark'
  },
  {
    'id': 'tib.nav.next_bookmark',
    'label': 'Next Bookmark (!>)',
    'hint': 'Jump to next bookmark.',
    'icon': 'tib.bookmark_next',
    'sectionId': 'SEC-NAV',
    'sectionTitle': 'Navigation',
    'slotKind': 'grid',
    'scope': 'Navigation',
    'handlerId': 'handler.nav.next_bookmark'
  },
  {
    'id': 'tib.find.quick_find',
    'label': 'Quick Find',
    'hint': 'Filter or highlight matching text across loaded rows/items.',
    'icon': 'tib.quick_find',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'hero',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.quick_find'
  },
  {
    'id': 'tib.find.filter_builder',
    'label': 'Filter Builder',
    'hint': 'Compose structured multi-column filter predicates.',
    'icon': 'tib.filter_builder',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'hero',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.filter_builder'
  },
  {
    'id': 'tib.find.local_sort',
    'label': 'Local Sort',
    'hint': 'Sort currently buffered rows in memory without re-querying.',
    'icon': 'tib.sort_local',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.local_sort'
  },
  {
    'id': 'tib.find.refresh_data',
    'label': 'Refresh Data',
    'hint': 'Re-fetch current dataset or catalog list.',
    'icon': 'tib.refresh',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.refresh_data'
  },
  {
    'id': 'tib.find.server_order_by',
    'label': 'Server ORDER BY',
    'hint': 'Re-query target engine with native ORDER BY clause.',
    'icon': 'tib.sort_server',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.server_order_by'
  },
  {
    'id': 'tib.find.fetch_step_limits',
    'label': 'Fetch & Step Limits',
    'hint': 'Configure Max Rows and Rows-per-Step batch size.',
    'icon': 'tib.fetch_limits',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.fetch_step_limits'
  },
  {
    'id': 'tib.find.clear_filters_sort',
    'label': 'Clear Filters & Sort',
    'hint': 'Reset active search, filter predicates, and sort order.',
    'icon': 'tib.clear_filters',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.clear_filters_sort'
  },
  {
    'id': 'tib.find.target_info',
    'label': 'Target Info',
    'hint': 'Inspect active session connection and read-only/PK status.',
    'icon': 'tib.connection_details',
    'sectionId': 'SEC-FIND',
    'sectionTitle': 'Find & Filter',
    'slotKind': 'grid',
    'scope': 'Find & Filter',
    'handlerId': 'handler.find.target_info'
  },
  {
    'id': 'tib.clip.copy',
    'label': 'Copy',
    'hint': 'Copy selected cells, SQL text, or diagram elements.',
    'icon': 'tib.copy',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'hero',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.copy'
  },
  {
    'id': 'tib.clip.paste',
    'label': 'Paste',
    'hint': 'Paste clipboard content into active editor, grid, or canvas.',
    'icon': 'tib.paste',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'hero',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.paste'
  },
  {
    'id': 'tib.clip.cut',
    'label': 'Cut',
    'hint': 'Cut selection to clipboard.',
    'icon': 'tib.cut',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.cut'
  },
  {
    'id': 'tib.clip.undo',
    'label': 'Undo',
    'hint': 'Undo last local edit action.',
    'icon': 'tib.undo',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.undo'
  },
  {
    'id': 'tib.clip.copy_special',
    'label': 'Copy Special',
    'hint': 'Copy with headers, CSV, TSV, JSON, INSERT, UPDATE, or DDN.',
    'icon': 'tib.copy_special',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.copy_special'
  },
  {
    'id': 'tib.clip.redo',
    'label': 'Redo',
    'hint': 'Redo last undone edit action.',
    'icon': 'tib.redo',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.redo'
  },
  {
    'id': 'tib.clip.select_all',
    'label': 'Select All',
    'hint': 'Select all rows, text, or canvas elements.',
    'icon': 'tib.select_all',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.select_all'
  },
  {
    'id': 'tib.clip.duplicate',
    'label': 'Duplicate',
    'hint': 'Duplicate selected element or block in place.',
    'icon': 'tib.record_duplicate',
    'sectionId': 'SEC-CLIP',
    'sectionTitle': 'Clipboard',
    'slotKind': 'grid',
    'scope': 'Clipboard',
    'handlerId': 'handler.clip.duplicate'
  },
  {
    'id': 'tib.file.save',
    'label': 'Save',
    'hint': 'Save active SQL script, asset, or transcript.',
    'icon': 'tib.save',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'hero',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.save'
  },
  {
    'id': 'tib.file.open_file',
    'label': 'Open File',
    'hint': 'Open SQL script or project file from workspace/disk.',
    'icon': 'tib.open_sql',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'hero',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.open_file'
  },
  {
    'id': 'tib.file.new',
    'label': 'New',
    'hint': 'Create a new blank script or project asset.',
    'icon': 'tib.new',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.new'
  },
  {
    'id': 'tib.file.recent_history',
    'label': 'Recent & History',
    'hint': 'Browse recently opened scripts and file history.',
    'icon': 'tib.history',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.recent_history'
  },
  {
    'id': 'tib.file.save_as',
    'label': 'Save As',
    'hint': 'Save a copy under a new filename or project folder.',
    'icon': 'tib.save_as',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.save_as'
  },
  {
    'id': 'tib.file.git_sync',
    'label': 'Git Sync',
    'hint': 'Pull or commit script/asset in project Git repository.',
    'icon': 'tib.git_sync',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.git_sync'
  },
  {
    'id': 'tib.file.revert_file',
    'label': 'Revert File',
    'hint': 'Reload last saved version and discard unsaved edits.',
    'icon': 'tib.record_revert',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.revert_file'
  },
  {
    'id': 'tib.file.clear_buffer',
    'label': 'Clear Buffer',
    'hint': 'Clear active editor buffer or terminal transcript.',
    'icon': 'tib.clear_console',
    'sectionId': 'SEC-FILE',
    'sectionTitle': 'Files & Scripts',
    'slotKind': 'grid',
    'scope': 'Files & Scripts',
    'handlerId': 'handler.file.clear_buffer'
  },
  {
    'id': 'tib.qlib.saved_queries',
    'label': 'Saved Queries',
    'hint': 'Browse and insert saved project queries.',
    'icon': 'tib.saved_queries',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'hero',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.saved_queries'
  },
  {
    'id': 'tib.qlib.sql_snippets',
    'label': 'SQL Snippets',
    'hint': 'Insert parameterized SQL & PSQL code snippets.',
    'icon': 'tib.snippets',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'hero',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.sql_snippets'
  },
  {
    'id': 'tib.qlib.save_to_library',
    'label': 'Save to Library',
    'hint': 'Save active query into project Query Library.',
    'icon': 'tib.save',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'grid',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.save_to_library'
  },
  {
    'id': 'tib.qlib.execution_history',
    'label': 'Execution History',
    'hint': 'Search chronological statement execution log.',
    'icon': 'tib.history',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'grid',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.execution_history'
  },
  {
    'id': 'tib.qlib.save_selection_as_snippet',
    'label': 'Save Selection as Snippet',
    'hint': 'Store highlighted SQL block as reusable snippet.',
    'icon': 'tib.save_snippet',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'grid',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.save_selection_as_snippet'
  },
  {
    'id': 'tib.qlib.sql_notebook_mode',
    'label': 'SQL Notebook Mode',
    'hint': 'Switch between SQL Studio and multi-cell SQL Notebook.',
    'icon': 'tib.sql_notebook',
    'sectionId': 'SEC-QLIB',
    'sectionTitle': 'Query Library',
    'slotKind': 'grid',
    'scope': 'Query Library',
    'handlerId': 'handler.qlib.sql_notebook_mode'
  },
  {
    'id': 'tib.transfer.export_data_asset',
    'label': 'Export Data / Asset',
    'hint': 'Export result set, DDL, DDN, or specification bundle.',
    'icon': 'tib.export_data',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'hero',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.export_data_asset'
  },
  {
    'id': 'tib.transfer.import_data_bundle',
    'label': 'Import Data / Bundle',
    'hint': 'Import tabular file, DDL script, or external design bundle.',
    'icon': 'tib.import_data',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'hero',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.import_data_bundle'
  },
  {
    'id': 'tib.transfer.excel_ods',
    'label': 'Excel / ODS',
    'hint': 'Export formatted spreadsheet (.xlsx / .ods).',
    'icon': 'tib.excel_ods',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.excel_ods'
  },
  {
    'id': 'tib.transfer.copy_inserts',
    'label': 'Copy INSERTs',
    'hint': 'Generate dialect-quoted SQL INSERT statements.',
    'icon': 'tib.copy_insert',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.copy_inserts'
  },
  {
    'id': 'tib.transfer.pdf_report',
    'label': 'PDF Report',
    'hint': 'Render printable PDF report or diagram sheet.',
    'icon': 'tib.pdf_report',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.pdf_report'
  },
  {
    'id': 'tib.transfer.copy_updates',
    'label': 'Copy UPDATEs',
    'hint': 'Generate PK-keyed SQL UPDATE statements.',
    'icon': 'tib.copy_update',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.copy_updates'
  },
  {
    'id': 'tib.transfer.copy_csv_tsv',
    'label': 'Copy CSV / TSV',
    'hint': 'Copy delimited rows to clipboard.',
    'icon': 'tib.copy_csv',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.copy_csv_tsv'
  },
  {
    'id': 'tib.transfer.open_in_sql_editor',
    'label': 'Open in SQL Editor',
    'hint': 'Hand off generated SQL into a new SQL Editor tab.',
    'icon': 'tib.open_sql_editor',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.open_in_sql_editor'
  },
  {
    'id': 'tib.transfer.copy_json',
    'label': 'Copy JSON',
    'hint': 'Copy rows or metadata as structured JSON.',
    'icon': 'tib.copy_json',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.copy_json'
  },
  {
    'id': 'tib.transfer.save_as_bi_question',
    'label': 'Save as BI Question',
    'hint': 'Promote active query/view into a Draft BI Question.',
    'icon': 'tib.save_bi',
    'sectionId': 'SEC-TRANSFER',
    'sectionTitle': 'Import & Export',
    'slotKind': 'grid',
    'scope': 'Import & Export',
    'handlerId': 'handler.transfer.save_as_bi_question'
  },
  {
    'id': 'tib.telem.refresh_snapshot',
    'label': 'Refresh Snapshot',
    'hint': 'Poll lightweight live metrics & object properties now.',
    'icon': 'tib.refresh',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'hero',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.refresh_snapshot'
  },
  {
    'id': 'tib.telem.compute_deep_stats',
    'label': 'Compute Deep Stats',
    'hint': 'Run explicit on-demand row count, bloat, or storage scan.',
    'icon': 'tib.metrics_plan',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'hero',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.compute_deep_stats'
  },
  {
    'id': 'tib.telem.live_session',
    'label': 'Live Session',
    'hint': 'Show real-time session sparklines.',
    'icon': 'tib.window_live',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.live_session'
  },
  {
    'id': 'tib.telem.auto_refresh',
    'label': 'Auto-Refresh',
    'hint': 'Set optional polling cadence while tab is focused.',
    'icon': 'tib.autorefresh',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.auto_refresh'
  },
  {
    'id': 'tib.telem.1h_24h_rollups',
    'label': '1h / 24h Rollups',
    'hint': 'Load 5-minute rollups from UCFG_METRIC_ROLLUP_5M.',
    'icon': 'tib.window_24h',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.1h_24h_rollups'
  },
  {
    'id': 'tib.telem.persist_to_vault',
    'label': 'Persist to Vault',
    'hint': 'Toggle recording samples into UserConfigurationDatabase.',
    'icon': 'tib.persist_vault',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.persist_to_vault'
  },
  {
    'id': 'tib.telem.30d_365d_vault',
    'label': '30d / 365d Vault',
    'hint': 'Load hourly min/avg/max trends from UCFG_METRIC_ROLLUP_1H.',
    'icon': 'tib.vault_history',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.30d_365d_vault'
  },
  {
    'id': 'tib.telem.prune_history',
    'label': 'Prune History',
    'hint': 'Delete stored historic samples for this object.',
    'icon': 'tib.prune_history',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.prune_history'
  },
  {
    'id': 'tib.telem.customize_cards',
    'label': 'Customize Cards',
    'hint': 'Configure visible KPI cards, charts, and property sections.',
    'icon': 'tib.layout_template',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.customize_cards'
  },
  {
    'id': 'tib.telem.export_health_report',
    'label': 'Export Health Report',
    'hint': 'Export dashboard charts and properties snapshot.',
    'icon': 'tib.pdf_report',
    'sectionId': 'SEC-TELEM',
    'sectionTitle': 'Refresh & History',
    'slotKind': 'grid',
    'scope': 'Refresh & History',
    'handlerId': 'handler.telem.export_health_report'
  },
  {
    'id': 'tib.canvas.pointer_select',
    'label': 'Pointer Select',
    'hint': 'Select, move, and inspect diagram nodes, cards, or controls.',
    'icon': 'tib.canvas_pointer',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'hero',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.pointer_select'
  },
  {
    'id': 'tib.canvas.recompute_layout',
    'label': 'Recompute Layout',
    'hint': 'Run deterministic server-side layered layout preserving pins.',
    'icon': 'tib.canvas_autolayout',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'hero',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.recompute_layout'
  },
  {
    'id': 'tib.canvas.marquee_select',
    'label': 'Marquee Select',
    'hint': 'Drag selection rectangle across multiple elements.',
    'icon': 'tib.canvas_marquee',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.marquee_select'
  },
  {
    'id': 'tib.canvas.zoom_in',
    'label': 'Zoom In',
    'hint': 'Increase crisp vector canvas magnification.',
    'icon': 'tib.zoom_in',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.zoom_in'
  },
  {
    'id': 'tib.canvas.pan_canvas',
    'label': 'Pan Canvas',
    'hint': 'Pan across large tiled diagrams.',
    'icon': 'tib.canvas_pan',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.pan_canvas'
  },
  {
    'id': 'tib.canvas.zoom_out',
    'label': 'Zoom Out',
    'hint': 'Decrease vector canvas magnification.',
    'icon': 'tib.zoom_out',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.zoom_out'
  },
  {
    'id': 'tib.canvas.align_distribute',
    'label': 'Align & Distribute',
    'hint': 'Align selected nodes along edges or centres.',
    'icon': 'tib.canvas_align',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.align_distribute'
  },
  {
    'id': 'tib.canvas.zoom_to_fit',
    'label': 'Zoom to Fit',
    'hint': 'Fit active diagram or screen frame into viewport.',
    'icon': 'tib.zoom_fit',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.zoom_to_fit'
  },
  {
    'id': 'tib.canvas.pin_lock_node',
    'label': 'Pin / Lock Node',
    'hint': 'Pin node coordinates during incremental re-layout.',
    'icon': 'tib.canvas_pin',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.pin_lock_node'
  },
  {
    'id': 'tib.canvas.actual_size_1_1',
    'label': 'Actual Size (1:1)',
    'hint': 'Reset zoom to 100% scale.',
    'icon': 'tib.zoom_100',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.actual_size_1_1'
  },
  {
    'id': 'tib.canvas.sketch_look',
    'label': 'Sketch Look',
    'hint': 'Toggle whiteboard hand-drawn rendering style.',
    'icon': 'tib.canvas_sketch',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.sketch_look'
  },
  {
    'id': 'tib.canvas.minimap_tiling',
    'label': 'Minimap & Tiling',
    'hint': 'Toggle corner overview minimap for server-tiled diagrams.',
    'icon': 'tib.canvas_minimap',
    'sectionId': 'SEC-CANVAS',
    'sectionTitle': 'Canvas & Zoom',
    'slotKind': 'grid',
    'scope': 'Canvas & Zoom',
    'handlerId': 'handler.canvas.minimap_tiling'
  },
  {
    'id': 'tib.gov.save_draft',
    'label': 'Save Draft',
    'hint': 'Write directed checkpoint version into designs.db.',
    'icon': 'tib.save',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'hero',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.save_draft'
  },
  {
    'id': 'tib.gov.accept_version',
    'label': 'Accept Version',
    'hint': 'Authorize & promote version to Accepted active baseline.',
    'icon': 'tib.gov_accept_version',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'hero',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.accept_version'
  },
  {
    'id': 'tib.gov.in_progress',
    'label': 'In Progress',
    'hint': 'Advance status from Draft to In-Progress.',
    'icon': 'tib.gov_in_progress',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.in_progress'
  },
  {
    'id': 'tib.gov.checkpoints_diff',
    'label': 'Checkpoints & Diff',
    'hint': 'Browse save-point history and inspect DDN diffs.',
    'icon': 'tib.history',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.checkpoints_diff'
  },
  {
    'id': 'tib.gov.submit_for_review',
    'label': 'Submit for Review',
    'hint': 'Mark version In-Review with optional Git review ref.',
    'icon': 'tib.gov_in_review',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.submit_for_review'
  },
  {
    'id': 'tib.gov.git_load_save',
    'label': 'Git Load / Save',
    'hint': 'Load or commit clean DDN text file in Git.',
    'icon': 'tib.git_sync',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.git_load_save'
  },
  {
    'id': 'tib.gov.branch_draft',
    'label': 'Branch Draft',
    'hint': 'Branch a new minor Draft checkpoint from Accepted.',
    'icon': 'tib.gov_branch_draft',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.branch_draft'
  },
  {
    'id': 'tib.gov.export_ddn',
    'label': 'Export DDN',
    'hint': 'Export standalone .ddn source document.',
    'icon': 'tib.ddn_export',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.export_ddn'
  },
  {
    'id': 'tib.gov.reconcile_active',
    'label': 'Reconcile Active',
    'hint': 'Merge changes accepted by others via DDN base diff.',
    'icon': 'tib.gov_reconcile',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.reconcile_active'
  },
  {
    'id': 'tib.gov.where_used',
    'label': 'Where Used',
    'hint': 'Inspect cross-design bindings across cubes, BI, and meshes.',
    'icon': 'tib.where_used',
    'sectionId': 'SEC-GOV',
    'sectionTitle': 'Checkpoints & Git',
    'slotKind': 'grid',
    'scope': 'Checkpoints & Git',
    'handlerId': 'handler.gov.where_used'
  },
  {
    'id': 'tib.natrev.preview_native_ddl',
    'label': 'Preview Native DDL',
    'hint': 'Inspect engine-native CREATE / ALTER / DROP statements.',
    'icon': 'tib.sql',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'hero',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.preview_native_ddl'
  },
  {
    'id': 'tib.natrev.apply_via_review',
    'label': 'Apply via Review',
    'hint': 'Submit change plan to ScratchRobin native-operation review.',
    'icon': 'tib.natrev_apply',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'hero',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.apply_via_review'
  },
  {
    'id': 'tib.natrev.diff_vs_live_catalog',
    'label': 'Diff vs Live Catalog',
    'hint': 'Compare proposed metadata against live database state.',
    'icon': 'tib.natrev_diff_live',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'grid',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.diff_vs_live_catalog'
  },
  {
    'id': 'tib.natrev.open_in_sql_editor',
    'label': 'Open in SQL Editor',
    'hint': 'Send generated DDL script to SQL Editor without executing.',
    'icon': 'tib.open_sql_editor',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'grid',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.open_in_sql_editor'
  },
  {
    'id': 'tib.natrev.destructive_check',
    'label': 'Destructive Check',
    'hint': 'Highlight irreversible column/table drops or type narrowing.',
    'icon': 'tib.natrev_destructive_warn',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'grid',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.destructive_check'
  },
  {
    'id': 'tib.natrev.discard_changes',
    'label': 'Discard Changes',
    'hint': 'Reset pending form or migration edits.',
    'icon': 'tib.record_revert',
    'sectionId': 'SEC-NATREV',
    'sectionTitle': 'DDL & Native Review',
    'slotKind': 'grid',
    'scope': 'DDL & Native Review',
    'handlerId': 'handler.natrev.discard_changes'
  },
  {
    'id': 'tib.conn.switch_target',
    'label': 'Switch Target',
    'hint': 'Select active engine/server/database connection.',
    'icon': 'tib.connection_details',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'hero',
    'scope': 'Connection',
    'handlerId': 'handler.conn.switch_target'
  },
  {
    'id': 'tib.conn.register_connector',
    'label': 'Register Connector',
    'hint': 'Register a new database server or embedded file.',
    'icon': 'tib.conn_register',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'hero',
    'scope': 'Connection',
    'handlerId': 'handler.conn.register_connector'
  },
  {
    'id': 'tib.conn.verify_reconnect',
    'label': 'Verify / Reconnect',
    'hint': 'Test connection health and re-establish session.',
    'icon': 'tib.conn_verify',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'grid',
    'scope': 'Connection',
    'handlerId': 'handler.conn.verify_reconnect'
  },
  {
    'id': 'tib.conn.session_limits',
    'label': 'Session Limits',
    'hint': 'Configure personal query timeout and row fetch caps.',
    'icon': 'tib.fetch_limits',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'grid',
    'scope': 'Connection',
    'handlerId': 'handler.conn.session_limits'
  },
  {
    'id': 'tib.conn.disconnect',
    'label': 'Disconnect',
    'hint': 'Close active database session cleanly.',
    'icon': 'tib.conn_disconnect',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'grid',
    'scope': 'Connection',
    'handlerId': 'handler.conn.disconnect'
  },
  {
    'id': 'tib.conn.role_isolation',
    'label': 'Role & Isolation',
    'hint': 'Inspect or switch database role, schema, or charset.',
    'icon': 'tib.conn_session_role',
    'sectionId': 'SEC-CONN',
    'sectionTitle': 'Connection',
    'slotKind': 'grid',
    'scope': 'Connection',
    'handlerId': 'handler.conn.role_isolation'
  },
  {
    'id': 'tib.cat_act.browse_data',
    'label': 'Browse Data',
    'hint': 'Open selected table or view in Data Viewer.',
    'icon': 'tib.data',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'hero',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.browse_data'
  },
  {
    'id': 'tib.cat_act.open_sql_editor',
    'label': 'Open SQL Editor',
    'hint': 'Open SQL Editor bound to this server/database.',
    'icon': 'tib.open_sql_editor',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'hero',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.open_sql_editor'
  },
  {
    'id': 'tib.cat_act.create_child_object',
    'label': 'Create Child Object',
    'hint': 'Open native creator form for child catalog object.',
    'icon': 'tib.cat_create_object',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.create_child_object'
  },
  {
    'id': 'tib.cat_act.schema_compare',
    'label': 'Schema Compare',
    'hint': 'Launch Schema Comparison seeded with this object.',
    'icon': 'tib.cat_schema_compare',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.schema_compare'
  },
  {
    'id': 'tib.cat_act.alter_edit_object',
    'label': 'Alter / Edit Object',
    'hint': 'Open native alter form for selected object.',
    'icon': 'tib.cat_alter_object',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.alter_edit_object'
  },
  {
    'id': 'tib.cat_act.discover_into_erd',
    'label': 'Discover into ERD',
    'hint': 'Import catalog schema into a Draft ERD model.',
    'icon': 'tib.cat_open_erd',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.discover_into_erd'
  },
  {
    'id': 'tib.cat_act.drop_object',
    'label': 'Drop Object',
    'hint': 'Drop selected object via native DDL review.',
    'icon': 'tib.cat_drop_object',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.drop_object'
  },
  {
    'id': 'tib.cat_act.maintenance_backup',
    'label': 'Maintenance & Backup',
    'hint': 'Open engine backup, sweep, vacuum, or trace tools.',
    'icon': 'tib.cat_maintenance',
    'sectionId': 'SEC-CAT-ACT',
    'sectionTitle': 'Object Actions',
    'slotKind': 'grid',
    'scope': 'Object Actions',
    'handlerId': 'handler.cat_act.maintenance_backup'
  },
  {
    'id': 'tib.erd_mod.entity_table',
    'label': '+ Entity / Table',
    'hint': 'Add entity or physical table at active modelling level.',
    'icon': 'tib.erd_add_entity',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'hero',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.entity_table'
  },
  {
    'id': 'tib.erd_mod.relationship',
    'label': '+ Relationship',
    'hint': 'Connect two entities/tables with cardinality & FK rules.',
    'icon': 'tib.erd_add_relation',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'hero',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.relationship'
  },
  {
    'id': 'tib.erd_mod.conceptual_box',
    'label': '+ Conceptual Box',
    'hint': 'Add free-form name-only whiteboard concept.',
    'icon': 'tib.erd_conceptual_box',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.conceptual_box'
  },
  {
    'id': 'tib.erd_mod.level_all',
    'label': 'Level: All',
    'hint': 'View cross-level relations across all four levels.',
    'icon': 'tib.erd_level_all',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.level_all'
  },
  {
    'id': 'tib.erd_mod.logical_entity',
    'label': '+ Logical Entity',
    'hint': 'Add engine-neutral typed logical entity.',
    'icon': 'tib.erd_logical_entity',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.logical_entity'
  },
  {
    'id': 'tib.erd_mod.level_conceptual',
    'label': 'Level: Conceptual',
    'hint': 'Focus on whiteboard conceptual entities.',
    'icon': 'tib.erd_level_conceptual',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.level_conceptual'
  },
  {
    'id': 'tib.erd_mod.physical_table',
    'label': '+ Physical Table',
    'hint': 'Add engine-specific physical table, columns & indexes.',
    'icon': 'tib.erd_physical_table',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.physical_table'
  },
  {
    'id': 'tib.erd_mod.level_logical',
    'label': 'Level: Logical',
    'hint': 'Focus on neutral logical data structures.',
    'icon': 'tib.erd_level_logical',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.level_logical'
  },
  {
    'id': 'tib.erd_mod.deployment_node',
    'label': '+ Deployment Node',
    'hint': 'Add server, cluster, rack, or cloud instance node.',
    'icon': 'tib.erd_deployment_node',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.deployment_node'
  },
  {
    'id': 'tib.erd_mod.level_physical',
    'label': 'Level: Physical',
    'hint': 'Focus on physical schema tables and keys.',
    'icon': 'tib.erd_level_physical',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.level_physical'
  },
  {
    'id': 'tib.erd_mod.whiteboard_note',
    'label': '+ Whiteboard Note',
    'hint': 'Attach architectural or conflict-review annotation.',
    'icon': 'tib.erd_note',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.whiteboard_note'
  },
  {
    'id': 'tib.erd_mod.level_deployment',
    'label': 'Level: Deployment',
    'hint': 'Focus on physical topology & server deployment.',
    'icon': 'tib.erd_level_deployment',
    'sectionId': 'SEC-ERD-MOD',
    'sectionTitle': 'Entities & Levels',
    'slotKind': 'grid',
    'scope': 'Entities & Levels',
    'handlerId': 'handler.erd_mod.level_deployment'
  },
  {
    'id': 'tib.erd_conv.engine_conversion',
    'label': 'Engine Conversion',
    'hint': 'Convert design across engines via neutral logical type maps.',
    'icon': 'tib.erd_engine_convert',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'hero',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.engine_conversion'
  },
  {
    'id': 'tib.erd_conv.alter_migration_plan',
    'label': 'Alter Migration Plan',
    'hint': 'Diff model against live DB/script and generate alter plan.',
    'icon': 'tib.erd_alter_plan',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'hero',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.alter_migration_plan'
  },
  {
    'id': 'tib.erd_conv.udt_type_maps',
    'label': 'UDT & Type Maps',
    'hint': 'Edit reusable user-defined types and per-engine type maps.',
    'icon': 'tib.erd_type_maps',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.udt_type_maps'
  },
  {
    'id': 'tib.erd_conv.import_catalog_ddl',
    'label': 'Import Catalog / DDL',
    'hint': 'Reverse-engineer live catalog or DDL script into DDN.',
    'icon': 'tib.import_data',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.import_catalog_ddl'
  },
  {
    'id': 'tib.erd_conv.naming_standards',
    'label': 'Naming Standards',
    'hint': 'Validate table/column/key naming conventions.',
    'icon': 'tib.erd_naming_standards',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.naming_standards'
  },
  {
    'id': 'tib.erd_conv.system_drift_overlay',
    'label': 'System Drift Overlay',
    'hint': 'Compare deployment landscape against registered servers.',
    'icon': 'tib.erd_system_drift',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.system_drift_overlay'
  },
  {
    'id': 'tib.erd_conv.suspect_bindings',
    'label': 'Suspect Bindings',
    'hint': 'Review catalog bindings flagged suspect after rename/drop.',
    'icon': 'tib.suspect_bindings',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.suspect_bindings'
  },
  {
    'id': 'tib.erd_conv.environment_matrix',
    'label': 'Environment Matrix',
    'hint': 'Compare Dev / Stage / Prod deployment targets.',
    'icon': 'tib.erd_env_matrix',
    'sectionId': 'SEC-ERD-CONV',
    'sectionTitle': 'Convert & Drift',
    'slotKind': 'grid',
    'scope': 'Convert & Drift',
    'handlerId': 'handler.erd_conv.environment_matrix'
  },
  {
    'id': 'tib.cube_dim.measure',
    'label': '+ Measure',
    'hint': 'Add or edit base, filtered, or calculated measures.',
    'icon': 'tib.cube_add_measure',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'hero',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.measure'
  },
  {
    'id': 'tib.cube_dim.dimension',
    'label': '+ Dimension',
    'hint': 'Add dimension entity, key/sort attributes, or role-play link.',
    'icon': 'tib.cube_add_dimension',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'hero',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.dimension'
  },
  {
    'id': 'tib.cube_dim.star_schema_view',
    'label': 'Star Schema View',
    'hint': 'Display dimensional star/snowflake DDN diagram.',
    'icon': 'tib.cube_star_view',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.star_schema_view'
  },
  {
    'id': 'tib.cube_dim.rule_reducer',
    'label': 'Rule Reducer',
    'hint': 'Prune redundant combinatorial aggregation candidates.',
    'icon': 'tib.cube_rule_reducer',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.rule_reducer'
  },
  {
    'id': 'tib.cube_dim.usage_matrix_view',
    'label': 'Usage Matrix View',
    'hint': 'Render matrix.relations@1 dimension usage grid.',
    'icon': 'tib.cube_usage_matrix',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.usage_matrix_view'
  },
  {
    'id': 'tib.cube_dim.aggregation_plans',
    'label': 'Aggregation Plans',
    'hint': 'Configure aggregate tables and refresh policies.',
    'icon': 'tib.cube_agg_plan',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.aggregation_plans'
  },
  {
    'id': 'tib.cube_dim.aggregation_grid',
    'label': 'Aggregation Grid',
    'hint': 'Render table.records@1 pre-aggregation grid.',
    'icon': 'tib.cube_agg_grid',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.aggregation_grid'
  },
  {
    'id': 'tib.cube_dim.check_connection',
    'label': 'Check Connection',
    'hint': 'Validate fact/dimension column bindings against live DB.',
    'icon': 'tib.conn_verify',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.check_connection'
  },
  {
    'id': 'tib.cube_dim.cube_properties',
    'label': 'Cube Properties',
    'hint': 'Edit measure groups, grain, and fact bindings.',
    'icon': 'tib.cube_properties',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.cube_properties'
  },
  {
    'id': 'tib.cube_dim.ai_draft_proposal',
    'label': 'AI Draft Proposal',
    'hint': 'Propose Draft measures/dimensions for human review.',
    'icon': 'tib.ai_draft',
    'sectionId': 'SEC-CUBE-DIM',
    'sectionTitle': 'Dimensions & Rules',
    'slotKind': 'grid',
    'scope': 'Dimensions & Rules',
    'handlerId': 'handler.cube_dim.ai_draft_proposal'
  },
  {
    'id': 'tib.bi_qry.structured_query',
    'label': 'Structured Query',
    'hint': 'Edit SBsql joins, aggregations, parameters, and fan-out checks.',
    'icon': 'tib.builder',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'hero',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.structured_query'
  },
  {
    'id': 'tib.bi_qry.chart_profile',
    'label': 'Chart Profile',
    'hint': 'Select DDNViewerSurface chart type (bar/line/KPI/pivot/etc.).',
    'icon': 'tib.bi_chart_profile',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'hero',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.chart_profile'
  },
  {
    'id': 'tib.bi_qry.dashboard_card',
    'label': '+ Dashboard Card',
    'hint': 'Place question, text, or static metric snapshot card.',
    'icon': 'tib.bi_add_card',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.dashboard_card'
  },
  {
    'id': 'tib.bi_qry.byok_ai_draft',
    'label': 'BYOK AI Draft',
    'hint': 'Search existing questions first and draft a reviewable question.',
    'icon': 'tib.ai_draft',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.byok_ai_draft'
  },
  {
    'id': 'tib.bi_qry.filters_pinning',
    'label': 'Filters & Pinning',
    'hint': 'Configure auto-apply filters and author-pinned defaults.',
    'icon': 'tib.filter_builder',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.filters_pinning'
  },
  {
    'id': 'tib.bi_qry.import_bi_bundle',
    'label': 'Import BI Bundle',
    'hint': 'Convert Superset YAML ZIP or Metabase export into Draft DDN.',
    'icon': 'tib.bi_import_bundle',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.import_bi_bundle'
  },
  {
    'id': 'tib.bi_qry.cross_filter_mode',
    'label': 'Cross-Filter Mode',
    'hint': 'Set card click action (cross_filter / highlight / none).',
    'icon': 'tib.bi_cross_filter',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.cross_filter_mode'
  },
  {
    'id': 'tib.bi_qry.alerts_subscriptions',
    'label': 'Alerts & Subscriptions',
    'hint': 'Configure reviewed outward alert/subscription switches.',
    'icon': 'tib.bi_alerts',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.alerts_subscriptions'
  },
  {
    'id': 'tib.bi_qry.accessible_table',
    'label': 'Accessible Table',
    'hint': 'Toggle companion accessible tabular data view.',
    'icon': 'tib.grid',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.accessible_table'
  },
  {
    'id': 'tib.bi_qry.kiosk_embeds',
    'label': 'Kiosk & Embeds',
    'hint': 'Manage remote dashboard viewer publication & device tokens.',
    'icon': 'tib.bi_kiosk_embed',
    'sectionId': 'SEC-BI-QRY',
    'sectionTitle': 'BI Query & Charts',
    'slotKind': 'grid',
    'scope': 'BI Query & Charts',
    'handlerId': 'handler.bi_qry.kiosk_embeds'
  },
  {
    'id': 'tib.mesh_ui.screen_frame',
    'label': '+ Screen Frame',
    'hint': 'Add wireframe screen frame (ui.frame) with optional SR-F code.',
    'icon': 'tib.mesh_add_screen',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'hero',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.screen_frame'
  },
  {
    'id': 'tib.mesh_ui.stencil_control',
    'label': '+ Stencil Control',
    'hint': 'Place input, button, checkbox, label, or list control.',
    'icon': 'tib.mesh_add_control',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'hero',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.stencil_control'
  },
  {
    'id': 'tib.mesh_ui.data_grid',
    'label': '+ Data Grid',
    'hint': 'Add ui.grid control with named data-bound columns.',
    'icon': 'tib.mesh_ctrl_grid',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.data_grid'
  },
  {
    'id': 'tib.mesh_ui.upload_screenshot',
    'label': 'Upload Screenshot',
    'hint': 'Store screenshot in content-addressed asset_blob (16 MiB cap).',
    'icon': 'tib.mesh_upload_shot',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.upload_screenshot'
  },
  {
    'id': 'tib.mesh_ui.dropdown_radio',
    'label': '+ Dropdown / Radio',
    'hint': 'Add ui.dropdown or ui.radio choice control.',
    'icon': 'tib.mesh_ctrl_dropdown',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.dropdown_radio'
  },
  {
    'id': 'tib.mesh_ui.draw_hotspot_region',
    'label': 'Draw Hotspot Region',
    'hint': 'Define rectangular ui.region bounds on screenshot.',
    'icon': 'tib.mesh_draw_region',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.draw_hotspot_region'
  },
  {
    'id': 'tib.mesh_ui.tab_bar',
    'label': '+ Tab Bar',
    'hint': 'Add ui.tabs container control.',
    'icon': 'tib.mesh_ctrl_tabs',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.tab_bar'
  },
  {
    'id': 'tib.mesh_ui.redact_regions',
    'label': 'Redact Regions',
    'hint': 'Destructively replace sensitive pixels in stored asset_blob.',
    'icon': 'tib.mesh_redact',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.redact_regions'
  },
  {
    'id': 'tib.mesh_ui.data_binding',
    'label': '+ Data Binding',
    'hint': 'Bind control or region to catalog table/column/question.',
    'icon': 'tib.mesh_data_binding',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.data_binding'
  },
  {
    'id': 'tib.mesh_ui.trace_as_mesh',
    'label': 'Trace as Mesh',
    'hint': 'Convert annotated screenshot regions into wireframe controls.',
    'icon': 'tib.mesh_trace',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.trace_as_mesh'
  },
  {
    'id': 'tib.mesh_ui.navigation_link',
    'label': '+ Navigation Link',
    'hint': 'Link control/region to target screen for Screen Flow view.',
    'icon': 'tib.mesh_nav_link',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.navigation_link'
  },
  {
    'id': 'tib.mesh_ui.import_sr_f_form',
    'label': 'Import SR-F Form',
    'hint': 'Import ScratchRobin ui_descriptors SR-F form as Draft mesh.',
    'icon': 'tib.mesh_import_srf',
    'sectionId': 'SEC-MESH-UI',
    'sectionTitle': 'Screens & Hotspots',
    'slotKind': 'grid',
    'scope': 'Screens & Hotspots',
    'handlerId': 'handler.mesh_ui.import_sr_f_form'
  },
  {
    'id': 'tib.cmp_src.run_comparison',
    'label': 'Run Comparison',
    'hint': 'Compare desired, live, or baseline metadata across endpoints.',
    'icon': 'tib.cmp_run',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'hero',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.run_comparison'
  },
  {
    'id': 'tib.cmp_src.build_change_plan',
    'label': 'Build Change Plan',
    'hint': 'Compile selected differences into ordered native DDL plan.',
    'icon': 'tib.erd_alter_plan',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'hero',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.build_change_plan'
  },
  {
    'id': 'tib.cmp_src.left_source',
    'label': 'Left Source',
    'hint': 'Pick source live database, DDN checkpoint, or DDL file.',
    'icon': 'tib.cmp_left_source',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.left_source'
  },
  {
    'id': 'tib.cmp_src.map_rename',
    'label': 'Map Rename',
    'hint': 'Link renamed table/column identities to preserve data.',
    'icon': 'tib.cmp_map_rename',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.map_rename'
  },
  {
    'id': 'tib.cmp_src.right_target',
    'label': 'Right Target',
    'hint': 'Pick target live database, DDN checkpoint, or DDL file.',
    'icon': 'tib.cmp_right_target',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.right_target'
  },
  {
    'id': 'tib.cmp_src.carry_difference',
    'label': 'Carry Difference',
    'hint': 'Include selected difference in migration plan.',
    'icon': 'tib.cmp_carry',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.carry_difference'
  },
  {
    'id': 'tib.cmp_src.object_type_scope',
    'label': 'Object Type Scope',
    'hint': 'Filter compared object families (view filter != deletion).',
    'icon': 'tib.filter_builder',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.object_type_scope'
  },
  {
    'id': 'tib.cmp_src.skip_difference',
    'label': 'Skip Difference',
    'hint': 'Exclude selected difference from migration plan.',
    'icon': 'tib.cmp_skip',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.skip_difference'
  },
  {
    'id': 'tib.cmp_src.ignore_options',
    'label': 'Ignore Options',
    'hint': 'Configure whitespace, comments, tablespace, and owner rules.',
    'icon': 'tib.cmp_ignore_rules',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.ignore_options'
  },
  {
    'id': 'tib.cmp_src.swap_endpoints',
    'label': 'Swap Endpoints',
    'hint': 'Reverse source and target comparison direction.',
    'icon': 'tib.cmp_swap',
    'sectionId': 'SEC-CMP-SRC',
    'sectionTitle': 'Compare & Map',
    'slotKind': 'grid',
    'scope': 'Compare & Map',
    'handlerId': 'handler.cmp_src.swap_endpoints'
  },
  {
    'id': 'tib.ops_run.start_operation',
    'label': 'Start Operation',
    'hint': 'Review and start selected native administration task.',
    'icon': 'tib.execute_statement',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'hero',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.start_operation'
  },
  {
    'id': 'tib.ops_run.stop_operation',
    'label': 'Stop Operation',
    'hint': 'Stop active trace session or cancel running background job.',
    'icon': 'tib.cancel',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'hero',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.stop_operation'
  },
  {
    'id': 'tib.ops_run.backup_database',
    'label': 'Backup Database',
    'hint': 'Configure native physical or logical backup job.',
    'icon': 'tib.ops_backup',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.backup_database'
  },
  {
    'id': 'tib.ops_run.live_engine_trace',
    'label': 'Live Engine Trace',
    'hint': 'Stream Firebird Trace / audit / active query telemetry.',
    'icon': 'tib.ops_live_trace',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.live_engine_trace'
  },
  {
    'id': 'tib.ops_run.restore_database',
    'label': 'Restore Database',
    'hint': 'Restore backup archive with page/validation options.',
    'icon': 'tib.ops_restore',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.restore_database'
  },
  {
    'id': 'tib.ops_run.limbo_tx_recovery',
    'label': 'Limbo Tx Recovery',
    'hint': 'Inspect and commit/rollback in-doubt two-phase transactions.',
    'icon': 'tib.ops_limbo_recovery',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.limbo_tx_recovery'
  },
  {
    'id': 'tib.ops_run.sweep_vacuum',
    'label': 'Sweep / Vacuum',
    'hint': 'Run Firebird gfix sweep, PostgreSQL VACUUM, or ANALYZE.',
    'icon': 'tib.ops_sweep_vacuum',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.sweep_vacuum'
  },
  {
    'id': 'tib.ops_run.download_job_log',
    'label': 'Download Job Log',
    'hint': 'Export complete native tool stdout/stderr log.',
    'icon': 'tib.ops_download_log',
    'sectionId': 'SEC-OPS-RUN',
    'sectionTitle': 'Engine Operations',
    'slotKind': 'grid',
    'scope': 'Engine Operations',
    'handlerId': 'handler.ops_run.download_job_log'
  },
  {
    'id': 'tib.security.manage_users',
    'label': 'Manage Users',
    'hint': 'Open engine-native User & Authentication Manager.',
    'icon': 'tib.security_users',
    'sectionId': 'SEC-SECURITY',
    'sectionTitle': 'Security & Access',
    'slotKind': 'hero',
    'scope': 'Security & Access',
    'handlerId': 'handler.security.manage_users'
  },
  {
    'id': 'tib.security.object_permissions',
    'label': 'Object Permissions',
    'hint': 'Inspect and edit Principal \u00d7 Privilege grants on the active object.',
    'icon': 'tib.security_grants',
    'sectionId': 'SEC-SECURITY',
    'sectionTitle': 'Security & Access',
    'slotKind': 'hero',
    'scope': 'Security & Access',
    'handlerId': 'handler.security.object_permissions'
  },
  {
    'id': 'tib.security.manage_roles',
    'label': 'Manage Roles',
    'hint': 'Open Role, Group & Membership Manager.',
    'icon': 'tib.security_roles',
    'sectionId': 'SEC-SECURITY',
    'sectionTitle': 'Security & Access',
    'slotKind': 'grid',
    'scope': 'Security & Access',
    'handlerId': 'handler.security.manage_roles'
  },
  {
    'id': 'tib.security.new_principal',
    'label': 'New User / Role',
    'hint': 'Create a new user account or SQL role in the active scope.',
    'icon': 'tib.cat_create_object',
    'sectionId': 'SEC-SECURITY',
    'sectionTitle': 'Security & Access',
    'slotKind': 'grid',
    'scope': 'Security & Access',
    'handlerId': 'handler.security.new_principal'
  },
  {
    'id': 'tib.inspector.all',
    'label': 'All Sections',
    'hint': 'Display all object inspector sections including Overview, Structure, Permissions, DDL, and Dependencies.',
    'icon': 'tib.inspect_all',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'hero',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.all'
  },
  {
    'id': 'tib.inspector.permissions',
    'label': 'Permissions',
    'hint': 'Focus the interactive Principal \u00d7 Privilege grants matrix for this object.',
    'icon': 'tib.inspect_permissions',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'hero',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.permissions'
  },
  {
    'id': 'tib.inspector.overview',
    'label': 'Overview',
    'hint': 'Show summary attributes, comment, and registration details.',
    'icon': 'tib.inspect_overview',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'grid',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.overview'
  },
  {
    'id': 'tib.inspector.structure',
    'label': 'Structure',
    'hint': 'Show columns, indexes, constraints, triggers, and partitions.',
    'icon': 'tib.inspect_structure',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'grid',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.structure'
  },
  {
    'id': 'tib.inspector.ddl',
    'label': 'DDL / SQL',
    'hint': 'Show native CREATE / ALTER DDL SQL definition.',
    'icon': 'tib.inspect_ddl',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'grid',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.ddl'
  },
  {
    'id': 'tib.inspector.dependencies',
    'label': 'Dependencies',
    'hint': 'Show object dependencies and dependents.',
    'icon': 'tib.inspect_dependencies',
    'sectionId': 'SEC-INSPECTOR',
    'sectionTitle': 'Inspector Sections',
    'slotKind': 'grid',
    'scope': 'Inspector Sections',
    'handlerId': 'handler.inspector.dependencies'
  }
]);

export const STANDARD_TIB_ACTIONS_BY_ID = Object.freeze(
  Object.fromEntries(STANDARD_TIB_ACTIONS.map((a) => [a.id, a]))
);

export const CALLABLE_CODE_TARGETS = Object.freeze([
  {
    'id': 'shell.quick.new',
    'label': 'Shell \u00b7 New Item / Tab',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:quick-action',
    'actionKey': 'new'
  },
  {
    'id': 'shell.quick.save',
    'label': 'Shell \u00b7 Save Active Work',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:quick-action',
    'actionKey': 'save'
  },
  {
    'id': 'shell.quick.undo',
    'label': 'Shell \u00b7 Undo',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:quick-action',
    'actionKey': 'undo'
  },
  {
    'id': 'shell.quick.redo',
    'label': 'Shell \u00b7 Redo',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:quick-action',
    'actionKey': 'redo'
  },
  {
    'id': 'shell.window.toggle_left_drawer',
    'label': 'Shell \u00b7 Toggle Left Side Drawer (3a)',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'toggle_left_drawer'
  },
  {
    'id': 'shell.window.toggle_right_drawer',
    'label': 'Shell \u00b7 Toggle Right Properties Drawer (3c)',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'toggle_right_drawer'
  },
  {
    'id': 'shell.window.toggle_icon_bar',
    'label': 'Shell \u00b7 Toggle Tabbed-Icon-Bar (3b)',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'toggle_icon_bar'
  },
  {
    'id': 'shell.window.toggle_status_bar',
    'label': 'Shell \u00b7 Toggle Status Bar (3d)',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'toggle_status_bar'
  },
  {
    'id': 'shell.window.detach_active',
    'label': 'Shell \u00b7 Float Active Application Window',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'detach_active'
  },
  {
    'id': 'project.settings.global',
    'label': 'Shell \u00b7 Open Preferences & Settings',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:open-preferences',
    'actionKey': 'open_preferences'
  },
  {
    'id': 'project.session.lock',
    'label': 'Shell \u00b7 Lock Session Screen',
    'category': 'Workbench Shell',
    'eventName': 'scratchrobin:shell-command',
    'actionKey': 'lock_session'
  },
  {
    'id': 'handler.workspace.primary_surface',
    'label': 'Workspace & Panels \u00b7 Primary Surface',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.primary_surface'
  },
  {
    'id': 'handler.workspace.secondary_split_pane',
    'label': 'Workspace & Panels \u00b7 Secondary Split Pane',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.secondary_split_pane'
  },
  {
    'id': 'handler.workspace.data_grid_view',
    'label': 'Workspace & Panels \u00b7 Data Grid View',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.data_grid_view'
  },
  {
    'id': 'handler.workspace.fields_list',
    'label': 'Workspace & Panels \u00b7 Fields List',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.fields_list'
  },
  {
    'id': 'handler.workspace.sql_source',
    'label': 'Workspace & Panels \u00b7 SQL Source',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.sql_source'
  },
  {
    'id': 'handler.workspace.object_info',
    'label': 'Workspace & Panels \u00b7 Object Info',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.object_info'
  },
  {
    'id': 'handler.workspace.visual_sql_builder',
    'label': 'Workspace & Panels \u00b7 Visual SQL Builder',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.visual_sql_builder'
  },
  {
    'id': 'handler.workspace.ddl_metadata',
    'label': 'Workspace & Panels \u00b7 DDL Metadata',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.ddl_metadata'
  },
  {
    'id': 'handler.workspace.metrics_plan',
    'label': 'Workspace & Panels \u00b7 Metrics & Plan',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.metrics_plan'
  },
  {
    'id': 'handler.workspace.messages',
    'label': 'Workspace & Panels \u00b7 Messages',
    'category': 'Workspace & Panels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.workspace.messages'
  },
  {
    'id': 'handler.pres.standard_grid',
    'label': 'Data Presentation \u00b7 Standard Grid',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.standard_grid'
  },
  {
    'id': 'handler.pres.layout_templates',
    'label': 'Data Presentation \u00b7 Layout Templates',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.layout_templates'
  },
  {
    'id': 'handler.pres.mini_forms',
    'label': 'Data Presentation \u00b7 Mini-Forms',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.mini_forms'
  },
  {
    'id': 'handler.pres.hybrid_on_edit',
    'label': 'Data Presentation \u00b7 Hybrid-on-Edit',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.hybrid_on_edit'
  },
  {
    'id': 'handler.pres.hybrid_split',
    'label': 'Data Presentation \u00b7 Hybrid Split',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.hybrid_split'
  },
  {
    'id': 'handler.pres.inherit_defaults',
    'label': 'Data Presentation \u00b7 Inherit Defaults',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.inherit_defaults'
  },
  {
    'id': 'handler.pres.single_form',
    'label': 'Data Presentation \u00b7 Single Form',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.single_form'
  },
  {
    'id': 'handler.pres.save_object_layout',
    'label': 'Data Presentation \u00b7 Save Object Layout',
    'category': 'Data Presentation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.pres.save_object_layout'
  },
  {
    'id': 'handler.coltext.font_colour_selector',
    'label': 'Columns & Text \u00b7 Font & Colour Selector',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.font_colour_selector'
  },
  {
    'id': 'handler.coltext.align_left',
    'label': 'Columns & Text \u00b7 Align Left',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_left'
  },
  {
    'id': 'handler.coltext.align_top',
    'label': 'Columns & Text \u00b7 Align Top',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_top'
  },
  {
    'id': 'handler.coltext.align_centre',
    'label': 'Columns & Text \u00b7 Align Centre',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_centre'
  },
  {
    'id': 'handler.coltext.align_middle',
    'label': 'Columns & Text \u00b7 Align Middle',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_middle'
  },
  {
    'id': 'handler.coltext.align_right',
    'label': 'Columns & Text \u00b7 Align Right',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_right'
  },
  {
    'id': 'handler.coltext.align_bottom',
    'label': 'Columns & Text \u00b7 Align Bottom',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.align_bottom'
  },
  {
    'id': 'handler.coltext.full_justify',
    'label': 'Columns & Text \u00b7 Full Justify',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.full_justify'
  },
  {
    'id': 'handler.coltext.wrap_clamped',
    'label': 'Columns & Text \u00b7 Wrap Clamped',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.wrap_clamped'
  },
  {
    'id': 'handler.coltext.no_wrap',
    'label': 'Columns & Text \u00b7 No Wrap',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.no_wrap'
  },
  {
    'id': 'handler.coltext.full_wrap',
    'label': 'Columns & Text \u00b7 Full Wrap',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.full_wrap'
  },
  {
    'id': 'handler.coltext.autosize_column',
    'label': 'Columns & Text \u00b7 Autosize Column',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.autosize_column'
  },
  {
    'id': 'handler.coltext.freeze_column',
    'label': 'Columns & Text \u00b7 Freeze Column',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.freeze_column'
  },
  {
    'id': 'handler.coltext.visible_columns',
    'label': 'Columns & Text \u00b7 Visible Columns',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.visible_columns'
  },
  {
    'id': 'handler.coltext.reset_layout',
    'label': 'Columns & Text \u00b7 Reset Layout',
    'category': 'Columns & Text',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.coltext.reset_layout'
  },
  {
    'id': 'handler.valfmt.format_sql_values',
    'label': 'Value Formatting \u00b7 Format SQL / Values',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.format_sql_values'
  },
  {
    'id': 'handler.valfmt.boolean_t_f',
    'label': 'Value Formatting \u00b7 Boolean T / F',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.boolean_t_f'
  },
  {
    'id': 'handler.valfmt.null_badge_style',
    'label': 'Value Formatting \u00b7 NULL Badge Style',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.null_badge_style'
  },
  {
    'id': 'handler.valfmt.boolean_yes_no',
    'label': 'Value Formatting \u00b7 Boolean Yes / No',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.boolean_yes_no'
  },
  {
    'id': 'handler.valfmt.numeric_precision',
    'label': 'Value Formatting \u00b7 Numeric Precision',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.numeric_precision'
  },
  {
    'id': 'handler.valfmt.boolean_1_0',
    'label': 'Value Formatting \u00b7 Boolean 1 / 0',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.boolean_1_0'
  },
  {
    'id': 'handler.valfmt.date_timezone',
    'label': 'Value Formatting \u00b7 Date & Timezone',
    'category': 'Value Formatting',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.valfmt.date_timezone'
  },
  {
    'id': 'handler.exec.execute_sql',
    'label': 'Query Execution \u00b7 Execute SQL',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.execute_sql'
  },
  {
    'id': 'handler.exec.execute_script',
    'label': 'Query Execution \u00b7 Execute Script',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.execute_script'
  },
  {
    'id': 'handler.exec.explain_plan',
    'label': 'Query Execution \u00b7 Explain Plan',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.explain_plan'
  },
  {
    'id': 'handler.exec.prepare_statement',
    'label': 'Query Execution \u00b7 Prepare Statement',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.prepare_statement'
  },
  {
    'id': 'handler.exec.analyze_metrics',
    'label': 'Query Execution \u00b7 Analyze & Metrics',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.analyze_metrics'
  },
  {
    'id': 'handler.exec.bind_parameters',
    'label': 'Query Execution \u00b7 Bind Parameters',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.bind_parameters'
  },
  {
    'id': 'handler.exec.cancel_query',
    'label': 'Query Execution \u00b7 Cancel Query',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.cancel_query'
  },
  {
    'id': 'handler.exec.statement_terminator',
    'label': 'Query Execution \u00b7 Statement Terminator',
    'category': 'Query Execution',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.exec.statement_terminator'
  },
  {
    'id': 'handler.tx.commit',
    'label': 'Transaction \u00b7 Commit',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.commit'
  },
  {
    'id': 'handler.tx.rollback',
    'label': 'Transaction \u00b7 Rollback',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.rollback'
  },
  {
    'id': 'handler.tx.start_transaction',
    'label': 'Transaction \u00b7 Start Transaction',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.start_transaction'
  },
  {
    'id': 'handler.tx.prepare_2pc',
    'label': 'Transaction \u00b7 Prepare 2PC',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.prepare_2pc'
  },
  {
    'id': 'handler.tx.auto_commit_toggle',
    'label': 'Transaction \u00b7 Auto-commit Toggle',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.auto_commit_toggle'
  },
  {
    'id': 'handler.tx.inspect_staged_sql',
    'label': 'Transaction \u00b7 Inspect Staged SQL',
    'category': 'Transaction',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.tx.inspect_staged_sql'
  },
  {
    'id': 'handler.rec.edit_accept_row',
    'label': 'Records \u00b7 Edit / Accept Row',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.edit_accept_row'
  },
  {
    'id': 'handler.rec.insert_row',
    'label': 'Records \u00b7 Insert Row',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.insert_row'
  },
  {
    'id': 'handler.rec.duplicate_row',
    'label': 'Records \u00b7 Duplicate Row',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.duplicate_row'
  },
  {
    'id': 'handler.rec.set_null',
    'label': 'Records \u00b7 Set NULL',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.set_null'
  },
  {
    'id': 'handler.rec.delete_row',
    'label': 'Records \u00b7 Delete Row',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.delete_row'
  },
  {
    'id': 'handler.rec.revert_row',
    'label': 'Records \u00b7 Revert Row',
    'category': 'Records',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.rec.revert_row'
  },
  {
    'id': 'handler.nav.locate_jump',
    'label': 'Navigation \u00b7 Locate / Jump',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.locate_jump'
  },
  {
    'id': 'handler.nav.bookmark',
    'label': 'Navigation \u00b7 Bookmark (!)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.bookmark'
  },
  {
    'id': 'handler.nav.first_row',
    'label': 'Navigation \u00b7 First Row (|<)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.first_row'
  },
  {
    'id': 'handler.nav.last_row',
    'label': 'Navigation \u00b7 Last Row (>|)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.last_row'
  },
  {
    'id': 'handler.nav.prev_page',
    'label': 'Navigation \u00b7 Prev Page (<<)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.prev_page'
  },
  {
    'id': 'handler.nav.next_page',
    'label': 'Navigation \u00b7 Next Page (>>)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.next_page'
  },
  {
    'id': 'handler.nav.prev_row',
    'label': 'Navigation \u00b7 Prev Row (<)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.prev_row'
  },
  {
    'id': 'handler.nav.next_row',
    'label': 'Navigation \u00b7 Next Row (>)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.next_row'
  },
  {
    'id': 'handler.nav.prev_bookmark',
    'label': 'Navigation \u00b7 Prev Bookmark (!<)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.prev_bookmark'
  },
  {
    'id': 'handler.nav.next_bookmark',
    'label': 'Navigation \u00b7 Next Bookmark (!>)',
    'category': 'Navigation',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.nav.next_bookmark'
  },
  {
    'id': 'handler.find.quick_find',
    'label': 'Find & Filter \u00b7 Quick Find',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.quick_find'
  },
  {
    'id': 'handler.find.filter_builder',
    'label': 'Find & Filter \u00b7 Filter Builder',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.filter_builder'
  },
  {
    'id': 'handler.find.local_sort',
    'label': 'Find & Filter \u00b7 Local Sort',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.local_sort'
  },
  {
    'id': 'handler.find.refresh_data',
    'label': 'Find & Filter \u00b7 Refresh Data',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.refresh_data'
  },
  {
    'id': 'handler.find.server_order_by',
    'label': 'Find & Filter \u00b7 Server ORDER BY',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.server_order_by'
  },
  {
    'id': 'handler.find.fetch_step_limits',
    'label': 'Find & Filter \u00b7 Fetch & Step Limits',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.fetch_step_limits'
  },
  {
    'id': 'handler.find.clear_filters_sort',
    'label': 'Find & Filter \u00b7 Clear Filters & Sort',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.clear_filters_sort'
  },
  {
    'id': 'handler.find.target_info',
    'label': 'Find & Filter \u00b7 Target Info',
    'category': 'Find & Filter',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.find.target_info'
  },
  {
    'id': 'handler.clip.copy',
    'label': 'Clipboard \u00b7 Copy',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.copy'
  },
  {
    'id': 'handler.clip.paste',
    'label': 'Clipboard \u00b7 Paste',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.paste'
  },
  {
    'id': 'handler.clip.cut',
    'label': 'Clipboard \u00b7 Cut',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.cut'
  },
  {
    'id': 'handler.clip.undo',
    'label': 'Clipboard \u00b7 Undo',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.undo'
  },
  {
    'id': 'handler.clip.copy_special',
    'label': 'Clipboard \u00b7 Copy Special',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.copy_special'
  },
  {
    'id': 'handler.clip.redo',
    'label': 'Clipboard \u00b7 Redo',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.redo'
  },
  {
    'id': 'handler.clip.select_all',
    'label': 'Clipboard \u00b7 Select All',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.select_all'
  },
  {
    'id': 'handler.clip.duplicate',
    'label': 'Clipboard \u00b7 Duplicate',
    'category': 'Clipboard',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.clip.duplicate'
  },
  {
    'id': 'handler.file.save',
    'label': 'Files & Scripts \u00b7 Save',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.save'
  },
  {
    'id': 'handler.file.open_file',
    'label': 'Files & Scripts \u00b7 Open File',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.open_file'
  },
  {
    'id': 'handler.file.new',
    'label': 'Files & Scripts \u00b7 New',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.new'
  },
  {
    'id': 'handler.file.recent_history',
    'label': 'Files & Scripts \u00b7 Recent & History',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.recent_history'
  },
  {
    'id': 'handler.file.save_as',
    'label': 'Files & Scripts \u00b7 Save As',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.save_as'
  },
  {
    'id': 'handler.file.git_sync',
    'label': 'Files & Scripts \u00b7 Git Sync',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.git_sync'
  },
  {
    'id': 'handler.file.revert_file',
    'label': 'Files & Scripts \u00b7 Revert File',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.revert_file'
  },
  {
    'id': 'handler.file.clear_buffer',
    'label': 'Files & Scripts \u00b7 Clear Buffer',
    'category': 'Files & Scripts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.file.clear_buffer'
  },
  {
    'id': 'handler.qlib.saved_queries',
    'label': 'Query Library \u00b7 Saved Queries',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.saved_queries'
  },
  {
    'id': 'handler.qlib.sql_snippets',
    'label': 'Query Library \u00b7 SQL Snippets',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.sql_snippets'
  },
  {
    'id': 'handler.qlib.save_to_library',
    'label': 'Query Library \u00b7 Save to Library',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.save_to_library'
  },
  {
    'id': 'handler.qlib.execution_history',
    'label': 'Query Library \u00b7 Execution History',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.execution_history'
  },
  {
    'id': 'handler.qlib.save_selection_as_snippet',
    'label': 'Query Library \u00b7 Save Selection as Snippet',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.save_selection_as_snippet'
  },
  {
    'id': 'handler.qlib.sql_notebook_mode',
    'label': 'Query Library \u00b7 SQL Notebook Mode',
    'category': 'Query Library',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.qlib.sql_notebook_mode'
  },
  {
    'id': 'handler.transfer.export_data_asset',
    'label': 'Import & Export \u00b7 Export Data / Asset',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.export_data_asset'
  },
  {
    'id': 'handler.transfer.import_data_bundle',
    'label': 'Import & Export \u00b7 Import Data / Bundle',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.import_data_bundle'
  },
  {
    'id': 'handler.transfer.excel_ods',
    'label': 'Import & Export \u00b7 Excel / ODS',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.excel_ods'
  },
  {
    'id': 'handler.transfer.copy_inserts',
    'label': 'Import & Export \u00b7 Copy INSERTs',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.copy_inserts'
  },
  {
    'id': 'handler.transfer.pdf_report',
    'label': 'Import & Export \u00b7 PDF Report',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.pdf_report'
  },
  {
    'id': 'handler.transfer.copy_updates',
    'label': 'Import & Export \u00b7 Copy UPDATEs',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.copy_updates'
  },
  {
    'id': 'handler.transfer.copy_csv_tsv',
    'label': 'Import & Export \u00b7 Copy CSV / TSV',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.copy_csv_tsv'
  },
  {
    'id': 'handler.transfer.open_in_sql_editor',
    'label': 'Import & Export \u00b7 Open in SQL Editor',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.open_in_sql_editor'
  },
  {
    'id': 'handler.transfer.copy_json',
    'label': 'Import & Export \u00b7 Copy JSON',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.copy_json'
  },
  {
    'id': 'handler.transfer.save_as_bi_question',
    'label': 'Import & Export \u00b7 Save as BI Question',
    'category': 'Import & Export',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.transfer.save_as_bi_question'
  },
  {
    'id': 'handler.telem.refresh_snapshot',
    'label': 'Refresh & History \u00b7 Refresh Snapshot',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.refresh_snapshot'
  },
  {
    'id': 'handler.telem.compute_deep_stats',
    'label': 'Refresh & History \u00b7 Compute Deep Stats',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.compute_deep_stats'
  },
  {
    'id': 'handler.telem.live_session',
    'label': 'Refresh & History \u00b7 Live Session',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.live_session'
  },
  {
    'id': 'handler.telem.auto_refresh',
    'label': 'Refresh & History \u00b7 Auto-Refresh',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.auto_refresh'
  },
  {
    'id': 'handler.telem.1h_24h_rollups',
    'label': 'Refresh & History \u00b7 1h / 24h Rollups',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.1h_24h_rollups'
  },
  {
    'id': 'handler.telem.persist_to_vault',
    'label': 'Refresh & History \u00b7 Persist to Vault',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.persist_to_vault'
  },
  {
    'id': 'handler.telem.30d_365d_vault',
    'label': 'Refresh & History \u00b7 30d / 365d Vault',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.30d_365d_vault'
  },
  {
    'id': 'handler.telem.prune_history',
    'label': 'Refresh & History \u00b7 Prune History',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.prune_history'
  },
  {
    'id': 'handler.telem.customize_cards',
    'label': 'Refresh & History \u00b7 Customize Cards',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.customize_cards'
  },
  {
    'id': 'handler.telem.export_health_report',
    'label': 'Refresh & History \u00b7 Export Health Report',
    'category': 'Refresh & History',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.telem.export_health_report'
  },
  {
    'id': 'handler.canvas.pointer_select',
    'label': 'Canvas & Zoom \u00b7 Pointer Select',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.pointer_select'
  },
  {
    'id': 'handler.canvas.recompute_layout',
    'label': 'Canvas & Zoom \u00b7 Recompute Layout',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.recompute_layout'
  },
  {
    'id': 'handler.canvas.marquee_select',
    'label': 'Canvas & Zoom \u00b7 Marquee Select',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.marquee_select'
  },
  {
    'id': 'handler.canvas.zoom_in',
    'label': 'Canvas & Zoom \u00b7 Zoom In',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.zoom_in'
  },
  {
    'id': 'handler.canvas.pan_canvas',
    'label': 'Canvas & Zoom \u00b7 Pan Canvas',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.pan_canvas'
  },
  {
    'id': 'handler.canvas.zoom_out',
    'label': 'Canvas & Zoom \u00b7 Zoom Out',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.zoom_out'
  },
  {
    'id': 'handler.canvas.align_distribute',
    'label': 'Canvas & Zoom \u00b7 Align & Distribute',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.align_distribute'
  },
  {
    'id': 'handler.canvas.zoom_to_fit',
    'label': 'Canvas & Zoom \u00b7 Zoom to Fit',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.zoom_to_fit'
  },
  {
    'id': 'handler.canvas.pin_lock_node',
    'label': 'Canvas & Zoom \u00b7 Pin / Lock Node',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.pin_lock_node'
  },
  {
    'id': 'handler.canvas.actual_size_1_1',
    'label': 'Canvas & Zoom \u00b7 Actual Size (1:1)',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.actual_size_1_1'
  },
  {
    'id': 'handler.canvas.sketch_look',
    'label': 'Canvas & Zoom \u00b7 Sketch Look',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.sketch_look'
  },
  {
    'id': 'handler.canvas.minimap_tiling',
    'label': 'Canvas & Zoom \u00b7 Minimap & Tiling',
    'category': 'Canvas & Zoom',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.canvas.minimap_tiling'
  },
  {
    'id': 'handler.gov.save_draft',
    'label': 'Checkpoints & Git \u00b7 Save Draft',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.save_draft'
  },
  {
    'id': 'handler.gov.accept_version',
    'label': 'Checkpoints & Git \u00b7 Accept Version',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.accept_version'
  },
  {
    'id': 'handler.gov.in_progress',
    'label': 'Checkpoints & Git \u00b7 In Progress',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.in_progress'
  },
  {
    'id': 'handler.gov.checkpoints_diff',
    'label': 'Checkpoints & Git \u00b7 Checkpoints & Diff',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.checkpoints_diff'
  },
  {
    'id': 'handler.gov.submit_for_review',
    'label': 'Checkpoints & Git \u00b7 Submit for Review',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.submit_for_review'
  },
  {
    'id': 'handler.gov.git_load_save',
    'label': 'Checkpoints & Git \u00b7 Git Load / Save',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.git_load_save'
  },
  {
    'id': 'handler.gov.branch_draft',
    'label': 'Checkpoints & Git \u00b7 Branch Draft',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.branch_draft'
  },
  {
    'id': 'handler.gov.export_ddn',
    'label': 'Checkpoints & Git \u00b7 Export DDN',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.export_ddn'
  },
  {
    'id': 'handler.gov.reconcile_active',
    'label': 'Checkpoints & Git \u00b7 Reconcile Active',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.reconcile_active'
  },
  {
    'id': 'handler.gov.where_used',
    'label': 'Checkpoints & Git \u00b7 Where Used',
    'category': 'Checkpoints & Git',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.gov.where_used'
  },
  {
    'id': 'handler.natrev.preview_native_ddl',
    'label': 'DDL & Native Review \u00b7 Preview Native DDL',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.preview_native_ddl'
  },
  {
    'id': 'handler.natrev.apply_via_review',
    'label': 'DDL & Native Review \u00b7 Apply via Review',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.apply_via_review'
  },
  {
    'id': 'handler.natrev.diff_vs_live_catalog',
    'label': 'DDL & Native Review \u00b7 Diff vs Live Catalog',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.diff_vs_live_catalog'
  },
  {
    'id': 'handler.natrev.open_in_sql_editor',
    'label': 'DDL & Native Review \u00b7 Open in SQL Editor',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.open_in_sql_editor'
  },
  {
    'id': 'handler.natrev.destructive_check',
    'label': 'DDL & Native Review \u00b7 Destructive Check',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.destructive_check'
  },
  {
    'id': 'handler.natrev.discard_changes',
    'label': 'DDL & Native Review \u00b7 Discard Changes',
    'category': 'DDL & Native Review',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.natrev.discard_changes'
  },
  {
    'id': 'handler.conn.switch_target',
    'label': 'Connection \u00b7 Switch Target',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.switch_target'
  },
  {
    'id': 'handler.conn.register_connector',
    'label': 'Connection \u00b7 Register Connector',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.register_connector'
  },
  {
    'id': 'handler.conn.verify_reconnect',
    'label': 'Connection \u00b7 Verify / Reconnect',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.verify_reconnect'
  },
  {
    'id': 'handler.conn.session_limits',
    'label': 'Connection \u00b7 Session Limits',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.session_limits'
  },
  {
    'id': 'handler.conn.disconnect',
    'label': 'Connection \u00b7 Disconnect',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.disconnect'
  },
  {
    'id': 'handler.conn.role_isolation',
    'label': 'Connection \u00b7 Role & Isolation',
    'category': 'Connection',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.conn.role_isolation'
  },
  {
    'id': 'handler.cat_act.browse_data',
    'label': 'Object Actions \u00b7 Browse Data',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.browse_data'
  },
  {
    'id': 'handler.cat_act.open_sql_editor',
    'label': 'Object Actions \u00b7 Open SQL Editor',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.open_sql_editor'
  },
  {
    'id': 'handler.cat_act.create_child_object',
    'label': 'Object Actions \u00b7 Create Child Object',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.create_child_object'
  },
  {
    'id': 'handler.cat_act.schema_compare',
    'label': 'Object Actions \u00b7 Schema Compare',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.schema_compare'
  },
  {
    'id': 'handler.cat_act.alter_edit_object',
    'label': 'Object Actions \u00b7 Alter / Edit Object',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.alter_edit_object'
  },
  {
    'id': 'handler.cat_act.discover_into_erd',
    'label': 'Object Actions \u00b7 Discover into ERD',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.discover_into_erd'
  },
  {
    'id': 'handler.cat_act.drop_object',
    'label': 'Object Actions \u00b7 Drop Object',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.drop_object'
  },
  {
    'id': 'handler.cat_act.maintenance_backup',
    'label': 'Object Actions \u00b7 Maintenance & Backup',
    'category': 'Object Actions',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cat_act.maintenance_backup'
  },
  {
    'id': 'handler.erd_mod.entity_table',
    'label': 'Entities & Levels \u00b7 + Entity / Table',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.entity_table'
  },
  {
    'id': 'handler.erd_mod.relationship',
    'label': 'Entities & Levels \u00b7 + Relationship',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.relationship'
  },
  {
    'id': 'handler.erd_mod.conceptual_box',
    'label': 'Entities & Levels \u00b7 + Conceptual Box',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.conceptual_box'
  },
  {
    'id': 'handler.erd_mod.level_all',
    'label': 'Entities & Levels \u00b7 Level: All',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.level_all'
  },
  {
    'id': 'handler.erd_mod.logical_entity',
    'label': 'Entities & Levels \u00b7 + Logical Entity',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.logical_entity'
  },
  {
    'id': 'handler.erd_mod.level_conceptual',
    'label': 'Entities & Levels \u00b7 Level: Conceptual',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.level_conceptual'
  },
  {
    'id': 'handler.erd_mod.physical_table',
    'label': 'Entities & Levels \u00b7 + Physical Table',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.physical_table'
  },
  {
    'id': 'handler.erd_mod.level_logical',
    'label': 'Entities & Levels \u00b7 Level: Logical',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.level_logical'
  },
  {
    'id': 'handler.erd_mod.deployment_node',
    'label': 'Entities & Levels \u00b7 + Deployment Node',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.deployment_node'
  },
  {
    'id': 'handler.erd_mod.level_physical',
    'label': 'Entities & Levels \u00b7 Level: Physical',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.level_physical'
  },
  {
    'id': 'handler.erd_mod.whiteboard_note',
    'label': 'Entities & Levels \u00b7 + Whiteboard Note',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.whiteboard_note'
  },
  {
    'id': 'handler.erd_mod.level_deployment',
    'label': 'Entities & Levels \u00b7 Level: Deployment',
    'category': 'Entities & Levels',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_mod.level_deployment'
  },
  {
    'id': 'handler.erd_conv.engine_conversion',
    'label': 'Convert & Drift \u00b7 Engine Conversion',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.engine_conversion'
  },
  {
    'id': 'handler.erd_conv.alter_migration_plan',
    'label': 'Convert & Drift \u00b7 Alter Migration Plan',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.alter_migration_plan'
  },
  {
    'id': 'handler.erd_conv.udt_type_maps',
    'label': 'Convert & Drift \u00b7 UDT & Type Maps',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.udt_type_maps'
  },
  {
    'id': 'handler.erd_conv.import_catalog_ddl',
    'label': 'Convert & Drift \u00b7 Import Catalog / DDL',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.import_catalog_ddl'
  },
  {
    'id': 'handler.erd_conv.naming_standards',
    'label': 'Convert & Drift \u00b7 Naming Standards',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.naming_standards'
  },
  {
    'id': 'handler.erd_conv.system_drift_overlay',
    'label': 'Convert & Drift \u00b7 System Drift Overlay',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.system_drift_overlay'
  },
  {
    'id': 'handler.erd_conv.suspect_bindings',
    'label': 'Convert & Drift \u00b7 Suspect Bindings',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.suspect_bindings'
  },
  {
    'id': 'handler.erd_conv.environment_matrix',
    'label': 'Convert & Drift \u00b7 Environment Matrix',
    'category': 'Convert & Drift',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.erd_conv.environment_matrix'
  },
  {
    'id': 'handler.cube_dim.measure',
    'label': 'Dimensions & Rules \u00b7 + Measure',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.measure'
  },
  {
    'id': 'handler.cube_dim.dimension',
    'label': 'Dimensions & Rules \u00b7 + Dimension',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.dimension'
  },
  {
    'id': 'handler.cube_dim.star_schema_view',
    'label': 'Dimensions & Rules \u00b7 Star Schema View',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.star_schema_view'
  },
  {
    'id': 'handler.cube_dim.rule_reducer',
    'label': 'Dimensions & Rules \u00b7 Rule Reducer',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.rule_reducer'
  },
  {
    'id': 'handler.cube_dim.usage_matrix_view',
    'label': 'Dimensions & Rules \u00b7 Usage Matrix View',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.usage_matrix_view'
  },
  {
    'id': 'handler.cube_dim.aggregation_plans',
    'label': 'Dimensions & Rules \u00b7 Aggregation Plans',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.aggregation_plans'
  },
  {
    'id': 'handler.cube_dim.aggregation_grid',
    'label': 'Dimensions & Rules \u00b7 Aggregation Grid',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.aggregation_grid'
  },
  {
    'id': 'handler.cube_dim.check_connection',
    'label': 'Dimensions & Rules \u00b7 Check Connection',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.check_connection'
  },
  {
    'id': 'handler.cube_dim.cube_properties',
    'label': 'Dimensions & Rules \u00b7 Cube Properties',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.cube_properties'
  },
  {
    'id': 'handler.cube_dim.ai_draft_proposal',
    'label': 'Dimensions & Rules \u00b7 AI Draft Proposal',
    'category': 'Dimensions & Rules',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cube_dim.ai_draft_proposal'
  },
  {
    'id': 'handler.bi_qry.structured_query',
    'label': 'BI Query & Charts \u00b7 Structured Query',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.structured_query'
  },
  {
    'id': 'handler.bi_qry.chart_profile',
    'label': 'BI Query & Charts \u00b7 Chart Profile',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.chart_profile'
  },
  {
    'id': 'handler.bi_qry.dashboard_card',
    'label': 'BI Query & Charts \u00b7 + Dashboard Card',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.dashboard_card'
  },
  {
    'id': 'handler.bi_qry.byok_ai_draft',
    'label': 'BI Query & Charts \u00b7 BYOK AI Draft',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.byok_ai_draft'
  },
  {
    'id': 'handler.bi_qry.filters_pinning',
    'label': 'BI Query & Charts \u00b7 Filters & Pinning',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.filters_pinning'
  },
  {
    'id': 'handler.bi_qry.import_bi_bundle',
    'label': 'BI Query & Charts \u00b7 Import BI Bundle',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.import_bi_bundle'
  },
  {
    'id': 'handler.bi_qry.cross_filter_mode',
    'label': 'BI Query & Charts \u00b7 Cross-Filter Mode',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.cross_filter_mode'
  },
  {
    'id': 'handler.bi_qry.alerts_subscriptions',
    'label': 'BI Query & Charts \u00b7 Alerts & Subscriptions',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.alerts_subscriptions'
  },
  {
    'id': 'handler.bi_qry.accessible_table',
    'label': 'BI Query & Charts \u00b7 Accessible Table',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.accessible_table'
  },
  {
    'id': 'handler.bi_qry.kiosk_embeds',
    'label': 'BI Query & Charts \u00b7 Kiosk & Embeds',
    'category': 'BI Query & Charts',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.bi_qry.kiosk_embeds'
  },
  {
    'id': 'handler.mesh_ui.screen_frame',
    'label': 'Screens & Hotspots \u00b7 + Screen Frame',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.screen_frame'
  },
  {
    'id': 'handler.mesh_ui.stencil_control',
    'label': 'Screens & Hotspots \u00b7 + Stencil Control',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.stencil_control'
  },
  {
    'id': 'handler.mesh_ui.data_grid',
    'label': 'Screens & Hotspots \u00b7 + Data Grid',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.data_grid'
  },
  {
    'id': 'handler.mesh_ui.upload_screenshot',
    'label': 'Screens & Hotspots \u00b7 Upload Screenshot',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.upload_screenshot'
  },
  {
    'id': 'handler.mesh_ui.dropdown_radio',
    'label': 'Screens & Hotspots \u00b7 + Dropdown / Radio',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.dropdown_radio'
  },
  {
    'id': 'handler.mesh_ui.draw_hotspot_region',
    'label': 'Screens & Hotspots \u00b7 Draw Hotspot Region',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.draw_hotspot_region'
  },
  {
    'id': 'handler.mesh_ui.tab_bar',
    'label': 'Screens & Hotspots \u00b7 + Tab Bar',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.tab_bar'
  },
  {
    'id': 'handler.mesh_ui.redact_regions',
    'label': 'Screens & Hotspots \u00b7 Redact Regions',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.redact_regions'
  },
  {
    'id': 'handler.mesh_ui.data_binding',
    'label': 'Screens & Hotspots \u00b7 + Data Binding',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.data_binding'
  },
  {
    'id': 'handler.mesh_ui.trace_as_mesh',
    'label': 'Screens & Hotspots \u00b7 Trace as Mesh',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.trace_as_mesh'
  },
  {
    'id': 'handler.mesh_ui.navigation_link',
    'label': 'Screens & Hotspots \u00b7 + Navigation Link',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.navigation_link'
  },
  {
    'id': 'handler.mesh_ui.import_sr_f_form',
    'label': 'Screens & Hotspots \u00b7 Import SR-F Form',
    'category': 'Screens & Hotspots',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.mesh_ui.import_sr_f_form'
  },
  {
    'id': 'handler.cmp_src.run_comparison',
    'label': 'Compare & Map \u00b7 Run Comparison',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.run_comparison'
  },
  {
    'id': 'handler.cmp_src.build_change_plan',
    'label': 'Compare & Map \u00b7 Build Change Plan',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.build_change_plan'
  },
  {
    'id': 'handler.cmp_src.left_source',
    'label': 'Compare & Map \u00b7 Left Source',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.left_source'
  },
  {
    'id': 'handler.cmp_src.map_rename',
    'label': 'Compare & Map \u00b7 Map Rename',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.map_rename'
  },
  {
    'id': 'handler.cmp_src.right_target',
    'label': 'Compare & Map \u00b7 Right Target',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.right_target'
  },
  {
    'id': 'handler.cmp_src.carry_difference',
    'label': 'Compare & Map \u00b7 Carry Difference',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.carry_difference'
  },
  {
    'id': 'handler.cmp_src.object_type_scope',
    'label': 'Compare & Map \u00b7 Object Type Scope',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.object_type_scope'
  },
  {
    'id': 'handler.cmp_src.skip_difference',
    'label': 'Compare & Map \u00b7 Skip Difference',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.skip_difference'
  },
  {
    'id': 'handler.cmp_src.ignore_options',
    'label': 'Compare & Map \u00b7 Ignore Options',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.ignore_options'
  },
  {
    'id': 'handler.cmp_src.swap_endpoints',
    'label': 'Compare & Map \u00b7 Swap Endpoints',
    'category': 'Compare & Map',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.cmp_src.swap_endpoints'
  },
  {
    'id': 'handler.ops_run.start_operation',
    'label': 'Engine Operations \u00b7 Start Operation',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.start_operation'
  },
  {
    'id': 'handler.ops_run.stop_operation',
    'label': 'Engine Operations \u00b7 Stop Operation',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.stop_operation'
  },
  {
    'id': 'handler.ops_run.backup_database',
    'label': 'Engine Operations \u00b7 Backup Database',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.backup_database'
  },
  {
    'id': 'handler.ops_run.live_engine_trace',
    'label': 'Engine Operations \u00b7 Live Engine Trace',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.live_engine_trace'
  },
  {
    'id': 'handler.ops_run.restore_database',
    'label': 'Engine Operations \u00b7 Restore Database',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.restore_database'
  },
  {
    'id': 'handler.ops_run.limbo_tx_recovery',
    'label': 'Engine Operations \u00b7 Limbo Tx Recovery',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.limbo_tx_recovery'
  },
  {
    'id': 'handler.ops_run.sweep_vacuum',
    'label': 'Engine Operations \u00b7 Sweep / Vacuum',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.sweep_vacuum'
  },
  {
    'id': 'handler.ops_run.download_job_log',
    'label': 'Engine Operations \u00b7 Download Job Log',
    'category': 'Engine Operations',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.ops_run.download_job_log'
  },
  {
    'id': 'handler.security.manage_users',
    'label': 'Security \u00b7 Manage Users',
    'category': 'Security & Access',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.security.manage_users'
  },
  {
    'id': 'handler.security.object_permissions',
    'label': 'Security \u00b7 Object Permissions Matrix',
    'category': 'Security & Access',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.security.object_permissions'
  },
  {
    'id': 'handler.security.manage_roles',
    'label': 'Security \u00b7 Manage Roles & Groups',
    'category': 'Security & Access',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.security.manage_roles'
  },
  {
    'id': 'handler.security.new_principal',
    'label': 'Security \u00b7 Create New User / Role',
    'category': 'Security & Access',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.security.new_principal'
  },
  {
    'id': 'handler.inspector.all',
    'label': 'Inspector \u00b7 Show All Sections',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.all'
  },
  {
    'id': 'handler.inspector.permissions',
    'label': 'Inspector \u00b7 Focus Object Permissions',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.permissions'
  },
  {
    'id': 'handler.inspector.overview',
    'label': 'Inspector \u00b7 Focus Overview',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.overview'
  },
  {
    'id': 'handler.inspector.structure',
    'label': 'Inspector \u00b7 Focus Structure',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.structure'
  },
  {
    'id': 'handler.inspector.ddl',
    'label': 'Inspector \u00b7 Focus DDL / SQL',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.ddl'
  },
  {
    'id': 'handler.inspector.dependencies',
    'label': 'Inspector \u00b7 Focus Dependencies',
    'category': 'Inspector Sections',
    'eventName': 'scratchrobin:tib-command',
    'actionKey': 'tib.inspector.dependencies'
  }
]);

export const STANDARD_WORKSURFACES = Object.freeze([
  {
    'num': 1,
    'id': 'catalog-inspector',
    'title': 'Catalog Object Inspector (server / database / table / view)',
    'sub_tabs': [
      {
        'id': 'dashboard',
        'label': 'Dashboard',
        'default': true,
        'sections': [
          'SEC-TELEM',
          'SEC-CAT-ACT',
          'SEC-WORKSPACE'
        ]
      },
      {
        'id': 'properties',
        'label': 'Properties',
        'default': false,
        'sections': [
          'SEC-TELEM',
          'SEC-FIND',
          'SEC-CLIP',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 2,
    'id': 'data-navigator',
    'title': 'Data Navigator (Unbound Connectors)',
    'sub_tabs': [
      {
        'id': 'connectors',
        'label': 'Connectors',
        'default': true,
        'sections': [
          'SEC-CONN',
          'SEC-FIND',
          'SEC-TELEM'
        ]
      }
    ]
  },
  {
    'num': 3,
    'id': 'data-viewer',
    'title': 'Data Viewer (Table & View Data)',
    'sub_tabs': [
      {
        'id': 'data',
        'label': 'Data',
        'default': true,
        'sections': [
          'SEC-WORKSPACE',
          'SEC-PRES',
          'SEC-REC',
          'SEC-NAV',
          'SEC-TX',
          'SEC-FIND'
        ]
      },
      {
        'id': 'view-format',
        'label': 'View & Format',
        'default': false,
        'sections': [
          'SEC-COLTEXT',
          'SEC-VALFMT',
          'SEC-PRES'
        ]
      },
      {
        'id': 'transfer-sql',
        'label': 'Transfer & SQL',
        'default': false,
        'sections': [
          'SEC-TRANSFER',
          'SEC-CLIP',
          'SEC-NATREV'
        ]
      }
    ]
  },
  {
    'num': 4,
    'id': 'sql-editor',
    'title': 'SQL Editor & Visual Builder',
    'sub_tabs': [
      {
        'id': 'query',
        'label': 'Query',
        'default': true,
        'sections': [
          'SEC-WORKSPACE',
          'SEC-EXEC',
          'SEC-TX',
          'SEC-QLIB',
          'SEC-CLIP',
          'SEC-CONN'
        ]
      },
      {
        'id': 'data',
        'label': 'Data',
        'default': false,
        'sections': [
          'SEC-PRES',
          'SEC-REC',
          'SEC-NAV',
          'SEC-TX',
          'SEC-FIND'
        ]
      },
      {
        'id': 'view-format',
        'label': 'View & Format',
        'default': false,
        'sections': [
          'SEC-COLTEXT',
          'SEC-VALFMT',
          'SEC-WORKSPACE'
        ]
      },
      {
        'id': 'transfer-files',
        'label': 'Transfer & Files',
        'default': false,
        'sections': [
          'SEC-FILE',
          'SEC-TRANSFER',
          'SEC-QLIB'
        ]
      }
    ]
  },
  {
    'num': 5,
    'id': 'object-editor',
    'title': 'Table & Object Creator / Alter Editor',
    'sub_tabs': [
      {
        'id': 'definition',
        'label': 'Definition',
        'default': true,
        'sections': [
          'SEC-WORKSPACE',
          'SEC-REC',
          'SEC-NATREV',
          'SEC-CLIP'
        ]
      },
      {
        'id': 'ddl-review',
        'label': 'DDL & Review',
        'default': false,
        'sections': [
          'SEC-NATREV',
          'SEC-VALFMT',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 6,
    'id': 'erd-designer',
    'title': 'ERD & Data Modelling Designer',
    'sub_tabs': [
      {
        'id': 'model-author',
        'label': 'Model & Author',
        'default': true,
        'sections': [
          'SEC-ERD-MOD',
          'SEC-CANVAS',
          'SEC-CLIP',
          'SEC-GOV'
        ]
      },
      {
        'id': 'canvas-levels',
        'label': 'Canvas & Levels',
        'default': false,
        'sections': [
          'SEC-CANVAS',
          'SEC-COLTEXT',
          'SEC-WORKSPACE'
        ]
      },
      {
        'id': 'compare-deploy',
        'label': 'Compare & Deploy',
        'default': false,
        'sections': [
          'SEC-ERD-CONV',
          'SEC-NATREV',
          'SEC-CONN'
        ]
      },
      {
        'id': 'governance-git',
        'label': 'Governance & Git',
        'default': false,
        'sections': [
          'SEC-GOV',
          'SEC-FIND',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 7,
    'id': 'cube-designer',
    'title': 'Cube Designer',
    'sub_tabs': [
      {
        'id': 'cube-elements',
        'label': 'Cube & Elements',
        'default': true,
        'sections': [
          'SEC-CUBE-DIM',
          'SEC-CANVAS',
          'SEC-CLIP',
          'SEC-GOV'
        ]
      },
      {
        'id': 'materialize-test',
        'label': 'Materialize & Test',
        'default': false,
        'sections': [
          'SEC-EXEC',
          'SEC-NATREV',
          'SEC-CONN'
        ]
      },
      {
        'id': 'governance-git',
        'label': 'Governance & Git',
        'default': false,
        'sections': [
          'SEC-GOV',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 8,
    'id': 'bi-designer',
    'title': 'BI Questions & Dashboards Designer',
    'sub_tabs': [
      {
        'id': 'question-query',
        'label': 'Question & Query',
        'default': true,
        'sections': [
          'SEC-BI-QRY',
          'SEC-EXEC',
          'SEC-QLIB',
          'SEC-CONN'
        ]
      },
      {
        'id': 'chart-dashboard',
        'label': 'Chart & Dashboard',
        'default': false,
        'sections': [
          'SEC-BI-QRY',
          'SEC-CANVAS',
          'SEC-COLTEXT',
          'SEC-VALFMT'
        ]
      },
      {
        'id': 'delivery-governance',
        'label': 'Delivery & Governance',
        'default': false,
        'sections': [
          'SEC-GOV',
          'SEC-NATREV',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 9,
    'id': 'screen-mesh-designer',
    'title': 'Screen Mesh Designer',
    'sub_tabs': [
      {
        'id': 'wireframe-regions',
        'label': 'Wireframe & Regions',
        'default': true,
        'sections': [
          'SEC-MESH-UI',
          'SEC-CANVAS',
          'SEC-CLIP',
          'SEC-GOV'
        ]
      },
      {
        'id': 'bindings-spec',
        'label': 'Bindings & Spec',
        'default': false,
        'sections': [
          'SEC-FIND',
          'SEC-COLTEXT',
          'SEC-TRANSFER'
        ]
      },
      {
        'id': 'governance-git',
        'label': 'Governance & Git',
        'default': false,
        'sections': [
          'SEC-GOV',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 10,
    'id': 'schema-compare',
    'title': 'Schema Comparison',
    'sub_tabs': [
      {
        'id': 'compare',
        'label': 'Compare',
        'default': true,
        'sections': [
          'SEC-CMP-SRC',
          'SEC-NAV',
          'SEC-FIND',
          'SEC-WORKSPACE'
        ]
      },
      {
        'id': 'migration-apply',
        'label': 'Migration Plan & Apply',
        'default': false,
        'sections': [
          'SEC-NATREV',
          'SEC-FILE',
          'SEC-TRANSFER'
        ]
      }
    ]
  },
  {
    'num': 11,
    'id': 'project-explorer',
    'title': 'Project Assets Explorer',
    'sub_tabs': [
      {
        'id': 'assets-git',
        'label': 'Assets & Git',
        'default': true,
        'sections': [
          'SEC-FILE',
          'SEC-GOV',
          'SEC-FIND',
          'SEC-CLIP'
        ]
      }
    ]
  },
  {
    'num': 12,
    'id': 'command-line',
    'title': 'Command Line / Native Shells (CLI \u00b7 PSQL \u00b7 Firebird ISQL)',
    'sub_tabs': [
      {
        'id': 'terminal',
        'label': 'Terminal',
        'default': true,
        'sections': [
          'SEC-CONN',
          'SEC-EXEC',
          'SEC-TX',
          'SEC-FILE',
          'SEC-CLIP'
        ]
      }
    ]
  },
  {
    'num': 13,
    'id': 'engine-operations',
    'title': 'Engine Operations & Monitoring (Backup \u00b7 Sweep/Vacuum \u00b7 Trace \u00b7 Limbo)',
    'sub_tabs': [
      {
        'id': 'operations',
        'label': 'Operations',
        'default': true,
        'sections': [
          'SEC-CONN',
          'SEC-OPS-RUN',
          'SEC-TELEM',
          'SEC-NATREV'
        ]
      }
    ]
  }
]);

const SECTION_ICON_MATCHERS = [
  [/workspace|surface|panel|view_mode|views/i, 'tib.section_panels', 'SEC-WORKSPACE'],
  [/presentation|display_mode|template/i, 'tib.section_data_presentation', 'SEC-PRES'],
  [/column|text|font|align|wrap/i, 'tib.section_columns_text', 'SEC-COLTEXT'],
  [/value|format|boolean|null/i, 'tib.section_value_formatting', 'SEC-VALFMT'],
  [/exec|run|script|query_exec/i, 'tib.section_execution', 'SEC-EXEC'],
  [/transaction|commit|rollback/i, 'tib.section_transaction', 'SEC-TX'],
  [/record|row|mutation|edit_row/i, 'tib.section_records', 'SEC-REC'],
  [/nav|cursor|bookmark|page/i, 'tib.section_navigation', 'SEC-NAV'],
  [/find|filter|sort|search|suspect/i, 'tib.section_find_filter', 'SEC-FIND'],
  [/clip|copy|paste|cut/i, 'tib.section_clipboard', 'SEC-CLIP'],
  [/file|asset|project/i, 'tib.section_files', 'SEC-FILE'],
  [/library|snippet|saved|authoring/i, 'tib.section_query_library', 'SEC-QLIB'],
  [/transfer|import|export|handoff/i, 'tib.section_import_export', 'SEC-TRANSFER'],
  [/dashboard|historic|metric|refresh|telem|statistic/i, 'tib.metrics_plan', 'SEC-TELEM'],
  [/canvas|zoom|layout|pin|stencil/i, 'tib.section_canvas', 'SEC-CANVAS'],
  [/checkpoint|status|git|provenance|lifecycle|governance/i, 'tib.section_files', 'SEC-GOV'],
  [/ddl|review|migration|outward|alter/i, 'tib.section_sql_generation', 'SEC-NATREV'],
  [/conn|target|session|terminal|registration/i, 'tib.section_connection', 'SEC-CONN'],
  [/compare|endpoint|diff/i, 'tib.cat_schema_compare', 'SEC-CMP-SRC'],
  [/cube|dimension|measure|agg/i, 'tib.cube_add_dimension', 'SEC-CUBE-DIM'],
  [/chart|question|bi|kiosk/i, 'tib.section_reports_bi', 'SEC-BI-QRY'],
  [/mesh|screen|wireframe|region|redact/i, 'tib.mesh_add_screen', 'SEC-MESH-UI'],
  [/entity|whiteboard|level|convert|drift/i, 'tib.erd_level_all', 'SEC-ERD-MOD'],
  [/security|principal|permission|grant/i, 'tib.section_security', 'SEC-SECURITY'],
  [/inspector_sections|properties_sections/i, 'tib.inspect_all', 'SEC-INSPECTOR'],
  [/operation|backup|maintenance|trace/i, 'tib.cat_maintenance', 'SEC-OPS-RUN'],
  [/catalog|object|action/i, 'tib.section_sql_generation', 'SEC-CAT-ACT'],
];

export function inferSectionMeta(group = {}) {
  if (group.sectionId && STANDARD_TIB_SECTIONS_BY_ID[group.sectionId]) {
    const std = STANDARD_TIB_SECTIONS_BY_ID[group.sectionId];
    return {
      sectionId: std.id,
      sectionIcon: group.sectionIcon || std.sectionIcon,
      defaultTitle: group.label || std.title,
    };
  }
  const probe = `${group.rawGroupId || group.id || ''} ${group.label || ''}`;
  for (const [rx, icon, secId] of SECTION_ICON_MATCHERS) {
    if (rx.test(probe)) {
      return {
        sectionId: group.sectionId || secId,
        sectionIcon: group.sectionIcon || icon,
        defaultTitle: group.label,
      };
    }
  }
  return {
    sectionId: group.sectionId || '',
    sectionIcon: group.sectionIcon || 'tib.section_panels',
    defaultTitle: group.label || 'Actions',
  };
}

/**
 * Formats any group's controls into the canonical TiB Section Card cluster structure:
 *   - Primary 1–2 standalone controls become 42x42 icon-only Hero buttons (`size: "large", showLabel: false`)
 *   - Remaining standalone buttons pack cleanly into a 2-row compact grid (`type: "stack"`)
 *   - Internal cluster dividers (`type: "separator"`) separate Hero and Grid clusters
 *   - Preserves existing explicit `stack`, `segmented`, `menu`, `split`, `select`, `color` controls intact!
 */
export function normalizeGroupControlsForTiB(rawControls = [], sectionId = '', sectionOverrides = {}) {
  const secCfg = (sectionId && sectionOverrides?.[sectionId]) || null;
  if (secCfg?.hidden === true) {
    return null;
  }
  const hiddenSet = new Set(Array.isArray(secCfg?.hidden_actions) ? secCfg.hidden_actions : []);
  const filtered = (rawControls || []).filter((ctrl) => {
    if (!ctrl) return false;
    const cid = typeof ctrl === 'string' ? ctrl : ctrl.actionId || ctrl.command || ctrl.id;
    return !cid || !hiddenSet.has(cid);
  });
  const addedHero = Array.isArray(secCfg?.added_hero_actions) ? secCfg.added_hero_actions : [];
  const addedGrid = Array.isArray(secCfg?.added_grid_actions) ? secCfg.added_grid_actions : [];

  const hasExplicitStructure = filtered.some(
    (c) =>
      typeof c === 'object' &&
      c !== null &&
      (c.type === 'stack' || c.type === 'segmented' || c.size === 'large')
  );

  if (hasExplicitStructure) {
    const normalized = filtered.map((c) => {
      if (typeof c === 'object' && c !== null && c.size === 'large' && c.keepLabel !== true) {
        return {...c, showLabel: false};
      }
      return c;
    });
    addedHero.forEach((aid) =>
      normalized.unshift({id: aid, actionId: aid, size: 'large', showLabel: false})
    );
    if (addedGrid.length > 0) {
      normalized.push({
        id: `added_grid_${sectionId || 'sec'}`,
        type: 'stack',
        controls: addedGrid,
      });
    }
    return normalized;
  }

  const allFlat = [
    ...addedHero.map((aid) => ({id: aid, actionId: aid, __forceHero: true})),
    ...filtered,
    ...addedGrid,
  ];
  if (allFlat.length === 0) return [];
  if (allFlat.length <= 2) {
    return allFlat.map((item, idx) => {
      if (typeof item === 'string') {
        return {id: item, actionId: item, size: 'large', showLabel: false};
      }
      return {...item, id: item.id || item.actionId || `hero_${idx}`, size: 'large', showLabel: false};
    });
  }

  const heroCount = allFlat.length >= 4 ? 2 : 1;
  const heroes = allFlat.slice(0, heroCount).map((item, idx) => {
    if (typeof item === 'string') {
      return {id: item, actionId: item, size: 'large', showLabel: false};
    }
    return {...item, id: item.id || item.actionId || `hero_${idx}`, size: 'large', showLabel: false};
  });
  const rest = allFlat.slice(heroCount).map((item) => {
    if (typeof item === 'object' && item !== null && item.__forceHero) {
      const copy = {...item};
      delete copy.__forceHero;
      return copy;
    }
    return item;
  });

  return [
    ...heroes,
    {type: 'separator'},
    {
      id: `grid_${sectionId || 'auto'}_${heroes[0]?.id || '0'}`
        .replace(/[^A-Za-z0-9_.:-]/g, '_')
        .slice(0, 108),
      type: 'stack',
      controls: rest,
    },
  ];
}
