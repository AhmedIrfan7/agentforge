// Shared with organization/workspace create forms alike -- extracted
// once settings/page.tsx (234) and workspaces/page.tsx (235) both
// needed the identical logic, same "share once a real second consumer
// exists" bar this codebase applies everywhere else.
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
