/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Owner direction 2026-11-08: the Tools menu lists only module commands that
 * start from a bare menu click. A menu click passes no arguments and no
 * session (CommandMenuAdapter.executeMenuCommand), so actions on an open
 * session, run, plan, asset or DDN view stay in their module's own tool.
 */

import {etlModuleDefinition} from 'sources/cdeadmin_ui/modules/etl/module';
import {contractModuleDefinition} from 'sources/cdeadmin_ui/modules/data_contract/module';
import {aiModuleDefinition} from 'sources/cdeadmin_ui/modules/ai/module';
import {discoveryIntelligenceModuleDefinition} from 'sources/cdeadmin_ui/modules/discovery_intelligence/module';
import {aiInterfaceModuleDefinition} from 'sources/cdeadmin_ui/modules/ai_interface/module';
import {schemaCompareModuleDefinition} from 'sources/cdeadmin_ui/modules/schema_compare/module';
import {lineageModuleDefinition} from 'sources/cdeadmin_ui/modules/lineage/module';
import {cdcModuleDefinition} from 'sources/cdeadmin_ui/modules/cdc/module';
import {replicationModuleDefinition} from 'sources/cdeadmin_ui/modules/replication/module';
import {apiModuleDefinition} from 'sources/cdeadmin_ui/modules/api/module';
import {biModuleDefinition} from 'sources/cdeadmin_ui/modules/bi/module';
import {tracingModuleDefinition} from 'sources/cdeadmin_ui/modules/tracing/module';
import {ddnModuleDefinition} from 'sources/cdeadmin_ui/integrations/ddn/module';
import {migrationModuleDefinition} from 'sources/cdeadmin_ui/modules/migration/module';
import {mlVectorModuleDefinition} from 'sources/cdeadmin_ui/modules/ml_vector/module';
import {qualityModuleDefinition} from 'sources/cdeadmin_ui/modules/quality/module';

const DEFINITIONS = [etlModuleDefinition, contractModuleDefinition, aiModuleDefinition,
  discoveryIntelligenceModuleDefinition, aiInterfaceModuleDefinition,
  schemaCompareModuleDefinition, lineageModuleDefinition, cdcModuleDefinition,
  replicationModuleDefinition, apiModuleDefinition, biModuleDefinition,
  tracingModuleDefinition, ddnModuleDefinition, migrationModuleDefinition,
  mlVectorModuleDefinition, qualityModuleDefinition];

const registry = {register() {}, get() {}, list: () => [], active() {}};

function commands() {
  return DEFINITIONS.flatMap((define) => define(registry).contributions?.commands ?? []);
}

/* Services that accept anything: the test is about what a menu click can
 * supply, not about the services behind the commands. */
function anything() {
  return new Proxy(function() {}, {
    get: (_target, prop) => prop === 'then' ? undefined : prop === 'id' ? 'session-1' : anything(),
    apply: () => anything(),
  });
}

describe('Tools menu module commands', () => {
  it('lists only commands that start from the menu', () => {
    const onTools = commands().filter((command) => command.surfaces.includes('tools'))
      .map((command) => command.id).sort();
    expect(onTools).toEqual(['ddn.diagrams.new', 'ddn.diagrams.show',
      'schema_compare.session.create']);
  });

  it('keeps the module actions for their own tools', () => {
    const byId = Object.fromEntries(commands().map((command) => [command.id, command]));
    for(const id of ['schema_compare.plan.apply', 'replication.failover.execute',
      'cdc.replay.execute', 'etl.run.start', 'ai.emergency.disable_writes',
      'ddn.designer.save']) {
      expect(byId[id].surfaces).toEqual(['toolbar']);
    }
    // Owner direction 2026-11-08: the proof-of-concept DDN viewer and designer
    // are off the menus; the open commands stay callable from the Project Explorer.
    expect(byId['ddn.designer.open'].surfaces).toEqual(['toolbar']);
    expect(byId['ddn.viewer.open'].surfaces).toEqual(['toolbar']);
  });

  it('runs every Tools command with no arguments and no session', async () => {
    const opened = [];
    const context = {services: anything(), commands: anything(),
      currentUser: {permissions: []},
      openSurface: (id) => opened.push(id), showActivity: (id) => opened.push(id)};
    for(const command of commands().filter((item) => item.surfaces.includes('tools'))) {
      expect(command.validateArguments ? command.validateArguments({}) : true).toBe(true);
      await command.execute({}, context);
    }
    expect(opened).toEqual(expect.arrayContaining(['schema_compare.compare_setup',
      'activity.diagrams']));
  });
});
