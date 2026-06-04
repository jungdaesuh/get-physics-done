#!/usr/bin/env node
/**
 * GPD bootstrap installer — installs or uninstalls Get Physics Done.
 *
 * Run with --help to see usage rendered from generated installer metadata.
 */

const fs = require("fs");
const crypto = require("crypto");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const readline = require("readline");
const {
  version: packageVersion,
  repository,
  gpdPythonVersion: rawPythonPackageVersion,
} = require("../package.json");

const pythonPackageVersion = typeof rawPythonPackageVersion === "string" ? rawPythonPackageVersion.trim() : "";
const GPD_HOME_ENV = "GPD_HOME";
const GPD_HOME_DIRNAME = ".gpd";
const GITHUB_MAIN_BRANCH = "main";
const BOOTSTRAP_TEST_PROBES_ENV = "GPD_BOOTSTRAP_TEST_PROBES";
const BOOTSTRAP_TEST_INSTALLER_METADATA_JSON_ENV = "GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_JSON";
const BOOTSTRAP_TEST_INSTALLER_METADATA_PATH_ENV = "GPD_BOOTSTRAP_TEST_INSTALLER_METADATA_PATH";
const BOOTSTRAP_DISABLE_NETWORK_PROBES_ENV = "GPD_BOOTSTRAP_DISABLE_NETWORK_PROBES";
const BOOTSTRAP_INSTALLER_METADATA_RELATIVE_PATH = path.join(
  "src",
  "gpd",
  "bootstrap",
  "installer_metadata.json"
);
const INSTALL_CANDIDATE_PROBE_TIMEOUT_MS = 5000;
const INSTALL_CANDIDATE_PROBE_REDIRECT_LIMIT = 5;
const MIN_SUPPORTED_NODE_MAJOR = 20;
const MIN_SUPPORTED_NODE_LABEL = `${MIN_SUPPORTED_NODE_MAJOR}+`;

const red = "\x1b[31m";
const green = "\x1b[32m";
const yellow = "\x1b[33m";
const cyan = "\x1b[36m";
const dim = "\x1b[2m";
const bold = "\x1b[1m";
const reset = "\x1b[0m";
const brandLogo = "\x1b[38;2;243;240;232m";
const brandTitle = "\x1b[38;2;247;244;237m";
const brandMeta = "\x1b[38;2;158;152;140m";
const brandAccent = "\x1b[38;2;216;199;163m";
const brandDisplayName = "Get Physics Done";
const brandOwner = "Physical Superintelligence PBC";
const brandOwnerShort = "PSI";
const brandCopyrightYear = 2026;
const productPositioning = "Open-source agentic AI system for physics research";

let bootstrapProbeOverridesCache = undefined;

let RUNTIME_CATALOG;
let ALL_RUNTIMES = [];
let RUNTIME_BY_NAME = {};

function runtimeRecord(runtime) {
  const record = RUNTIME_BY_NAME[runtime];
  if (!record) {
    throw new Error(`Unknown runtime: ${runtime}`);
  }
  return record;
}

function runtimeDisplayName(runtime) {
  return runtimeRecord(runtime).display_name;
}

function runtimeConfigDirName(runtime) {
  return runtimeRecord(runtime).config_dir_name;
}

function runtimeInstallFlag(runtime) {
  return runtimeRecord(runtime).install_flag;
}

function runtimeSelectionFlags(runtime) {
  return runtimeRecord(runtime).selection_flags || [];
}

function runtimeSelectionFlagList(runtime) {
  return [...new Set([runtimeInstallFlag(runtime), ...runtimeSelectionFlags(runtime)])];
}

function runtimeSelectionAliases(runtime) {
  return runtimeRecord(runtime).selection_aliases || [];
}

function runtimeCommandPrefix(runtime) {
  const record = runtimeRecord(runtime);
  return record.public_command_surface_prefix || record.command_prefix || "";
}

function runtimeSurfaceCommand(runtime, commandName) {
  return `${runtimeCommandPrefix(runtime)}${commandName}`;
}

function runtimeLaunchCommand(runtime) {
  return runtimeRecord(runtime).launch_command;
}

function runtimeInstallerHelpExampleScope(runtime) {
  return runtimeRecord(runtime).installer_help_example_scope || null;
}

const RUNTIME_ID_RE = /^[a-z0-9][a-z0-9-]*$/;
const RUNTIME_FLAG_RE = /^--[a-z0-9][a-z0-9-]*$/;
const RUNTIME_ENV_VAR_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const BOOTSTRAP_PACKAGE_NAME_RE = /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/;

function requireJsonObject(payload, label) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return payload;
}

function requireJsonArray(payload, label) {
  if (!Array.isArray(payload)) {
    throw new Error(`${label} must be a JSON array`);
  }
  return payload;
}

function requireStrictString(value, label) {
  if (typeof value !== "string" || !value || value.trim() !== value) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function requireStrictPatternString(value, label, pattern, description) {
  const normalized = requireStrictString(value, label);
  if (!pattern.test(normalized)) {
    throw new Error(`${label} must be ${description}`);
  }
  return normalized;
}

function requireRuntimeEnvVarName(value, label) {
  return requireStrictPatternString(value, label, RUNTIME_ENV_VAR_RE, "an environment variable name");
}

function requireRelativeCatalogPath(value, label, { allowSlash = true } = {}) {
  const rawValue = requireStrictString(value, label);
  const normalized = rawValue.replace(/\\/g, "/");
  const parts = normalized.split("/").filter((part) => part.length > 0);
  if (
    normalized.startsWith("/") ||
    normalized.startsWith("~") ||
    /^[A-Za-z]:/.test(normalized) ||
    parts.includes("..") ||
    parts.includes(".") ||
    (!allowSlash && parts.length !== 1)
  ) {
    throw new Error(`${label} must be a safe ${allowSlash ? "relative path" : "relative path segment"} without traversal`);
  }
  return rawValue;
}

function requireRuntimeFlagList(value, label, options = {}) {
  const items = requireStrictStringList(value, label, options);
  for (const [index, item] of items.entries()) {
    requireStrictPatternString(item, `${label}[${index}]`, RUNTIME_FLAG_RE, "a --kebab-case flag");
  }
  return items;
}

function requireStrictInteger(value, label) {
  if (!Number.isInteger(value)) {
    throw new Error(`${label} must be an integer`);
  }
  return value;
}

function requireNonNegativeInteger(value, label) {
  const integer = requireStrictInteger(value, label);
  if (integer < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return integer;
}

function requireStrictIntegerList(value, label, { allowEmpty = false } = {}) {
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be a list of integers`);
  }
  if (value.length === 0 && !allowEmpty) {
    throw new Error(`${label} must contain at least one integer`);
  }

  const seen = new Set();
  const items = [];
  for (const [index, item] of value.entries()) {
    const integer = requireStrictInteger(item, `${label}[${index}]`);
    if (seen.has(integer)) {
      throw new Error(`${label} must not contain duplicate values`);
    }
    seen.add(integer);
    items.push(integer);
  }
  return items;
}

function requireKnownKeys(payload, allowedKeys, label) {
  const unknownKeys = Object.keys(payload).filter((key) => !allowedKeys.has(key));
  if (unknownKeys.length > 0) {
    throw new Error(`${label} contains unknown key(s): ${unknownKeys.join(", ")}`);
  }
}

function requirePresentKeys(payload, requiredKeys, label) {
  const missingKeys = [...requiredKeys].filter((key) => !Object.prototype.hasOwnProperty.call(payload, key));
  if (missingKeys.length > 0) {
    throw new Error(`${label} is missing required key(s): ${missingKeys.join(", ")}`);
  }
}

function requireStrictStringList(value, label, { allowEmpty = false } = {}) {
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be a list of strings`);
  }
  if (value.length === 0 && !allowEmpty) {
    throw new Error(`${label} must contain at least one string`);
  }

  const seen = new Set();
  const items = [];
  for (const [index, item] of value.entries()) {
    const normalized = requireStrictString(item, `${label}[${index}]`);
    if (seen.has(normalized)) {
      throw new Error(`${label} must not contain duplicate values`);
    }
    seen.add(normalized);
    items.push(normalized);
  }
  return items;
}

function packageRootDir() {
  return path.resolve(__dirname, "..");
}

function parseJsonPayload(text, label) {
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`${label} must be valid JSON: ${err.message}`);
  }
}

function readJsonFile(filePath, label) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, "utf-8");
  } catch (err) {
    throw new Error(`Cannot load ${label} at ${filePath}: ${err.message}`);
  }
  return parseJsonPayload(raw, label);
}

function defaultInstallerMetadataPath() {
  return path.join(packageRootDir(), BOOTSTRAP_INSTALLER_METADATA_RELATIVE_PATH);
}

function loadBootstrapInstallerMetadataPayload() {
  const inlineMetadata = process.env[BOOTSTRAP_TEST_INSTALLER_METADATA_JSON_ENV];
  if (inlineMetadata) {
    return parseJsonPayload(inlineMetadata, BOOTSTRAP_TEST_INSTALLER_METADATA_JSON_ENV);
  }

  const overridePath = process.env[BOOTSTRAP_TEST_INSTALLER_METADATA_PATH_ENV];
  if (overridePath) {
    return readJsonFile(path.resolve(overridePath), BOOTSTRAP_TEST_INSTALLER_METADATA_PATH_ENV);
  }

  return readJsonFile(defaultInstallerMetadataPath(), "bootstrap installer metadata");
}

function normalizeSha256Value(value, label) {
  const rawValue = requireStrictString(value, label).toLowerCase();
  const hash = rawValue.startsWith("sha256:") ? rawValue.slice("sha256:".length) : rawValue;
  if (!/^[a-f0-9]{64}$/.test(hash)) {
    throw new Error(`${label} must be a SHA-256 hex digest`);
  }
  return hash;
}

function validateSourceHashes(sourceHashes, options = {}) {
  const payload = requireJsonObject(sourceHashes, "bootstrap installer metadata.source_hashes");
  const sourcePaths = Object.keys(payload);
  if (sourcePaths.length === 0) {
    throw new Error("bootstrap installer metadata.source_hashes must not be empty");
  }

  const validated = {};
  for (const sourcePath of sourcePaths.sort()) {
    const normalizedSourcePath = requireRelativeCatalogPath(
      sourcePath,
      `bootstrap installer metadata.source_hashes.${sourcePath}`,
      { allowSlash: true }
    ).replace(/\\/g, "/");
    const expectedHash = normalizeSha256Value(payload[sourcePath], `bootstrap installer metadata.source_hashes.${sourcePath}`);
    if (!options.skipSourceHashCheck) {
      const absoluteSourcePath = path.join(packageRootDir(), normalizedSourcePath);
      let sourceBytes;
      try {
        sourceBytes = fs.readFileSync(absoluteSourcePath);
      } catch (err) {
        throw new Error(`Cannot read metadata source ${normalizedSourcePath}: ${err.message}`);
      }
      const actualHash = crypto.createHash("sha256").update(sourceBytes).digest("hex");
      if (actualHash !== expectedHash) {
        throw new Error(
          `bootstrap installer metadata source hash mismatch for ${normalizedSourcePath}: `
          + `expected ${expectedHash}, got ${actualHash}`
        );
      }
    }
    validated[normalizedSourcePath] = expectedHash;
  }
  return validated;
}

function validatePythonVersionMetadata(version, label) {
  const payload = requireJsonObject(version, label);
  const keys = ["major", "minor"];
  requireKnownKeys(payload, new Set(keys), label);
  requirePresentKeys(payload, keys, label);
  const major = requireNonNegativeInteger(payload.major, `${label}.major`);
  const minor = requireNonNegativeInteger(payload.minor, `${label}.minor`);
  return { major, minor };
}

function validatePythonCompatibilityMetadata(pythonCompatibility) {
  const label = "bootstrap installer metadata.python_compatibility";
  const payload = requireJsonObject(pythonCompatibility, label);
  const keys = [
    "schema_version",
    "minimum_supported_python",
    "minimum_supported_python_label",
    "preferred_versioned_python_minors",
    "recommended_python_version",
  ];
  requireKnownKeys(payload, new Set(keys), label);
  requirePresentKeys(payload, keys, label);
  if (payload.schema_version !== 1) {
    throw new Error(`Unsupported bootstrap Python compatibility schema_version: ${JSON.stringify(payload.schema_version)}`);
  }

  const minimumSupportedPython = validatePythonVersionMetadata(
    payload.minimum_supported_python,
    `${label}.minimum_supported_python`
  );
  const minimumSupportedPythonLabel = requireStrictString(
    payload.minimum_supported_python_label,
    `${label}.minimum_supported_python_label`
  );
  const expectedMinimumLabel = `${minimumSupportedPython.major}.${minimumSupportedPython.minor}`;
  if (minimumSupportedPythonLabel !== expectedMinimumLabel) {
    throw new Error(
      `${label}.minimum_supported_python_label must match minimum_supported_python (${expectedMinimumLabel})`
    );
  }

  const preferredVersionedPythonMinors = requireStrictIntegerList(
    payload.preferred_versioned_python_minors,
    `${label}.preferred_versioned_python_minors`
  );
  for (const [index, minor] of preferredVersionedPythonMinors.entries()) {
    if (minor < minimumSupportedPython.minor) {
      throw new Error(
        `${label}.preferred_versioned_python_minors[${index}] must be >= minimum_supported_python.minor`
      );
    }
  }
  if (!preferredVersionedPythonMinors.includes(minimumSupportedPython.minor)) {
    throw new Error(`${label}.preferred_versioned_python_minors must include minimum_supported_python.minor`);
  }

  const recommendedPythonVersion = validatePythonVersionMetadata(
    payload.recommended_python_version,
    `${label}.recommended_python_version`
  );
  if (recommendedPythonVersion.major !== minimumSupportedPython.major) {
    throw new Error(`${label}.recommended_python_version.major must match minimum_supported_python.major`);
  }
  if (recommendedPythonVersion.minor !== preferredVersionedPythonMinors[0]) {
    throw new Error(`${label}.recommended_python_version.minor must match the first preferred_versioned_python_minors entry`);
  }

  return {
    schemaVersion: 1,
    minimumSupportedPython,
    minimumSupportedPythonLabel,
    preferredVersionedPythonMinors,
    recommendedPythonVersion,
  };
}

function validateRuntimeCatalogGlobalConfigMetadata(globalConfig, label) {
  const payload = requireJsonObject(globalConfig, label);
  const strategy = requireStrictString(payload.strategy, `${label}.strategy`);
  if (strategy !== "env_or_home" && strategy !== "xdg_app") {
    throw new Error(`${label}.strategy must be one of: env_or_home, xdg_app`);
  }

  const requiredKeys = strategy === "env_or_home"
    ? ["strategy", "env_var", "home_subpath"]
    : ["strategy", "env_dir_var", "env_file_var", "xdg_subdir", "home_subpath"];
  const requiredKeySet = new Set(requiredKeys);
  requireKnownKeys(payload, requiredKeySet, label);
  requirePresentKeys(payload, requiredKeys, label);

  if (strategy === "env_or_home") {
    return {
      strategy,
      env_var: requireRuntimeEnvVarName(payload.env_var, `${label}.env_var`),
      home_subpath: requireRelativeCatalogPath(payload.home_subpath, `${label}.home_subpath`),
    };
  }

  return {
    strategy,
    env_dir_var: requireRuntimeEnvVarName(payload.env_dir_var, `${label}.env_dir_var`),
    env_file_var: requireRuntimeEnvVarName(payload.env_file_var, `${label}.env_file_var`),
    xdg_subdir: requireRelativeCatalogPath(payload.xdg_subdir, `${label}.xdg_subdir`),
    home_subpath: requireRelativeCatalogPath(payload.home_subpath, `${label}.home_subpath`),
  };
}

function parseCommandPrefix(value, label) {
  const prefix = requireStrictString(value, label);
  if (!/^[/$][A-Za-z0-9][A-Za-z0-9._-]*(?::|-)$/.test(prefix)) {
    throw new Error(`${label} must be a slash or dollar command prefix ending in ':' or '-'`);
  }
  return prefix;
}

function parsePublicCommandSurfacePrefix(value, label, commandPrefix) {
  const prefix = value === undefined || value === null ? commandPrefix : requireStrictString(value, label);
  if (!/^[/$][A-Za-z0-9][A-Za-z0-9._-]*(?::|-)$/.test(prefix)) {
    throw new Error(`${label} must be a slash or dollar command prefix ending in ':' or '-'`);
  }
  return prefix;
}

function parseInstallHelpExampleScope(value, label) {
  if (value === undefined || value === null) {
    return null;
  }
  const scope = requireStrictString(value, label);
  if (scope !== "global" && scope !== "local") {
    throw new Error(`${label} must be one of: global, local`);
  }
  return scope;
}

function validateRuntimeMetadataEntry(entry, index) {
  const label = `bootstrap installer metadata.runtimes[${index}]`;
  const payload = requireJsonObject(entry, label);
  const requiredKeys = [
    "runtime_name",
    "display_name",
    "priority",
    "config_dir_name",
    "install_flag",
    "launch_command",
    "selection_flags",
    "selection_aliases",
    "command_prefix",
    "public_command_surface_prefix",
    "installer_help_example_scope",
    "global_config",
  ];
  requireKnownKeys(payload, new Set(requiredKeys), label);
  requirePresentKeys(payload, requiredKeys, label);
  const commandPrefix = parseCommandPrefix(payload.command_prefix, `${label}.command_prefix`);

  return {
    runtime_name: requireStrictPatternString(
      payload.runtime_name,
      `${label}.runtime_name`,
      RUNTIME_ID_RE,
      "a lowercase runtime id"
    ),
    display_name: requireStrictString(payload.display_name, `${label}.display_name`),
    priority: requireStrictInteger(payload.priority, `${label}.priority`),
    config_dir_name: requireRelativeCatalogPath(payload.config_dir_name, `${label}.config_dir_name`, {
      allowSlash: false,
    }),
    install_flag: requireStrictPatternString(
      payload.install_flag,
      `${label}.install_flag`,
      RUNTIME_FLAG_RE,
      "a --kebab-case flag"
    ),
    launch_command: requireStrictString(payload.launch_command, `${label}.launch_command`),
    selection_flags: requireRuntimeFlagList(payload.selection_flags, `${label}.selection_flags`),
    selection_aliases: requireStrictStringList(payload.selection_aliases, `${label}.selection_aliases`),
    command_prefix: commandPrefix,
    public_command_surface_prefix: parsePublicCommandSurfacePrefix(
      payload.public_command_surface_prefix,
      `${label}.public_command_surface_prefix`,
      commandPrefix
    ),
    installer_help_example_scope: parseInstallHelpExampleScope(
      payload.installer_help_example_scope,
      `${label}.installer_help_example_scope`
    ),
    global_config: validateRuntimeCatalogGlobalConfigMetadata(payload.global_config, `${label}.global_config`),
  };
}

function validateRuntimeMetadataHelpExampleScopes(entries) {
  const scopeOwners = new Map();
  for (const entry of entries) {
    if (!entry.installer_help_example_scope) {
      continue;
    }
    const existingOwner = scopeOwners.get(entry.installer_help_example_scope);
    if (existingOwner && existingOwner !== entry.runtime_name) {
      throw new Error(
        `bootstrap installer metadata.runtimes contains duplicate installer_help_example_scope ${JSON.stringify(entry.installer_help_example_scope)} for ${JSON.stringify(existingOwner)} and ${JSON.stringify(entry.runtime_name)}`
      );
    }
    scopeOwners.set(entry.installer_help_example_scope, entry.runtime_name);
  }
}

function validateRuntimeMetadataList(runtimes) {
  const payload = requireJsonArray(runtimes, "bootstrap installer metadata.runtimes");
  if (payload.length === 0) {
    throw new Error("bootstrap installer metadata.runtimes must not be empty");
  }
  const entries = payload.map((entry, index) => validateRuntimeMetadataEntry(entry, index));
  entries.sort((left, right) => {
    if (left.priority !== right.priority) {
      return left.priority - right.priority;
    }
    return left.runtime_name.localeCompare(right.runtime_name);
  });

  const runtimeNames = new Map();
  const installFlags = new Map();
  const selectionFlags = new Map();
  const selectionTokens = new Map();
  for (const entry of entries) {
    if (runtimeNames.has(entry.runtime_name)) {
      throw new Error(
        `bootstrap installer metadata.runtimes contains duplicate runtime_name ${JSON.stringify(entry.runtime_name)}`
      );
    }
    runtimeNames.set(entry.runtime_name, entry.runtime_name);

    const existingInstallFlagRuntime = installFlags.get(entry.install_flag);
    if (existingInstallFlagRuntime && existingInstallFlagRuntime !== entry.runtime_name) {
      throw new Error(
        `bootstrap installer metadata.runtimes contains duplicate install_flag ${JSON.stringify(entry.install_flag)} for ${JSON.stringify(existingInstallFlagRuntime)} and ${JSON.stringify(entry.runtime_name)}`
      );
    }
    installFlags.set(entry.install_flag, entry.runtime_name);

    for (const flag of entry.selection_flags) {
      const existingRuntime = selectionFlags.get(flag);
      if (existingRuntime && existingRuntime !== entry.runtime_name) {
        throw new Error(
          `bootstrap installer metadata.runtimes contains duplicate selection flag ${JSON.stringify(flag)} for ${JSON.stringify(existingRuntime)} and ${JSON.stringify(entry.runtime_name)}`
        );
      }
      selectionFlags.set(flag, entry.runtime_name);
    }

    const tokens = new Set([
      entry.runtime_name,
      entry.display_name.toLowerCase(),
      entry.launch_command,
      ...entry.selection_aliases,
      ...entry.selection_flags.map((flag) => flag.replace(/^--/, "")),
      entry.install_flag.replace(/^--/, ""),
    ]);
    for (const token of tokens) {
      const normalizedToken = token.toLowerCase();
      const existingRuntime = selectionTokens.get(normalizedToken);
      if (existingRuntime && existingRuntime !== entry.runtime_name) {
        throw new Error(
          `bootstrap installer metadata.runtimes contains duplicate runtime selection token ${JSON.stringify(token)} for ${JSON.stringify(existingRuntime)} and ${JSON.stringify(entry.runtime_name)}`
        );
      }
      selectionTokens.set(normalizedToken, entry.runtime_name);
    }
  }

  validateRuntimeMetadataHelpExampleScopes(entries);

  return entries;
}

function validateSharedInstallMetadata(installMetadata) {
  const label = "bootstrap installer metadata.shared_install_metadata";
  const keys = [
    "schemaVersion",
    "bootstrapPackageName",
    "bootstrapCommand",
    "installRootDirName",
    "manifestName",
    "patchesDirName",
  ];
  const payload = requireJsonObject(installMetadata, label);
  requireKnownKeys(payload, new Set(keys), label);
  requirePresentKeys(payload, keys, label);
  if (payload.schemaVersion !== 1) {
    throw new Error(
      `Unsupported bootstrap shared install metadata schemaVersion: ${JSON.stringify(payload.schemaVersion)}`
    );
  }

  const bootstrapPackageName = requireStrictPatternString(
    payload.bootstrapPackageName,
    `${label}.bootstrapPackageName`,
    BOOTSTRAP_PACKAGE_NAME_RE,
    "a lowercase npm package name"
  );
  const bootstrapCommand = requireStrictString(payload.bootstrapCommand, `${label}.bootstrapCommand`);
  const expectedBootstrapCommand = `npx -y ${bootstrapPackageName}`;
  if (bootstrapCommand !== expectedBootstrapCommand) {
    throw new Error(`${label}.bootstrapCommand must be ${JSON.stringify(expectedBootstrapCommand)}`);
  }

  return {
    schemaVersion: 1,
    bootstrapPackageName,
    bootstrapCommand,
    installRootDirName: requireRelativeCatalogPath(payload.installRootDirName, `${label}.installRootDirName`, {
      allowSlash: false,
    }),
    manifestName: requireRelativeCatalogPath(payload.manifestName, `${label}.manifestName`, {
      allowSlash: false,
    }),
    patchesDirName: requireRelativeCatalogPath(payload.patchesDirName, `${label}.patchesDirName`, {
      allowSlash: false,
    }),
  };
}

function validateSharedPublicSurfaceTextMetadata(publicSurfaceText) {
  const sharedPublicSurfaceTextLabel = "bootstrap installer metadata.shared_public_surface_text";
  const sharedPublicSurfaceTextKeys = [
    "schemaVersion",
    "beginnerHubUrl",
    "beginnerPreflightRequirements",
    "beginnerCaveats",
    "beginnerStartupLadder",
    "localCliBridgeCommands",
    "localCliBridge",
    "resumeAuthority",
    "recoveryLadder",
    "settingsCommandSentence",
    "settingsRecommendationSentence",
  ];
  const payload = requireJsonObject(
    publicSurfaceText,
    sharedPublicSurfaceTextLabel
  );
  requireKnownKeys(payload, new Set(sharedPublicSurfaceTextKeys), sharedPublicSurfaceTextLabel);
  requirePresentKeys(payload, sharedPublicSurfaceTextKeys, sharedPublicSurfaceTextLabel);
  if (payload.schemaVersion !== 1) {
    throw new Error(
      `Unsupported bootstrap public surface text schemaVersion: ${JSON.stringify(payload.schemaVersion)}`
    );
  }

  const localCliBridgeLabel = "bootstrap installer metadata.shared_public_surface_text.localCliBridge";
  const localCliBridgeKeys = [
    "doctorCommand",
    "helpCommand",
    "permissionsStatusCommand",
    "permissionsSyncCommand",
    "resumeCommand",
    "resumeRecentCommand",
    "observeExecutionCommand",
    "costCommand",
    "presetsListCommand",
    "planPreflightCommand",
    "integrationsStatusWolframCommand",
    "terminalPhrase",
    "purposePhrase",
    "installLocalExample",
    "doctorLocalCommand",
    "doctorGlobalCommand",
    "validateCommandContextCommand",
    "unattendedReadinessCommand",
  ];
  const localCliBridge = requireJsonObject(
    payload.localCliBridge,
    localCliBridgeLabel
  );
  requireKnownKeys(localCliBridge, new Set(localCliBridgeKeys), localCliBridgeLabel);
  requirePresentKeys(localCliBridge, localCliBridgeKeys, localCliBridgeLabel);

  const resumeAuthorityLabel = "bootstrap installer metadata.shared_public_surface_text.resumeAuthority";
  const resumeAuthorityKeys = ["durableAuthorityPhrase", "publicVocabularyIntro", "publicFields"];
  const resumeAuthority = requireJsonObject(
    payload.resumeAuthority,
    resumeAuthorityLabel
  );
  requireKnownKeys(resumeAuthority, new Set(resumeAuthorityKeys), resumeAuthorityLabel);
  requirePresentKeys(resumeAuthority, resumeAuthorityKeys, resumeAuthorityLabel);

  const recoveryLadderLabel = "bootstrap installer metadata.shared_public_surface_text.recoveryLadder";
  const recoveryLadderKeys = [
    "title",
    "localSnapshotCommand",
    "localSnapshotPhrase",
    "crossWorkspaceCommand",
    "crossWorkspacePhrase",
    "resumePhrase",
    "nextPhrase",
    "pausePhrase",
  ];
  const recoveryLadder = requireJsonObject(
    payload.recoveryLadder,
    recoveryLadderLabel
  );
  requireKnownKeys(recoveryLadder, new Set(recoveryLadderKeys), recoveryLadderLabel);
  requirePresentKeys(recoveryLadder, recoveryLadderKeys, recoveryLadderLabel);

  return {
    schemaVersion: 1,
    beginnerHubUrl: requireStrictString(
      payload.beginnerHubUrl,
      "bootstrap installer metadata.shared_public_surface_text.beginnerHubUrl"
    ),
    beginnerPreflightRequirements: requireStrictStringList(
      payload.beginnerPreflightRequirements,
      "bootstrap installer metadata.shared_public_surface_text.beginnerPreflightRequirements"
    ),
    beginnerCaveats: requireStrictStringList(
      payload.beginnerCaveats,
      "bootstrap installer metadata.shared_public_surface_text.beginnerCaveats"
    ),
    beginnerStartupLadder: requireStrictStringList(
      payload.beginnerStartupLadder,
      "bootstrap installer metadata.shared_public_surface_text.beginnerStartupLadder"
    ),
    localCliBridgeCommands: requireStrictStringList(
      payload.localCliBridgeCommands,
      "bootstrap installer metadata.shared_public_surface_text.localCliBridgeCommands"
    ),
    localCliBridge: {
      doctorCommand: requireStrictString(localCliBridge.doctorCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.doctorCommand"),
      helpCommand: requireStrictString(localCliBridge.helpCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.helpCommand"),
      permissionsStatusCommand: requireStrictString(localCliBridge.permissionsStatusCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.permissionsStatusCommand"),
      permissionsSyncCommand: requireStrictString(localCliBridge.permissionsSyncCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.permissionsSyncCommand"),
      resumeCommand: requireStrictString(localCliBridge.resumeCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.resumeCommand"),
      resumeRecentCommand: requireStrictString(localCliBridge.resumeRecentCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.resumeRecentCommand"),
      observeExecutionCommand: requireStrictString(localCliBridge.observeExecutionCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.observeExecutionCommand"),
      costCommand: requireStrictString(localCliBridge.costCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.costCommand"),
      presetsListCommand: requireStrictString(localCliBridge.presetsListCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.presetsListCommand"),
      planPreflightCommand: requireStrictString(localCliBridge.planPreflightCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.planPreflightCommand"),
      integrationsStatusWolframCommand: requireStrictString(localCliBridge.integrationsStatusWolframCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.integrationsStatusWolframCommand"),
      terminalPhrase: requireStrictString(localCliBridge.terminalPhrase, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.terminalPhrase"),
      purposePhrase: requireStrictString(localCliBridge.purposePhrase, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.purposePhrase"),
      installLocalExample: requireStrictString(localCliBridge.installLocalExample, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.installLocalExample"),
      doctorLocalCommand: requireStrictString(localCliBridge.doctorLocalCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.doctorLocalCommand"),
      doctorGlobalCommand: requireStrictString(localCliBridge.doctorGlobalCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.doctorGlobalCommand"),
      validateCommandContextCommand: requireStrictString(localCliBridge.validateCommandContextCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.validateCommandContextCommand"),
      unattendedReadinessCommand: requireStrictString(localCliBridge.unattendedReadinessCommand, "bootstrap installer metadata.shared_public_surface_text.localCliBridge.unattendedReadinessCommand"),
    },
    resumeAuthority: {
      durableAuthorityPhrase: requireStrictString(
        resumeAuthority.durableAuthorityPhrase,
        "bootstrap installer metadata.shared_public_surface_text.resumeAuthority.durableAuthorityPhrase"
      ),
      publicVocabularyIntro: requireStrictString(
        resumeAuthority.publicVocabularyIntro,
        "bootstrap installer metadata.shared_public_surface_text.resumeAuthority.publicVocabularyIntro"
      ),
      publicFields: requireStrictStringList(
        resumeAuthority.publicFields,
        "bootstrap installer metadata.shared_public_surface_text.resumeAuthority.publicFields"
      ),
    },
    recoveryLadder: {
      title: requireStrictString(recoveryLadder.title, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.title"),
      localSnapshotCommand: requireStrictString(recoveryLadder.localSnapshotCommand, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.localSnapshotCommand"),
      localSnapshotPhrase: requireStrictString(recoveryLadder.localSnapshotPhrase, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.localSnapshotPhrase"),
      crossWorkspaceCommand: requireStrictString(recoveryLadder.crossWorkspaceCommand, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.crossWorkspaceCommand"),
      crossWorkspacePhrase: requireStrictString(recoveryLadder.crossWorkspacePhrase, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.crossWorkspacePhrase"),
      resumePhrase: requireStrictString(recoveryLadder.resumePhrase, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.resumePhrase"),
      nextPhrase: requireStrictString(recoveryLadder.nextPhrase, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.nextPhrase"),
      pausePhrase: requireStrictString(recoveryLadder.pausePhrase, "bootstrap installer metadata.shared_public_surface_text.recoveryLadder.pausePhrase"),
    },
    settingsCommandSentence: requireStrictString(
      payload.settingsCommandSentence,
      "bootstrap installer metadata.shared_public_surface_text.settingsCommandSentence"
    ),
    settingsRecommendationSentence: requireStrictString(
      payload.settingsRecommendationSentence,
      "bootstrap installer metadata.shared_public_surface_text.settingsRecommendationSentence"
    ),
  };
}

function validateBootstrapInstallerMetadata(metadataPayload, options = {}) {
  const payload = requireJsonObject(metadataPayload, "bootstrap installer metadata");
  requireKnownKeys(
    payload,
    new Set([
      "schema_version",
      "source_hashes",
      "python_compatibility",
      "runtimes",
      "shared_install_metadata",
      "shared_public_surface_text",
    ]),
    "bootstrap installer metadata"
  );
  requirePresentKeys(
    payload,
    [
      "schema_version",
      "source_hashes",
      "python_compatibility",
      "runtimes",
      "shared_install_metadata",
      "shared_public_surface_text",
    ],
    "bootstrap installer metadata"
  );
  if (payload.schema_version !== 1) {
    throw new Error(`Unsupported bootstrap installer metadata schema_version: ${JSON.stringify(payload.schema_version)}`);
  }

  return {
    schemaVersion: 1,
    sourceHashes: validateSourceHashes(payload.source_hashes, options),
    pythonCompatibility: validatePythonCompatibilityMetadata(payload.python_compatibility),
    runtimes: validateRuntimeMetadataList(payload.runtimes),
    sharedInstallMetadata: validateSharedInstallMetadata(payload.shared_install_metadata),
    sharedPublicSurfaceText: validateSharedPublicSurfaceTextMetadata(payload.shared_public_surface_text),
  };
}

function loadBootstrapInstallerMetadata() {
  return validateBootstrapInstallerMetadata(loadBootstrapInstallerMetadataPayload());
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

const BOOTSTRAP_INSTALLER_METADATA = loadBootstrapInstallerMetadata();
const PYTHON_COMPATIBILITY = BOOTSTRAP_INSTALLER_METADATA.pythonCompatibility;
const MIN_SUPPORTED_PYTHON_MAJOR = PYTHON_COMPATIBILITY.minimumSupportedPython.major;
const MIN_SUPPORTED_PYTHON_MINOR = PYTHON_COMPATIBILITY.minimumSupportedPython.minor;
const MIN_SUPPORTED_PYTHON_LABEL = `${PYTHON_COMPATIBILITY.minimumSupportedPythonLabel}+`;
const PREFERRED_VERSIONED_PYTHON_MINORS = PYTHON_COMPATIBILITY.preferredVersionedPythonMinors;
RUNTIME_CATALOG = BOOTSTRAP_INSTALLER_METADATA.runtimes;
ALL_RUNTIMES = RUNTIME_CATALOG.map((runtime) => runtime.runtime_name);
RUNTIME_BY_NAME = Object.fromEntries(RUNTIME_CATALOG.map((runtime) => [runtime.runtime_name, runtime]));
const SHARED_INSTALL_METADATA = BOOTSTRAP_INSTALLER_METADATA.sharedInstallMetadata;
const SHARED_PUBLIC_SURFACE_TEXT = BOOTSTRAP_INSTALLER_METADATA.sharedPublicSurfaceText;

function loadSharedInstallMetadata() {
  return cloneJson(SHARED_INSTALL_METADATA);
}

function loadSharedPublicSurfaceText() {
  return cloneJson(SHARED_PUBLIC_SURFACE_TEXT);
}

function sharedBootstrapCommand() {
  return SHARED_INSTALL_METADATA.bootstrapCommand;
}

function beginnerStartupLadderText() {
  return `\`${SHARED_PUBLIC_SURFACE_TEXT.beginnerStartupLadder.join(" -> ")}\``;
}

function settingsCommandFollowUp(runtime = null) {
  const sentence = SHARED_PUBLIC_SURFACE_TEXT.settingsCommandSentence;
  if (!runtime) {
    return sentence;
  }
  return `${sentence} For ${runtimeDisplayName(runtime)}, that command is \`${runtimeSurfaceCommand(runtime, "settings")}\`.`;
}

function sharedLocalCliHelpCommand() {
  return SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.helpCommand;
}

function sharedDoctorCommand() {
  return SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.doctorCommand;
}

function sharedUnattendedReadinessCommand() {
  return SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.unattendedReadinessCommand;
}

function sharedPermissionsStatusCommand() {
  return SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.permissionsStatusCommand;
}

function sharedPermissionsSyncCommand() {
  return SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.permissionsSyncCommand;
}

function joinBacktickedCommands(commands) {
  const rendered = commands.map((command) => `\`${command}\``);
  if (rendered.length <= 1) {
    return rendered.join("");
  }
  if (rendered.length === 2) {
    return `${rendered[0]} and ${rendered[1]}`;
  }
  return `${rendered.slice(0, -1).join(", ")}, and ${rendered.at(-1)}`;
}

function localCliBridgeNote() {
  return (
    `Use ${joinBacktickedCommands(SHARED_PUBLIC_SURFACE_TEXT.localCliBridgeCommands)} `
    + `${SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.terminalPhrase} when you want `
    + `${SHARED_PUBLIC_SURFACE_TEXT.localCliBridge.purposePhrase}.`
  );
}

function localCliDiagnosticsFollowUpLine() {
  return (
    `Use \`${sharedLocalCliHelpCommand()}\` for local install, readiness, validation, permissions, observability, and diagnostics. `
    + `Local CLI bridge: ${localCliBridgeNote()}`
  );
}

function log(msg) {
  console.log(` ${cyan}i${reset} ${msg}`);
}

function errLog(msg) {
  console.error(` ${cyan}i${reset} ${msg}`);
}

function success(msg) {
  console.log(` ${green}✓${reset} ${msg}`);
}

function warn(msg) {
  console.log(` ${yellow}⚠${reset} ${msg}`);
}

function error(msg) {
  console.error(` ${red}✗${reset} ${msg}`);
}

function nodeMajorVersion(versionText) {
  const match = String(versionText || "").trim().match(/^v?(\d+)(?:\.|$)/);
  return match ? parseInt(match[1], 10) : null;
}

function ensureSupportedNodeVersion(versionText = process.versions.node) {
  const major = nodeMajorVersion(versionText);
  if (major === null || major < MIN_SUPPORTED_NODE_MAJOR) {
    const current = versionText ? ` Current Node.js: ${versionText}.` : "";
    throw new Error(
      `Node.js ${MIN_SUPPORTED_NODE_LABEL} is required to run the GPD bootstrap installer.${current} `
      + "Upgrade Node.js, then rerun the installer."
    );
  }
}

function isWindows() {
  return process.platform === "win32";
}

function pythonVersionInfo(python) {
  const result = spawnSync(python, ["--version"], { encoding: "utf-8" });
  if (result.status !== 0) {
    return null;
  }

  const versionText = (result.stdout || result.stderr).trim();
  const match = versionText.match(/(\d+)\.(\d+)/);
  if (!match) {
    return null;
  }

  return {
    command: python,
    text: versionText,
    major: parseInt(match[1], 10),
    minor: parseInt(match[2], 10),
  };
}

function isSupportedPython(info) {
  if (!info) {
    return false;
  }
  return info.major > MIN_SUPPORTED_PYTHON_MAJOR
    || (info.major === MIN_SUPPORTED_PYTHON_MAJOR && info.minor >= MIN_SUPPORTED_PYTHON_MINOR);
}

function preferredPythonCommands() {
  return [
    ...PREFERRED_VERSIONED_PYTHON_MINORS.map((minor) => `python${MIN_SUPPORTED_PYTHON_MAJOR}.${minor}`),
    `python${MIN_SUPPORTED_PYTHON_MAJOR}`,
    "python",
  ];
}

function checkPython() {
  // Prefer explicit, known-good minor versions before generic aliases so a
  // too-new `python3` does not mask an installed compatible interpreter.
  for (const cmd of preferredPythonCommands()) {
    const info = pythonVersionInfo(cmd);
    if (isSupportedPython(info)) {
      return info;
    }
  }
  return null;
}

function hasVenvSupport(python) {
  const result = spawnSync(python, ["-m", "venv", "--help"], { stdio: "ignore" });
  return result.status === 0;
}

function checkPip(python) {
  const result = spawnSync(python, ["-m", "pip", "--version"], { encoding: "utf-8" });
  if (result.status !== 0) {
    return null;
  }
  return (result.stdout || result.stderr).trim();
}

function normalizedRepositoryUrl(repositoryField) {
  const raw = typeof repositoryField === "string"
    ? repositoryField
    : repositoryField && typeof repositoryField.url === "string"
      ? repositoryField.url
      : "";
  if (!raw) {
    return null;
  }

  let normalized = raw.trim();
  if (normalized.startsWith("git+")) {
    normalized = normalized.slice(4);
  }
  if (normalized.startsWith("git@github.com:")) {
    normalized = `https://github.com/${normalized.slice("git@github.com:".length)}`;
  }
  return normalized.replace(/\/+$/, "") || null;
}

function repositoryBaseUrl(repositoryField) {
  const normalized = normalizedRepositoryUrl(repositoryField);
  if (!normalized) {
    return null;
  }
  return normalized.replace(/\.git$/i, "") || null;
}

function repositoryGitUrl(repositoryField) {
  let normalized = normalizedRepositoryUrl(repositoryField);
  if (!normalized) {
    return null;
  }
  if (!normalized.endsWith(".git")) {
    normalized = `${normalized}.git`;
  }
  return normalized || null;
}

function releaseInstallCandidates(version) {
  const repoBaseUrl = repositoryBaseUrl(repository);
  const repoGitUrl = repositoryGitUrl(repository);
  const candidates = [];

  if (repoBaseUrl) {
    candidates.push(
      {
        label: `GitHub source archive for v${version}`,
        spec: `${repoBaseUrl}/archive/refs/tags/v${version}.tar.gz`,
        probe: {
          kind: "http",
        },
      }
    );
  }

  // Release fallback candidates stay pinned to the selected version tag.
  // PyPI is tried before these candidates.
  if (repoGitUrl) {
    candidates.push(
      {
        label: `HTTPS git checkout for v${version}`,
        spec: `git+${repoGitUrl}@v${version}`,
        probe: {
          kind: "git",
          repoUrl: repoGitUrl,
          ref: `v${version}`,
          refNamespace: "tags",
        },
      }
    );
  }

  return candidates;
}

function mainBranchInstallCandidates() {
  const repoBaseUrl = repositoryBaseUrl(repository);
  const repoGitUrl = repositoryGitUrl(repository);
  const candidates = [];

  if (repoBaseUrl) {
    candidates.push({
      label: `current ${GITHUB_MAIN_BRANCH} branch source archive`,
      spec: `${repoBaseUrl}/archive/refs/heads/${GITHUB_MAIN_BRANCH}.tar.gz`,
      noCache: true,
      probe: {
        kind: "http",
      },
    });
  }

  if (repoGitUrl) {
    candidates.push({
      label: `HTTPS git checkout of ${GITHUB_MAIN_BRANCH}`,
      spec: `git+${repoGitUrl}@${GITHUB_MAIN_BRANCH}`,
      noCache: true,
      probe: {
        kind: "git",
        repoUrl: repoGitUrl,
        ref: GITHUB_MAIN_BRANCH,
        refNamespace: "heads",
      },
    });
  }

  return candidates;
}

function bootstrapProbeOverrides() {
  if (bootstrapProbeOverridesCache !== undefined) {
    return bootstrapProbeOverridesCache;
  }

  const raw = process.env[BOOTSTRAP_TEST_PROBES_ENV];
  if (!raw) {
    bootstrapProbeOverridesCache = {};
    return bootstrapProbeOverridesCache;
  }

  try {
    const parsed = JSON.parse(raw);
    bootstrapProbeOverridesCache = parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    warn(`Ignoring invalid ${BOOTSTRAP_TEST_PROBES_ENV} JSON.`);
    bootstrapProbeOverridesCache = {};
  }

  return bootstrapProbeOverridesCache;
}

function normalizeProbeStatus(value) {
  if (value === true) {
    return { status: "available", reason: "test override" };
  }
  if (value === false) {
    return { status: "unavailable", reason: "test override" };
  }
  if (value === null || value === "unknown") {
    return { status: "unknown", reason: "test override" };
  }
  if (value === "available" || value === "unavailable") {
    return { status: value, reason: "test override" };
  }
  if (typeof value === "object" && value !== null) {
    const status = value.status || value.availability;
    if (status === "available" || status === "unavailable" || status === "unknown") {
      return { status, reason: value.reason || "test override" };
    }
  }
  return null;
}

function probeOverrideForCandidate(candidate) {
  const overrides = bootstrapProbeOverrides();
  return normalizeProbeStatus(overrides[candidate.spec]);
}

function formatProbeReason(reason) {
  if (!reason) {
    return "";
  }
  const trimmedReason = reason.trim();
  if (!trimmedReason) {
    return "";
  }
  const normalizedReason = trimmedReason.replace(/[.?!]+$/u, "") || trimmedReason;
  return `: ${normalizedReason}`;
}

function probeHttpCandidate(urlString, redirectCount = 0) {
  return new Promise((resolve) => {
    let targetUrl;
    try {
      targetUrl = new URL(urlString);
    } catch (err) {
      resolve({ status: "unknown", reason: err.message });
      return;
    }

    const transport = targetUrl.protocol === "http:" ? http : https;
    const request = transport.request(
      targetUrl,
      {
        method: "HEAD",
        headers: {
          "User-Agent": `${SHARED_INSTALL_METADATA.bootstrapPackageName}-bootstrap/${packageVersion}`,
        },
      },
      (response) => {
        const { statusCode = 0, headers } = response;
        response.resume();

        if ([301, 302, 303, 307, 308].includes(statusCode) && headers.location) {
          if (redirectCount >= INSTALL_CANDIDATE_PROBE_REDIRECT_LIMIT) {
            resolve({ status: "unknown", reason: "too many redirects" });
            return;
          }
          const nextUrl = new URL(headers.location, targetUrl).toString();
          resolve(probeHttpCandidate(nextUrl, redirectCount + 1));
          return;
        }

        if (statusCode >= 200 && statusCode < 400) {
          resolve({ status: "available", reason: `HTTP ${statusCode}` });
          return;
        }
        if (statusCode >= 400 && statusCode < 500) {
          resolve({ status: "unavailable", reason: `HTTP ${statusCode}` });
          return;
        }
        resolve({ status: "unknown", reason: `HTTP ${statusCode}` });
      }
    );

    request.on("error", (err) => {
      resolve({ status: "unknown", reason: err.message });
    });

    request.setTimeout(INSTALL_CANDIDATE_PROBE_TIMEOUT_MS, () => {
      request.destroy(new Error("timed out"));
    });

    request.end();
  });
}

function probeGitCandidate(repoUrl, ref, refNamespace) {
  const gitArgs = ["ls-remote", "--exit-code", refNamespace === "tags" ? "--tags" : "--heads", repoUrl, ref];
  const gitEnv = { ...process.env, GIT_TERMINAL_PROMPT: "0" };

  const result = spawnSync("git", gitArgs, {
    encoding: "utf-8",
    env: gitEnv,
    timeout: INSTALL_CANDIDATE_PROBE_TIMEOUT_MS,
  });

  if (result.error) {
    if (result.error.code === "ENOENT") {
      return { status: "unavailable", reason: "git is not installed" };
    }
    return { status: "unknown", reason: result.error.message };
  }
  if (result.status === 0) {
    return { status: "available", reason: "git ls-remote succeeded" };
  }

  const detail = (result.stderr || result.stdout || "").trim().split("\n")[0] || `git exit ${result.status}`;
  if (
    result.status === 2
    || /authentication failed|repository not found|access denied|not found|permission denied|could not read from remote repository/i.test(detail)
  ) {
    return { status: "unavailable", reason: detail };
  }

  return { status: "unknown", reason: detail };
}

async function probeInstallCandidate(candidate) {
  const override = probeOverrideForCandidate(candidate);
  if (override) {
    return override;
  }

  if (process.env[BOOTSTRAP_DISABLE_NETWORK_PROBES_ENV] === "1") {
    return { status: "unknown", reason: "network probes disabled" };
  }

  if (!candidate.probe) {
    return { status: "unknown", reason: "no preflight probe configured" };
  }
  if (candidate.probe.kind === "http") {
    return probeHttpCandidate(candidate.probe.url || candidate.spec);
  }
  if (candidate.probe.kind === "git") {
    return probeGitCandidate(candidate.probe.repoUrl, candidate.probe.ref, candidate.probe.refNamespace);
  }
  return { status: "unknown", reason: "unsupported preflight probe" };
}

async function resolveInstallCandidates(candidates) {
  const skipped = [];

  for (const [index, candidate] of candidates.entries()) {
    const probe = await probeInstallCandidate(candidate);
    if (probe.status === "unavailable") {
      skipped.push({ candidate, probe });
      continue;
    }
    return {
      candidates: [candidate, ...candidates.slice(index + 1)],
      skipped,
    };
  }

  return { candidates: [], skipped };
}

function logUnavailableCandidates(skipped) {
  for (const { candidate, probe } of skipped) {
    log(`Detected that ${candidate.label} is unavailable${formatProbeReason(probe.reason)}.`);
  }
}

function installFromCandidates(python, candidates, env, options = {}) {
  const { forceReinstall = false, firstAttemptMessage = null } = options;
  if (candidates.length === 0) {
    return { ok: false };
  }

  if (typeof firstAttemptMessage === "function") {
    const message = firstAttemptMessage(candidates[0]);
    if (message) {
      log(message);
    }
  }

  let installResult = runPipInstall(python, candidates[0].spec, env, {
    forceReinstall,
    noCache: candidates[0].noCache,
  });
  if (installResult.status === 0) {
    return { ok: true, installedFrom: candidates[0].spec };
  }
  flushCapturedOutput(installResult);

  for (const [index, candidate] of candidates.entries()) {
    if (index === 0) {
      continue;
    }
    const previousLabel = candidates[index - 1].label;
    log(`${previousLabel} failed. Falling back to ${candidate.label}...`);
    installResult = runPipInstall(python, candidate.spec, env, {
      forceReinstall,
      noCache: candidate.noCache,
    });
    if (installResult.status === 0) {
      return { ok: true, installedFrom: candidate.spec };
    }
    flushCapturedOutput(installResult);
  }

  return { ok: false };
}

function runPipInstall(python, spec, env, options = {}) {
  const args = ["-m", "pip", "install", "--upgrade", "--quiet"];
  if (options.forceReinstall) {
    args.push("--force-reinstall");
  }
  if (options.noCache) {
    args.push("--no-cache-dir");
  }
  args.push(spec);
  return spawnSync(
    python,
    args,
    {
      encoding: "utf-8",
      env,
    }
  );
}

function flushCapturedOutput(result) {
  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  if (result.error) {
    process.stderr.write(`${result.error.message}\n`);
  }
}

function gpdHomeDir() {
  return process.env[GPD_HOME_ENV] || path.join(os.homedir(), GPD_HOME_DIRNAME);
}

function managedEnvDir(gpdHome) {
  return path.join(gpdHome, "venv");
}

function managedPythonPath(venvDir) {
  return path.join(venvDir, isWindows() ? "Scripts" : "bin", isWindows() ? "python.exe" : "python");
}

function ensureManagedEnvironment(basePython) {
  const gpdHome = gpdHomeDir();
  const venvDir = managedEnvDir(gpdHome);
  const managedPython = managedPythonPath(venvDir);
  const existingManaged = pythonVersionInfo(managedPython);
  const hadExistingManaged = Boolean(existingManaged);

  let shouldCreate = !existingManaged;
  if (
    existingManaged
    && (
      !isSupportedPython(existingManaged)
      || existingManaged.major > basePython.major
      || (existingManaged.major === basePython.major && existingManaged.minor > basePython.minor)
    )
  ) {
    log(
      `Recreating managed environment at ${venvDir} `
      + `(found ${existingManaged.text}; switching to ${basePython.text}).`
    );
    fs.rmSync(venvDir, { recursive: true, force: true });
    shouldCreate = true;
  }

  if (shouldCreate) {
    log(`Creating managed Python environment at ${venvDir}...`);
    fs.mkdirSync(gpdHome, { recursive: true });
    const venvResult = spawnSync(basePython.command, ["-m", "venv", venvDir], {
      stdio: "inherit",
    });
    if (venvResult.status !== 0) {
      error("Failed to create the managed Python environment.");
      error(`Install Python ${MIN_SUPPORTED_PYTHON_LABEL} with the standard library \`venv\` module, then rerun the bootstrap installer.`);
      process.exit(1);
    }
  }

  let pipVersion = checkPip(managedPython);
  if (!pipVersion) {
    log("Bootstrapping pip inside the managed environment...");
    const ensurePipResult = spawnSync(managedPython, ["-m", "ensurepip", "--upgrade"], {
      stdio: "inherit",
    });
    if (ensurePipResult.status !== 0) {
      error("Managed Python environment is missing pip and could not be repaired.");
      process.exit(1);
    }
    pipVersion = checkPip(managedPython);
    if (!pipVersion) {
      error("Managed Python environment is missing pip.");
      process.exit(1);
    }
  }

  log(`Using managed environment at ${venvDir}`);
  log(`Found ${pipVersion}`);
  return { gpdHome, venvDir, python: managedPython, reusedExisting: hadExistingManaged && !shouldCreate };
}

async function installManagedPackage(python, pythonVersion, options = {}) {
  const { forceReinstall = false, preferMain = false, purpose = "install" } = options;
  const requestedVersion = pythonVersion;
  const pipInstallEnv = { ...process.env, PIP_DISABLE_PIP_VERSION_CHECK: "1" };

  if (preferMain) {
    const resolution = await resolveInstallCandidates(mainBranchInstallCandidates());
    const upgradeCandidates = resolution.candidates;
    if (upgradeCandidates.length > 0) {
      log(`Upgrading GPD from the latest GitHub ${GITHUB_MAIN_BRANCH} branch into the managed environment...`);
      logUnavailableCandidates(resolution.skipped);
      if (resolution.skipped.length > 0) {
        log(`Using ${upgradeCandidates[0].label} for the ${GITHUB_MAIN_BRANCH}-branch upgrade.`);
      }
      const installAttempt = installFromCandidates(python, upgradeCandidates, pipInstallEnv, {
        forceReinstall: true,
      });
      if (installAttempt.ok) {
        return { ok: true, requestedVersion, installedFrom: installAttempt.installedFrom };
      }

      log(`GitHub ${GITHUB_MAIN_BRANCH} upgrade failed across all main-branch candidates.`);
      return { ok: false, requestedVersion };
    } else if (resolution.skipped.length > 0) {
      logUnavailableCandidates(resolution.skipped);
      log(`No accessible GitHub ${GITHUB_MAIN_BRANCH} source candidate was detected for the upgrade.`);
      return { ok: false, requestedVersion };
    }
  }

  const action = purpose === "uninstall"
    ? "Preparing managed GPD CLI"
    : forceReinstall
      ? "Reinstalling GPD"
      : "Installing GPD";

  // 1. Try PyPI first — fast, reliable, no auth needed.
  const pypiSpec = `${SHARED_INSTALL_METADATA.bootstrapPackageName}==${pythonVersion}`;
  log(`${action} from PyPI (${pypiSpec}) into the managed environment...`);
  const pypiResult = runPipInstall(python, pypiSpec, pipInstallEnv, { forceReinstall });
  if (pypiResult.status === 0) {
    return { ok: true, requestedVersion, installedFrom: pypiSpec };
  }
  flushCapturedOutput(pypiResult);
  log(`PyPI install failed. Falling back to GitHub source...`);

  // 2. Fall back to tagged GitHub release candidates.
  const resolution = await resolveInstallCandidates(releaseInstallCandidates(pythonVersion));
  const releaseCandidates = resolution.candidates;
  logUnavailableCandidates(resolution.skipped);

  if (releaseCandidates.length > 0) {
    const installAttempt = installFromCandidates(python, releaseCandidates, pipInstallEnv, {
      forceReinstall,
      firstAttemptMessage: (candidate) => `${action} from ${candidate.label} into the managed environment...`,
    });
    if (installAttempt.ok) {
      return { ok: true, requestedVersion, installedFrom: installAttempt.installedFrom };
    }
  } else if (resolution.skipped.length > 0) {
    log("No accessible tagged GitHub release source candidate was detected.");
  }

  return { ok: false, requestedVersion };
}

function runManagedCliCommand(python, cliArgs, options = {}) {
  const { captureOutput = false, env = {} } = options;
  const spawnOptions = { env: { ...process.env, ...env } };
  if (captureOutput) {
    spawnOptions.encoding = "utf-8";
  } else {
    spawnOptions.stdio = "inherit";
  }
  return spawnSync(python, cliArgs, spawnOptions);
}

function describeFailedCommand(result) {
  if (result.error) {
    return result.error.message;
  }
  if (result.signal) {
    return `signal ${result.signal}`;
  }
  return `exit ${result.status}`;
}

async function prompt(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

function expandTilde(value) {
  if (value === "~") {
    return os.homedir();
  }
  if (value && value.startsWith("~/")) {
    return path.join(os.homedir(), value.slice(2));
  }
  return value;
}

function runtimeGlobalConfigDir(runtime) {
  const policy = runtimeRecord(runtime).global_config;
  if (policy.strategy === "env_or_home") {
    if (policy.env_var && process.env[policy.env_var]) {
      return expandTilde(process.env[policy.env_var]);
    }
    return path.join(os.homedir(), policy.home_subpath);
  }

  if (policy.strategy === "xdg_app") {
    if (policy.env_dir_var && process.env[policy.env_dir_var]) {
      return expandTilde(process.env[policy.env_dir_var]);
    }
    if (policy.env_file_var && process.env[policy.env_file_var]) {
      return path.dirname(expandTilde(process.env[policy.env_file_var]));
    }
    if (process.env.XDG_CONFIG_HOME && policy.xdg_subdir) {
      return path.join(expandTilde(process.env.XDG_CONFIG_HOME), policy.xdg_subdir);
    }
    return path.join(os.homedir(), policy.home_subpath);
  }

  throw new Error(`Unsupported config policy for runtime ${runtime}`);
}

function normalizedConfigDirCandidate(targetDir) {
  return path.resolve(expandTilde(targetDir));
}

function runtimeGlobalConfigDirCandidates(runtime) {
  const policy = runtimeRecord(runtime).global_config;
  const candidates = [];
  const addCandidate = (candidate) => {
    if (!candidate) {
      return;
    }
    const resolved = normalizedConfigDirCandidate(candidate);
    if (!candidates.includes(resolved)) {
      candidates.push(resolved);
    }
  };

  addCandidate(runtimeGlobalConfigDir(runtime));
  addCandidate(path.join(os.homedir(), policy.home_subpath));
  return candidates;
}

function targetDirMatchesGlobal(runtime, targetDir) {
  const resolvedTargetDir = normalizedConfigDirCandidate(targetDir);
  return runtimeGlobalConfigDirCandidates(runtime).includes(resolvedTargetDir);
}

function formatDisplayPath(filePath) {
  const home = os.homedir().replace(/\\/g, "/");
  const normalized = String(filePath).replace(/\\/g, "/");
  if (normalized === home) {
    return "~";
  }
  if (normalized.startsWith(`${home}/`)) {
    return `~${normalized.slice(home.length)}`;
  }
  return normalized;
}

function formatRuntimeList(runtimes) {
  const names = runtimes.map((runtime) => runtimeDisplayName(runtime));
  if (names.length === 0) {
    return "no runtimes";
  }
  if (names.length === 1) {
    return names[0];
  }
  if (names.length === 2) {
    return `${names[0]} and ${names[1]}`;
  }
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

function formatLocationExample(runtimes, scope) {
  if (runtimes.length !== 1) {
    return "one config dir per runtime";
  }

  const runtime = runtimes[0];
  if (scope === "global") {
    return formatDisplayPath(runtimeGlobalConfigDir(runtime));
  }
  return `./${runtimeConfigDirName(runtime)}`;
}

function stripAnsi(text) {
  return String(text || "").replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "");
}

function parseJsonText(text) {
  const cleaned = stripAnsi(text).trim();
  if (!cleaned) {
    return null;
  }
  try {
    return JSON.parse(cleaned);
  } catch {
    return null;
  }
}

function shellQuote(arg) {
  const text = String(arg);
  if (text === "") {
    return "''";
  }
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(text)) {
    return text;
  }
  return `'${text.replace(/'/g, `'\\''`)}'`;
}

function formatShellCommand(argv) {
  return argv.map((arg) => shellQuote(arg)).join(" ");
}

function runtimeDoctorHint(runtime, scope, targetDir = null) {
  const parts = ["gpd", "doctor", "--runtime", runtime, `--${scope}`];
  if (targetDir) {
    parts.push("--target-dir", targetDir);
  }
  return formatShellCommand(parts);
}

function buildRuntimeDoctorArgs(runtime, scope, targetDir = null) {
  const args = ["-m", "gpd.cli", "--raw", "doctor", "--runtime", runtime, `--${scope}`];
  if (targetDir) {
    args.push("--target-dir", targetDir);
  }
  return args;
}

function doctorCheckMessages(check, field) {
  if (!check || typeof check !== "object") {
    return [];
  }
  const messages = Array.isArray(check[field]) ? check[field] : [];
  const label = typeof check.label === "string" && check.label.trim() ? check.label.trim() : "Readiness Check";
  return messages
    .filter((message) => typeof message === "string" && message.trim())
    .map((message) => `${label}: ${message.trim()}`);
}

function collectDoctorAdvisories(report) {
  const advisories = [];
  const seen = new Set();
  const checks = Array.isArray(report && report.checks) ? report.checks : [];

  for (const check of checks) {
    for (const message of doctorCheckMessages(check, "warnings")) {
      if (!seen.has(message)) {
        seen.add(message);
        advisories.push(message);
      }
    }
    if ((check && check.status) === "warn") {
      for (const message of doctorCheckMessages(check, "issues")) {
        if (!seen.has(message)) {
          seen.add(message);
          advisories.push(message);
        }
      }
    }
  }

  return advisories;
}

function collectDoctorBlockers(report) {
  const blockers = [];
  const seen = new Set();
  const checks = Array.isArray(report && report.checks) ? report.checks : [];

  for (const check of checks) {
    if ((check && check.status) !== "fail") {
      continue;
    }
    const messages = [
      ...doctorCheckMessages(check, "issues"),
      ...doctorCheckMessages(check, "warnings"),
    ];
    if (messages.length === 0) {
      const label = typeof check.label === "string" && check.label.trim() ? check.label.trim() : "Readiness Check";
      messages.push(`${label}: readiness check failed.`);
    }
    for (const message of messages) {
      if (!seen.has(message)) {
        seen.add(message);
        blockers.push(message);
      }
    }
  }

  return blockers;
}

function collectRepairableRuntimeTargetMessages(report) {
  const messages = [];
  const seen = new Set();
  const checks = Array.isArray(report && report.checks) ? report.checks : [];

  for (const check of checks) {
    if ((check && check.status) !== "fail") {
      continue;
    }
    if (typeof check.label !== "string" || check.label.trim() !== "Runtime Config Target") {
      continue;
    }
    const details = check.details && typeof check.details === "object" ? check.details : null;
    if (!details || details.install_state !== "owned_incomplete") {
      continue;
    }
    const checkMessages = [
      ...doctorCheckMessages(check, "issues"),
      ...doctorCheckMessages(check, "warnings"),
    ];
    if (checkMessages.length === 0) {
      checkMessages.push("Runtime Config Target: incomplete owned install will be repaired.");
    }
    for (const message of checkMessages) {
      if (!seen.has(message)) {
        seen.add(message);
        messages.push(message);
      }
    }
  }

  return messages;
}

function extractDoctorErrorMessage(result) {
  const stderrJson = parseJsonText(result.stderr);
  if (stderrJson && typeof stderrJson.error === "string" && stderrJson.error.trim()) {
    return stderrJson.error.trim();
  }

  const stdoutJson = parseJsonText(result.stdout);
  if (stdoutJson && typeof stdoutJson.error === "string" && stdoutJson.error.trim()) {
    return stdoutJson.error.trim();
  }

  const stderrText = stripAnsi(result.stderr).trim();
  if (stderrText) {
    return stderrText;
  }

  const stdoutText = stripAnsi(result.stdout).trim();
  if (stdoutText) {
    return stdoutText;
  }

  return `managed doctor exited with status ${result.status}`;
}

function runManagedDoctorReadinessCheck(managedPython, runtime, scope, targetDir = null) {
  const result = spawnSync(managedPython, buildRuntimeDoctorArgs(runtime, scope, targetDir), {
    encoding: "utf-8",
    env: process.env,
  });

  if (result.error) {
    return {
      ok: false,
      errorMessage: result.error.message,
    };
  }

  if (result.status !== 0) {
    return {
      ok: false,
      errorMessage: extractDoctorErrorMessage(result),
    };
  }

  const report = parseJsonText(result.stdout);
  if (!report || typeof report !== "object" || !Array.isArray(report.checks)) {
    return {
      ok: false,
      errorMessage: "managed doctor did not return a valid readiness report.",
    };
  }

  return {
    ok: true,
    report,
  };
}

function runInstallReadinessPreflight(managedPython, runtimes, scope, targetDir = null) {
  console.log(` ${bold}${brandTitle}Runtime launcher/target preflight${reset}`);
  console.log("");

  const blockers = [];
  const advisoriesByRuntime = [];

  for (const runtime of runtimes) {
    const displayName = runtimeDisplayName(runtime);
    const doctorCheck = runManagedDoctorReadinessCheck(managedPython, runtime, scope, targetDir);
    if (!doctorCheck.ok) {
      blockers.push(`${displayName}: ${doctorCheck.errorMessage}`);
      continue;
    }

    const report = doctorCheck.report;
    const repairableMessages = collectRepairableRuntimeTargetMessages(report);
    const repairableSet = new Set(repairableMessages);
    const reportBlockers = collectDoctorBlockers(report).filter((message) => !repairableSet.has(message));
    if (reportBlockers.length > 0 || (report.overall === "fail" && repairableMessages.length === 0)) {
      const messages = reportBlockers.length > 0
        ? reportBlockers
        : ["Runtime readiness reported a failure without blocking details."];
      blockers.push(...messages.map((message) => `${displayName}: ${message}`));
      continue;
    }

    const advisories = [...collectDoctorAdvisories(report), ...repairableMessages];
    const uniqueAdvisories = [...new Set(advisories)];
    if (uniqueAdvisories.length > 0) {
      advisoriesByRuntime.push([displayName, uniqueAdvisories]);
    }
  }

  if (blockers.length > 0) {
    console.log("");
    error("Runtime launcher/target preflight failed.");
    [...new Set(blockers)].forEach((message) => error(message));
    const doctorHints = runtimes.map((runtime) => `\`${runtimeDoctorHint(runtime, scope, targetDir)}\``).join(", ");
    errLog(`Fix the blocking readiness issue(s) above, then rerun the bootstrap installer. Inspect directly with ${doctorHints}.`);
    return false;
  }

  console.log("");
  success(`Runtime launcher/target preflight passed for ${formatRuntimeList(runtimes)}.`);
  for (const [displayName, advisories] of advisoriesByRuntime) {
    advisories.forEach((message) => warn(`${displayName}: ${message}`));
  }
  const doctorHints = runtimes.map((runtime) => `\`${runtimeDoctorHint(runtime, scope, targetDir)}\``).join(", ");
  log(`Inspect runtime readiness later with ${doctorHints}.`);
  console.log("");
  return true;
}

function formatMenuOption(index, label, details = [], options = {}) {
  const { labelWidth = label.length } = options;
  const filteredDetails = details.filter(Boolean);
  const detailText = filteredDetails.length === 0
    ? ""
    : `  ${filteredDetails.map((detail) => `${bold}${brandAccent}·${reset} ${dim}${brandMeta}${detail}${reset}`).join(" ")}`;
  return ` ${bold}${brandAccent}[${index}]${reset} ${bold}${brandTitle}${label.padEnd(labelWidth, " ")}${reset}${detailText}`;
}

function documentedRuntimeFlags() {
  return RUNTIME_CATALOG.flatMap((runtime) => runtimeSelectionFlagList(runtime.runtime_name));
}

function runtimeHelpExampleRuntime(scope, fallback = ALL_RUNTIMES[0]) {
  const match = RUNTIME_CATALOG.find((runtime) => runtimeInstallerHelpExampleScope(runtime.runtime_name) === scope);
  return match ? match.runtime_name : fallback;
}

function printBanner() {
  console.log("");
  console.log(`${bold}${brandLogo} ██████╗ ██████╗ ██████╗${reset}`);
  console.log(`${bold}${brandLogo}██╔════╝ ██╔══██╗██╔══██╗${reset}`);
  console.log(`${bold}${brandLogo}██║  ███╗██████╔╝██║  ██║${reset}`);
  console.log(`${bold}${brandLogo}██║   ██║██╔═══╝ ██║  ██║${reset}`);
  console.log(`${bold}${brandLogo}╚██████╔╝██║     ██████╔╝${reset}`);
  console.log(`${bold}${brandLogo} ╚═════╝ ╚═╝     ╚═════╝${reset}`);
  console.log("");
  console.log(` ${bold}${brandTitle}GPD v${packageVersion} - ${brandDisplayName}${reset}`);
  console.log(` ${dim}${brandMeta}© ${brandCopyrightYear} ${brandOwner} (${brandOwnerShort})${reset}`);
  console.log("");
}

function printHelp() {
  const installCommand = sharedBootstrapCommand();
  const primaryRuntime = ALL_RUNTIMES[0];
  const globalHelpRuntime = runtimeHelpExampleRuntime("global", primaryRuntime);
  const localHelpRuntime = runtimeHelpExampleRuntime("local", globalHelpRuntime);
  const primaryFlag = runtimeInstallFlag(globalHelpRuntime);
  const helpExampleFlag = runtimeInstallFlag(localHelpRuntime);
  const targetDirExample = `/path/to/${runtimeConfigDirName(localHelpRuntime)}`;
  console.log(` ${yellow}Usage:${reset} ${installCommand} [install|uninstall] [options]`);
  console.log("");
  console.log(` ${dim}${productPositioning}${reset}`);
  console.log("");
  console.log(` ${yellow}Options:${reset}`);
  console.log(` ${cyan}-l, --local${reset}             Use the current project only`);
  console.log(` ${cyan}-g, --global${reset}            Use the global runtime config dir`);
  console.log(` ${cyan}--uninstall${reset}             Uninstall from selected runtime config`);
  console.log(` ${cyan}--reinstall${reset}             Reinstall \${GPD_HOME:-~/.gpd}/venv from the PyPI pinned release, with tagged GitHub fallback`);
  console.log(` ${cyan}--upgrade${reset}               Upgrade \${GPD_HOME:-~/.gpd}/venv from the latest unreleased GitHub main source`);
  const runtimeFlagRows = ALL_RUNTIMES.map((runtime) => [
    runtime,
    runtimeSelectionFlagList(runtime).join(", "),
  ]);
  const runtimeFlagColumnWidth = Math.max(...runtimeFlagRows.map(([, flags]) => flags.length)) + 1;
  for (const [runtime, flags] of runtimeFlagRows) {
    const padding = " ".repeat(runtimeFlagColumnWidth - flags.length);
    console.log(` ${cyan}${flags}${reset}${padding}Select ${runtimeDisplayName(runtime)} only`);
  }
  console.log(` ${cyan}--all${reset}                  Select all supported runtimes`);
  console.log(` ${cyan}--target-dir <path>${reset}    Override the runtime config directory; defaults to local scope unless the path resolves to that runtime's canonical global config dir`);
  console.log(` ${cyan}--force-statusline${reset}     Replace an existing runtime statusline`);
  console.log(` ${cyan}-h, --help${reset}              Show this help message`);
  console.log("");
  console.log(` ${yellow}Examples:${reset}`);
  console.log(` ${dim}# Interactive install${reset}`);
  console.log(` ${installCommand}`);
  console.log("");
  console.log(` ${dim}# Install for ${runtimeDisplayName(primaryRuntime)} globally${reset}`);
  console.log(` ${installCommand} ${primaryFlag} --global`);
  console.log("");
  console.log(` ${dim}# Install for ${runtimeDisplayName(localHelpRuntime)} locally${reset}`);
  console.log(` ${installCommand} ${helpExampleFlag} --local`);
  console.log("");
  console.log(` ${dim}# Reinstall the PyPI pinned release${reset}`);
  console.log(` ${installCommand} --reinstall ${primaryFlag} --local`);
  console.log("");
  console.log(` ${dim}# Upgrade to the latest unreleased GitHub main source${reset}`);
  console.log(` ${installCommand} --upgrade ${primaryFlag} --local`);
  console.log("");
  console.log(` ${dim}# Install for all runtimes globally${reset}`);
  console.log(` ${installCommand} --all --global`);
  console.log("");
  console.log(` ${dim}# Install into an explicit local target directory${reset}`);
  console.log(` ${installCommand} ${helpExampleFlag} --local --target-dir ${targetDirExample}`);
  console.log("");
  console.log(` ${dim}# Interactive uninstall${reset}`);
  console.log(` ${installCommand} --uninstall`);
  console.log("");
  console.log(` ${dim}# Uninstall from ${runtimeDisplayName(primaryRuntime)} globally${reset}`);
  console.log(` ${installCommand} --uninstall ${primaryFlag} --global`);
  console.log("");
  console.log(` ${dim}# Uninstall from all runtimes globally${reset}`);
  console.log(` ${installCommand} --uninstall --all --global`);
  console.log("");
  console.log(` ${dim}# Equivalent uninstall subcommand form${reset}`);
  console.log(` ${installCommand} uninstall ${primaryRuntime} --local`);
  console.log("");
  console.log(` ${yellow}After install:${reset}`);
  console.log(` Beginner path: ${SHARED_PUBLIC_SURFACE_TEXT.beginnerHubUrl}`);
  console.log(` Runtime surface: run the selected runtime's help command; first-run order is ${beginnerStartupLadderText()}.`);
  console.log(
    ` Terminal surface: use \`${sharedLocalCliHelpCommand()}\`, \`${sharedDoctorCommand()}\`, `
    + `and \`${sharedUnattendedReadinessCommand()}\`.`
  );
  console.log("");
}

function parseTargetDirArg(args) {
  const inline = args.find((arg) => arg.startsWith("--target-dir="));
  if (inline) {
    const value = inline.slice("--target-dir=".length).trim();
    if (!value) {
      error("Missing value for --target-dir.");
      process.exit(1);
    }
    return value;
  }

  const index = args.indexOf("--target-dir");
  if (index === -1) {
    return null;
  }

  const value = args[index + 1];
  if (!value || value.startsWith("-")) {
    error("Missing value for --target-dir.");
    process.exit(1);
  }
  return value;
}

function validateBootstrapArgs(args) {
  const allowedFlags = new Set([
    "--all",
    "--force-statusline",
    "--global",
    "--help",
    "--local",
    "--reinstall",
    "--uninstall",
    "--upgrade",
    "-g",
    "-h",
    "-l",
    ...documentedRuntimeFlags(),
  ]);

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--target-dir") {
      index += 1;
      continue;
    }
    if (typeof arg === "string" && arg.startsWith("--target-dir=")) {
      continue;
    }
    if (allowedFlags.has(arg)) {
      continue;
    }

    const label = typeof arg === "string" && arg.startsWith("-")
      ? "Unknown bootstrap option"
      : "Unexpected bootstrap argument";
    error(`${label}: ${arg}. Run ${sharedBootstrapCommand()} --help for usage.`);
    process.exit(1);
  }
}

function runtimeTokenFlagMap() {
  const mapping = new Map();
  for (const runtime of ALL_RUNTIMES) {
    const aliases = new Set([
      runtime,
      runtimeDisplayName(runtime).toLowerCase(),
      ...runtimeSelectionAliases(runtime),
      ...runtimeSelectionFlagList(runtime).map((flag) => flag.replace(/^--/, "")),
    ]);
    for (const alias of aliases) {
      mapping.set(alias.toLowerCase(), runtimeInstallFlag(runtime));
    }
  }
  return mapping;
}

function normalizeBootstrapArgs(args) {
  if (args.length === 0) {
    return [];
  }

  const normalized = [];
  const firstArg = String(args[0]).toLowerCase();
  const usesSubcommandSyntax = firstArg === "install" || firstArg === "uninstall";
  const runtimeFlagsByToken = runtimeTokenFlagMap();
  let index = usesSubcommandSyntax ? 1 : 0;

  if (firstArg === "uninstall" && !args.includes("--uninstall")) {
    normalized.push("--uninstall");
  }

  while (index < args.length) {
    const arg = args[index];
    if (arg === "--target-dir") {
      normalized.push(arg);
      if (index + 1 < args.length) {
        normalized.push(args[index + 1]);
      }
      index += 2;
      continue;
    }
    if (typeof arg === "string" && arg.startsWith("--target-dir=")) {
      normalized.push(arg);
      index += 1;
      continue;
    }
    if (usesSubcommandSyntax && typeof arg === "string" && !arg.startsWith("-")) {
      const bareToken = arg.trim().toLowerCase();
      if (bareToken === "all") {
        normalized.push("--all");
        index += 1;
        continue;
      }
      const runtimeFlag = runtimeFlagsByToken.get(bareToken);
      if (runtimeFlag) {
        normalized.push(runtimeFlag);
        index += 1;
        continue;
      }
    }
    normalized.push(arg);
    index += 1;
  }

  return normalized;
}

function parseSelectedRuntimes(args) {
  const selected = [];
  const seen = new Set();

  if (args.includes("--all")) {
    return [...ALL_RUNTIMES];
  }

  for (const runtime of ALL_RUNTIMES) {
    const flags = runtimeSelectionFlagList(runtime);
    if (flags.some((flag) => args.includes(flag)) && !seen.has(runtime)) {
      selected.push(runtime);
      seen.add(runtime);
    }
  }

  return selected;
}

function explicitRuntimeSelectionFlags(args) {
  const selectedFlags = [];
  for (const runtime of ALL_RUNTIMES) {
    const flags = runtimeSelectionFlagList(runtime);
    for (const flag of flags) {
      if (args.includes(flag)) {
        selectedFlags.push(flag);
      }
    }
  }
  return selectedFlags;
}

function validateAllRuntimeSelection(args, action) {
  if (args.includes("--all") && explicitRuntimeSelectionFlags(args).length > 0) {
    error(`Cannot combine explicit runtimes with --all for ${action}`);
    process.exit(1);
  }
}

function runtimeSelectionMenuEntries({ allowAll = true } = {}) {
  const entries = ALL_RUNTIMES.map((runtime, index) => ({
    choice: String(index + 1),
    label: runtimeDisplayName(runtime),
    details: [runtime],
  }));
  if (allowAll) {
    entries.push({
      choice: String(ALL_RUNTIMES.length + 1),
      label: "All runtimes",
      details: [],
    });
  }
  return entries;
}

function resolveRuntimeSelectionChoice(choice, { allowAll = true } = {}) {
  const normalizedChoice = (choice || "1").toLowerCase();
  if (
    normalizedChoice === String(ALL_RUNTIMES.length + 1) ||
    normalizedChoice === "all" ||
    normalizedChoice === "all runtimes"
  ) {
    if (allowAll) {
      return { runtimes: [...ALL_RUNTIMES] };
    }
    return { error: "Select exactly one runtime when using --target-dir." };
  }

  const numericIndex = Number.parseInt(normalizedChoice, 10);
  if (Number.isInteger(numericIndex) && numericIndex >= 1 && numericIndex <= ALL_RUNTIMES.length) {
    return { runtimes: [ALL_RUNTIMES[numericIndex - 1]] };
  }

  for (const runtime of ALL_RUNTIMES) {
    const aliases = new Set([runtime, runtimeDisplayName(runtime).toLowerCase(), ...runtimeSelectionAliases(runtime)]);
    if (aliases.has(normalizedChoice)) {
      return { runtimes: [runtime] };
    }
  }

  return { error: `Invalid runtime selection: ${normalizedChoice}` };
}

async function selectRuntimes(args, action = "install", options = {}) {
  const { requireSingleRuntime = false } = options;
  const selected = parseSelectedRuntimes(args);
  if (selected.length > 0) {
    return selected;
  }

  if (!process.stdin.isTTY) {
    const mode = action === "uninstall" ? "--uninstall " : "";
    error(
      `Specify a runtime with ${documentedRuntimeFlags().join("/")} or use --all when running ${mode}non-interactively.`
    );
    process.exit(1);
  }

  const allowAll = !requireSingleRuntime;
  const menuEntries = runtimeSelectionMenuEntries({ allowAll });
  const optionLabelWidth = Math.max(
    ...menuEntries.map((entry) => entry.label.length)
  );
  const sectionTitle = action === "uninstall" ? "Select runtime(s) to uninstall" : "Select runtime(s) to install";
  console.log(` ${bold}${brandTitle}${sectionTitle}${reset}`);
  console.log("");
  for (const entry of menuEntries) {
    console.log(formatMenuOption(entry.choice, entry.label, entry.details, { labelWidth: optionLabelWidth }));
  }
  console.log("");

  const choice = await prompt(` ${bold}${brandTitle}Enter choice${reset} ${dim}[1]${reset}: `);
  const selection = resolveRuntimeSelectionChoice(choice, { allowAll });
  if (selection.runtimes) {
    return selection.runtimes;
  }
  error(selection.error);
  process.exit(1);
}

async function selectInstallScope(args, runtimes, targetDir, action = "install") {
  if (targetDir) {
    if (args.includes("--global") || args.includes("-g")) {
      return "global";
    }
    if (args.includes("--local") || args.includes("-l")) {
      return "local";
    }
    return targetDirMatchesGlobal(runtimes[0], targetDir) ? "global" : "local";
  }
  if (args.includes("--global") || args.includes("-g")) {
    return "global";
  }
  if (args.includes("--local") || args.includes("-l")) {
    return "local";
  }

  if (!process.stdin.isTTY) {
    const mode = action === "uninstall" ? "--uninstall " : "";
    error(`Specify --global or --local when running ${mode}non-interactively.`);
    process.exit(1);
  }

  const globalExample = formatLocationExample(runtimes, "global");
  const localExample = formatLocationExample(runtimes, "local");
  const optionLabelWidth = Math.max("Local".length, "Global".length);
  const sectionTitle = action === "uninstall" ? "Uninstall location" : "Install location";

  console.log(` ${bold}${brandTitle}${sectionTitle}${reset}`);
  console.log("");
  console.log(formatMenuOption(1, "Local", ["current project only", localExample], { labelWidth: optionLabelWidth }));
  console.log(formatMenuOption(2, "Global", ["all projects", globalExample], { labelWidth: optionLabelWidth }));
  console.log("");

  const choice = ((await prompt(` ${bold}${brandTitle}Enter choice${reset} ${dim}[1]${reset}: `)) || "1").toLowerCase();
  if (choice === "1" || choice === "local") {
    return "local";
  }
  if (choice === "2" || choice === "global") {
    return "global";
  }

  error(`Invalid location selection: ${choice}`);
  process.exit(1);
}

function buildRuntimeCommandArgs(command, runtimes, scope, targetDir = null, options = {}) {
  const { forceStatusline = false, skipReadinessCheck = false } = options;
  const cliArgs = ["-m", "gpd.cli", command];
  if (runtimes.length === ALL_RUNTIMES.length) {
    cliArgs.push("--all");
  } else {
    cliArgs.push(...runtimes);
  }
  cliArgs.push(`--${scope}`);
  if (targetDir) {
    cliArgs.push("--target-dir", targetDir);
  }
  if (command === "uninstall") {
    cliArgs.push("--yes");
  }
  if (forceStatusline && command === "install") {
    cliArgs.push("--force-statusline");
  }
  if (skipReadinessCheck && command === "install") {
    cliArgs.push("--skip-readiness-check");
  }
  return cliArgs;
}

async function main() {
  ensureSupportedNodeVersion();

  const args = normalizeBootstrapArgs(process.argv.slice(2));
  const hasHelp = args.includes("--help") || args.includes("-h");
  const isUninstall = args.includes("--uninstall");
  const forceStatusline = args.includes("--force-statusline");
  const reinstallManagedPackage = args.includes("--reinstall");
  const upgradeManagedPackage = args.includes("--upgrade");
  const targetDir = parseTargetDirArg(args);
  validateBootstrapArgs(args);
  const parsedRuntimes = parseSelectedRuntimes(args);

  printBanner();

  if (hasHelp) {
    printHelp();
    return;
  }

  if (!pythonPackageVersion) {
    error("Bootstrap package is missing its companion Python release metadata.");
    process.exit(1);
  }

  if ((args.includes("--global") || args.includes("-g")) && (args.includes("--local") || args.includes("-l"))) {
    error("Cannot specify both --global and --local.");
    process.exit(1);
  }
  const action = isUninstall ? "uninstall" : "install";
  validateAllRuntimeSelection(args, action);
  if (isUninstall && reinstallManagedPackage) {
    error("Cannot combine --uninstall with --reinstall.");
    process.exit(1);
  }
  if (isUninstall && upgradeManagedPackage) {
    error("Cannot combine --uninstall with --upgrade.");
    process.exit(1);
  }
  if (reinstallManagedPackage && upgradeManagedPackage) {
    error("Cannot combine --reinstall with --upgrade.");
    process.exit(1);
  }
  if (isUninstall && forceStatusline) {
    error("Cannot combine --uninstall with --force-statusline.");
    process.exit(1);
  }
  if (targetDir && parsedRuntimes.length === 0 && !process.stdin.isTTY) {
    error(`Specify exactly one runtime with ${documentedRuntimeFlags().join("/")} when using --target-dir non-interactively.`);
    process.exit(1);
  }

  const selectedRuntimes = await selectRuntimes(args, action, { requireSingleRuntime: Boolean(targetDir) });
  if (targetDir && selectedRuntimes.length !== 1) {
    error("Cannot combine --target-dir with --all or multiple runtimes. Select exactly one runtime.");
    process.exit(1);
  }
  const scope = await selectInstallScope(args, selectedRuntimes, targetDir, action);

  const basePython = checkPython();
  if (!basePython) {
    error(`Python ${MIN_SUPPORTED_PYTHON_LABEL} is required but not found.`);
    error("Install from https://python.org or via your package manager.");
    process.exit(1);
  }
  success(`Found ${basePython.text}`);

  if (!hasVenvSupport(basePython.command)) {
    error(`Python ${MIN_SUPPORTED_PYTHON_LABEL} with the standard library 'venv' module is required, but ${basePython.command} cannot create virtual environments.`);
    error("Install venv support for that interpreter, then rerun the bootstrap installer.");
    process.exit(1);
  }

  const managedEnv = ensureManagedEnvironment(basePython);
  const cliArgs = buildRuntimeCommandArgs(action, selectedRuntimes, scope, targetDir, {
    forceStatusline,
    skipReadinessCheck: !isUninstall,
  });

  if (isUninstall) {
    log(`Uninstalling GPD from ${formatRuntimeList(selectedRuntimes)} (${scope})...`);
  }

  if (isUninstall && managedEnv.reusedExisting) {
    log("Trying existing managed GPD CLI for uninstall...");
    const existingUninstall = runManagedCliCommand(managedEnv.python, cliArgs, { captureOutput: true });
    if (existingUninstall.status === 0) {
      flushCapturedOutput(existingUninstall);
      return;
    }
    log(
      "Existing managed GPD CLI could not complete uninstall "
      + `(${describeFailedCommand(existingUninstall)}); preparing current managed GPD CLI...`
    );
  }

  const packageInstall = await installManagedPackage(managedEnv.python, pythonPackageVersion, {
    forceReinstall: reinstallManagedPackage || upgradeManagedPackage,
    preferMain: upgradeManagedPackage,
    purpose: isUninstall ? "uninstall" : "install",
  });
  if (!packageInstall.ok) {
    const failureSource = upgradeManagedPackage
      ? `the latest unreleased GitHub ${GITHUB_MAIN_BRANCH} source`
      : "the PyPI pinned release or tagged GitHub release sources";
    error(`Failed to install GPD v${packageInstall.requestedVersion} from ${failureSource}.`);
    process.exit(1);
  }

  if (!isUninstall) {
    const readinessOk = runInstallReadinessPreflight(managedEnv.python, selectedRuntimes, scope, targetDir);
    if (!readinessOk) {
      process.exitCode = 1;
      return;
    }
  }

  // Run the installer/uninstaller through the managed Python interpreter.
  const result = runManagedCliCommand(
    managedEnv.python,
    cliArgs,
    isUninstall ? {} : { env: { GPD_BOOTSTRAP_EMBEDDED_INSTALL: "1" } }
  );

  if (result.status === 0) {
    return;
  } else {
    error(`${isUninstall ? "Uninstall" : "Installation"} failed. Check the output above for details.`);
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch((err) => {
    error(err.message);
    process.exit(1);
  });
}

module.exports = {
  ensureSupportedNodeVersion,
  loadBootstrapInstallerMetadata,
  loadSharedInstallMetadata,
  loadSharedPublicSurfaceText,
  nodeMajorVersion,
  resolveRuntimeSelectionChoice,
  runtimeGlobalConfigDirCandidates,
  runtimeSelectionMenuEntries,
  targetDirMatchesGlobal,
  validateBootstrapInstallerMetadata,
};
