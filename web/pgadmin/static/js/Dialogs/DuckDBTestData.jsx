import PropTypes from 'prop-types';
import NativeTestDataRecipeView from './NativeTestDataRecipeView';

const DUCKDB_NOTES =
  'Use constant (value), default, sequential (start/step as exact signed 64-bit strings), random-integer (min/max as exact strings), or choice/file (values). Maximum 32 tables, 5000 requested rows, 4 MiB recipe and 1 MiB SQL file. Recipes and scripts may contain data. Native defaults, constraints and file effects apply when the shared Query Tool executes the script.';

export default function DuckDBTestData({post, databaseTargetId, engine = 'duckdb'}) {
  return (
    <NativeTestDataRecipeView
      post={post}
      databaseTargetId={databaseTargetId}
      engine={engine}
      notesText={DUCKDB_NOTES}
    />
  );
}

DuckDBTestData.propTypes = {
  post: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string.isRequired,
  engine: PropTypes.oneOf(['duckdb', 'sqlite']),
};
