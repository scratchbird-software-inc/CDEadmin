/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import fs from 'fs';
import path from 'path';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {Icon} from '../../../pgadmin/static/js/cdeadmin_ui/icons/Icon';
import {ProjectHelpReferenceDialog} from '../../../pgadmin/static/js/cdeadmin_ui/shell/ProjectShellDialogs';

const REPO_ROOT = path.resolve(__dirname, '../../../..');
const BRAND_SOURCE_DIR = path.join(REPO_ROOT, 'website', 'assets', 'brand');
const CATALOG_BRAND_DIR = path.join(
  REPO_ROOT,
  'web',
  'pgadmin',
  'static',
  'assets',
  'cdeadmin',
  'branding'
);

describe('Official ScratchBird CDE Family Brand Logos & About Box', () => {
  afterEach(() => {
    cleanup();
    document.documentElement.removeAttribute('data-cde-theme');
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-sr-scheme');
  });

  it('keeps all 10 light and dark family brand SVGs byte-identical to website/assets/brand', () => {
    const expectedFiles = [
      'scratchrobin.svg',
      'scratchrobin-dark.svg',
      'scratchbird.svg',
      'scratchbird-dark.svg',
      'scratchweaver.svg',
      'scratchweaver-dark.svg',
      'ddn.svg',
      'ddn-dark.svg',
      'opensource.svg',
      'opensource-dark.svg',
    ];
    for (const fileName of expectedFiles) {
      const canonical = fs.readFileSync(path.join(BRAND_SOURCE_DIR, fileName), 'utf8');
      const vendored = fs.readFileSync(path.join(CATALOG_BRAND_DIR, fileName), 'utf8');
      expect(vendored).toBe(canonical);
    }
  });

  it('switches ScratchRobin and family icons between light and dark variants when theme changes', async () => {
    document.documentElement.setAttribute('data-cde-theme', 'light');
    const {container} = render(
      <div>
        <Icon iconKey="tool.scratchrobin" label="ScratchRobin Tool" />
        <Icon iconKey="brand.scratchbird" label="ScratchBird" />
        <Icon iconKey="brand.scratchweaver" label="ScratchWeaver" />
        <Icon iconKey="brand.ddn" label="DDN" />
        <Icon iconKey="brand.opensource" label="Open Source" />
      </div>
    );

    for (const el of container.querySelectorAll('[data-icon-variant]')) {
      expect(el.getAttribute('data-icon-variant')).toBe('light');
    }

    await act(async () => {
      document.documentElement.setAttribute('data-cde-theme', 'dark');
      window.dispatchEvent(new CustomEvent('scratchrobin:scheme-changed'));
    });

    for (const el of container.querySelectorAll('[data-icon-variant]')) {
      expect(el.getAttribute('data-icon-variant')).toBe('dark');
    }
  });

  it('displays Release, Build Date / Time, Commit, and family logos in ProjectShell Help -> About', async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          product_name: 'ScratchRobin',
          release: '0.325-alpha',
          version: '0.325-alpha',
          build_datetime: '2026-11-23 22:55:00 EST (2026-11-24T03:55:00Z)',
          build_timestamp_utc: '2026-11-24T03:55:00Z',
          commit_hash: '620cfa78a92cf5a0d02135eefcc337ea70c4590e',
          app_mode: 'Desktop',
          electron: '43.7.11',
          python_version: '3.14.6',
          fork_summary: 'Multi-engine administration console.',
          attribution: 'Released under the PostgreSQL Licence.',
        },
      }),
    });

    render(
      <ProjectHelpReferenceDialog
        open
        topic="about"
        onClose={() => {}}
        fetchImpl={mockFetch}
      />
    );

    await waitFor(() => expect(mockFetch).toHaveBeenCalledWith('/about/', expect.any(Object)));
    await screen.findByText('2026-11-23 22:55:00 EST (2026-11-24T03:55:00Z)');
    expect(screen.getAllByText(/0\.325-alpha/).length).toBeGreaterThan(0);
    expect(screen.getByText('620cfa78a92cf5a0d02135eefcc337ea70c4590e')).toBeTruthy();
    expect(document.querySelector('[data-cdeadmin-qa-key="project-about-family-logos"]')).toBeTruthy();
  });
});
