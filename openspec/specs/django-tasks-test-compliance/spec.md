# django-tasks-test-compliance

## Purpose

Prove this package's Django task backend against Django's own applicable
`django.tasks` tests for the installed Django version, by importing that
suite in the default pytest run.

## Requirements

### Requirement: Default suite includes Django task contract tests
The package's default test command SHALL collect Django's applicable
`django.tasks` tests for the **installed Django version** alongside this
package's existing tests. Those imported tests SHALL run against this package's
Redis task backend, not Django's Dummy or Immediate backends as the default.
This package SHALL NOT keep a copied snapshot of Django's test files in the
repository.

#### Scenario: Default pytest collects the imported tests
- **WHEN** a developer runs the package's standard pytest command
- **THEN** the installed Django version's applicable task contract tests are
  collected and executed as Django tests in that same run, without a separate
  job, marker, extra command, or a rewritten pytest copy of the methods

#### Scenario: Tests track the installed Django version
- **WHEN** the project's Django dependency is upgraded and the default pytest
  command is run
- **THEN** the imported tests are that new Django version's tests, without a
  manual recopy of Django source into this repository

#### Scenario: Same Django version reuses a local cache
- **WHEN** Django's tests tree for the installed version has already been
  cached locally and the default pytest command is run again
- **THEN** those tests are collected from that version-pinned cache without
  fetching Django source again

#### Scenario: Old cache is discardable after a Django upgrade
- **WHEN** the installed Django version changes
- **THEN** the previous version's cached tree is no longer used, and that
  version-named `.django-src-<version>_cache` directory can be deleted without
  affecting the new run

#### Scenario: Imported tests use the Redis task backend
- **WHEN** an imported contract test enqueues or looks up a task through Django's
  default task backend
- **THEN** that backend is this package's Redis task backend backed by the
  suite's Redis test instance

### Requirement: Import only tests that apply to a third-party backend
The imported suite SHALL include Django's task fixtures and backend-agnostic
task API cases (decorator, `using()`, validation, enqueue/`aenqueue`, result
lookup, pickle/reconstruct). It SHALL NOT include DummyBackend, ImmediateBackend,
or custom-backend test modules, and SHALL NOT require Dummy's in-memory result
list or Immediate's synchronous SUCCESSFUL-on-enqueue behaviour.

#### Scenario: Dummy and Immediate backend suites are absent
- **WHEN** the default pytest run collects tests
- **THEN** Django's DummyBackend, ImmediateBackend, and custom-backend test
  modules are not part of the collected suite

#### Scenario: Dummy in-memory results are not asserted
- **WHEN** an imported enqueue test completes
- **THEN** it does not require a DummyBackend `.results` list to pass

#### Scenario: Immediate sync-run-on-enqueue is not required
- **WHEN** an imported enqueue test completes without a worker having finished
  the task
- **THEN** the expected status is READY, not SUCCESSFUL

### Requirement: Failures are first-class regressions
A failing imported Django contract test SHALL fail the default test run the
same way as any other package test. Skips SHALL be limited to cases that
assert Dummy- or Immediate-specific behaviour excluded by the slim import.

#### Scenario: A contract mismatch fails the suite
- **WHEN** this backend violates an imported Django contract assertion
- **THEN** the default pytest run fails against that installed Django version's
  contract

#### Scenario: Excluded Dummy or Immediate behaviour is skipped, not failed
- **WHEN** a Django test method exists only to assert Dummy `.results` or
  Immediate SUCCESSFUL-on-enqueue behaviour
- **THEN** that method is omitted or skipped rather than adapted into a false
  pass
