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
  return node.moduleSpecifier.text;
}

function isLocalModule(modulePath) {
  return modulePath.startsWith(".");
}

function toPosix(filePath) {
  return filePath.split(path.sep).join("/");
}

function findRepositoryRoot(startPath) {
  let currentPath = path.dirname(startPath);

  while (true) {
    const markers = [
      path.join(currentPath, ".git"),
      path.join(currentPath, "package.json"),
      path.join(currentPath, "tsconfig.json"),
    ];

    if (markers.some((marker) => fs.existsSync(marker))) {
      return currentPath;
    }

    const parentPath = path.dirname(currentPath);
    if (parentPath === currentPath) {
      return path.dirname(startPath);
    }

    currentPath = parentPath;
  }
}

function resolveLocalImport(filePath, modulePath) {
  const basePath = path.resolve(path.dirname(filePath), modulePath);
  const repositoryRoot = findRepositoryRoot(filePath);
  const candidates = [
    basePath,
    `${basePath}.ts`,
    `${basePath}.tsx`,
    `${basePath}.js`,
    `${basePath}.jsx`,
    path.join(basePath, "index.ts"),
    path.join(basePath, "index.tsx"),
    path.join(basePath, "index.js"),
    path.join(basePath, "index.jsx"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return toPosix(path.relative(repositoryRoot, candidate));
    }
  }

  return null;
}

function buildImportReference(filePath, node) {
  const modulePath = getImportPath(node);
  const kind = isLocalModule(modulePath) ? "local" : "external";

  return {
    module: modulePath,
    resolved: kind === "local" ? resolveLocalImport(filePath, modulePath) : null,
    kind,
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

function extractMetadata(filePath) {
  const sourceText = fs.readFileSync(filePath, "utf8");
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
  };

  function visit(node) {
    if (ts.isImportDeclaration(node)) {
      metadata.imports.push(buildImportReference(filePath, node));
    }

    if (ts.isClassDeclaration(node) && node.name) {
      metadata.classes.push(node.name.text);
    }

    collectFunctionNames(node, metadata.functions);
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return metadata;
}

function main() {
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
