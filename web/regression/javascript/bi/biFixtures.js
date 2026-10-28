/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Fixtures for the BI builder tests. The question documents are the output of
 * the backend validator (bi.validate_question) for the questions defined in
 * tools/tests/test_cdeadmin_bi_saved_questions.py (detail_question,
 * summary_question, the semantic "Cube question") and
 * tools/tests/test_cdeadmin_bi_execution.py (SQL-to-question cases), copied
 * here so the UI is tested against the real contract shapes. The conversion
 * outcomes are the real bi_sql_to_question responses for those statements.
 */

export const questions = {
  'detail': {
    'contract_version': '1.0.0',
    'name': 'Big sales',
    'description': '',
    'collection_id': null,
    'semantic_model': null,
    'query': {
      'kind': 'builder',
      'builder': {
        'source': {
          'relation': [
            'sales'
          ]
        },
        'columns': [
          {
            'column': 'region'
          },
          {
            'column': 'amount',
            'alias': 'total'
          }
        ],
        'group_by': [],
        'aggregations': [],
        'filters': [
          {
            'operator': 'gt',
            'column': 'amount',
            'value': 10
          }
        ],
        'order_by': [
          {
            'column': 'amount',
            'direction': 'desc'
          }
        ],
        'limit': 3
      }
    },
    'visualization': {
      'type': 'table',
      'settings': {}
    },
    'parameters': [],
    'result_policy': {
      'redact_columns': [],
      'export': {
        'enabled': false,
        'formats': []
      },
      'cache_ttl_seconds': 300,
      'page_size': 100
    }
  },
  'summary': {
    'contract_version': '1.0.0',
    'name': 'Revenue by region',
    'description': '',
    'collection_id': null,
    'semantic_model': null,
    'query': {
      'kind': 'builder',
      'builder': {
        'source': {
          'relation': [
            'sales'
          ]
        },
        'columns': [],
        'group_by': [
          {
            'column': 'region'
          }
        ],
        'aggregations': [
          {
            'function': 'sum',
            'column': 'amount',
            'alias': 'revenue'
          },
          {
            'function': 'count',
            'alias': 'orders'
          }
        ],
        'filters': [
          {
            'operator': 'gte',
            'column': 'amount',
            'parameter_id': 'min_amount'
          }
        ],
        'order_by': [
          {
            'column': 'revenue',
            'direction': 'desc'
          }
        ],
        'limit': 10
      }
    },
    'visualization': {
      'type': 'bar',
      'settings': {
        'x': 'region'
      }
    },
    'parameters': [
      {
        'id': 'min_amount',
        'name': 'min_amount',
        'type': 'integer',
        'required': false,
        'allowed_values': [],
        'default': 0
      }
    ],
    'result_policy': {
      'redact_columns': [],
      'export': {
        'enabled': false,
        'formats': []
      },
      'cache_ttl_seconds': 300,
      'page_size': 100
    }
  },
  'semantic': {
    'contract_version': '1.0.0',
    'name': 'Cube question',
    'description': '',
    'collection_id': null,
    'semantic_model': {
      'id': 'model-1',
      'revision': 1
    },
    'query': {
      'kind': 'semantic',
      'builder': {
        'group_by': [
          'region'
        ],
        'aggregations': [
          {
            'measure_id': 'revenue'
          }
        ],
        'filters': [
          {
            'operator': 'eq',
            'field': {
              'source_id': 'sales',
              'field': 'region'
            },
            'value': 'west'
          }
        ],
        'order_by': [
          {
            'id': 'revenue',
            'direction': 'desc'
          }
        ],
        'limit': 5
      }
    },
    'visualization': {
      'type': 'table',
      'settings': {}
    },
    'parameters': [],
    'result_policy': {
      'redact_columns': [],
      'export': {
        'enabled': false,
        'formats': []
      },
      'cache_ttl_seconds': 300,
      'page_size': 100
    }
  },
  'raw': {
    'contract_version': '1.0.0',
    'name': 'Raw floor',
    'description': '',
    'collection_id': null,
    'semantic_model': null,
    'query': {
      'kind': 'sql',
      'sql': 'SELECT region FROM sales WHERE amount > {{floor}}'
    },
    'visualization': {
      'type': 'table',
      'settings': {}
    },
    'parameters': [
      {
        'id': 'floor',
        'name': 'floor',
        'type': 'integer',
        'required': false,
        'allowed_values': [],
        'default': 3
      }
    ],
    'result_policy': {
      'redact_columns': [],
      'export': {
        'enabled': false,
        'formats': []
      },
      'cache_ttl_seconds': 300,
      'page_size': 100
    }
  },
  'filters': {
    'contract_version': '1.0.0',
    'name': 'Typed filters',
    'description': '',
    'collection_id': null,
    'semantic_model': null,
    'query': {
      'kind': 'builder',
      'builder': {
        'source': {
          'relation': [
            'sales'
          ]
        },
        'columns': [
          {
            'column': 'region'
          },
          {
            'column': 'amount',
            'alias': 'total'
          }
        ],
        'group_by': [],
        'aggregations': [],
        'filters': [
          {
            'operator': 'between',
            'column': 'amount',
            'value': [
              5,
              30
            ]
          },
          {
            'operator': 'in',
            'column': 'region',
            'value': [
              'east',
              'west'
            ]
          },
          {
            'operator': 'gte',
            'column': 'amount',
            'parameter_id': 'min_amount'
          },
          {
            'operator': 'is_not_null',
            'column': 'region'
          }
        ],
        'order_by': [
          {
            'column': 'amount',
            'direction': 'desc'
          }
        ],
        'limit': 3
      }
    },
    'visualization': {
      'type': 'table',
      'settings': {}
    },
    'parameters': [
      {
        'id': 'min_amount',
        'name': 'min_amount',
        'type': 'integer',
        'required': false,
        'allowed_values': [],
        'default': 5
      }
    ],
    'result_policy': {
      'redact_columns': [],
      'export': {
        'enabled': false,
        'formats': []
      },
      'cache_ttl_seconds': 300,
      'page_size': 100
    }
  }
};

export const conversions = {
  'exact': {
    'fidelity': 'exact',
    'mapped': true,
    'question': {
      'contract_version': '1.0.0',
      'name': 'Converted question',
      'description': '',
      'collection_id': null,
      'semantic_model': null,
      'query': {
        'kind': 'builder',
        'builder': {
          'source': {
            'relation': [
              'sales'
            ]
          },
          'columns': [],
          'group_by': [
            {
              'column': 'region'
            }
          ],
          'aggregations': [
            {
              'function': 'sum',
              'column': 'amount',
              'alias': 'revenue'
            },
            {
              'function': 'count',
              'alias': 'orders'
            }
          ],
          'filters': [
            {
              'operator': 'gte',
              'column': 'amount',
              'parameter_id': 'floor'
            },
            {
              'operator': 'ne',
              'column': 'region',
              'value': 'x'
            }
          ],
          'order_by': [
            {
              'column': 'revenue',
              'direction': 'desc'
            }
          ],
          'limit': 5
        }
      },
      'visualization': {
        'type': 'table',
        'settings': {}
      },
      'parameters': [
        {
          'id': 'floor',
          'name': 'floor',
          'type': 'integer',
          'required': true,
          'allowed_values': []
        }
      ],
      'result_policy': {
        'redact_columns': [],
        'export': {
          'enabled': false,
          'formats': []
        },
        'cache_ttl_seconds': 300,
        'page_size': 100
      }
    },
    'builder': {
      'source': {
        'relation': [
          'sales'
        ]
      },
      'filters': [
        {
          'column': 'amount',
          'operator': 'gte',
          'parameter_id': 'floor'
        },
        {
          'column': 'region',
          'operator': 'ne',
          'value': 'x'
        }
      ],
      'group_by': [
        {
          'column': 'region'
        }
      ],
      'columns': [],
      'aggregations': [
        {
          'function': 'sum',
          'column': 'amount',
          'alias': 'revenue'
        },
        {
          'function': 'count',
          'alias': 'orders'
        }
      ],
      'order_by': [
        {
          'column': 'revenue',
          'direction': 'desc'
        }
      ],
      'limit': 5
    },
    'loss': []
  },
  'lossy': {
    'fidelity': 'lossy',
    'mapped': true,
    'question': {
      'contract_version': '1.0.0',
      'name': 'Converted question',
      'description': '',
      'collection_id': null,
      'semantic_model': null,
      'query': {
        'kind': 'builder',
        'builder': {
          'source': {
            'relation': [
              'main',
              'sales'
            ]
          },
          'columns': [
            {
              'column': 'region'
            },
            {
              'column': 'amount'
            }
          ],
          'group_by': [],
          'aggregations': [],
          'filters': [
            {
              'operator': 'between',
              'column': 'amount',
              'value': [
                5,
                30
              ]
            },
            {
              'operator': 'in',
              'column': 'region',
              'value': [
                'east',
                'west'
              ]
            }
          ],
          'order_by': [
            {
              'column': 'amount',
              'direction': 'desc'
            }
          ],
          'limit': 500
        }
      },
      'visualization': {
        'type': 'table',
        'settings': {}
      },
      'parameters': [],
      'result_policy': {
        'redact_columns': [],
        'export': {
          'enabled': false,
          'formats': []
        },
        'cache_ttl_seconds': 300,
        'page_size': 100
      }
    },
    'builder': {
      'source': {
        'relation': [
          'main',
          'sales'
        ]
      },
      'filters': [
        {
          'column': 'amount',
          'operator': 'between',
          'value': [
            5,
            30
          ]
        },
        {
          'column': 'region',
          'operator': 'in',
          'value': [
            'east',
            'west'
          ]
        }
      ],
      'columns': [
        {
          'column': 'region'
        },
        {
          'column': 'amount'
        }
      ],
      'group_by': [],
      'aggregations': [],
      'order_by': [
        {
          'column': 'amount',
          'direction': 'desc'
        }
      ]
    },
    'loss': [
      {
        'code': 'implicit_limit',
        'severity': 'warning',
        'detail': 'the statement has no LIMIT; builder state applies the default row cap of 500, so a larger result is truncated'
      },
      {
        'code': 'comments_dropped',
        'severity': 'info',
        'detail': 'SQL comments are not kept in builder state'
      }
    ]
  },
  'none': {
    'fidelity': 'none',
    'mapped': false,
    'question': {
      'contract_version': '1.0.0',
      'name': 'Converted question',
      'description': '',
      'collection_id': null,
      'semantic_model': null,
      'query': {
        'kind': 'sql',
        'sql': 'SELECT a.x FROM a JOIN b ON a.id = b.id'
      },
      'visualization': {
        'type': 'table',
        'settings': {}
      },
      'parameters': [],
      'result_policy': {
        'redact_columns': [],
        'export': {
          'enabled': false,
          'formats': []
        },
        'cache_ttl_seconds': 300,
        'page_size': 100
      }
    },
    'builder': null,
    'loss': [
      {
        'code': 'unmappable_join',
        'severity': 'blocking',
        'detail': 'joins are not expressible in builder state'
      },
      {
        'code': 'unmappable_trailing',
        'severity': 'blocking',
        'detail': 'unsupported clause near \'JOIN\''
      }
    ]
  }
};
