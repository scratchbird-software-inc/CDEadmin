import PropTypes from 'prop-types';
import NativeTestDataRecipeView from './NativeTestDataRecipeView';

const MYSQL_NOTES =
  'Use constant (value), default, sequential (start/step as exact strings), random-integer (min/max as exact strings), choice/file (values), generated (table resource ID and column), returned (native parent AUTO_INCREMENT allocation), or existing (table resource ID, column and order_by column names). Existing sources read up to 200 rows per table only when the script runs; choose a unique ordering key for repeatable row selection. Empty existing selections supply NULL; default-only AUTO_INCREMENT parents use LAST_INSERT_ID. Maximum 32 tables, 5000 requested rows, 4 MiB recipe and 1 MiB SQL file. Recipes and scripts may contain data. Native privileges, triggers and constraints apply on execution; AUTO_INCREMENT allocation and nontransactional storage may survive rollback. Trigger-supplied IDs without a native allocation produce NULL returned references.';

export default function MySQLTestData({post, databaseTargetId, engine = 'mysql'}) {
  return (
    <NativeTestDataRecipeView
      post={post}
      databaseTargetId={databaseTargetId}
      engine={engine}
      notesText={MYSQL_NOTES}
    />
  );
}

MySQLTestData.propTypes = {
  engine: PropTypes.oneOf(['mysql', 'mariadb']),
  post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string.isRequired,
};
