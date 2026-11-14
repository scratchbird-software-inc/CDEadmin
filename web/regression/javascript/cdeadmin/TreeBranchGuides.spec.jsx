/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {render} from '@testing-library/react';
import {
  TreeBranchGuides,
  isLastTreeSibling,
  treeBranchSegments,
} from 'sources/components/PgTree/FileTreeItem/TreeBranchGuides';

function node(id, depth, parent=null) {
  return {id, depth, parent, children: []};
}

describe('CDEadmin branching tree guides', () => {
  it('draws tees, end elbows, and continuing ancestor lines', () => {
    const hiddenRoot = node('hidden', 0);
    const connectors = node('connectors', 1, hiddenRoot);
    const projects = node('projects', 1, hiddenRoot);
    hiddenRoot.children = [connectors, projects];
    const firebird = node('firebird', 2, connectors);
    const mysql = node('mysql', 2, connectors);
    connectors.children = [firebird, mysql];
    const local = node('local', 3, firebird);
    firebird.children = [local];

    expect(isLastTreeSibling(firebird)).toBe(false);
    expect(isLastTreeSibling(mysql)).toBe(true);
    expect(treeBranchSegments(firebird)).toEqual([
      {kind: 'current', continues: true, isLast: false},
    ]);
    expect(treeBranchSegments(local)).toEqual([
      {kind: 'ancestor', continues: true, isLast: false},
      {kind: 'current', continues: false, isLast: true},
    ]);
  });

  it('renders one non-textual segment per visible branch depth', () => {
    const root = node('root', 0);
    const parent = node('parent', 1, root);
    root.children = [parent];
    const child = node('child', 2, parent);
    parent.children = [child];

    const {container} = render(<TreeBranchGuides item={child} />);
    expect(container.querySelector('.tree-branch'))
      .toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelectorAll('.tree-branch-segment')).toHaveLength(1);
    expect(container.querySelector('.tree-branch-segment.current.is-last'))
      .toBeInTheDocument();
  });

  it('uses thicker curved paths connected to circular toggles with no old thin pseudo-element lines or selection brackets', () => {
    const reactaspenOverride = require('sources/Theme/overrides/reactaspen.override').default;
    const themeStub = {
      typography: {fontFamily: 'sans-serif'},
      shape: {borderRadius: 4},
      palette: {
        primary: {light: '#dbeafe', main: '#2563eb', contrastText: '#fff'},
        default: {main: '#f8fafc'},
        grey: {600: '#475569'},
        text: {primary: '#0f172a', muted: '#64748b'},
      },
      otherVars: {
        borderColor: '#cbd5e1',
        treeConnFg: '#334155',
        activeBorder: '#2563eb',
        activeColor: '#0f172a',
        emptySpaceBg: '#ffffff',
        tree: {
          textFg: '#0f172a',
          inputBg: '#ffffff',
          iconFg: '#334155',
          bgHover: '#f1f5f9',
          fgHover: '#0f172a',
          bgSelected: '#dbeafe',
          fgSelected: '#0f172a',
          borderSelected: '#2563eb',
        },
      },
    };
    const fileEntryStyles = reactaspenOverride(themeStub)['.file-entry'];

    // Old thin straight 1px pseudo-element lines are gone
    expect(fileEntryStyles['span.tree-branch-segment']['&:before']).toBeUndefined();
    expect(fileEntryStyles['button.directory-toggle']['&.open:after']).toEqual({display: 'none'});
    expect(fileEntryStyles['span.tree-node-terminal.leaf']['&:before']).toBeUndefined();

    // Circular [+] / [-] toggle and bracket-free row selection
    expect(fileEntryStyles['button.directory-toggle'].borderRadius).toBe('50%');
    expect(fileEntryStyles['&.active, &.prompt'].borderRight).toBeUndefined();
    expect(fileEntryStyles['&.active, &.prompt'].boxShadow).toBe('none !important');

    // Thicker curved SVG stroke widths (2.2 base guide, 2.5 active branch)
    const hiddenRoot = node('hidden', 0);
    const connectors = node('connectors', 1, hiddenRoot);
    hiddenRoot.children = [connectors];
    const firebird = node('firebird', 2, connectors);
    const mysql = node('mysql', 2, connectors);
    connectors.children = [firebird, mysql];
    const local = node('local', 3, firebird);
    const remote = node('remote', 3, firebird);
    firebird.children = [local, remote];

    const {container} = render(<TreeBranchGuides item={local} activeItem={local} hasToggle />);
    const paths = Array.from(container.querySelectorAll('svg path'));
    expect(paths.some((p) => p.getAttribute('stroke-width') === '2.2')).toBe(true);
    expect(paths.some((p) => p.getAttribute('stroke-width') === '2.5')).toBe(true);
  });
});
