#!/usr/bin/env python3
"""Actual native configuration discovery and read-only object inspection."""
import argparse
import hashlib
import json
from pathlib import Path

from tools.cdeadmin_firebird_stream_browser_gate import qualify, run_local


def exercise(options, driver, wait, click, native, route, password, evidence):
    context = options.exercise_context
    result = driver.execute_async_script('''
      const endpointId=arguments[0], target=arguments[1];
      const done=arguments[arguments.length-1];
      const app=window.pgAdmin, tree=app.Browser.tree;
      const node=app.Browser.Nodes.server;
      let endpoint;
      for (const row of document.querySelectorAll('.file-entry')) {
        const item=tree.itemFrom(row), data=item && tree.itemData(item);
        if (data?._type==='server' && String(data._id)===String(endpointId)) {
          endpoint=item; break;
        }
      }
      if (!endpoint) {done({error:'Owned endpoint not found'});return;}
      window.__configurationEndpointItem=endpoint;
      const base=node.generate_url(endpoint,'cde_workspace',
        tree.itemData(endpoint),true);
      const url=base+(base.includes('?')?'&':'?')+
        'database_target_id='+encodeURIComponent(target);
      const headers={'Content-Type':'application/json'};
      headers[app.csrf_token_header]=app.csrf_token;
      (async()=>{
        const response=await fetch(url,{credentials:'same-origin',headers});
        if (!response.ok) throw new Error('Workspace refused');
        const initial=(await response.json()).data;
        const resources=[...(initial.resource_page?.items||[])];
        let cursor=initial.resource_page?.next_cursor;
        const generation=initial.resource_page?.generation;
        while(cursor) {
          const response=await fetch(url,{method:'POST',
            credentials:'same-origin',headers,body:JSON.stringify({
              action:'resource_page',request:{continuation:cursor,generation,
                database_target_id:target}})});
          if (!response.ok) throw new Error('Resource continuation refused');
          const page=(await response.json()).data;
          resources.push(...(page.items||[]));cursor=page.next_cursor;
        }
        done({settings:resources.filter(x=>x.resource_kind==='configuration'),
          plugins:resources.filter(x=>x.resource_kind==='plugin').length,
          descriptor:initial.visual_admin.objects.find(
            x=>x.resource_kind==='configuration')});
      })().catch(()=>done({error:'Configuration discovery failed'}));
    ''', context['endpoint_id'], context['database_target_id'])
    assert 'error' not in result
    assert len(result['settings']) == 77
    assert result['plugins'] == 0
    assert [item['operation_id'] for item in
            result['descriptor']['operations']] == ['inspect']
    selected = next(item for item in result['settings']
                    if item['display_name'] == 'AuthServer')
    driver.execute_script('''
      const node=window.pgAdmin.Browser.Nodes.server;
      node.callbacks.open_cde_workspace.call(node,
        {item:window.__configurationEndpointItem},'object',{
          resource_id:arguments[0],database_target_id:arguments[1],
          resource_kind:'configuration',operation_id:'inspect',
          task_title:'Effective Firebird configuration'});
    ''', selected['resource_id'], context['database_target_id'])
    wait.until(lambda d: d.find_elements(
        'css selector', '[aria-label="Object properties sections"]'))
    click('Refresh object properties')
    wait.until(lambda d: next((button for button in d.find_elements(
        'tag name', 'button') if button.text == 'Refresh object properties' and
        button.is_displayed() and button.is_enabled()), None))
    wait.until(lambda d: 'RDB$CONFIG database configuration snapshot' in
               d.find_element('tag name', 'body').text)
    tabs = driver.find_elements(
        'css selector', '[aria-label="Selected object operations"] '
        '[role="tab"]')
    assert len(tabs) == 1 and tabs[0].is_displayed()
    driver.save_screenshot(str(evidence / 'configuration-inspector.png'))
    (evidence / 'checks.json').write_text(json.dumps({
        'count': len(result['settings']), 'plugin_objects': 0,
        'native_inspector_refreshed': True, 'mutation_controls_absent': True,
        'browser': driver.capabilities['browserVersion']}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-config', 'runtime', 'assets', 'driver', 'evidence'):
        parser.add_argument('--'+name, type=Path, required=True)
    options = parser.parse_args()
    options.workspace_tab = 'resources'
    before = hashlib.sha256(options.source_config.read_bytes()).hexdigest()
    result = run_local(options.runtime, options.evidence,
                       lambda *args: qualify(options, *args, exercise=(
                           lambda *values: exercise(options, *values))))
    result['source_configuration_unchanged'] = before == hashlib.sha256(
        options.source_config.read_bytes()).hexdigest()
    result['complete'] &= result['source_configuration_unchanged']
    (options.evidence / 'summary.json').write_text(
        json.dumps(result, indent=2)+'\n')
    raise SystemExit(0 if result['complete'] else 1)
