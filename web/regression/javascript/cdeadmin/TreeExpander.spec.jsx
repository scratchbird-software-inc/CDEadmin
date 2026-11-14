/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen} from '@testing-library/react';
import {FileType, ItemType} from 'react-aspen';

import {FileTreeItem} from
  'sources/components/PgTree/FileTreeItem';
import {FileTreeX} from 'sources/components/PgTree/FileTreeX';
import {FileTreeXEvent} from 'sources/components/PgTree/types';
import pgAdmin from 'sources/pgadmin';
import {manageTreeEvents} from 'sources/tree/tree';

describe('CDEadmin tree expander', () => {
  it('opens provider objects on activation without toggling their branch', async () => {
    const tree = new FileTreeX({model: {root: {}}, onEvent: jest.fn()});
    tree.setActiveFile = jest.fn().mockResolvedValue();
    tree.toggleDirectory = jest.fn();
    const dispatch = jest.spyOn(tree.events, 'dispatch');
    const item = {_metadata: {data: {_type: 'cde_resource'}}};
    const event = {};
    await tree.handleItemDoubleClicked(event, item);
    expect(tree.setActiveFile).toHaveBeenCalledWith(item);
    expect(dispatch).toHaveBeenCalledWith(FileTreeXEvent.onTreeEvents, event, 'activated', item);
    expect(tree.toggleDirectory).not.toHaveBeenCalled();
  });
  it('dispatches a directory toggle immediately and only once', () => {
    const data = {
      id: 'engine_type_firebird',
      _id: 'firebird',
      _type: 'engine_type',
      _label: 'Firebird',
      label: 'Firebird',
      inode: true,
      icon_key: 'engine.firebird',
    };
    const item = {
      id: 7,
      depth: 2,
      expanded: false,
      children: [],
      parent: {parent: null, path: '/browser', children: []},
      _metadata: {data},
      getMetadata: () => data,
    };
    item.parent.children.push(item);
    const onClick = jest.fn();

    render(<FileTreeItem
      item={item}
      itemType={ItemType.Directory}
      decorations={{
        classlist: [],
        addChangeListener: jest.fn(),
        removeChangeListener: jest.fn(),
      }}
      onClick={onClick}
      onDoubleClick={jest.fn()}
      onContextMenu={jest.fn()}
      onMouseEnter={jest.fn()}
      onMouseLeave={jest.fn()}
      changeDirectoryCount={jest.fn()}
      events={{dispatch: jest.fn()}}
    />);

    fireEvent.click(screen.getByRole('button', {
      name: 'Expand Firebird',
    }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick.mock.calls[0][1]).toBe(item);
    expect(onClick.mock.calls[0][2]).toBe(ItemType.Directory);
  });

  it('does not open a directory when beforeopen refuses it', async () => {
    const tree = new FileTreeX({});
    const openDirectory = jest.fn();
    tree.fileTreeHandle = {openDirectory};
    tree.events.add(FileTreeXEvent.onTreeEvents,
      (_event, eventName) => eventName !== 'beforeopen');
    const directory = {
      id: 10,
      type: FileType.Directory,
      expanded: false,
    };

    await tree.toggleDirectory(directory);

    expect(openDirectory).not.toHaveBeenCalled();
  });

  it('propagates a provider node beforeopen refusal through the tree bridge', () => {
    const previousBrowser = pgAdmin.Browser;
    const beforeopen = jest.fn(() => false);
    const data = {_type: 'cde_database_target', id: 'database-1'};
    const item = {
      parent: {path: '/browser/server-1'},
      _metadata: {data},
      getMetadata: () => data,
    };
    pgAdmin.Browser = {
      Nodes: {cde_database_target: {callbacks: {beforeopen}}},
      tree: {addNewNode: jest.fn()},
      Events: {trigger: jest.fn()},
    };

    try {
      expect(manageTreeEvents({}, 'beforeopen', item)).toBe(false);
      expect(beforeopen).toHaveBeenCalledWith(
        item, data, pgAdmin.Browser, [], 'beforeopen'
      );
    } finally {
      pgAdmin.Browser = previousBrowser;
    }
  });

  it('suppresses [+] toggle on childless rows and draws connected vertical stem on expanded circles', () => {
    const emptyGroupData = {
      id: 'cde_group_exceptions',
      _id: 'cde_group_exceptions',
      _type: 'cde_resource_group',
      _label: 'exceptions',
      label: 'exceptions',
      inode: true,
      has_children: false,
    };
    const emptyItem = {
      id: 21,
      depth: 4,
      expanded: false,
      children: [],
      parent: {parent: null, path: '/browser', children: []},
      _metadata: {data: emptyGroupData},
      getMetadata: () => emptyGroupData,
    };
    emptyItem.parent.children.push(emptyItem);

    const {container: emptyContainer} = render(<FileTreeItem
      item={emptyItem}
      itemType={ItemType.Directory}
      decorations={{classlist: [], addChangeListener: jest.fn(), removeChangeListener: jest.fn()}}
      onClick={jest.fn()}
      onDoubleClick={jest.fn()}
      onContextMenu={jest.fn()}
      onMouseEnter={jest.fn()}
      onMouseLeave={jest.fn()}
      changeDirectoryCount={jest.fn()}
      events={{dispatch: jest.fn()}}
    />);
    expect(emptyContainer.querySelector('button.directory-toggle')).toBeNull();
    expect(emptyContainer.querySelector('span.tree-node-terminal.leaf')).toBeInTheDocument();

    const openData = {
      id: 'server_group_1',
      _id: 1,
      _type: 'server_group',
      _label: 'Connectors (24)',
      label: 'Connectors (24)',
      inode: true,
      has_children: true,
    };
    const childStub = {id: 23, depth: 2, children: [], _metadata: {data: {_type: 'engine_type'}}};
    const openItem = {
      id: 22,
      depth: 1,
      expanded: true,
      isExpanded: true,
      children: [childStub],
      parent: {parent: null, path: '/browser', children: []},
      _metadata: {data: openData},
      getMetadata: () => openData,
    };
    openItem.parent.children.push(openItem);

    const {container: openContainer, rerender} = render(<FileTreeItem
      item={openItem}
      itemType={ItemType.Directory}
      decorations={{classlist: [], addChangeListener: jest.fn(), removeChangeListener: jest.fn()}}
      onClick={jest.fn()}
      onDoubleClick={jest.fn()}
      onContextMenu={jest.fn()}
      onMouseEnter={jest.fn()}
      onMouseLeave={jest.fn()}
      changeDirectoryCount={jest.fn()}
      events={{dispatch: jest.fn()}}
    />);
    expect(openContainer.querySelector('button.directory-toggle.open')).toBeInTheDocument();
    expect(openContainer.querySelector('svg.directory-toggle-stem path')).toHaveAttribute('d', 'M 10 21 V 28');
    expect(openContainer.querySelector('.file-name').textContent).toBe('Connectors (24)');

    const gettext = require('sources/gettext').default;
    const {act} = require('@testing-library/react');
    try {
      act(() => {
        gettext.setCatalog(null, 'fr');
      });
      rerender(<FileTreeItem
        item={openItem}
        itemType={ItemType.Directory}
        decorations={{classlist: [], addChangeListener: jest.fn(), removeChangeListener: jest.fn()}}
        onClick={jest.fn()}
        onDoubleClick={jest.fn()}
        onContextMenu={jest.fn()}
        onMouseEnter={jest.fn()}
        onMouseLeave={jest.fn()}
        changeDirectoryCount={jest.fn()}
        events={{dispatch: jest.fn()}}
      />);
      expect(openContainer.querySelector('.file-name').textContent).toBe('Connecteurs (24)');
    } finally {
      act(() => {
        gettext.setCatalog(null, 'en');
      });
    }
  });

  it('updates open modal dialogs immediately on live language switch without losing input state', () => {
    const gettext = require('sources/gettext').default;
    const ModalProvider = require('sources/helpers/ModalProvider').default;
    const {useModal} = require('sources/helpers/ModalProvider');
    const ConnectServerContent = require('sources/Dialogs/ConnectServerContent').default;
    const Theme = require('sources/Theme').default;
    const React = require('react');
    const {act} = require('@testing-library/react');

    let modalApi = null;
    function Harness() {
      modalApi = useModal();
      return null;
    }

    try {
      render(
        <Theme>
          <ModalProvider>
            <Harness />
          </ModalProvider>
        </Theme>
      );

      act(() => {
        modalApi.showModal(gettext('Verify Endpoint'), (onClose) => (
          <ConnectServerContent
            closeModal={onClose}
            data={{
              prompt_password: true,
              require_username_input: true,
              suggested_username: 'SYSDBA',
              server_label: 'localhost',
              allow_save_password: true,
            }}
            onOK={jest.fn()}
          />
        ), {id: 'test-live-i18n-modal'});
      });

      const userInput = screen.getByLabelText('User or principal');
      fireEvent.change(userInput, {target: {value: 'CUSTOM_ADMIN'}});
      expect(screen.getByText('Verify Endpoint')).toBeInTheDocument();

      act(() => {
        gettext.setCatalog(null, 'fr');
      });

      expect(screen.getByText('Vérifier le point de terminaison')).toBeInTheDocument();
      expect(screen.getByText('Utilisateur ou principal')).toBeInTheDocument();
      expect(screen.getByText('Annuler')).toBeInTheDocument();
      expect(screen.getByDisplayValue('CUSTOM_ADMIN')).toBeInTheDocument();
    } finally {
      act(() => {
        gettext.setCatalog(null, 'en');
      });
    }
  });

  it('refreshes empty and populated branches in FileTreeX and updates has_children on add/drop', async () => {
    const tree = new FileTreeX({
      model: {root: {pathfx: {dirname: () => '/browser', basename: () => 't1'}}},
      remove: jest.fn().mockResolvedValue(),
      onEvent: jest.fn(),
    });
    const groupData = {_type: 'cde_resource_group', id: 'tables', has_children: true};
    const groupItem = {
      id: 40,
      path: '/browser/tables',
      isExpanded: true,
      children: [],
      _children: [],
      _metadata: {data: groupData},
    };
    const closeDirectory = jest.fn().mockResolvedValue();
    const openDirectory = jest.fn().mockImplementation(async (dir) => {
      // Simulate last table dropped -> 0 children after reload
      dir.children = [];
    });
    tree.fileTreeHandle = {closeDirectory, openDirectory};
    tree.changeResolvePath = jest.fn().mockResolvedValue();
    tree.changeDirectoryCount = jest.fn();
    tree.forceUpdate = jest.fn();

    await tree.refresh(groupItem);
    expect(groupData.has_children).toBe(false);
    expect(closeDirectory).toHaveBeenCalledTimes(2);
    expect(tree.forceUpdate).toHaveBeenCalled();
  });
});
