// Data-only DDN publications; identifiers are adapter-owned, values are quoted.
const quoted = (value) => JSON.stringify(String(value ?? 'Unavailable'));

export function dashboardPanelFiles(panels, title, moduleName) {
  const recordId = (panel, row, index) => {
    const id = row.bindingId ?? `${panel.id}_${index}`;
    if(!/^[a-z][a-z0-9_]{0,2047}$/.test(id)) throw new Error('Invalid dashboard binding identity.');
    return id;
  };
  const records = panels.flatMap((panel) => panel.rows.map((row, index) =>
    `record ${recordId(panel, row, index)} ${quoted(row[0])} { x_record: { ` +
    `value: ${quoted(row[1])}, unit: ${quoted(row[2] ?? '')}, ` +
    `rate: ${quoted(row[3] ?? '')} }; }`)).join('\n');
  const views = panels.map((panel) => `view ${panel.id} ${quoted(panel.title)} {
    data: [@observations];
    select: [${panel.rows.map((row, index) => `@observations.${recordId(panel, row, index)}`).join(', ')}];
    projection { kind: table; profile: "table.records@1";
      records: [${panel.rows.map((row, index) => `@observations.${recordId(panel, row, index)}`).join(', ')}];
      columns: [{key: "name", label: "Measure"}, {key: "x_record.value", label: "Value"},
        {key: "x_record.unit", label: "Unit / meaning"}, {key: "x_record.rate", label: "Per second"}];
    }
    publication { size: content; fit: none; }
  }`).join('\n');
  // DDN admits at most twelve embedded views per composition. Keep every
  // observation and expose additional compositions instead of dropping metrics.
  const pages = [];
  for(let offset = 0; offset < panels.length; offset += 12) {
    const page = panels.slice(offset, offset + 12);
    const number = pages.length + 1;
    pages.push(`view ${number === 1 ? 'dashboard' : `dashboard_page_${number}`} ${quoted(number === 1 ? title : `${title} — page ${number}`)} {
      data: [@observations];
      select: [];
      projection { kind: panels; profile: "panels.composed@1"; columns: 2;
        panels: [${page.map((panel, index) => `{id: ${quoted(panel.id)}, title: ${quoted(panel.title)}, row: ${Math.floor(index / 2)}, column: ${index % 2}, view: @${panel.id}}`).join(', ')}];
      }
      publication { size: content; fit: none; }
    }`);
  }
  return {'dashboard.ddn': `ddn "0.5"; module ${quoted(moduleName)};
    data observations { ${records} }
    ${views}
    ${pages.join('\n')}`};
}
