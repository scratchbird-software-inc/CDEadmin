import PropTypes from 'prop-types';
import gettext from 'sources/gettext';

export default function SurfaceLayoutTemplateList({templates, onSelect}) {
  if (templates.length === 0) {
    return <p>{gettext('No saved templates yet.')}</p>;
  }
  return (
    <div style={{display: 'grid', gap: 6}}>
      {templates.map((template) => (
        <button
          key={template.template_id}
          type="button"
          className="sr-btn"
          style={{justifyContent: 'space-between'}}
          onClick={() => onSelect(template)}
        >
          <strong>{template.name}</strong>
          <span style={{fontSize: '0.72rem', opacity: 0.7}}>{template.updated_at}</span>
        </button>
      ))}
    </div>
  );
}

SurfaceLayoutTemplateList.propTypes = {
  templates: PropTypes.array.isRequired,
  onSelect: PropTypes.func.isRequired,
};
