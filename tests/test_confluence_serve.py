from types import SimpleNamespace

import serve_confluence


def test_scheduler_registers_a_single_interval_job():
    settings = SimpleNamespace(scan_interval_minutes=30)
    sched = serve_confluence.build_confluence_scheduler(settings, job=lambda: None)
    ids = [j.id for j in sched.get_jobs()]
    assert ids == ["confluence"]
