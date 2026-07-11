import { nextJsConfig } from "@repo/eslint-config/next-js";

/** @type {import("eslint").Linter.Config[]} */
export default [
  // Local `vercel build` artifacts (untracked) — not part of the lintable source.
  { ignores: [".vercel/**"] },
  ...nextJsConfig,
];
