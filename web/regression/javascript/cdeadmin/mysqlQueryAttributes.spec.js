import {mysqlQueryAttributes} from '../../../pgadmin/static/js/cdeadmin_ui/editors/mysqlQueryAttributes';

test('query attribute transport preserves native exact-value objects and NULL', () => {
  expect(mysqlQueryAttributes('{"tag":null,"n":{"encoding":"integer","data":"9007199254740993"}}'))
    .toEqual({tag:null,n:{encoding:'integer',data:'9007199254740993'}});
});

test.each(['null','[]','false','{"tag":"private-attribute-value"'])('invalid attribute JSON cannot become an execution request: %s', source => {
  expect(() => mysqlQueryAttributes(source)).toThrow('MySQL query attributes require a JSON object');
  try {mysqlQueryAttributes(source);} catch (error) {expect(error.message).not.toContain('private-attribute-value');}
});
