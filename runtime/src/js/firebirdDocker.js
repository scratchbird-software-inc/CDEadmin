/** Explicit desktop Docker provisioning; no web-server subprocesses. */
import {execFile} from 'node:child_process';
import {mkdir, open, readFile, readdir, realpath, stat, rename, unlink} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {inspectExecutable} from './firebirdIsql.js';

export const IMAGE = 'firebirdsql/firebird:5.0.4';
const LABEL = 'org.scratchrobin.firebird-provision';
const DATA = '/var/lib/firebird/data';
const uuid = value => typeof value === 'string' && /^[a-f0-9-]{36}$/.test(value);
function name(value, label) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$/.test(value)) throw new Error(`Invalid ${label}.`);
  return value;
}
function port(value) {
  if (!Number.isInteger(value) || value < 1024 || value > 65535) throw new Error('Choose a port from 1024 through 65535.');
  return value;
}
export function configuration(value) {
  if (!value || Object.keys(value).some(key => !['context', 'container', 'storage', 'volume', 'bind', 'port', 'eventPort', 'database', 'version'].includes(key))) throw new Error('Unknown provisioning fields.');
  if (value.version !== '5.0.4' || !['volume', 'directory'].includes(value.storage) || !['127.0.0.1', '0.0.0.0'].includes(value.bind)) throw new Error('Unsupported image, storage or IPv4 bind address.');
  if (typeof value.database !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,58}\.fdb$/.test(value.database)) throw new Error('Use a simple .fdb filename.');
  const result = {context: name(value.context, 'Docker context'), container: name(value.container, 'container name'),
    storage: value.storage, bind: value.bind, port: port(value.port), eventPort: value.eventPort == null ? null : port(value.eventPort),
    database: value.database, version: value.version};
  if (result.eventPort === result.port || result.eventPort === 3050) throw new Error('SQL and event ports must be distinct, including the native SQL port 3050.');
  if (value.storage === 'volume') result.volume = name(value.volume, 'volume name');
  return result;
}
function environment(base, password) {
  const result = {...base};
  for (const key of Object.keys(result)) if (key.startsWith('FIREBIRD_') || ['DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'].includes(key)) delete result[key];
  if (password !== undefined) result.FIREBIRD_ROOT_PASSWORD = password;
  return result;
}
async function command(executable, args, env, timeout=30000) {
  return new Promise((resolve, reject) => execFile(executable, args, {env, timeout, maxBuffer: 2 * 1024 * 1024, shell: false}, (error, stdout) => {
    if (error) reject(new Error('Docker command did not return successfully. Inspect the named resources before retrying.'));
    else resolve(stdout.trim());
  }));
}
async function directoryIdentity(filename) {
  const resolved = await realpath(filename), detail = await stat(resolved);
  if (!detail.isDirectory() || (await readdir(resolved)).length) throw new Error('Select an empty local directory. Existing contents are preserved.');
  if (resolved.includes(',') || /[\0\r\n]/.test(resolved)) throw new Error('Directory path cannot contain commas or control characters.');
  return {path: resolved, device: detail.dev, inode: detail.ino};
}
export function createArguments(record) {
  const c = record.configuration;
  const args = ['--context', c.context, 'create', '--pull=never', '--name', c.container,
    '--label', `${LABEL}=${record.review_id}`, '--publish', `${c.bind}:${c.port}:3050`,
    '--mount', c.storage === 'volume' ? `type=volume,source=${c.volume},target=${DATA}` : `type=bind,source=${record.directory.path},target=${DATA}`,
    '--env', 'FIREBIRD_ROOT_PASSWORD', '--env', `FIREBIRD_DATABASE=${c.database}`, '--env', 'FIREBIRD_DATABASE_DEFAULT_CHARSET=UTF8'];
  if (c.eventPort !== null) args.push('--publish', `${c.bind}:${c.eventPort}:${c.eventPort}`, '--env', `FIREBIRD_CONF_RemoteAuxPort=${c.eventPort}`);
  return [...args, record.image_id];
}

export class FirebirdDocker {
  constructor({root, execute=command, env=process.env, now=Date.now}) {
    this.root = root; this.execute = execute; this.env = env; this.now = now; this.reviews = new Map();
  }
  async persist(record) {
    const root = typeof this.root === 'function' ? this.root() : this.root;
    await mkdir(root, {recursive: true, mode: 0o700});
    const temporary = path.join(root, `${record.review_id}.${randomUUID()}.tmp`);
    try {
      const file = await open(temporary, 'wx', 0o600);
      try {await file.writeFile(JSON.stringify(record, null, 2)); await file.sync();} finally {await file.close();}
      await rename(temporary, path.join(root, `${record.review_id}.json`));
      const directory = await open(root, 'r');
      try {await directory.sync();} finally {await directory.close();}
    } finally {await unlink(temporary).catch(() => {});}
  }
  async receipt(id) {
    if (!uuid(id)) throw new Error('Invalid receipt ID.');
    const root = typeof this.root === 'function' ? this.root() : this.root;
    return JSON.parse(await readFile(path.join(root, `${id}.json`), 'utf8'));
  }
  async daemon(binary, context) {
    const clean = environment(this.env);
    const endpoint = JSON.parse(await this.execute(binary, ['context', 'inspect', context, '--format', '{{json .Endpoints.docker.Host}}'], clean));
    if (typeof endpoint !== 'string' || !/^(unix|ssh|tcp):\/\//.test(endpoint) || new URL(endpoint).password) throw new Error('Unsupported Docker endpoint.');
    let id;
    try {id = JSON.parse(await this.execute(binary, ['--context', context, 'info', '--format', '{{json .ID}}'], clean));}
    catch {throw new Error(`Docker context ${context} cannot reach its daemon at ${endpoint}. Select the intended available context.`);}
    if (typeof id !== 'string' || !id) throw new Error('Docker daemon identity is unavailable.');
    return {endpoint, id};
  }
  async contexts(executable) {
    const binary = await inspectExecutable(executable), clean = environment(this.env);
    const version = await this.execute(binary, ['--version'], clean, 5000);
    if (!/^Docker version /i.test(version)) throw new Error('Choose the Docker CLI executable.');
    const output = await this.execute(binary, ['context', 'ls', '--format', '{{json .}}'], clean);
    const contexts = output.split('\n').filter(Boolean).map(line => {
      const item = JSON.parse(line), endpoint = item.DockerEndpoint;
      name(item.Name, 'Docker context');
      if (typeof endpoint !== 'string' || !/^(unix|ssh|tcp):\/\//.test(endpoint) || new URL(endpoint).password) throw new Error('Unsupported Docker context endpoint.');
      return {name: item.Name, endpoint, current: item.Current === true};
    });
    if (!contexts.length || contexts.length > 128) throw new Error('Docker context inventory is empty or exceeds 128 entries.');
    return {executable: binary, contexts};
  }
  async prepare({executable, config, directory, owner}) {
    for (const [id, review] of this.reviews) if (review.record.expires_at < this.now()) this.reviews.delete(id);
    if (this.reviews.size >= 32) throw new Error('Too many pending Docker reviews; wait for their ten-minute expiry.');
    const c = configuration(config), binary = await inspectExecutable(executable), clean = environment(this.env);
    const version = await this.execute(binary, ['--version'], clean, 5000);
    if (!/^Docker version /i.test(version)) throw new Error('Choose the Docker CLI executable.');
    const daemon = await this.daemon(binary, c.context);
    let selectedDirectory;
    if (c.storage === 'directory') {
      if (!daemon.endpoint.startsWith('unix://')) throw new Error('Directory mounts require a local Unix-socket Docker context.');
      selectedDirectory = await directoryIdentity(directory);
    }
    const containers = await this.execute(binary, ['--context', c.context, 'container', 'ls', '--all', '--format', '{{.Names}}'], clean);
    if (containers.split('\n').includes(c.container)) throw new Error('Container name already exists.');
    if (c.storage === 'volume') {
      const volumes = await this.execute(binary, ['--context', c.context, 'volume', 'ls', '--format', '{{.Name}}'], clean);
      if (volumes.split('\n').includes(c.volume)) throw new Error('Volume already exists; this workflow creates new storage only.');
    }
    let image;
    const inspect = () => this.execute(binary, ['--context', c.context, 'image', 'inspect', IMAGE, '--format', '{{json .Id}}'], clean);
    try {image = JSON.parse(await inspect());}
    catch {await this.execute(binary, ['--context', c.context, 'pull', IMAGE], clean, 600000); image = JSON.parse(await inspect());}
    if (typeof image !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(image)) throw new Error('Immutable image identity is unavailable.');
    const record = {format: 'scratchrobin.firebird.docker-provision@1', review_id: randomUUID(),
      state: 'prepared', created_at: this.now(), expires_at: this.now() + 600000,
      execution_host: 'local-desktop Docker CLI', daemon, executable: binary,
      image: IMAGE, image_id: image, configuration: c, ...(selectedDirectory ? {directory: selectedDirectory} : {}),
      native_connection_verified: false};
    await this.persist(record);
    this.reviews.set(record.review_id, {record, owner});
    return record;
  }
  async apply({review_id, password, confirmed, owner}) {
    const pending = this.reviews.get(review_id);
    if (!pending || pending.owner !== owner || confirmed !== true || pending.record.expires_at < this.now()) throw new Error('The confirmed unconsumed review is unavailable or expired.');
    if (typeof password !== 'string' || !password || password.length > 255 || /[\0\r\n]/.test(password)) throw new Error('Enter a nonempty bootstrap password without line breaks.');
    this.reviews.delete(review_id);
    const record = JSON.parse(JSON.stringify(pending.record)), c = record.configuration, binary = record.executable;
    const clean = environment(this.env), args = ['--context', c.context];
    const sameDaemon = async () => {
      if (JSON.stringify(await this.daemon(binary, c.context)) !== JSON.stringify(record.daemon)) throw new Error('Docker context/daemon changed since review.');
    };
    try {
      await sameDaemon();
      const image = JSON.parse(await this.execute(binary, [...args, 'image', 'inspect', record.image_id, '--format', '{{json .Id}}'], clean));
      if (image !== record.image_id) throw new Error('Reviewed image is unavailable.');
      if (c.storage === 'directory' && JSON.stringify(await directoryIdentity(record.directory.path)) !== JSON.stringify(record.directory)) throw new Error('Selected directory changed since review.');
      if (c.storage === 'volume') {
        const names = await this.execute(binary, [...args, 'volume', 'ls', '--format', '{{.Name}}'], clean);
        if (names.split('\n').includes(c.volume)) throw new Error('Volume appeared after review; no existing storage is admitted.');
        record.state = 'creating_volume'; await this.persist(record);
        await sameDaemon();
        await this.execute(binary, [...args, 'volume', 'create', '--label', `${LABEL}=${review_id}`, c.volume], clean);
        const label = await this.execute(binary, [...args, 'volume', 'inspect', c.volume, '--format', `{{index .Labels "${LABEL}"}}`], clean);
        if (label !== review_id) throw new Error('Volume ownership was not confirmed.');
        record.volume_created = c.volume;
      }
      record.state = 'creating_container'; await this.persist(record);
      await sameDaemon();
      const id = await this.execute(binary, createArguments(record), environment(this.env, password));
      if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('Container identity was not returned.');
      record.container_id = id; record.state = 'starting_container'; await this.persist(record);
      await sameDaemon();
      await this.execute(binary, [...args, 'start', id], clean);
      const running = await this.execute(binary, [...args, 'inspect', id, '--format', '{{json .State.Running}}'], clean);
      record.state = running === 'true' ? 'container_running' : 'container_not_running';
      record.native_connection_verified = false;
    } catch {
      record.last_phase = record.state;
      record.state = 'unconfirmed_or_partial';
      record.message = 'Provisioning did not complete with confirmed Docker observations. Inspect the recorded names and Docker daemon before taking further action. This review cannot be replayed; no resources were automatically removed.';
    }
    await this.persist(record);
    return record;
  }
}

export function setupFirebirdDocker({ipcMain, BrowserWindow, dialog, getOrigin, service}) {
  const windowFor = event => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window.isDestroyed() || event.senderFrame !== event.sender.mainFrame ||
        new URL(event.senderFrame.url).origin !== new URL(getOrigin()).origin) throw new Error('Docker provisioning requires the local application window.');
    if (process.platform !== 'linux') throw new Error('Docker provisioning is qualified on the Linux desktop host.');
    return window;
  };
  ipcMain.handle('firebird-docker:contexts', async event => {
    const window = windowFor(event);
    const chosen = await dialog.showOpenDialog(window, {title: 'Select local Docker CLI', properties: ['openFile']});
    windowFor(event);
    if (chosen.canceled || chosen.filePaths.length !== 1) return {state: 'cancelled_before_preparation'};
    const result = await service.contexts(chosen.filePaths[0]);
    windowFor(event); return result;
  });
  ipcMain.handle('firebird-docker:prepare', async (event, request) => {
    const window = windowFor(event), config = configuration(request);
    const chosen = await dialog.showOpenDialog(window, {title: 'Select local Docker CLI', properties: ['openFile']});
    windowFor(event);
    if (chosen.canceled || chosen.filePaths.length !== 1) return {state: 'cancelled_before_preparation'};
    let directory;
    if (config.storage === 'directory') {
      const selected = await dialog.showOpenDialog(window, {title: 'Select empty local Firebird data directory', properties: ['openDirectory']});
      windowFor(event);
      if (selected.canceled || selected.filePaths.length !== 1) return {state: 'cancelled_before_preparation'};
      [directory] = selected.filePaths;
    }
    const result = await service.prepare({executable: chosen.filePaths[0], config, directory, owner: event.sender.id});
    windowFor(event);
    return result;
  });
  ipcMain.handle('firebird-docker:apply', (event, request) => {
    windowFor(event);
    if (!request || Object.keys(request).some(key => !['review_id', 'password', 'confirmed'].includes(key))) throw new Error('Invalid Docker apply request.');
    return service.apply({...request, owner: event.sender.id});
  });
  ipcMain.handle('firebird-docker:receipt', (event, id) => {windowFor(event); return service.receipt(id);});
}
