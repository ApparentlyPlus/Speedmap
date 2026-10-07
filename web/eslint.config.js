// The source has carried eslint-disable lines for no-console and the hooks rules since before
// there was a config to read them, so this is the smallest one that makes them mean something.
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/", "src/api/schema.ts"] },
  ...tseslint.configs.recommended,
  {
    plugins: { "react-hooks": reactHooks },
    rules: { ...reactHooks.configs.recommended.rules, "no-console": "error" },
  },
);
