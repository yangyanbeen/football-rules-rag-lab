"""Validate all install destinations and clean editable upstream before any installation."""
import argparse,sys
from task13_audit import ROOT,upstream_clean


def validate_targets(environment,report):
    env=(ROOT/environment).resolve();out=(ROOT/report).resolve();base=ROOT/'.runtime/task13'
    if not env.is_relative_to(base) or env==base or env.exists():raise ValueError('Use a new task13 environment directory')
    if not out.is_relative_to(ROOT) or out.exists() or out.suffix!='.json' or out.is_relative_to(env):raise ValueError('Use a new JSON receipt inside the checkout and outside the new environment')
    if not any(out.is_relative_to(ROOT/n) for n in ('reports','.runtime','.tmp')):raise ValueError('Receipt must stay in a report or private evidence directory')
    upstream_clean();return True


if __name__=='__main__':
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--environment',default='.runtime/task13/venv-final');p.add_argument('--report');a,unknown=p.parse_known_args()
    if '--help' not in sys.argv and '-h' not in sys.argv:
        if not a.report:raise ValueError('--report required before installation')
        validate_targets(a.environment,a.report)
    from prepare_task13_environment import main
    main()
