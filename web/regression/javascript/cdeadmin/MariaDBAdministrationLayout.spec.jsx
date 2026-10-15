import {act, render, screen} from '@testing-library/react';
import Theme from 'sources/Theme';
import {VisualAdministration} from 'sources/Dialogs/ProviderWorkspaceContent';

it('uses compact MariaDB native controls with its stable form reference', async () => {
  const resource={resource_kind:'package',resource_id:'package:owned',display_name:'owned',display_path:['demo','owned']};
  const catalog={engine_id:'mariadb',objects:[{resource_kind:'package',title:'Package',operations:[{
    operation_id:'replace_body',form_id:'mariadb.package.replace_body',title:'Replace package body',target_required:true,confirmation_required:true,
    form:{form_key:'mariadb-native-package-operation',fields:[
      {field_id:'definition',label:'Declaration or body fragment',control:'code',required:true},
      {field_id:'confirmation',label:'Confirmation',control:'text',required:true},
    ]},
  }]}]};
  let view;
  await act(async () => {view=render(<Theme><VisualAdministration catalog={catalog} resources={[resource]}
    post={jest.fn().mockResolvedValue(resource)} selectedResource={resource} initialResourceKind="package" objectEditor /></Theme>);});
  const {container}=view;
  expect(container.querySelector('[data-cde-firebird-compact-form]')).not.toBeNull();
  expect(screen.getByText('SR-F-001412')).toBeVisible();
  expect(screen.queryByText('Apply confirmed batch')).toBeNull();
});
