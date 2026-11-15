/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import _ from 'lodash';
import { styled } from '@mui/material/styles';
import React, { useEffect } from 'react';
import {DataTable as PgTable} from 'sources/cdeadmin_ui/data/DataTable';
import gettext from 'sources/gettext';
import PropTypes from 'prop-types';
import getApiInstance from 'sources/api_instance';
import { getURL } from '../../../static/utils/utils';
import Loader from 'sources/components/Loader';
import EmptyPanelMessage from '../../../../static/js/components/EmptyPanelMessage';
import { toPrettySize } from '../../../../static/js/utils';
import withStandardTabInfo from '../../../../static/js/helpers/withStandardTabInfo';
import { BROWSER_PANELS } from '../../../../browser/static/js/constants';
import { usePgAdmin } from '../../../../static/js/PgAdminProvider';

const AUTH_STATS_MESSAGE = gettext(
  'You will need to authenticate and connect the server or a database on that server to see the statistics.'
);

const Root = styled('div')(({theme}) => ({
  height : '100%',
  padding: '16px 24px',
  boxSizing: 'border-box',
  '& .Statistics-emptyPanel': {
    minHeight: '100%',
    minWidth: '100%',
    background: theme.otherVars.emptySpaceBg,
    overflow: 'auto',
    padding: '16px 24px',
    boxSizing: 'border-box',
    display: 'flex',
  }
}));

function getColumn(data, singleLineStatistics, prettifyFields=[]) {
  let columns = [];
  if (!singleLineStatistics) {
    if (!_.isUndefined(data)) {
      data.forEach((row) => {
        columns.push({
          header: row.name,
          accessorKey: row.name,
          enableSorting: true,
          enableResizing: true,
          enableFilters: true,
          sortingFn: 'alphanumeric',
        });
      });
    }
  } else {
    columns = [
      {
        header: gettext('Statistics'),
        accessorKey: 'name',
        enableSorting: true,
        enableResizing: true,
        enableFilters: true,
      },
      {
        header: 'Value',
        accessorKey: 'value',
        enableSorting: false,
        enableResizing: true,
        enableFilters: true,
      },
    ];
  }
  columns.forEach((c)=>{
    // Prettify the cell view
    if(prettifyFields.includes(c.header)) {
      c.cell = ({cell})=><>{toPrettySize(cell.getValue())}</>;
      c.cell.displayName = 'Cell';
      c.cell.propTypes = {
        value: PropTypes.any,
      };
    }
  });
  return columns;
}

function isKeyValueStatisticColumns(columns) {
  return (
    Array.isArray(columns) &&
    columns.length === 2 &&
    columns[0]?.name === 'Statistic' &&
    columns[1]?.name === 'Value'
  );
}

function getTableData(res, node) {
  let nodeStats = [],
    colData;
  if (res?.data?.data) {
    let data = res.data.data;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    if (
      isKeyValueStatisticColumns(data.columns) ||
      node?.hasCollectiveStatistics ||
      rows.length > 1
    ) {
      rows.forEach((row) => {
        nodeStats.push({ ...row, icon: '' });
      });
      colData = getColumn(data.columns, false, node?.statsPrettifyFields);
    } else if (rows.length === 1) {
      nodeStats = createSingleLineStatistics(data, node?.statsPrettifyFields);
      colData = getColumn(data.columns, true);
    }
  }
  return [nodeStats, colData];
}

export function resolveStatisticsUrl(nodeData, treeNodeInfo, node, nodeItem) {
  const nodeType = nodeData?._type;
  const gid = treeNodeInfo?.server_group?._id || 1;

  if (nodeType === 'engine_type' || nodeType === 'localhost_placeholder') {
    const engineId = nodeData?.engine_id || nodeData?._id;
    if (!engineId) return null;
    return `/browser/engine_type/stats/${encodeURIComponent(gid)}/${encodeURIComponent(engineId)}`;
  }

  if (nodeType === 'cde_database_target') {
    const sid = treeNodeInfo?.server?._id || nodeData?._pid;
    const targetId = nodeData?.cde_database_target_id || nodeData?._id;
    if (!sid || !targetId) return null;
    return `/browser/server/stats/${encodeURIComponent(gid)}/${encodeURIComponent(sid)}?database_target_id=${encodeURIComponent(targetId)}`;
  }

  if (nodeType === 'server' && nodeData?._id != null) {
    return `/browser/server/stats/${encodeURIComponent(gid)}/${encodeURIComponent(nodeData._id)}`;
  }

  if (node?.hasStatistics) {
    return getURL(nodeData, true, treeNodeInfo, node, nodeItem, 'stats');
  }

  return null;
}

function createSingleLineStatistics(data, prettifyFields) {
  let row = data['rows'][0],
    columns = data['columns'],
    res = [],
    name,
    value;

  for (let idx in columns) {
    name = columns[idx]['name'];
    if (row?.[name]) {
      value =
        _.indexOf(prettifyFields, name) != -1
          ? toPrettySize(row[name])
          : row[name];
    } else {
      value = null;
    }

    res.push({
      name: name,
      value: value,
      icon: '',
    });
  }

  return res;
}

function Statistics({ nodeData, nodeItem, node, treeNodeInfo, isActive, isStale, setIsStale }) {
  const [tableData, setTableData] = React.useState([]);
  const [msg, setMsg] = React.useState('');
  const [loaderText, setLoaderText] = React.useState('');
  const [columns, setColumns] = React.useState([
    {
      header: gettext('Statistic'),
      accessorKey: 'name',
      enableSorting: true,
      enableResizing: true,
      enableFilters: true,
    },
    {
      header: gettext('Value'),
      accessorKey: 'value',
      enableSorting: true,
      enableResizing: true,
      enableFilters: true,
    },
  ]);
  const pgAdmin = usePgAdmin();

  useEffect(() => {
    if(!isStale || !isActive) {
      return;
    }

    if (!node && !nodeData) {
      setTableData([]);
      setLoaderText('');
      setMsg(gettext('Please select an object in the tree view.'));
      setIsStale(false);
      return;
    }

    const url = resolveStatisticsUrl(nodeData, treeNodeInfo, node, nodeItem);
    if (!url) {
      setTableData([]);
      setLoaderText('');
      setMsg(gettext('No statistics are available for the selected object.'));
      setIsStale(false);
      return;
    }

    const api = getApiInstance();
    setTableData([]);
    setMsg('');
    setLoaderText(gettext('Loading...'));

    api({
      url: url,
      type: 'GET',
    })
      .then((res) => {
        let [nodeStats, colData] = getTableData(res, node);
        setTableData(nodeStats);
        if (!_.isUndefined(colData)) {
          setColumns(colData);
        }
        if (!nodeStats || nodeStats.length === 0) {
          setMsg(res?.data?.info || AUTH_STATS_MESSAGE);
        } else {
          setMsg('');
        }
        setLoaderText('');
      })
      .catch((err) => {
        setLoaderText('');
        setTableData([]);

        if (err?.response?.data?.info == 'CRYPTKEY_MISSING') {
          pgAdmin?.Browser?.notifier?.pgNotifier?.('error', err.request, 'The master password is not set', function(mesg) {
            setTimeout(function() {
              if (mesg == 'CRYPTKEY_SET') {
                setMsg(AUTH_STATS_MESSAGE);
              } else if (mesg == 'CRYPTKEY_NOT_SET') {
                setMsg(gettext('The master password is not set.'));
              }
            }, 100);
          });
        } else {
          setMsg(err?.response?.data?.info || AUTH_STATS_MESSAGE);
        }
      });

    setIsStale(false);
  }, [isStale, isActive, nodeData?.id]);

  return (
    <Root>
      {tableData.length > 0 ? (
        <PgTable
          columns={columns}
          data={tableData}
          msg={msg}
          type={'panel'}
        ></PgTable>
      ) : (
        <div className='Statistics-emptyPanel'>
          <Loader message={loaderText} />
          <EmptyPanelMessage text={gettext(msg)}/>
        </div>
      )}
    </Root>
  );
}

Statistics.propTypes = {
  nodeData: PropTypes.object,
  nodeItem: PropTypes.object,
  treeNodeInfo: PropTypes.object,
  node: PropTypes.oneOfType([PropTypes.func, PropTypes.object]),
  isActive: PropTypes.bool,
  isStale: PropTypes.bool,
  setIsStale: PropTypes.func,
};

export default withStandardTabInfo(Statistics, BROWSER_PANELS.STATISTICS);
