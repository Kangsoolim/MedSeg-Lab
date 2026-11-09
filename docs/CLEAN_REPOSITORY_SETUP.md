# Clean repository setup — v0.6.0-rc.1

The independent staging directory was absent before extraction. Only the verified r2 archive was extracted, then explicit audited corrections/additions were made. No original `.git` directory, old author metadata, branch, tag, remote or history was copied. The development and course repositories were not rewritten.

The root `.gitattributes` uses `* -text` so clones retain the byte-exact manifest and executing-code fingerprints, including when a user has global CRLF conversion enabled. Existing vendored and license bytes are preserved. Legacy whitespace remains unchanged; the new reports/verifier pass their focused whitespace check.

The new local branch is `codex/release-candidate`. Repository-local configuration sets `user.useConfigOnly=true`, `core.autocrlf=false`, `user.name=Kangsoolim` and `user.email=266002731+Kangsoolim@users.noreply.github.com`. The user requested GitHub noreply. The authenticated GitHub connector confirmed this login and numeric account ID; the address follows GitHub's [documented ID-based format](https://docs.github.com/en/account-and-profile/reference/email-addresses-reference#your-noreply-email-address). No private mailbox, invented author, global Git configuration change or original-repository identity change is used.

After local gates pass, the sole root commit is `Prepare audited MedSeg-Lab v0.6.0-rc.1 source candidate`, with local annotated tag `v0.6.0-rc.1`. Resolve exact identifiers locally with:

```powershell
git log --format=fuller --max-count=1
git rev-parse HEAD
git cat-file -p refs/tags/v0.6.0-rc.1
git rev-list --count HEAD
git remote -v
git fsck --full
.\backend\.venv\Scripts\python.exe -B scripts/Verify-PublicSource.py
```

Expected: one root commit, one RC annotated tag, no parent/old tags/remotes/alternates, and none of the four old private blobs in any stored object. Local ignored installation/runtime directories are not the public payload; only the exact manifest files plus the manifest belong to the source distribution. Generated QA runs were preserved privately outside the final staging directory. No user run was removed to satisfy this gate.

The original r2 manifest is immutable inside its retained archive. The final manifest deliberately supersedes it and records origin/delta provenance. Never copy the entire installed directory to publish; use the verified source archive. No GitHub repository, GitHub Release, remote configuration or push was performed.
