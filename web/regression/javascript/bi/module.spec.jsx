/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import React from 'react';
import pgAdmin from 'sources/pgadmin';
import {CommandRegistry} from 'sources/cdeadmin_ui/commands/CommandRegistry';
import {CapabilityRegistry, ContributionRegistry,
  ServiceRegistry} from 'sources/cdeadmin_ui/platform/PlatformRegistry';
import {registerCorePlatformServices} from 'sources/cdeadmin_ui/platform/PlatformServices';
import {ModuleRegistry} from 'sources/cdeadmin_ui/platform/ModuleRegistry';
import {SurfaceRegistry} from 'sources/cdeadmin_ui/platform/SurfaceRegistry';
import {ToolFactoryRegistry} from 'sources/cdeadmin_ui/workspace/ToolRegistry';
import {EmptyState} from 'sources/cdeadmin_ui/feedback/EmptyState';
import {
  BI_MODULE_ID, BI_QUESTIONS_SURFACE_ID, BIQuestionsTool, registerBIModule,
} from 'sources/cdeadmin_ui/modules/bi';
import {openRegisteredTool} from 'pgbrowser/ProviderContextMenu';

function architecture() {
  const services = new ServiceRegistry(); registerCorePlatformServices(services);
  const registries = {services, capabilities: new CapabilityRegistry(),
    surfaces: new SurfaceRegistry(new ToolFactoryRegistry()), commands: new CommandRegistry(),
    inspector: new ContributionRegistry('inspector'), toolbox: new ContributionRegistry('toolbox'),
    status: new ContributionRegistry('status'), activity: new ContributionRegistry('activity'),
    bottom: new ContributionRegistry('bottom')};
  const modules = new ModuleRegistry(registries);
  registerBIModule({modules});
  return {...registries, modules};
}

const descriptorFor = (host) => host.surfaces.descriptor(BI_QUESTIONS_SURFACE_ID, {
  toolInstanceId: 'bi.questions:2', projectId: 'p', restoreRef: 'bi.questions:2',
  context: {providerId: 'sqlite', endpointId: 2}});

describe('BI module registration', () => {
  it('registers the BI questions surface through the generic tool registry', async () => {
    const host = architecture();
    await host.modules.activate(BI_MODULE_ID);
    expect(host.surfaces.list().map((surface) => surface.id)).toContain(BI_QUESTIONS_SURFACE_ID);
  });

  it('requires a module registry', () => {
    expect(() => registerBIModule({})).toThrow(/module registry/);
  });

  it('restores into the tool when the endpoint route is supplied', async () => {
    const host = architecture();
    await host.modules.activate(BI_MODULE_ID);
    const api = {post: jest.fn()};
    const setSurfaceState = jest.fn();
    const element = await host.surfaces.restore(descriptorFor(host), {
      api, endpointUrl: '/browser/server/cde_workspace/1/2', setSurfaceState});
    expect(element.type).toBe(BIQuestionsTool);
    expect(element.props).toMatchObject({api, endpointUrl: '/browser/server/cde_workspace/1/2'});
    element.props.onDirtyChange(true);
    expect(setSurfaceState).toHaveBeenCalledWith({dirty: true, persistence: 'dirty'});
    element.props.onDirtyChange(false);
    expect(setSurfaceState).toHaveBeenLastCalledWith({dirty: false, persistence: 'clean'});
  });

  it('asks to be opened again when a reloaded layout has no endpoint route', async () => {
    const host = architecture();
    await host.modules.activate(BI_MODULE_ID);
    const element = await host.surfaces.restore(descriptorFor(host), {});
    expect(element.type).toBe(EmptyState);
    expect(React.isValidElement(element)).toBe(true);
  });

  it('blocks closing while the question has unsaved changes', async () => {
    const host = architecture();
    await host.modules.activate(BI_MODULE_ID);
    const surface = host.surfaces.list().find((item) => item.id === BI_QUESTIONS_SURFACE_ID);
    expect(await surface.canClose({}, {dirty: true})).toMatchObject({allowed: false});
    expect(await surface.canClose({}, {dirty: false})).toMatchObject({allowed: true});
  });
});

describe('open_tool handler', () => {
  const original = {nodes: pgAdmin.Browser.Nodes, context: pgAdmin.Browser.CDEadminCommandContext,
    notifier: pgAdmin.Browser.notifier};
  afterEach(() => {
    pgAdmin.Browser.Nodes = original.nodes;
    pgAdmin.Browser.CDEadminCommandContext = original.context;
    pgAdmin.Browser.notifier = original.notifier;
  });

  const endpoint = {item: {id: 'item'}, data: {_id: 2, label: 'Sales DB', cde_engine_id: 'sqlite'}};

  it('opens the named surface with the endpoint identity and route, and no engine logic', async () => {
    const openSurface = jest.fn().mockResolvedValue(true);
    pgAdmin.Browser.Nodes = {server: {generate_url: jest.fn(() => '/browser/server/cde_workspace/1/2')}};
    pgAdmin.Browser.CDEadminCommandContext = () => ({openSurface});
    await openRegisteredTool('bi.questions', endpoint, 'BI questions');
    expect(openSurface).toHaveBeenCalledTimes(1);
    const [surfaceId, input, restoreContext] = openSurface.mock.calls[0];
    expect(surfaceId).toBe('bi.questions');
    expect(input).toEqual({
      toolInstanceId: 'bi.questions:2', restoreRef: 'bi.questions:2',
      title: expect.stringContaining('BI questions'),
      context: {providerId: 'sqlite', endpointId: 2}});
    expect(input.title).toContain('Sales DB');
    expect(restoreContext).toMatchObject({endpointUrl: '/browser/server/cde_workspace/1/2', endpointLabel: 'Sales DB'});
    expect(typeof restoreContext.api.post).toBe('function');
  });

  it('reports a missing tool host instead of failing silently', () => {
    pgAdmin.Browser.CDEadminCommandContext = () => undefined;
    expect(() => openRegisteredTool('bi.questions', endpoint, 'BI questions')).toThrow(/tool host is unavailable/);
    expect(() => openRegisteredTool('', endpoint, 'BI questions')).toThrow(/does not name a surface/);
  });

  it('shows the notifier message when the surface cannot open', async () => {
    const error = jest.fn();
    pgAdmin.Browser.Nodes = {server: {generate_url: () => '/x'}};
    pgAdmin.Browser.notifier = {error};
    pgAdmin.Browser.CDEadminCommandContext = () => ({openSurface: jest.fn().mockRejectedValue(new Error('boom'))});
    await openRegisteredTool('bi.questions', endpoint, 'BI questions');
    expect(error).toHaveBeenCalledWith('boom');
  });
});
