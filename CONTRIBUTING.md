# Contributing

## Branch model

- `main` — production. Auto-deploys to `app.ftu.fyi`.
- `dev`  — staging. Auto-deploys to `dev.ftu.fyi`.
- `feat/<short-name>` — your work. Branch from `dev`.

## Workflow

1. `git checkout dev && git pull`
2. `git checkout -b feat/my-thing`
3. Write tests first. Implement. Run locally:
   ```bash
   cd backend && pytest && ruff check . && mypy app
   cd ../frontend && npm run build
   ```
4. Open PR → `dev`. CI must be green.
5. Request review from @minhtcai (or a peer).
6. After approval, squash-merge to `dev` (auto-deploys to staging).
7. Weekly: open `dev` → `main` PR, merge once staging has had time to bake.

## Commit style

```
<type>: <short summary>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`.

Examples:
- `feat: add item search endpoint`
- `fix: return 404 instead of 500 for missing item`
- `docs: clarify migration workflow`

## Pull request checklist

Before marking a PR ready:

- [ ] Tests pass locally (`pytest` green)
- [ ] Linter clean (`ruff check .`)
- [ ] Type checker clean (`mypy app`)
- [ ] Frontend builds (`npm run build`)
- [ ] Coverage on new code ≥ 80% (ideal; we'll enforce via CI soon)
- [ ] No secrets in the diff (grep for `ftu.fyi`, `password`, `API_KEY`)
- [ ] Docs updated if behavior or setup changed
- [ ] PR description explains the **why**, not just the what

## Code review

- At least one approval before merging.
- All CI checks must pass.
- Direct pushes to `main` or `dev` are disabled by branch protection.
- If your PR sits without review for 24h, ping in the class channel.

## Testing

Minimum 80% coverage on new code. Check locally:

```bash
pytest --cov=app --cov-report=term-missing
```

## Code style

- Python: ruff + mypy (both run in CI).
- TypeScript: tsc strict mode.
- Avoid drive-by refactors unrelated to your PR — keep diffs reviewable.

## Security

- Never commit `.env` files, credentials, or keys.
- Never log secrets (`print(token)` is a bug).
- User input is untrusted — always validate via Pydantic schemas.
- Database queries must use parameterized SQL (SQLAlchemy handles this for you).
