const fs = require('node:fs');
const path = require('node:path');
const {DefaultArtifactClient} = require('@actions/artifact');

async function main() {
  const root = path.resolve(process.env.INPUT_PATH);
  fs.mkdirSync(root, {recursive: true});
  const manifest = path.resolve('web/pgadmin/static/vendor/ddn/current/resource-manifest.json');
  if (fs.existsSync(manifest)) fs.copyFileSync(manifest, path.join(root, 'ddn-resource-manifest.json'));
  const files = [];
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!entry.name.startsWith('owned-') && !entry.name.startsWith('mariadb-parent-') && entry.name !== 'ddn-intake') visit(target);
      } else if (entry.isFile() && ['.json', '.xml', '.log', '.png', '.md'].includes(path.extname(entry.name))) {
        files.push(target);
      }
    }
  }
  visit(root);
  if (!files.length) {
    const failure = path.join(root, 'setup-incomplete.json');
    fs.writeFileSync(failure, JSON.stringify({complete: false, reason: 'Setup ended before qualification evidence was written.'}));
    files.push(failure);
  }
  const result = await new DefaultArtifactClient().uploadArtifact(process.env.INPUT_NAME, files, root, {retentionDays: 14});
  console.log(`Preserved ${files.length} native evidence files; artifact ${result.id}`);
}
main().catch(error => {console.error(error); process.exitCode = 1;});
