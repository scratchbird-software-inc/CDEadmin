import gettext from 'sources/gettext';
import {DISPLAY_MODES} from './dataEditSurfaceHelpers';

export function presentationChoices() {
  return [
    ['default', gettext('Use surface presentation')],
    [DISPLAY_MODES.GRID, gettext('Standard Grid')],
    [DISPLAY_MODES.MINI_FORMS, gettext('Mini-Forms')],
    [DISPLAY_MODES.SINGLE_FORM, gettext('Single Form')],
    [DISPLAY_MODES.HYBRID, gettext('Hybrid')],
    [DISPLAY_MODES.HYBRID_EDIT, gettext('Hybrid When Editing')],
  ];
}

const displayAreaIcons = {
  first_area: 'view.toolbar',
  second_area: 'view.status',
  first_presentation: 'action.layout_grid',
  second_presentation: 'action.layout_mini_forms',
};

export function displayAreaControl(register, prefix, name, label, choices, value, select, index) {
  const actionId = register(name, displayAreaIcons[name], label, (detail) => {
    const selected = detail?.item?.id ?? detail?.item ?? detail?.value;
    if (choices.some(([id]) => id === selected)) select(selected);
  });
  const items = choices.map(([id, title]) => ({id, label: title, checked: id === value}));
  return {
    control: {id: actionId, actionId, type: 'menu', items},
    menu: {
      id: `${prefix}.view.${name}`, label, index,
      items: items.map(({id, ...item}, position) => ({
        ...item, id: `${prefix}.view.${name}.${id}`, index: position + 1,
        callback: () => select(id),
      })),
    },
  };
}
