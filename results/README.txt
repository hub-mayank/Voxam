Raw results (no secrets). Commit them: they are test-report evidence.

Every file here needs a sidecar <file>.meta.json with provider (mock|stub|live), model,
date, git_sha (+dirty if the tree had uncommitted changes), n (sample size; say what it counts
in n_unit). Scripts write it with app.results_meta.write_meta(). A test fails if one is missing.
Mock and stub results prove plumbing, never model quality.
