"""Read-only inspector checks on the owned seeded Firebird fixture."""

import json
from types import SimpleNamespace

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tools.cdeadmin_firebird_admin_mapping_gate import (
    _create_client, _resources, _route_arguments,
)
from tools.cdeadmin_firebird_seeded_transaction_gate import _load_profile
from tools.cdeadmin_ui_evidence import expand, named_tree_item


CASES = (
    ('Tables', 'table', 'CUSTOMERS'),
    ('Tables', 'table', 'ASSETS'),
    ('Views', 'view', 'OPEN_WORK_ORDERS'),
    ('Sequences', 'sequence', 'INSPECTION_NUMBER'),
)


def native_expectations(profiles):
    import firebird.driver as driver
    route = _load_profile(profiles)
    password = route.pop('password')
    _create_client(SimpleNamespace(acquire_secret=None))
    connection = driver.connect(password=password,
                                **_route_arguments(route, driver))
    try:
        resources = _resources(connection, {'route': route})
        result = {}
        for _group, kind, name in CASES:
            resource = next(item for item in resources if
                            item['resource_kind'] == kind and
                            item['display_name'] == name)
            ddl = resource['native'].get('ddl')
            if not isinstance(ddl, str) or not ddl.strip():
                raise RuntimeError(f'Native DDL is absent for {name}')
            columns = []
            if kind in ('table', 'view'):
                cursor = connection.cursor()
                cursor.execute(
                    'SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS '
                    'WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION',
                    (name,))
                columns = [row[0] for row in cursor.fetchall()]
                cursor.close()
                if not columns:
                    raise RuntimeError(f'Native columns are absent for {name}')
            result[name] = {'ddl': ddl, 'columns': columns}
        return result
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def verify(driver, wait, options, capture):
    expected = native_expectations(options.profiles)
    print('Inspector database state:', driver.execute_async_script("""
      const done = arguments[arguments.length - 1];
      const tree = window.pgAdmin.Browser.tree;
      const item = tree.selected();
      const data = tree.itemData(item);
      const app = window.pgAdmin;
      const headers = {[app.csrf_token_header]: app.csrf_token};
      fetch(data.children_url, {headers}).then(r => r.json())
      .then(body => done({
        type: data._type, childCount: item.children?.length,
        groups: body.data?.map(value => value.label), error: body.errormsg
      })).catch(e => done({error: String(e)}));
    """), flush=True)
    collapsed = driver.find_elements(
        By.CSS_SELECTOR,
        f'button[aria-label="Collapse {options.database}"]')
    if collapsed:
        collapsed[-1].click()
    expand(wait, options.database)
    capture('object-database-expanded')
    results = []

    def inspector():
        return driver.find_element(
            By.CSS_SELECTOR, 'aside[aria-label="Inspector"]')

    def section(label, section_id):
        control = wait.until(lambda _browser: next(iter(
            inspector().find_elements(By.CSS_SELECTOR, '[role="combobox"]')
        ), None))
        control.click()
        try:
            item = wait.until(lambda browser: next((
                option for option in browser.find_elements(
                    By.CSS_SELECTOR, '[role="option"]')
                if option.is_displayed() and
                ' '.join(option.text.split()) == label), None))
        except Exception:
            capture('object-section-selection-failed')
            print('Inspector section choices:', [
                option.text for option in driver.find_elements(
                    By.CSS_SELECTOR, '[role="option"]')
                if option.is_displayed()], flush=True)
            raise
        item.click()
        return wait.until(lambda _browser: next(iter(
            inspector().find_elements(
                By.CSS_SELECTOR,
                f'[aria-label="{section_id} object section"]')
        ), None))

    for group, kind, name in CASES:
        reveal_tree_item(driver, wait, group)
        expand(wait, group)
        reveal_tree_item(driver, wait, name).click()
        wait.until(lambda _browser: name in inspector().text and
                   not inspector().find_elements(
                       By.CSS_SELECTOR,
                       '[aria-label="Loading object properties"]'))
        panel = section('Creation statement (DDL)', 'ddl')
        wait.until(lambda _browser:
                   panel.get_attribute('textContent') == expected[name]['ddl'])
        capture(f'object-{name}-ddl')
        try:
            keyboard = {'passed': True, **ddl_keyboard_evidence(
                driver, wait, panel)}
        except Exception as error:
            keyboard = {'passed': False, 'error': str(error)}
        capture(f'object-{name}-ddl-keyboard-bottom')
        if expected[name]['columns']:
            panel = section('Columns', 'columns')
            wait.until(lambda _browser: all(
                column in panel.text for column in expected[name]['columns']))
            capture(f'object-{name}-columns')
        results.append({'name': name, 'kind': kind,
                        'exact_provider_ddl_rendered': True,
                        'ddl_keyboard': keyboard,
                        'native_column_names': expected[name]['columns']})
    (options.output_root / 'populated-inspector.json').write_text(
        json.dumps(results, indent=2) + '\n', encoding='utf-8')
    if any(not item['ddl_keyboard']['passed'] for item in results):
        raise RuntimeError('Populated inspector keyboard checks failed; '
                           'see populated-inspector.json')
    return results


def assert_text_visible(observation):
    """Require the final glyph inside every clipping ancestor, not just DOM."""
    glyph, clip = observation['glyph'], observation['clip']
    if (glyph['width'] <= 0 or glyph['height'] <= 0 or
            glyph['left'] < clip['left'] - 1 or
            glyph['right'] > clip['right'] + 1 or
            glyph['top'] < clip['top'] - 1 or
            glyph['bottom'] > clip['bottom'] + 1):
        raise RuntimeError(
            'DDL final character is clipped after keyboard End: '
            + str(observation))


def ddl_keyboard_evidence(driver, wait, panel):
    selector = driver.find_element(
        By.CSS_SELECTOR, 'aside[aria-label="Inspector"] [role="combobox"]')
    selector_layout = driver.execute_script("""
      const node = arguments[0], css = getComputedStyle(node);
      return {white_space: css.whiteSpace, text_overflow: css.textOverflow,
        content_width: node.scrollWidth, viewport_width: node.clientWidth};
    """, selector)
    if (selector_layout['white_space'] != 'normal' or
            selector_layout['text_overflow'] != 'clip' or
            selector_layout['content_width'] >
            selector_layout['viewport_width'] + 1):
        raise RuntimeError('Inspector selector truncates its label: '
                           + str(selector_layout))
    selector.send_keys(Keys.TAB)
    wait.until(lambda browser: browser.switch_to.active_element == panel)
    wait.until(lambda browser: not browser.find_elements(
        By.CSS_SELECTOR, '[data-testid="object-breadcrumbs"]'))
    panel.send_keys(Keys.END)
    wait.until(lambda browser: browser.execute_script(
        'return arguments[0].scrollTop >= arguments[0].scrollHeight - '
        'arguments[0].clientHeight - 1', panel))
    geometry_script = r"""
      const panel = arguments[0];
      const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
      let last, node;
      while ((node = walker.nextNode())) if (/\S/.test(node.textContent))
        last = node;
      if (!last) throw new Error('DDL text is absent');
      const end = last.textContent.trimEnd().length;
      const range = document.createRange();
      range.setStart(last, end - 1); range.setEnd(last, end);
      const glyph = range.getBoundingClientRect().toJSON();
      const clip = {left: 0, top: 0, right: innerWidth, bottom: innerHeight};
      for (let item = panel; item; item = item.parentElement) {
        const css = getComputedStyle(item);
        const rect = item.getBoundingClientRect();
        if (/auto|scroll|hidden|clip/.test(css.overflowY)) {
          clip.top = Math.max(clip.top, rect.top + item.clientTop);
          clip.bottom = Math.min(clip.bottom,
            rect.top + item.clientTop + item.clientHeight);
        }
        if (/auto|scroll|hidden|clip/.test(css.overflowX)) {
          clip.left = Math.max(clip.left, rect.left + item.clientLeft);
          clip.right = Math.min(clip.right,
            rect.left + item.clientLeft + item.clientWidth);
        }
      }
      return {glyph, clip, scroll_top: panel.scrollTop,
        content_height: panel.scrollHeight,
        viewport_height: panel.clientHeight};
    """
    observed = {}

    def visible(browser):
        nonlocal observed
        observed = browser.execute_script(geometry_script, panel)
        try:
            assert_text_visible(observed)
            return True
        except RuntimeError:
            return False

    try:
        wait.until(visible)
    except Exception:
        if observed:
            assert_text_visible(observed)
        raise
    observed['selector'] = selector_layout
    return observed


def reveal_tree_item(driver, wait, label):
    """Scroll the virtual navigator so offscreen rows can be mounted."""
    scroll_script = """
      const root = document.querySelector('[role="tree"]');
      const scroll = root && [root, ...root.querySelectorAll('*')].find(
        node => node.scrollHeight > node.clientHeight &&
          /auto|scroll/.test(getComputedStyle(node).overflowY));
      if (scroll) scroll.scrollTop = arguments[0] === 'reset' ? 0 :
        scroll.scrollTop + Math.max(40, scroll.clientHeight * .65);
    """
    driver.execute_script(scroll_script, 'reset')

    def find(browser):
        item = named_tree_item(browser, label)
        if item:
            browser.execute_script(
                'arguments[0].scrollIntoView({block:"nearest",'
                'inline:"nearest"})', item)
            return item
        browser.execute_script(scroll_script, 'next')
        return None

    return wait.until(find)
