// Application command metadata must not overwrite Electron's internal IDs.
export function nativeMenuTemplate(items) {
  const fields = ['label', 'id', 'type', 'enabled', 'visible', 'checked',
    'accelerator', 'role', 'click'];
  return items.map(item => {
    const result = Object.fromEntries(fields.filter(field =>
      item[field] !== undefined).map(field => [field, item[field]]));
    if (item.submenu) result.submenu = nativeMenuTemplate(item.submenu);
    return result;
  });
}
