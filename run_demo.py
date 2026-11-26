"""Run the project's regression suite and its end-to-end demonstrations.

Used by the runtime manifest so a single entry covers both the original
regression and the trial-card walkthrough; any failing check exits non-zero.
"""
import importlib

import check_project


def _run(module_name):
    module = importlib.import_module(module_name)
    module.main()
    print(f'DEMO OK {module_name}')


def main():
    status = check_project.main()
    if status != 0:
        return status
    for name in ('tests.demo', 'tests.trial_demo', 'tests.trial_fixture'):
        _run(name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
