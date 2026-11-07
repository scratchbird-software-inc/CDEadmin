/////////////////////////////////////////////////////////////
//
// ScratchRobin - retired tool panels in saved layouts
//
//////////////////////////////////////////////////////////////

import { loadLayoutData } from 'rc-dock/lib/Serializer';
import { BROWSER_PANELS, TOOLS_SUPPORTING_RESTORE, isRetiredToolPanel }
  from '../../../pgadmin/browser/static/js/constants';

// Owner direction 2026-11-07: pgAdmin's ERD tool is retired. A saved layout
// that still holds one of its tabs must restore without it.
describe('retired tool panels', () => {
  it('recognises the retired ERD tool panel and nothing else', () => {
    expect(isRetiredToolPanel('id-erd-tool_4')).toBe(true);
    expect(isRetiredToolPanel('id-erd-tool')).toBe(true);
    for (const id of ['id-query-tool_1', 'id-schema-diff-tool_2',
      'id-psql-tool_3', 'id-erd', undefined, null]) {
      expect(isRetiredToolPanel(id)).toBe(false);
    }
    expect(Object.values(BROWSER_PANELS)).not.toContain('id-erd-tool');
    expect(TOOLS_SUPPORTING_RESTORE).not.toContain('id-erd-tool');
  });

  it('drops a retired tab from a restored layout and keeps the rest', () => {
    const saved = {
      dockbox: {mode: 'horizontal', children: [{
        tabs: [{id: 'id-query-tool_1'}, {id: 'id-erd-tool_9'}],
        activeId: 'id-erd-tool_9',
      }]},
    };
    const loadTab = (tab) => (isRetiredToolPanel(tab.id) ? null :
      {id: tab.id, title: tab.id, content: null});
    const layout = loadLayoutData(saved, {dockbox: {mode: 'horizontal', children: []}},
      loadTab);
    const ids = layout.dockbox.children[0].tabs.map((tab) => tab.id);
    expect(ids).toEqual(['id-query-tool_1']);
  });
});
