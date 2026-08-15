import { defineConfig, globalIgnores } from "eslint/config";
import prettierConfig from "eslint-config-prettier";
import tseslint from "typescript-eslint";

const eslintConfig = defineConfig([
  ...tseslint.configs.recommended,
  // Must come last: disables ESLint stylistic rules that conflict with Prettier.
  prettierConfig,
  globalIgnores(["dist/**", "node_modules/**"]),
]);

export default eslintConfig;
