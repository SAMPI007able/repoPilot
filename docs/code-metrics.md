# Code metrics

## Per-file cyclomatic complexity

The repository indexer calculates an aggregate McCabe cyclomatic complexity score for every parsed JavaScript, TypeScript, Python, or Java file. TypeScript and JavaScript scores come from the TypeScript compiler AST; Python scores come from the Python AST (with a syntax-tolerant fallback); Java scores come from a comment-aware source scan so indexing does not require a JDK.

Each file starts at **1** for its module-level execution path. The score then increases by one for:

- every function, method, constructor, getter, setter, function expression, or arrow function;
- every `if`, `for`, `for...in`, `for...of`, `while`, or `do...while` statement;
- every `catch` clause and non-default `case` clause;
- every ternary conditional expression; and
- every short-circuit `&&`, `||`, or `??` operator.

The workspace displays the five files with the highest aggregate score, ordered by score descending and then by path. This is a hotspot-ranking metric: a high value identifies files with more combined control-flow paths, but it does not by itself establish that the code is defective.
