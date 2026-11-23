import PropTypes from 'prop-types';
import NativeTestDataRecipeView from './NativeTestDataRecipeView';

const PG_NOTES =
  'Use constant (value), default, sequential (start/step as exact strings), random-integer (min/max as exact strings), choice/file (values), generated (table resource ID and column), returned (native parent INSERT RETURNING value), or existing (table resource ID, column and order_by column names). Existing sources read up to 200 rows per table only when the script runs; choose a unique ordering key for repeatable row selection. Empty samples or trigger-suppressed parents supply NULL. Maximum 32 tables, 5000 requested rows, 4 MiB recipe and 1 MiB SQL file. Recipes and scripts may contain data. Native privileges, RLS, triggers and constraints apply on execution; sequence advances may survive rollback.';

export default function PostgresqlTestData({post, databaseTargetId}) {
  return (
    <NativeTestDataRecipeView
      post={post}
      databaseTargetId={databaseTargetId}
      engine="postgresql"
      notesText={PG_NOTES}
    />
  );
}

PostgresqlTestData.propTypes = {
  post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string.isRequired,
};
