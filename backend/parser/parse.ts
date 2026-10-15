const fs = require("fs");
const path = require("path");

function resolveTypeScript() {
  const candidates = [
    path.join(__dirname, "node_modules", "typescript"),
    path.join(__dirname, "..", "..", "frontend", "node_modules", "typescript"),
    "typescript",
  ];

  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      continue;
    }
  }

  throw new Error(
    "Unable to resolve the TypeScript compiler API. Install it in backend/parser or ensure frontend/node_modules/typescript exists."
  );
}

const ts = resolveTypeScript();

function getScriptKind(filePath) {
  if (filePath.endsWith(".tsx")) {
    return ts.ScriptKind.TSX;
  }

  if (filePath.endsWith(".ts")) {
    return ts.ScriptKind.TS;
  }

  if (filePath.endsWith(".jsx")) {
    return ts.ScriptKind.JSX;
  }

  return ts.ScriptKind.JS;
}

function getImportPath(node) {
  const specifier = node.moduleSpecifier;
  if (specifier && typeof specifier.text === "string" && specifier.text.length > 0) {
    return specifier.text;
  }
  return null;
}

function isLocalModule(modulePath) {
  return typeof modulePath === "string" && modulePath.startsWith(".");
}

const compilerOptionsCache = new Map();
const workspacePackagesCache = new Map();
const SOURCE_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"];
const TYPESCRIPT_EXTENSIONS = new Set(SOURCE_EXTENSIONS);

function toPosix(filePath) {
  return filePath.split(path.sep).join("/");
}

function findRepositoryRoot(startPath) {
  let currentPath = path.dirname(startPath);
  let nearestMarker = null;

  while (true) {
    if (fs.existsSync(path.join(currentPath, ".git"))) {
      return currentPath;
    }

    if (
      nearestMarker === null &&
      ["package.json", "tsconfig.json", "jsconfig.json"].some((marker) =>
        fs.existsSync(path.join(currentPath, marker))
      )
    ) {
      nearestMarker = currentPath;
    }

    const parentPath = path.dirname(currentPath);
    if (parentPath === currentPath) {
      return nearestMarker || path.dirname(startPath);
    }

    currentPath = parentPath;
  }
}

function isWithinRepository(repositoryRoot, candidate) {
  const relative = path.relative(repositoryRoot, candidate);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function isRepositorySourceFile(repositoryRoot, candidate) {
  const relative = toPosix(path.relative(repositoryRoot, candidate));
  return (
    isWithinRepository(repositoryRoot, candidate) &&
    !relative.split("/").includes("node_modules") &&
    !candidate.endsWith(".d.ts") &&
    SOURCE_EXTENSIONS.includes(path.extname(candidate).toLowerCase())
  );
}

function resolveSourceCandidate(basePath) {
  const candidates = [
    basePath,
    ...SOURCE_EXTENSIONS.map((extension) => `${basePath}${extension}`),
    ...SOURCE_EXTENSIONS.map((extension) => path.join(basePath, `index${extension}`)),
  ];

  for (const candidate of candidates) {
    if (
      SOURCE_EXTENSIONS.includes(path.extname(candidate).toLowerCase()) &&
      !candidate.endsWith(".d.ts") &&
      fs.existsSync(candidate) &&
      fs.statSync(candidate).isFile()
    ) {
      return candidate;
    }
  }

  return null;
}

function loadCompilerOptions(filePath, repositoryRoot) {
  const configPath =
    ts.findConfigFile(path.dirname(filePath), ts.sys.fileExists, "tsconfig.json") ||
    ts.findConfigFile(path.dirname(filePath), ts.sys.fileExists, "jsconfig.json");
  const cacheKey = configPath || repositoryRoot;
  if (compilerOptionsCache.has(cacheKey)) {
    return compilerOptionsCache.get(cacheKey);
  }

  let options = {
    allowJs: true,
    moduleResolution: ts.ModuleResolutionKind.NodeNext,
  };
  if (configPath) {
    const config = ts.readConfigFile(configPath, ts.sys.readFile);
    if (!config.error) {
      options = ts.parseJsonConfigFileContent(
        config.config,
        ts.sys,
        path.dirname(configPath)
      ).options;
    }
  }
  compilerOptionsCache.set(cacheKey, options);
  return options;
}

function collectPackageDirectories(root, output) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory() || [".git", "node_modules", "dist", "build", "coverage"].includes(entry.name)) {
      continue;
    }
    const directory = path.join(root, entry.name);
    if (fs.existsSync(path.join(directory, "package.json"))) {
      output.push(directory);
    }
    collectPackageDirectories(directory, output);
  }
}

function matchesWorkspacePattern(relativeDirectory, patterns) {
  const normalized = toPosix(relativeDirectory).replace(/^\.\//, "").replace(/\/$/, "");
  return patterns.some((pattern) => {
    const normalizedPattern = toPosix(pattern).replace(/^\.\//, "").replace(/\/$/, "");
    const escaped = normalizedPattern.replace(/[.+^${}()|[\]\\]/g, "\\$&");
    const expression = escaped.replace(/\*\*/g, "__DOUBLE_STAR__").replace(/\*/g, "[^/]+").replace(/__DOUBLE_STAR__/g, ".*");
    return new RegExp(`^${expression}$`).test(normalized);
  });
}

function loadWorkspacePackages(repositoryRoot) {
  if (workspacePackagesCache.has(repositoryRoot)) {
    return workspacePackagesCache.get(repositoryRoot);
  }

  const packages = new Map();
  const rootPackagePath = path.join(repositoryRoot, "package.json");
  if (fs.existsSync(rootPackagePath)) {
    const rootPackage = JSON.parse(fs.readFileSync(rootPackagePath, "utf8"));
    const workspaces = Array.isArray(rootPackage.workspaces)
      ? rootPackage.workspaces
      : rootPackage.workspaces?.packages;
    if (Array.isArray(workspaces) && workspaces.length > 0) {
      const directories = [];
      collectPackageDirectories(repositoryRoot, directories);
      for (const directory of directories) {
        if (!matchesWorkspacePattern(path.relative(repositoryRoot, directory), workspaces)) {
          continue;
        }
        try {
          const manifest = JSON.parse(fs.readFileSync(path.join(directory, "package.json"), "utf8"));
          if (manifest.name) {
            packages.set(manifest.name, { directory, manifest });
          }
        } catch (_error) {
          // Invalid package manifests are reported elsewhere and should not abort indexing.
        }
      }
    }
  }
  workspacePackagesCache.set(repositoryRoot, packages);
  return packages;
}

function resolveWorkspaceModule(modulePath, repositoryRoot) {
  if (typeof modulePath !== "string" || modulePath.length === 0) {
    return null;
  }
  const packages = loadWorkspacePackages(repositoryRoot);
  const packageName = [...packages.keys()]
    .sort((left, right) => right.length - left.length)
    .find((name) => modulePath === name || modulePath.startsWith(`${name}/`));
  if (!packageName) {
    return null;
  }

  const { directory, manifest } = packages.get(packageName);
  const suffix = modulePath.slice(packageName.length).replace(/^\//, "");
  const entryCandidates = suffix
    ? [path.join(directory, suffix), path.join(directory, "src", suffix)]
    : [
        manifest.source && path.join(directory, manifest.source),
        manifest.types && path.join(directory, manifest.types),
        manifest.module && path.join(directory, manifest.module),
        manifest.main && path.join(directory, manifest.main),
        path.join(directory, "src", "index"),
        path.join(directory, "index"),
      ].filter(Boolean);

  for (const candidate of entryCandidates) {
    const resolved = resolveSourceCandidate(candidate);
    if (resolved) {
      return resolved;
    }
  }
  return null;
}

function resolveRepositoryImport(filePath, modulePath, repositoryRoot) {
  const relativeCandidate = isLocalModule(modulePath)
    ? resolveSourceCandidate(path.resolve(path.dirname(filePath), modulePath))
    : null;
  if (relativeCandidate) {
    return relativeCandidate;
  }

  const compilerOptions = loadCompilerOptions(filePath, repositoryRoot);
  const typescriptResolution = ts.resolveModuleName(
    modulePath,
    filePath,
    compilerOptions,
    ts.sys
  ).resolvedModule?.resolvedFileName;
  if (
    typescriptResolution &&
    isRepositorySourceFile(repositoryRoot, typescriptResolution)
  ) {
    return typescriptResolution;
  }

  return resolveWorkspaceModule(modulePath, repositoryRoot);
}

function buildImportReference(filePath, modulePath, repositoryRoot) {
  const resolvedPath = resolveRepositoryImport(filePath, modulePath, repositoryRoot);

  return {
    module: modulePath,
    resolved: resolvedPath ? toPosix(path.relative(repositoryRoot, resolvedPath)) : null,
    kind: resolvedPath || isLocalModule(modulePath) ? "local" : "external",
  };
}

function collectFunctionNames(node, functions) {
  if (ts.isFunctionDeclaration(node) && node.name) {
    functions.push(node.name.text);
  }

  if (ts.isMethodDeclaration(node) && node.name && ts.isIdentifier(node.name)) {
    functions.push(node.name.text);
  }
}

function isFunctionLike(node) {
  return (
    ts.isFunctionDeclaration(node) ||
    ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) ||
    ts.isMethodDeclaration(node) ||
    ts.isConstructorDeclaration(node) ||
    ts.isGetAccessorDeclaration(node) ||
    ts.isSetAccessorDeclaration(node)
  );
}

function isComplexityDecision(node) {
  if (
    ts.isIfStatement(node) ||
    ts.isForStatement(node) ||
    ts.isForInStatement(node) ||
    ts.isForOfStatement(node) ||
    ts.isWhileStatement(node) ||
    ts.isDoStatement(node) ||
    ts.isCatchClause(node) ||
    ts.isConditionalExpression(node) ||
    ts.isCaseClause(node)
  ) {
    return true;
  }

  return ts.isBinaryExpression(node) && [
    ts.SyntaxKind.AmpersandAmpersandToken,
    ts.SyntaxKind.BarBarToken,
    ts.SyntaxKind.QuestionQuestionToken,
  ].includes(node.operatorToken.kind);
}

function emptyMetadata(filePath, sourceText) {
  return {
    file: path.basename(filePath),
    source_code: sourceText,
    classes: [],
    functions: [],
    imports: [],
    complexity: 1,
  };
}

function extractMetadata(filePath, repositoryRoot = findRepositoryRoot(filePath)) {
  const sourceText = fs.readFileSync(filePath, "utf8");
  if (!TYPESCRIPT_EXTENSIONS.has(path.extname(filePath).toLowerCase())) {
    return emptyMetadata(filePath, sourceText);
  }
  const sourceFile = ts.createSourceFile(
    filePath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    getScriptKind(filePath)
  );

  const metadata = {
    file: path.basename(filePath),
    source_code: sourceText,
    classes: [],
    functions: [],
    imports: [],
    complexity: 1,
  };

  function visit(node) {
    if (ts.isImportDeclaration(node)) {
      const importPath = getImportPath(node);
      if (importPath) {
        metadata.imports.push(buildImportReference(filePath, importPath, repositoryRoot));
      }
    }

    if (ts.isExportDeclaration(node) && node.moduleSpecifier) {
      const importPath = getImportPath(node);
      if (importPath) {
        metadata.imports.push(buildImportReference(filePath, importPath, repositoryRoot));
      }
    }

    if (
      ts.isCallExpression(node) &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0]) &&
      (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(node.expression) && node.expression.text === "require"))
    ) {
      metadata.imports.push(
        buildImportReference(filePath, node.arguments[0].text, repositoryRoot)
      );
    }

    if (ts.isClassDeclaration(node) && node.name) {
      metadata.classes.push(node.name.text);
    }

    collectFunctionNames(node, metadata.functions);
    if (isFunctionLike(node) || isComplexityDecision(node)) {
      metadata.complexity += 1;
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return metadata;
}

function main() {
  if (process.argv[2] === "--batch") {
    const manifestPath = process.argv[3];
    if (!manifestPath) {
      throw new Error("Expected a manifest path for batch parsing.");
    }

    const entries = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    for (const entry of entries) {
      const metadata = extractMetadata(
        path.resolve(entry.file_path),
        path.resolve(entry.repository_root || findRepositoryRoot(entry.file_path))
      );
      metadata.relative_path = entry.relative_path;
      process.stdout.write(`${JSON.stringify(metadata)}\n`);
    }
    return;
  }

  const filePath = process.argv[2];

  if (!filePath) {
    throw new Error("Expected a file path argument.");
  }

  const absolutePath = path.resolve(filePath);
  const metadata = extractMetadata(absolutePath);
  process.stdout.write(JSON.stringify(metadata));
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
}
